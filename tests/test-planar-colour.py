#!/usr/bin/env python3
"""The planar Metal renderer draws channel factors and enlarged colour images (#660).

The planar snapshot refused channel factors other than 1 and a colour image
the host enlarges in software. The host draws them so:

* a scalar image with channel factors goes through its scalar CLUT program,
  with the table `fminf(255, fmaxf(0, t[i] * factor))`: the snapshot now builds
  the same table for the view's own image, as it does for a fused series (#658);
* a colour image is windowed into ARGB bytes by `compute8bitRepresentation`
  (opacity table and filter included), and `loadTextureIn:` lays a table over
  those bytes before they are interpolated when a CLUT or a factor asks for one
  (`vImageTableLookUp_ARGB8888`, the opaque alpha table, the CLUT or the CLUT
  times the factors converted to bytes as C converts them), then enlarges them
  with `vImageScale_ARGB8888` in software interpolation. The snapshot now hands
  every colour image over as those bytes, with the table the host lays, and
  Metal draws the interpolated bytes themselves, as the fixed-function texture
  does.

Checked here:

* the sources: the refusals are gone (a fused colour series stays refused);
  the view's own CLUT carries the factors with the host's formula; colour
  images take the host's bytes; the colour table is the host's, in the host's
  branch structure;
* the frame, on both backends: the upload is the host's table over the bytes
  (independently looked up here), before the enlargement, which is
  `vImageScale_ARGB8888` of the tabled bytes and differs from tabling the
  enlarged ones; every texel centre of the render is the tabled bytes; the
  Metal 4 pilot draws the same bytes; a colour table without colour bytes, and
  an enlargement with nearest sampling, are refused.

`<git revision>` as an optional argument reads the sources from that revision,
the negative control.
"""
from pathlib import Path
import re
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
revision = sys.argv[1] if len(sys.argv) > 1 else None


def read(path):
    if revision:
        return subprocess.check_output(['git', '-C', str(root), 'show', revision + ':' + path]).decode('latin1')
    return (root / path).read_bytes().decode('latin1')


failures = []
bridge = read('Horos/Sources/PlanarHostBridge.m')
view = read('Horos/Sources/DCMView.m')
snapshot = bridge[bridge.index('- (NSDictionary *)horosPlanarSnapshot'):]
refusal = snapshot[:snapshot.index('return @{@"error": unsupported};')]
for refused, why in [('redFactor != 1', 'channel factors'), ('[view softwareInterpolation] && pix.isRGB', 'an enlarged colour image')]:
    if refused in refusal:
        failures.append('the planar snapshot still refuses %s' % why)
if '(fused && pix.isRGB)' not in refusal:
    failures.append('a fused colour series is no longer refused')
if not re.search(r'\} else \{\s*\[view getCLUT:&r :&g :&b\];\s*\}.*?for \(NSUInteger i = 0; i < 256; \+\+i\) \{\s*'
                 r'rgba\[4\*i\] = fminf\(255, fmaxf\(0, r\[i\] \* redFactor\)\);', snapshot, re.S):
    failures.append('the view\'s own CLUT does not carry the channel factors')
if not re.search(r'rgba\[4\*i\] = fminf\(255, fmaxf\(0, rT\[i\] \* redFactor\)\);', view):
    failures.append('the host\'s scalar table is no longer the formula the snapshot copies')
if 'if (pix.isRGB || pix.subtractedfImage || pix.shutterEnabled) {' not in snapshot:
    failures.append('a colour image is not handed over as the host\'s bytes')
table = re.search(r'if \(pix\.isRGB && \(colorTransfer \|\| redFactor != 1\.0 \|\| greenFactor != 1\.0 \|\| blueFactor != 1\.0\)\) \{'
                  r'.*?table\[i\] = opaqueTable\[i\];\s*'
                  r'if \(redFactor != 1\.0 \|\| greenFactor != 1\.0 \|\| blueFactor != 1\.0\) \{\s*'
                  r'table\[256 \+ i\] = r\[i\] \* redFactor;\s*table\[512 \+ i\] = g\[i\] \* greenFactor;\s*table\[768 \+ i\] = b\[i\] \* blueFactor;\s*'
                  r'\} else \{\s*table\[256 \+ i\] = r\[i\]; table\[512 \+ i\] = g\[i\]; table\[768 \+ i\] = b\[i\];', snapshot, re.S)
host = view[view.index('if( isRGB == YES)\n    {\n        if( self.curDCM.isLUT12Bit)'):]
host = host[:host.index('else if( redFactor != 1.0 || greenFactor != 1.0 || blueFactor != 1.0)')]
host_table = re.search(r'else if\(\(localColorTransfer == YES\) \|\| \(blending == YES\)\).*?'
                       r'if\( redFactor != 1\.0 \|\| greenFactor != 1\.0 \|\| blueFactor != 1\.0\).*?'
                       r'credTable\[ i\] = rT\[ i\] \* redFactor;\s*cgreenTable\[ i\] = gT\[ i\] \* greenFactor;\s*cblueTable\[ i\] = bT\[ i\] \* blueFactor;.*?'
                       r'vImageTableLookUp_ARGB8888\( &dest, &dest, \(Pixel_8\*\) currentAlphaTable, \(Pixel_8\*\) &credTable.*?'
                       r'vImageTableLookUp_ARGB8888\( &dest, &dest, \(Pixel_8\*\) currentAlphaTable, \(Pixel_8\*\) rT', host, re.S)
if not table or not host_table:
    failures.append('the colour table is not the one loadTextureIn: lays, in its branches')
if 'if( blending == NO) currentAlphaTable = opaqueTable;' not in view:
    failures.append('the host\'s alpha table for the view\'s own image is no longer the opaque one')
if not re.search(r'vImageScale_ARGB8888\( &src, &dst, nil, QUALITY\);', view) or '#define QUALITY kvImageNoFlags' not in view:
    failures.append('the host no longer enlarges colour bytes with vImageScale_ARGB8888 and no flags')
if failures:
    for failure in failures:
        print('FAIL:', failure)
    raise SystemExit(1)

DRIVER = r'''
import Foundation
import Metal
import Accelerate

func expect(_ ok: Bool, _ reason: @autoclosure () -> String) { if !ok { print("FAIL: " + reason()); exit(1) } }

func texture(_ image: MTLTexture) -> [UInt8] {
    var values = [UInt8](repeating: 0, count: image.width * image.height * 4)
    image.getBytes(&values, bytesPerRow: image.width * 4, from: MTLRegionMake2D(0, 0, image.width, image.height), mipmapLevel: 0)
    return values
}

@main struct Check {
    static func main() throws {
        guard let device = MTLCreateSystemDefaultDevice() else { print("skipped: no Metal device"); exit(2) }
        let metal = try PlanarMetalRenderer(device: device)
        let pilot = PlanarMetal4Renderer.isSupported(device) ? try PlanarMetal4Renderer(device: device) : nil
        let w = 37, h = 29
        // Windowed ARGB bytes, every value of every channel reached.
        var bytes = [UInt8](repeating: 0, count: w * h * 4)
        for i in 0..<(w * h) {
            bytes[4 * i] = UInt8((i * 13) % 256)
            bytes[4 * i + 1] = UInt8((i * 7 + 3) % 256); bytes[4 * i + 2] = UInt8((i * 11 + 5) % 256); bytes[4 * i + 3] = UInt8((i * 17 + 1) % 256)
        }
        // A non-linear table per channel, alpha opaque, as the host lays it.
        var tables = [UInt8](repeating: 255, count: 1024)
        for i in 0..<256 {
            tables[256 + i] = UInt8((i * i / 255 + 40) % 256)
            tables[512 + i] = UInt8(255 - i)
            tables[768 + i] = UInt8(Float(i) * 0.63)
        }
        var identity = [UInt8](); for i in 0..<256 { identity += [UInt8(i), UInt8(i), UInt8(i), 255] }
        func frame(table: [UInt8]?, scale: Int = 1, nearest: Bool = false, colour: Bool = true, hostBytes: Bool = true) throws -> PlanarFrame {
            let value: NSMutableDictionary = ["width": w, "height": h, "pixels": Data(count: w * h * 4), "clut": Data(identity),
                "frameIdentity": "colour", "level": 127.5, "widthWindow": 255.0, "isColor": colour,
                "screenToPixel": [0.0, 0.0, Double(w), 0.0, 0.0, Double(h)], "viewSize": [w * scale, h * scale],
                "softwareScale": scale, "nearest": nearest]
            if hostBytes { value["hostBytes"] = Data(bytes) }
            if let table { value["colourTable"] = Data(table) }
            return try PlanarFrame(value)
        }
        // The table, looked up here by hand: alpha, red, green and blue in ARGB order.
        var tabled = bytes
        for i in 0..<(w * h) { for c in 0..<4 { tabled[4 * i + c] = tables[256 * c + Int(bytes[4 * i + c])] } }
        let plain = try frame(table: tables)
        let (upload, format, size) = try plain.uploadPixels(device: device)
        expect([UInt8](upload) == tabled && format == .rgba8Unorm && size == 4, "the upload is not the host's table over the bytes")
        try metal.update(plain)
        expect(texture(metal.image!) == tabled, "the Metal 3 texture is not the tabled bytes")
        if let pilot { try pilot.update(plain); expect(texture(pilot.image!) == tabled, "the Metal 4 pilot's texture is not the tabled bytes") }
        // Every texel centre draws the tabled bytes themselves (BGRA out).
        let picture = [UInt8](try metal.renderBGRA(width: w, height: h))
        for i in 0..<(w * h) {
            let got = (picture[4 * i + 2], picture[4 * i + 1], picture[4 * i])
            let wanted = (tabled[4 * i + 1], tabled[4 * i + 2], tabled[4 * i + 3])
            expect(got == wanted, "pixel \(i) draws \(got), the tabled bytes are \(wanted)")
        }
        if let pilot { expect([UInt8](try pilot.renderBGRA(width: w, height: h)) == picture, "the Metal 4 pilot draws differently") }
        // Without a table the bytes are drawn as they are.
        let bare = [UInt8](try frame(table: nil).uploadPixels(device: device).pixels)
        expect(bare == bytes, "a colour image without a table is not uploaded as the host's bytes")
        // Enlarged: the host tables, then enlarges; the other order differs.
        for scale in [2, 3] {
            let big = [UInt8](try frame(table: tables, scale: scale).uploadPixels(device: device).pixels)
            func enlarge(_ source: [UInt8]) -> [UInt8] {
                var input = source, result = [UInt8](repeating: 0, count: source.count * scale * scale)
                let status = result.withUnsafeMutableBytes { destination in
                    input.withUnsafeMutableBytes { from in
                        var a = vImage_Buffer(data: from.baseAddress!, height: vImagePixelCount(h), width: vImagePixelCount(w), rowBytes: w * 4)
                        var b = vImage_Buffer(data: destination.baseAddress!, height: vImagePixelCount(h * scale), width: vImagePixelCount(w * scale), rowBytes: w * scale * 4)
                        return vImageScale_ARGB8888(&a, &b, nil, vImage_Flags(kvImageNoFlags))
                    }
                }
                expect(status == kvImageNoError, "vImageScale_ARGB8888 failed")
                return result
            }
            expect(big == enlarge(tabled), "the \(scale)x colour image is not vImageScale_ARGB8888 of the tabled bytes")
            var late = enlarge(bytes)
            for i in 0..<(late.count / 4) { for c in 0..<4 { late[4 * i + c] = tables[256 * c + Int(late[4 * i + c])] } }
            expect(big != late, "tabling after enlarging gives the same bytes: the order is not being checked")
            try metal.update(try frame(table: tables, scale: scale))
            expect(texture(metal.image!) == big, "the \(scale)x Metal 3 texture is not the enlarged tabled bytes")
        }
        // Refused: a colour table without colour bytes, colour bytes enlarged with nearest sampling.
        expect((try? frame(table: tables, hostBytes: false)) == nil, "a colour table without the host's bytes was accepted")
        expect((try? frame(table: tables, colour: false, hostBytes: false)) == nil, "a colour table on a scalar image was accepted")
        expect((try? frame(table: nil, scale: 2, nearest: true)) == nil, "an enlargement with nearest sampling was accepted")
        print("PASS: colour bytes through the host's table (\(w * h) pixels), before the 2x and 3x enlargements, on both backends; every texel centre draws the tabled bytes")
    }
}
'''

with tempfile.TemporaryDirectory(prefix='horos-planar-colour-') as name:
    directory = Path(name)
    sources = ['VolumeAllocation.swift', 'VolumeSession.swift', 'MPRMetalReslicer.swift', 'MetalPerformanceTrace.swift',
               'MetalComputePipelineCache.swift', 'Metal4ComputeSubmitter.swift', 'PlanarMetalRenderer.swift',
               'PlanarMetal4Renderer.swift']
    for source in sources:
        (directory / source).write_text(read('Horos/Sources/' + source))
    (directory / 'Check.swift').write_text(DRIVER)
    build = subprocess.run(['xcrun', 'swiftc', '-O', '-parse-as-library', '-suppress-warnings',
                            *[str(directory / source) for source in sources], str(directory / 'Check.swift'),
                            '-o', str(directory / 'check')])
    if build.returncode:
        print('FAIL: the planar renderer does not build with the colour driver')
        raise SystemExit(1)
    result = subprocess.run([str(directory / 'check')], timeout=300)
    raise SystemExit(result.returncode)
