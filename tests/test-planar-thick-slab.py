#!/usr/bin/env python3
"""The planar Metal renderer reduces a 2D thick slab as the host does (#659).

A 2D viewer in thick-slab mean, MIP or MinIP used to be refused by the planar
snapshot (`pix.stackMode`), so it drew with «Original renderer (Metal paused)».
The reduction now runs on the MPR's reslice kernel, over the slices
`-[DCMPix computeThickSlab]` reduces, in its order, compiled with safe math.

The reference is the application's own `computeThickSlab`, linked from the
built `DCMPix.o` as `tests/test-thick-slab-cpu-reference.py` does: a 17 x 13
series of nine slices whose values are not integers, so the mean's rounding
depends on the order of the sum and on how the count divides it. For mean,
maximum and minimum, thickness 1 to 6, both directions and every position
(slabs that run off either end included), the Metal path must give the host's
floats bit for bit, through `PlanarThickSlab.sliceIndices` (the rule the bridge
asks), `PlanarFrame.uploadPixels`, the Metal 3 texture and the Metal 4 pilot's.
The 2x and 3x software enlargement must equal `vImageScale_PlanarF` of the
host's slab, and an opacity table must be applied to the slab, not to the
current slice.

Also checked in the sources: the bridge refuses only the volume-rendering slab
(modes 4 and 5) and colour slabs, asks the Swift rule, skips a slice without
pixels as the host does, and keys its copy of the other slices by the volume's
generation; the MPR kernel's mean multiplies by the reciprocal, and the planar
engine asks for safe math.

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
renderer = read('Horos/Sources/PlanarMetalRenderer.swift')
reslicer = read('Horos/Sources/MPRMetalReslicer.swift')
cache = read('Horos/Sources/MetalComputePipelineCache.swift')

snapshot = bridge[bridge.index('- (NSDictionary *)horosPlanarSnapshot'):]
refusal = snapshot[:snapshot.index('return @{@"error": unsupported};')]
if re.search(r'pix\.stackMode\s*\|\|', refusal):
    failures.append('the planar snapshot still refuses every thick slab')
else:
    for kept, why in [('pix.thickSlabVRActivated', 'the volume-rendering slab'), ('pix.stackMode > 3', 'modes 4 and 5'),
                      ('pix.stackMode && pix.isRGB', 'a colour slab')]:
        if kept not in refusal:
            failures.append('the snapshot no longer refuses %s (%s)' % (kept, why))
if 'HorosPlanarThickSlab sliceIndicesWithPosition:' not in snapshot:
    failures.append('the bridge does not ask the Swift rule for the slab slices')
if 'if (!samples) continue;' not in snapshot:
    failures.append('the bridge does not skip a slice without pixels, as computeMax does')
if 'identity.generation' not in snapshot or 'slabKeyKey' not in snapshot:
    failures.append('the copy of the other slices is not keyed by the volume generation')
if 'accumulated * (1.0f / float(counted))' not in reslicer:
    failures.append('the MPR kernel does not multiply the mean by the reciprocal, as the host does')
if 'safeMath' not in cache or 'mathMode = .safe' not in cache:
    failures.append('the compute pipeline cache cannot compile with safe math')
if 'MPRMetalReslicer(device: device, safeMath: true)' not in renderer:
    failures.append('the planar slab does not run the reslice kernel with safe math')
if 'struct PlanarSlab' not in renderer or 'PlanarSlabProjection' not in renderer:
    failures.append('the planar renderer has no thick-slab stage')
if failures:
    for failure in failures:
        print('FAIL:', failure)
    raise SystemExit(1)

objects = [root / 'build/Build/Intermediates.noindex/Horos.build' / configuration /
           'Horos.build/Objects-normal/arm64/DCMPix.o' for configuration in ('Debug', 'Release')]
obj = next((o for o in objects if o.is_file()), None)
if obj is None:
    print('needs a built DCMPix.o in %s' % ' or '.join(str(o) for o in objects), file=sys.stderr)
    raise SystemExit(2)

PROBE = r'''
#import <Foundation/Foundation.h>
#import "DCMPix.h"
#include <cstdio>
#include <cstdlib>
#include <cmath>

static const int kWidth = 17, kHeight = 13, kSlices = 9;

@interface DCMPix (HorosThickSlabProbe)
- (float*) computeThickSlab;
@end

@interface ProbePix : DCMPix
- (void) prepareSlice:(int) index;
- (void) setSlab:(int) thickness direction:(int) direction mode:(int) mode position:(int) position array:(NSArray*) array;
@end
@implementation ProbePix
- (void) CheckLoad {}
- (void) prepareSlice:(int) index
{
    width = kWidth; height = kHeight; isRGB = NO; thickSlabVRActivated = NO;
    fImage = (float*) calloc( kWidth * kHeight, sizeof( float));
    // Not integers and not monotonic in the slice index: the mean's last bit
    // depends on the order of the sum and on how the count divides it.
    for( int y = 0; y < kHeight; y++)
        for( int x = 0; x < kWidth; x++)
            fImage[ y * kWidth + x] = sinf( x * 0.7f + y * 1.3f + index * 2.1f) * 1000.f + index * 0.1f
                + (float)(( x * y + index) % 7) * 0.013f;
}
- (void) setSlab:(int) thickness direction:(int) direction mode:(int) mode position:(int) position array:(NSArray*) array
{
    stack = thickness; stackDirection = direction; stackMode = mode; pixPos = position;
    [pixArray release];
    pixArray = [array retain];
    ww = 256; wl = 127;
}
@end

int main( int argc, char **argv) { @autoreleasepool {
    FILE *out = fopen( argv[ 1], "wb");
    if( !out) return 3;
    NSMutableArray *slices = [NSMutableArray array];
    for( int i = 0; i < kSlices; i++)
    {
        ProbePix *pix = [[ProbePix alloc] init];
        [pix prepareSlice: i];
        [slices addObject: pix];
    }
    int header[ 3] = { kWidth, kHeight, kSlices };
    fwrite( header, sizeof header, 1, out);
    for( ProbePix *pix in slices) fwrite( [pix fImage], sizeof( float), kWidth * kHeight, out);
    for( int mode = 1; mode <= 3; mode++)
        for( int thickness = 1; thickness <= 6; thickness++)
            for( int direction = 0; direction <= 1; direction++)
                for( int position = 0; position < kSlices; position++)
                {
                    ProbePix *pix = [slices objectAtIndex: position];
                    [pix setSlab: thickness direction: direction mode: mode position: position array: slices];
                    float *got = [pix computeThickSlab];
                    if( !got) return 4;
                    int parameters[ 4] = { mode, thickness, direction, position };
                    fwrite( parameters, sizeof parameters, 1, out);
                    fwrite( got, sizeof( float), kWidth * kHeight, out);
                    free( got);
                }
    fclose( out);
    return 0;
}}
'''

DRIVER = r'''
import Foundation
import Metal
import Accelerate
import simd

func expect(_ ok: Bool, _ reason: @autoclosure () -> String) { if !ok { print("FAIL: " + reason()); exit(1) } }

func floats(_ data: Data) -> [Float] { data.withUnsafeBytes { Array($0.bindMemory(to: Float.self)) } }

func texture(_ image: MTLTexture) -> [Float] {
    var values = [Float](repeating: 0, count: image.width * image.height)
    values.withUnsafeMutableBytes { bytes in
        image.getBytes(bytes.baseAddress!, bytesPerRow: image.width * 4,
                       from: MTLRegionMake2D(0, 0, image.width, image.height), mipmapLevel: 0)
    }
    return values
}

@main struct Check {
    static func main() throws {
        guard let device = MTLCreateSystemDefaultDevice() else { print("skipped: no Metal device"); exit(2) }
        let file = try Data(contentsOf: URL(fileURLWithPath: CommandLine.arguments[1]))
        let words = file.withUnsafeBytes { Array($0.bindMemory(to: Int32.self)) }
        let w = Int(words[0]), h = Int(words[1]), depth = Int(words[2])
        let plane = w * h * 4
        var offset = 12
        var slices = [Data]()
        for _ in 0..<depth { slices.append(file.subdata(in: offset..<offset + plane)); offset += plane }
        let metal = try PlanarMetalRenderer(device: device)
        let pilot = PlanarMetal4Renderer.isSupported(device) ? try PlanarMetal4Renderer(device: device) : nil
        var gray = [UInt8]()
        for i in 0..<256 { gray += [UInt8(i), UInt8(i), UInt8(i), 255] }
        let curve = (0..<4096).map { Float(log10(1 + Double($0) / 4095 * 9)) }
        let table = curve.withUnsafeBytes { Data($0) }
        var cases = 0, pixels = 0, clamped = 0, enlarged = 0, tabled = 0, fastDiffers = 0
        let fast = try MPRMetalReslicer(device: device)

        while offset < file.count {
            let parameters = file.subdata(in: offset..<offset + 16).withUnsafeBytes { Array($0.bindMemory(to: Int32.self)) }
            offset += 16
            let host = file.subdata(in: offset..<offset + plane); offset += plane
            let mode = Int(parameters[0]), thickness = Int(parameters[1])
            let direction = Int(parameters[2]), position = Int(parameters[3])
            let label = "mode \(mode) thickness \(thickness) direction \(direction) position \(position)"

            let indices = PlanarThickSlab.sliceIndices(position: position, stack: thickness, direction: direction, count: depth)
                .map { $0.intValue }
            if indices.count + 1 < thickness { clamped += 1 }
            func snapshot(scale: Int = 1, transfer: Bool = false) -> NSMutableDictionary {
                let value: NSMutableDictionary = ["width": w, "height": h, "pixels": slices[position], "clut": Data(gray),
                    "frameIdentity": "slab-\(mode)-\(thickness)-\(direction)-\(position)", "level": 0.0, "widthWindow": 2000.0,
                    "screenToPixel": [0.0, 0.0, Double(w), 0.0, 0.0, Double(h)], "viewSize": [w * scale, h * scale],
                    "softwareScale": scale]
                if !indices.isEmpty {
                    value["slabMode"] = mode
                    value["slabSlices"] = indices.reduce(into: Data()) { $0.append(slices[$1]) }
                    value["slabCount"] = indices.count + 1
                }
                if transfer {
                    value["transferFunction"] = table; value["transferLevel"] = 0.0; value["transferWidth"] = 2000.0
                }
                return value
            }

            let frame = try PlanarFrame(snapshot())
            expect((frame.slab == nil) == indices.isEmpty, "\(label): a slab frame for \(indices.count + 1) slices")
            let (uploaded, format, _) = try frame.uploadPixels(device: device)
            expect(format == .r32Float, "\(label): the slab is not uploaded as floats")
            let expected = floats(host), got = floats(uploaded)
            for index in 0..<expected.count {
                expect(got[index] == expected[index],
                       "\(label): pixel \(index) is \(got[index]), the host's slab is \(expected[index])")
            }
            try metal.update(frame)
            expect(texture(metal.image!) == expected, "\(label): the Metal 3 texture is not the host's slab")
            if let pilot {
                try pilot.update(frame)
                expect(texture(pilot.image!) == expected, "\(label): the Metal 4 pilot's texture is not the host's slab")
            }
            if let slab = frame.slab, slab.projection == .mean {
                // For the record: the MPR's fast-math kernel on the same slices.
                var voxels = slices[position]; voxels.append(slab.others)
                try fast.upload(ResliceVolume(width: w, height: h, depth: slab.count, voxels: voxels,
                                              voxelToWorld: matrix_identity_float4x4))
                let reduced = floats(try fast.reslice(ReslicePlane(origin: SIMD3(0, 0, Float(slab.count - 1) * 0.5),
                    rowStep: SIMD3(1, 0, 0), columnStep: SIMD3(0, 1, 0), width: w, height: h,
                    thickness: Float(slab.count - 1), sampleStep: 1, projection: .mean, background: 0)))
                fastDiffers += zip(reduced, expected).filter { $0 != $1 }.count
            }

            // The host enlarges its slab, not the current slice.
            if position == 4 && direction == 0 {
                for scale in [2, 3] {
                    let bigger = try PlanarFrame(snapshot(scale: scale)).uploadPixels(device: device).pixels
                    var input = host, reference = Data(count: plane * scale * scale)
                    let status = reference.withUnsafeMutableBytes { destination in
                        input.withUnsafeMutableBytes { source in
                            var from = vImage_Buffer(data: source.baseAddress!, height: vImagePixelCount(h),
                                                     width: vImagePixelCount(w), rowBytes: w * 4)
                            var to = vImage_Buffer(data: destination.baseAddress!, height: vImagePixelCount(h * scale),
                                                   width: vImagePixelCount(w * scale), rowBytes: w * scale * 4)
                            return vImageScale_PlanarF(&from, &to, nil, vImage_Flags(kvImageNoFlags))
                        }
                    }
                    expect(status == kvImageNoError, "vImage failed")
                    expect(floats(bigger) == floats(reference), "\(label): the \(scale)x enlargement is not the host's slab enlarged")
                    enlarged += 1
                }
                // An opacity table follows the reduction.
                let withTable = try PlanarFrame(snapshot(transfer: true))
                let bytes = try withTable.uploadPixels(device: device).pixels
                let reference = try PlanarTransferPass.shared(for: device).apply(withTable.transfer!, to: host, count: w * h)
                expect(bytes == reference, "\(label): the opacity table did not follow the reduction")
                tabled += 1
            }
            cases += 1
            pixels += expected.count
        }
        expect(cases == 3 * 6 * 2 * depth, "only \(cases) cases were read")
        expect(clamped > 0 && enlarged > 0 && tabled > 0, "the comparison missed clamped, enlarged or tabled slabs")
        print("PASS: \(cases) slabs, \(pixels) pixels equal to computeThickSlab bit for bit through the Swift rule, the upload, the Metal 3 texture\(pilot == nil ? "" : " and the Metal 4 pilot's"); \(clamped) clamped at an end; \(enlarged) enlargements and \(tabled) tabled slabs; the MPR's fast-math mean would differ in \(fastDiffers) pixels")
    }
}
'''

FRAMEWORKS = ['Foundation', 'AppKit', 'AVFoundation', 'CoreData', 'CoreMedia', 'CoreVideo', 'Accelerate']


def objective_c_stubs():
    listing = subprocess.run(['nm', '-u', str(obj)], capture_output=True, text=True, check=True).stdout
    names = sorted({m.group(1) for m in re.finditer(r'_OBJC_CLASS_\$_(\w+)', listing)})
    sources = root / 'Horos/Sources'
    declared = [n for n in names
                if n != 'ROI' and ((sources / (n + '.h')).is_file() or (sources / (n + '.m')).is_file()
                                   or (sources / (n + '.mm')).is_file())]
    return ('@interface ROI : NSObject @end\n@implementation ROI @end\n'
            + ''.join('@interface %s : NSObject @end\n@implementation %s @end\n' % (n, n) for n in declared))


def link(directory, placeholders):
    assembly = ''.join('.globl %s\n%s: .quad 0\n' % (s, s) for s in sorted(placeholders))
    (directory / 'placeholders.s').write_text('.data\n' + assembly)
    command = ['xcrun', 'clang++', '-std=c++11', '-Wno-deprecated-declarations', '-I' + str(root / 'Horos/Sources'),
               str(directory / 'probe.mm'), str(directory / 'stubs.mm'), str(directory / 'placeholders.s'), str(obj),
               '-Wl,-undefined,dynamic_lookup', '-o', str(directory / 'probe')]
    for framework in FRAMEWORKS:
        command += ['-framework', framework]
    subprocess.run(command, check=True, capture_output=True)


with tempfile.TemporaryDirectory(prefix='horos-planar-slab-') as name:
    directory = Path(name)
    (directory / 'probe.mm').write_text(PROBE)
    (directory / 'stubs.mm').write_text('#import <Foundation/Foundation.h>\n' + objective_c_stubs())
    placeholders = set()
    for _ in range(200):
        link(directory, placeholders)
        try:
            run = subprocess.run([str(directory / 'probe'), str(directory / 'slabs.bin')],
                                 capture_output=True, text=True, timeout=120)
        except subprocess.TimeoutExpired:
            print('FAIL: computeThickSlab did not finish in 120 s')
            raise SystemExit(1)
        missing = re.search(r"symbol not found in flat namespace '([^']+)'", run.stderr)
        if not missing:
            break
        if missing.group(1) in placeholders:
            print('cannot satisfy %s' % missing.group(1), file=sys.stderr)
            raise SystemExit(1)
        placeholders.add(missing.group(1))
    if run.returncode:
        sys.stderr.write(run.stderr)
        print('FAIL: the host probe did not produce the slabs')
        raise SystemExit(1)

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
        print('FAIL: the planar renderer does not build with the thick-slab driver')
        raise SystemExit(1)
    result = subprocess.run([str(directory / 'check'), str(directory / 'slabs.bin')], timeout=300)
    raise SystemExit(result.returncode)
