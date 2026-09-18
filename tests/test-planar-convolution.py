#!/usr/bin/env python3
"""The planar Metal renderer runs the menu's convolution filters as the host does (#661).

A 2D image with a filter from *2D Viewer -> Convolution Filters* used to be refused
by the planar snapshot (`horosPlanarHasPresentationFilter`), so a filtered series
drew with «Original renderer (Metal paused)». The filter now runs in Metal where
the host runs it: after a thick slab, before the window, the opacity table and
any enlargement.

The reference is the host's own code, the application's `DCMPix.o` linked as
`tests/test-planar-thick-slab.py` links it: every filter the menu offers (read
from `DefaultsOsiriX.m`, 3x3 and 5x5, symmetric and not, summing to zero or not)
on a 37 x 29 scalar image whose values change sign, so the sums cancel; the same
with a thick slab in mean, maximum and minimum under it; and on a colour image.
The host filters with vImage:

* scalar, `vImageConvolve_PlanarF`, which sums in an order of its own. No fixed
  order reproduces it bit for bit, and near a cancelling sum two correct float
  sums differ by thousands of units in the last place of the result, so the
  A111 bound of eight ULPs cannot hold for the menu's sharpening and edge
  filters. The bound here is the one float summation guarantees: the two sums
  of n x n products each lie within (n x n) * 2^-24 * sum|w * x| of the exact
  one, so they differ by at most twice that. The first row, which DCMPix
  replaces with the source's first value, must be exact;
* colour, `vImageConvolve_ARGB8888`, integer arithmetic: bit for bit.

The scalar result is also held against A111's independent reference, the same
sum in float64, within one float sum's bound.

Through `PlanarFrame.uploadPixels`, the Metal 3 texture and the Metal 4 pilot's;
a filter changed on the open frame changes the frame and its pixels; an opacity
table follows the filter; a 2x enlargement is vImage's of the filtered image.

Also checked in the sources: the snapshot no longer refuses a filter and hands
the kernel over; the renderer runs it after the slab and before the table.

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

snapshot = bridge[bridge.index('- (NSDictionary *)horosPlanarSnapshot'):]
refusal = snapshot[:snapshot.index('return @{@"error": unsupported};')]
if 'horosPlanarHasPresentationFilter' in refusal:
    failures.append('the planar snapshot still refuses a convolution filter')
for key in ('convolutionSize', 'convolutionKernel', 'convolutionNormalization'):
    if '@"%s"' % key not in snapshot:
        failures.append('the snapshot does not hand over ' + key)
upload = renderer[renderer.index('func uploadPixels'):] if 'func uploadPixels' in renderer else ''
if 'PlanarConvolutionPass' not in upload:
    failures.append('the upload does not run the convolution filter')
elif not (upload.index('PlanarSlabProjection') < upload.index('PlanarConvolutionPass') < upload.index('PlanarTransferPass')):
    failures.append('the filter does not run after the slab and before the opacity table, as the host runs it')
if failures:
    for failure in failures:
        print('FAIL:', failure)
    raise SystemExit(1)

# Every filter the menu offers, as DefaultsOsiriX registers it: normalisation = sum of the kernel.
defaults = read('Horos/Sources/DefaultsOsiriX.m')
filters = [(name, int(size), [int(v) for v in values.split(',')])
           for values, size, name in re.findall(r'short\s+vals\[\d+\]\s*=\s*\{([^}]*)\};\s*\[self addConvolutionFilter:(\d+)\s*:vals\s*:@"([^"]+)"',
                                                defaults)]
if len(filters) < 20 or {size for _, size, _ in filters} != {3, 5}:
    print('FAIL: the menu filters were not read from DefaultsOsiriX.m (%d found)' % len(filters))
    raise SystemExit(1)

objects = [root / 'build/Build/Intermediates.noindex/Horos.build' / configuration /
           'Horos.build/Objects-normal/arm64/DCMPix.o' for configuration in ('Debug', 'Release')]
obj = next((o for o in objects if o.is_file()), None)
if obj is None:
    print('needs a built DCMPix.o in %s' % ' or '.join(str(o) for o in objects), file=sys.stderr)
    raise SystemExit(2)

FILTERS = '\n'.join('    { %d, %d, { %s } },' % (size, sum(values), ', '.join('%d' % v for v in values + [0] * (25 - len(values))))
                    for _, size, values in filters)

PROBE = r'''
#import <Foundation/Foundation.h>
#import "DCMPix.h"
#include <cstdio>
#include <cstdlib>
#include <cmath>
#include <cstring>

static const int kWidth = 37, kHeight = 29, kSlices = 5;
struct Filter { int size; int normalization; int values[25]; };
static const Filter kFilters[] = {
FILTERS
};

@interface DCMPix (HorosConvolutionProbe)
- (float*) computeThickSlab;
- (float*) applyConvolutionOnImage:(float*) src RGB:(BOOL) color;
@end

@interface ProbePix : DCMPix
- (void) prepareSlice:(int) index colour:(BOOL) colour;
- (void) setSlab:(int) thickness mode:(int) mode position:(int) position array:(NSArray*) array;
@end
@implementation ProbePix
- (void) CheckLoad {}
- (void) prepareSlice:(int) index colour:(BOOL) colour
{
    width = kWidth; height = kHeight; isRGB = colour; thickSlabVRActivated = NO; stackMode = 0; stack = 0;
    fImage = (float*) calloc( kWidth * kHeight, sizeof( float));
    if( colour)
    {
        unsigned char *bytes = (unsigned char*) fImage;
        for( int i = 0; i < kWidth * kHeight * 4; i++) bytes[ i] = (unsigned char)(( i * 37 + index * 11 + ( i / 4) % 13 * 29) & 255);
    }
    else
        // Signs change across the image, so sharpening and edge sums cancel.
        for( int y = 0; y < kHeight; y++)
            for( int x = 0; x < kWidth; x++)
                fImage[ y * kWidth + x] = sinf( x * 0.9f + y * 1.7f + index * 2.3f) * 1500.f + cosf( x * y * 0.05f) * 300.f
                    + (float)(( x * 7 + y * 3 + index) % 11) * 0.37f - 400.f;
}
- (void) setSlab:(int) thickness mode:(int) mode position:(int) position array:(NSArray*) array
{
    stack = thickness; stackDirection = 0; stackMode = mode; pixPos = position;
    [pixArray release];
    pixArray = [array retain];
    ww = 256; wl = 127;
}
@end

static void write( FILE *out, const void *data, size_t size) { fwrite( data, size, 1, out); }

int main( int argc, char **argv) { @autoreleasepool {
    FILE *out = fopen( argv[ 1], "wb");
    if( !out) return 3;
    const int count = (int)( sizeof kFilters / sizeof kFilters[ 0]);
    NSMutableArray *slices = [NSMutableArray array];
    for( int i = 0; i < kSlices; i++)
    {
        ProbePix *pix = [[ProbePix alloc] init];
        [pix prepareSlice: i colour: NO];
        [slices addObject: pix];
    }
    ProbePix *colour = [[ProbePix alloc] init];
    [colour prepareSlice: 0 colour: YES];
    int header[ 4] = { kWidth, kHeight, kSlices, count };
    write( out, header, sizeof header);
    for( ProbePix *pix in slices) write( out, [pix fImage], sizeof( float) * kWidth * kHeight);
    write( out, [colour fImage], 4 * kWidth * kHeight);
    for( int f = 0; f < count; f++)
    {
        float kernel[ 25] = { 0 };
        for( int i = 0; i < 25; i++) kernel[ i] = kFilters[ f].values[ i];
        // mode 0: the current slice alone; 1-3: a thick slab of three under the filter.
        for( int mode = 0; mode <= 3; mode++)
        {
            ProbePix *pix = [slices objectAtIndex: 2];
            if( mode) [pix setSlab: 3 mode: mode position: 2 array: slices];
            else [pix setSlab: 0 mode: 0 position: 2 array: slices];
            [pix setConvolutionKernel: kernel : kFilters[ f].size : kFilters[ f].normalization];
            float *got = [pix computefImage];
            if( !got) return 4;
            int parameters[ 2] = { f, mode };
            write( out, parameters, sizeof parameters);
            write( out, got, sizeof( float) * kWidth * kHeight);
            if( got != [pix fImage]) free( got);
            [pix setConvolutionKernel: nil : 0 : 0];
        }
        [colour setConvolutionKernel: kernel : kFilters[ f].size : kFilters[ f].normalization];
        float *filtered = [colour applyConvolutionOnImage: [colour fImage] RGB: YES];
        if( !filtered || filtered == [colour fImage]) return 5;
        int parameters[ 2] = { f, -1 };
        write( out, parameters, sizeof parameters);
        write( out, filtered, 4 * kWidth * kHeight);
        free( filtered);
        [colour setConvolutionKernel: nil : 0 : 0];
    }
    fclose( out);
    return 0;
}}
'''.replace('FILTERS', FILTERS)

DRIVER = r'''
import Foundation
import Metal
import Accelerate

func expect(_ ok: Bool, _ reason: @autoclosure () -> String) { if !ok { print("FAIL: " + reason()); exit(1) } }
func floats(_ data: Data) -> [Float] { data.withUnsafeBytes { Array($0.bindMemory(to: Float.self)) } }

func texture(_ image: MTLTexture, bytesPerPixel: Int) -> Data {
    var values = Data(count: image.width * image.height * bytesPerPixel)
    values.withUnsafeMutableBytes { bytes in
        image.getBytes(bytes.baseAddress!, bytesPerRow: image.width * bytesPerPixel,
                       from: MTLRegionMake2D(0, 0, image.width, image.height), mipmapLevel: 0)
    }
    return values
}

@main struct Check {
    static func main() throws {
        guard let device = MTLCreateSystemDefaultDevice() else { print("skipped: no Metal device"); exit(2) }
        let file = try Data(contentsOf: URL(fileURLWithPath: CommandLine.arguments[1]))
        let header = file.withUnsafeBytes { Array($0.bindMemory(to: Int32.self).prefix(4)) }
        let w = Int(header[0]), h = Int(header[1]), depth = Int(header[2]), filterCount = Int(header[3])
        let plane = w * h * 4
        var offset = 16
        var slices = [Data]()
        for _ in 0..<depth { slices.append(file.subdata(in: offset..<offset + plane)); offset += plane }
        let colourSource = file.subdata(in: offset..<offset + plane); offset += plane
        let metal = try PlanarMetalRenderer(device: device)
        let pilot = PlanarMetal4Renderer.isSupported(device) ? try PlanarMetal4Renderer(device: device) : nil
        var gray = [UInt8]()
        for i in 0..<256 { gray += [UInt8(i), UInt8(i), UInt8(i), 255] }
        let kernels: [[Float]] = KERNELS
        let sizes: [Int] = SIZES
        let normalizations: [Float] = NORMALIZATIONS
        var scalarCases = 0, colourCases = 0, pixels = 0, worst = 0.0, worstExact = 0.0, differing = 0

        func snapshot(_ filter: Int?, mode: Int, colour: Bool = false, scale: Int = 1, table: Bool = false) -> NSMutableDictionary {
            let value: NSMutableDictionary = ["width": w, "height": h, "pixels": colour ? colourSource : slices[2], "clut": Data(gray),
                "frameIdentity": "filter", "level": 0.0, "widthWindow": 3000.0, "isColor": colour,
                "screenToPixel": [0.0, 0.0, Double(w), 0.0, 0.0, Double(h)], "viewSize": [w * scale, h * scale],
                "softwareScale": scale]
            if mode > 0 {
                // The slices computeThickSlab reduces with slice 2, three of them, direction 0, as the bridge asks.
                let others = PlanarThickSlab.sliceIndices(position: 2, stack: 3, direction: 0, count: depth).map { $0.intValue }
                value["slabMode"] = mode
                value["slabSlices"] = others.reduce(into: Data()) { $0.append(slices[$1]) }
                value["slabCount"] = others.count + 1
            }
            if let filter {
                var kernel = kernels[filter] + [Float](repeating: 0, count: 25 - kernels[filter].count)
                value["convolutionSize"] = sizes[filter]
                value["convolutionKernel"] = Data(bytes: &kernel, count: 25 * 4)
                value["convolutionNormalization"] = normalizations[filter]
            }
            if table {
                let curve = (0..<4096).map { Float(log10(1 + Double($0) / 4095 * 9)) }
                value["transferFunction"] = curve.withUnsafeBytes { Data($0) }
                value["transferLevel"] = 0.0; value["transferWidth"] = 3000.0
            }
            return value
        }

        while offset < file.count {
            let parameters = file.subdata(in: offset..<offset + 8).withUnsafeBytes { Array($0.bindMemory(to: Int32.self)) }
            offset += 8
            let host = file.subdata(in: offset..<offset + plane); offset += plane
            let filter = Int(parameters[0]), mode = Int(parameters[1])
            let label = "filter \(filter) (\(sizes[filter])x\(sizes[filter]), normalisation \(normalizations[filter])) mode \(mode)"
            let colour = mode < 0
            let frame = try PlanarFrame(snapshot(filter, mode: max(0, mode), colour: colour))
            expect(frame.convolution != nil, "\(label): the frame has no filter")
            let (uploaded, format, bytesPerPixel) = try frame.uploadPixels(device: device)
            if colour {
                expect(format == .rgba8Unorm, "\(label): the colour image is not uploaded as bytes")
                if uploaded != host {
                    let first = zip(uploaded, host).enumerated().first { $0.element.0 != $0.element.1 }!
                    expect(false, "\(label): byte \(first.offset) is \(first.element.0), vImage's is \(first.element.1)")
                }
                colourCases += 1
            } else {
                expect(format == .r32Float, "\(label): the filtered image is not uploaded as floats")
                // What the filter read: the slice, or the slab the host reduced (bit for bit, #659).
                let source = floats(try PlanarFrame(snapshot(nil, mode: mode)).uploadPixels(device: device).pixels)
                let got = floats(uploaded), expected = floats(host)
                let n = sizes[filter], radius = n / 2
                let weights = frame.convolution!.weights
                for y in 0..<h {
                    for x in 0..<w {
                        let index = y * w + x
                        if y == 0 {
                            expect(got[index] == expected[index] && got[index] == source[0],
                                   "\(label): the first row is \(got[index]), the host writes its first value \(expected[index])")
                            continue
                        }
                        var terms = 0.0, exact = 0.0
                        for j in 0..<n { for i in 0..<n {
                            let sy = min(max(y + j - radius, 0), h - 1), sx = min(max(x + i - radius, 0), w - 1)
                            let product = Double(source[sy * w + sx]) * Double(weights[j * n + i])
                            terms += abs(product); exact += product
                        } }
                        // A111's independent reference: the same sum in float64. One float sum of
                        // n x n products lies within n x n * 2^-24 * sum|w x| of it.
                        let single = Double(n * n) * pow(2, -24) * terms + Double(Float(exact).ulp)
                        expect(abs(Double(got[index]) - exact) <= single,
                               "\(label): pixel (\(x), \(y)) is \(got[index]), the float64 convolution is \(exact)")
                        if single > 0 { worstExact = max(worstExact, abs(Double(got[index]) - exact) / single) }
                        let bound = 2 * Double(n * n) * pow(2, -24) * terms
                        let gap = abs(Double(got[index]) - Double(expected[index]))
                        expect(gap <= bound, "\(label): pixel (\(x), \(y)) is \(got[index]), vImage's is \(expected[index]); \(gap) > the summation bound \(bound)")
                        if bound > 0 { worst = max(worst, gap / bound) }
                        if got[index] != expected[index] { differing += 1 }
                    }
                }
                scalarCases += 1
            }
            try metal.update(frame)
            expect(texture(metal.image!, bytesPerPixel: bytesPerPixel) == uploaded, "\(label): the Metal 3 texture is not the filtered upload")
            if let pilot {
                try pilot.update(frame)
                expect(texture(pilot.image!, bytesPerPixel: bytesPerPixel) == uploaded, "\(label): the Metal 4 pilot's texture is not the filtered upload")
            }
            pixels += w * h
        }
        expect(scalarCases == filterCount * 4 && colourCases == filterCount, "only \(scalarCases) scalar and \(colourCases) colour cases were read")

        // A filter changed on the open frame changes the frame and its pixels.
        let blur = try PlanarFrame(snapshot(0, mode: 0)), other = try PlanarFrame(snapshot(filterCount - 1, mode: 0))
        let none = try PlanarFrame(snapshot(nil, mode: 0))
        expect(blur != other && blur != none, "changing or removing the filter leaves the frame equal")
        expect(try blur.uploadPixels(device: device).pixels != other.uploadPixels(device: device).pixels,
               "changing the filter leaves the pixels")
        expect(try none.uploadPixels(device: device).pixels == slices[2], "without a filter the slice is uploaded as it is")
        // An opacity table follows the filter.
        let tabled = try PlanarFrame(snapshot(0, mode: 0, table: true))
        let filtered = try PlanarFrame(snapshot(0, mode: 0)).uploadPixels(device: device).pixels
        expect(try tabled.uploadPixels(device: device).pixels ==
               PlanarTransferPass.shared(for: device).apply(tabled.transfer!, to: filtered, count: w * h),
               "the opacity table did not follow the filter")
        // A 2x enlargement is vImage's of the filtered image.
        let bigger = try PlanarFrame(snapshot(0, mode: 0, scale: 2)).uploadPixels(device: device).pixels
        var input = filtered, reference = Data(count: plane * 4)
        let status = reference.withUnsafeMutableBytes { destination in
            input.withUnsafeMutableBytes { source in
                var from = vImage_Buffer(data: source.baseAddress!, height: vImagePixelCount(h), width: vImagePixelCount(w), rowBytes: w * 4)
                var to = vImage_Buffer(data: destination.baseAddress!, height: vImagePixelCount(h * 2), width: vImagePixelCount(w * 2), rowBytes: w * 8)
                return vImageScale_PlanarF(&from, &to, nil, vImage_Flags(kvImageNoFlags))
            }
        }
        expect(status == kvImageNoError && bigger == reference, "the 2x enlargement is not vImage's of the filtered image")
        print(String(format: "PASS: %d filters (3x3 and 5x5) on %d scalar cases, with and without a thick slab, within the float summation bound of vImage's result (worst %.3f of it; %d of the pixels not bit for bit, the first row exact) and of the independent float64 convolution (worst %.3f of one sum's bound), and %d colour cases bit for bit; %d pixels through the upload, the Metal 3 texture%@; a changed filter, the opacity table after it and the 2x enlargement hold",
                     filterCount, scalarCases, worst, differing, worstExact, colourCases, pixels, pilot == nil ? "" : " and the Metal 4 pilot's"))
    }
}
'''
DRIVER = (DRIVER.replace('KERNELS', '[' + ', '.join('[' + ', '.join('%d' % v for v in values) + ']' for _, _, values in filters) + ']')
          .replace('SIZES', '[' + ', '.join('%d' % size for _, size, _ in filters) + ']')
          .replace('NORMALIZATIONS', '[' + ', '.join('%d' % sum(values) for _, _, values in filters) + ']'))

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


with tempfile.TemporaryDirectory(prefix='horos-planar-convolution-') as name:
    directory = Path(name)
    (directory / 'probe.mm').write_text(PROBE)
    (directory / 'stubs.mm').write_text('#import <Foundation/Foundation.h>\n' + objective_c_stubs())
    placeholders = set()
    for _ in range(200):
        link(directory, placeholders)
        try:
            run = subprocess.run([str(directory / 'probe'), str(directory / 'filters.bin')],
                                 capture_output=True, text=True, timeout=120)
        except subprocess.TimeoutExpired:
            print('FAIL: the host probe did not finish in 120 s')
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
        print('FAIL: the host probe did not produce the filtered images (exit %d)' % run.returncode)
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
        print('FAIL: the planar renderer does not build with the convolution driver')
        raise SystemExit(1)
    result = subprocess.run([str(directory / 'check'), str(directory / 'filters.bin')], timeout=300)
    raise SystemExit(result.returncode)
