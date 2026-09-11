#!/usr/bin/env python3
"""Compare the actual planar Metal shader with an independent scalar oracle.

No app or window is launched. Fixtures and GPU readback remain in memory.
Tolerance fixed before comparison: one 8-bit level per channel; nearest and
constant/discrete-CLUT cases are exact where no rounding boundary is involved.
"""
from pathlib import Path
import argparse
import re
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--renderer-source', type=Path, default=root/'Horos/Sources/PlanarMetalRenderer.swift')
args = parser.parse_args()
# Compile the real host RGB windowing rule as the control. Copying its formula
# into the Swift oracle would let the same quantization mistake pass both sides.
pix = (root/'Horos/Sources/DCMPix.m').read_bytes().decode('latin1')
rgb = pix[pix.index('// ***** SOURCE IMAGE IS RGBA'):]
span = re.search(r'long\s+diff = max - min, val;', rgb).group()
loop = re.search(r'for\( long i = 0; i < 256; i\+\+\)\s*\{[^{}]*convTable\[i\] = val;\s*\}', rgb).group()
bounds = re.search(r'min = iwl - iww / 2;\s*max = iwl \+ iww / 2;', pix).group()
host_rule = 'void hostRGBTable(float iwl, float iww, unsigned char *convTable) { float min, max;\n' + bounds + '\n' + span + '\n' + loop + '\n}\n'
driver = r'''
import Foundation
import Metal

@main struct Check {
    static func main() throws {
        guard let device = MTLCreateSystemDefaultDevice() else { print("skipped: Metal device unavailable"); exit(2) }
        let renderer = try PlanarMetalRenderer(device: device)
        let w=8, h=5
        let values = (0..<w*h).map { Float(($0*31)%256) }
        let floats = values.withUnsafeBytes { Data($0) }
        var argb=[UInt8](), clut=[UInt8]()
        for i in 0..<w*h { argb += [255,UInt8((i*31)%256),UInt8(255-(i*31)%256),UInt8((i*11)%256)] }
        // Deliberately discrete: interpolating colours would create forbidden green.
        for i in 0..<256 { clut += i < 128 ? [0,0,255,255] : [255,255,0,255] }
        func payload(color:Bool, nearest:Bool) -> NSMutableDictionary {
            ["width":w,"height":h,"pixels":color ? Data(argb) : floats,"clut":Data(clut),
             "frameIdentity":"synthetic/1","level":128.0,"widthWindow":256.0,
             "screenToPixel":[0.0,0.0,8.0,0.0,0.0,5.0],"viewSize":[8.0,5.0],
             "isColor":color,"nearest":nearest]
        }
        func byte(_ value:Double) -> Int { Int((min(1,max(0,value))*255+0.5).rounded(.down)) }
        func expected(_ frame:PlanarFrame, _ outW:Int, _ outH:Int, _ color:Bool, _ nearest:Bool) -> [UInt8] {
            var result=[UInt8]()
            let scale=min(Double(outW)/8,Double(outH)/5), sx=8*scale, sy=5*scale
            func scalar(_ x:Int,_ y:Int,_ c:Int)->Double {
                let index=min(h-1,max(0,y))*w+min(w-1,max(0,x))
                return color ? Double(argb[index*4+c+1]) : Double(values[index])
            }
            for row in 0..<outH { for column in 0..<outW {
                let u=(Double(column)+0.5-(Double(outW)-sx)/2)/sx
                let v=(Double(row)+0.5-(Double(outH)-sy)/2)/sy
                let x=Double(frame.mapping.x)+u*Double(frame.mapping.z)+v*Double(frame.geometry.x)
                let y=Double(frame.mapping.y)+u*Double(frame.mapping.w)+v*Double(frame.geometry.y)
                if u<0 || u>=1 || v<0 || v>=1 || x<0 || x>=Double(w) || y<0 || y>=Double(h) {
                    result += [0,0,0,255]; continue
                }
                var rgb=[UInt8]()
                for channel in 0..<3 {
                    let intensity:Double
                    if nearest { intensity=scalar(Int(floor(x)),Int(floor(y)),channel) }
                    else {
                        let xx=x-0.5, yy=y-0.5, x0=Int(floor(xx)), y0=Int(floor(yy))
                        let dx=xx-Double(x0),dy=yy-Double(y0)
                        intensity=scalar(x0,y0,channel)*(1-dx)*(1-dy)
                            + scalar(x0+1,y0,channel)*dx*(1-dy)
                            + scalar(x0,y0+1,channel)*(1-dx)*dy
                            + scalar(x0+1,y0+1,channel)*dx*dy
                    }
                    let minimum=Double(frame.window.x)-Double(frame.window.y)/2
                    let index = color
                        ? Int(min(255,max(0,(intensity-minimum)*255/Double(Int(frame.window.y)))))
                        : byte((intensity-minimum)/Double(frame.window.y))
                    rgb.append(clut[4*index+channel])
                }
                result += [rgb[2],rgb[1],rgb[0],255]
            }}
            return result
        }
        var checked=0
        // Exact host conversion-table comparison, including a CLUT transition
        // between entries 0 and 1: fixed8 RGB black must stay entry 0, not red.
        let bytePixels=Data((0..<256).flatMap { [UInt8(255),UInt8($0),UInt8($0),UInt8($0)] })
        for (level,widthWindow) in [(127.0,256.0),(128.0,256.0),(127.0,251.75)] {
            var host=[UInt8](repeating:0,count:256)
            host.withUnsafeMutableBufferPointer { hostRGBTable(Float(level),Float(widthWindow),$0.baseAddress!) }
            if level==127 && widthWindow==256 { assert(host[0]==0 && host[1]==1) }
            for boundaryOnly in [true,false] {
                let table=(0..<256).flatMap { i -> [UInt8] in
                    if boundaryOnly { return i==0 ? [0,0,0,255] : [255,0,0,255] }
                    return [UInt8(i),UInt8(255-i),UInt8((i*73)%256),255]
                }
                let frame=try PlanarFrame([
                    "width":256,"height":1,"pixels":bytePixels,"clut":Data(table),
                    "frameIdentity":"synthetic/host-rgb","level":level,"widthWindow":widthWindow,
                    "screenToPixel":[0.0,0.0,256.0,0.0,0.0,1.0],"viewSize":[256.0,1.0],
                    "isColor":true,"nearest":true])
                try renderer.update(frame)
                let actual=[UInt8](try renderer.renderBGRA(width:256,height:1))
                for i in 0..<256 {
                    let offset=Int(host[i])*4
                    let expected=[table[offset+2],table[offset+1],table[offset],255]
                    assert(Array(actual[i*4..<i*4+4])==expected,
                        "DCMPix RGB mismatch pixel=\(i) level=\(level) width=\(widthWindow) boundary=\(boundaryOnly)")
                }
                checked += 256
            }
        }
        for color in [false,true] { for inverted in (color ? [false] : [false,true]) { for nearest in [false,true] { for transform in 0..<3 {
            var frame=try PlanarFrame(payload(color:color,nearest:nearest))
            if inverted { frame.window.y = -frame.window.y }
            if transform==1 { frame.mapping=SIMD4(8,0,-8,0) }
            if transform==2 { frame.mapping=SIMD4(1,0.3,4,1);frame.geometry.x = -1;frame.geometry.y=3 }
            try renderer.update(frame)
            for size in [(8,5),(17,11),(6,16)] {
                let actual=[UInt8](try renderer.renderBGRA(width:size.0,height:size.1))
                let reference=expected(frame,size.0,size.1,color,nearest)
                let errors=zip(actual,reference).map { abs(Int($0)-Int($1)) }
                guard errors.max()! <= 1 else {
                    fatalError("pixel mismatch color=\(color) nearest=\(nearest) transform=\(transform) size=\(size) max=\(errors.max()!) index=\(errors.firstIndex(where:{$0>1})!)")
                }
                checked += size.0*size.1
            }
        }}}}
        // Original float values survive every display operation unchanged.
        assert(floats == values.withUnsafeBytes { Data($0) })
        for key in ["pixels","clut","widthWindow","screenToPixel"] {
            let bad=payload(color:false,nearest:false)
            if key=="pixels" || key=="clut" { bad[key]=Data() }
            if key=="widthWindow" { bad[key]=0 }
            if key=="screenToPixel" { bad[key]=[Double.nan,0,8,0,0,5] }
            do { _=try PlanarFrame(bad);fatalError("accepted invalid \(key)") } catch {}
        }
        let emptyRGBSpan=payload(color:true,nearest:true)
        emptyRGBSpan["widthWindow"]=0.5
        do { _=try PlanarFrame(emptyRGBSpan);fatalError("accepted zero integer RGB span") } catch {}
        let registry=VolumeSessionRegistry()
        let identity=VolumeIdentity(studyInstanceUID:"1",seriesInstanceUID:"2")!
        let session=registry.open(identity:identity,owner:"host")!
        weak var retired: VolumeLoadToken?
        do { let completed=registry.makeLoadToken(for:session)!; retired=completed; assert(completed.deliver()) }
        let cancelled=registry.makeLoadToken(for:session)!
        assert(retired == nil, "completed frame tokens accumulate in the session")
        let worker=PlanarRenderWorker(device:device)
        let frame=try PlanarFrame(payload(color:false,nearest:false))
        cancelled.cancel()
        var unexpected=0
        worker.submit(frame:frame,width:64,height:64,token:cancelled) { _ in unexpected += 1 }
        let token=registry.makeLoadToken(for:session)!
        var delivered=false
        worker.submit(frame:frame,width:64,height:64,token:token) { result in
            if case .success = result { delivered=token.deliver() }
        }
        let until=Date(timeIntervalSinceNow:10)
        while !delivered && Date()<until { RunLoop.current.run(until:Date(timeIntervalSinceNow:0.01)) }
        assert(delivered && unexpected==0)
        let closing=registry.makeLoadToken(for:session)!
        worker.submit(frame:frame,width:256,height:256,token:closing) { _ in unexpected += 1 }
        registry.close(session); worker.cancel()
        RunLoop.current.run(until:Date(timeIntervalSinceNow:0.3))
        assert(closing.isCancelled && unexpected==0 && registry.openSessionCount==0)
        renderer.clear();assert(renderer.image == nil)
        print("PASS: \(checked) GPU pixels, scalar/ARGB, discrete CLUT, interpolation, transforms, letterbox; cancellation/teardown")
    }
}
'''
with tempfile.TemporaryDirectory(prefix='horos-planar-metal-') as temporary:
    work = Path(temporary)
    (work/'Check.swift').write_text(driver)
    (work/'HostRGB.c').write_text(host_rule)
    (work/'HostRGB.h').write_text('void hostRGBTable(float level, float width, unsigned char *table);\n')
    subprocess.run(['xcrun','clang','-O0','-c',str(work/'HostRGB.c'),'-o',str(work/'HostRGB.o')],check=True)
    sources = ['VolumeAllocation.swift', 'VolumeSession.swift', 'PlanarComparison.swift']
    subprocess.run(['xcrun','swiftc','-parse-as-library',*[str(root/'Horos/Sources'/name) for name in sources],
                    str(args.renderer_source),str(work/'HostRGB.o'),'-import-objc-header',str(work/'HostRGB.h'),
                    str(work/'Check.swift'),'-o',str(work/'check')],check=True)
    result = subprocess.run([str(work/'check')],timeout=30)
    if result.returncode == 2:
        raise SystemExit(2)
    result.check_returncode()
