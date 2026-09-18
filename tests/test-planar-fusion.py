#!/usr/bin/env python3
"""The planar Metal renderer draws a fused series over the image (#658).

A 2D viewer with a fused series (`view.blendingView`, PET over CT) used to be
refused by the planar snapshot, so it drew with «Original renderer (Metal
paused)». The host draws the image, then `[blendingView drawRectIn:...]` with
GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA: the fused series through its scalar CLUT
program, with its own window and the table `loadTextureIn:blending:YES` builds -
the colours the PET CLUT mode gives, its channel factors, and its alpha table -
and with its own origin, scale, rotation, flips and pixel ratio in the frame it
is handed, the image's. Only in the key view, and only while the two series'
locations are in sync. Under a fusion the image itself is added to the clear
colour (GL_ONE, GL_ONE), which is white under the B/W Inverse CLUT.

Checked here:

* the sources: the snapshot no longer refuses a fusion; it attaches the fused
  series under the host's conditions, with that table and that mapping, and a
  white CLUT for the image under a white clear colour; a colour fused series is
  refused; DCMView draws the fused series itself only when Metal did not;
* the mapping: the application's own `DCMView.o` and `PlanarHostBridge.o`,
  linked as `tests/test-planar-host-presentation.py` links `DCMPix.o`: for
  random frames, backing scales, zooms, rotations, origins, flips and pixel
  ratios, `horosPixelAt:drawnIn:` for a fused view equals, bit for bit, the
  host's `ConvertFromUpLeftView2GL:` on that view with the image's drawing
  frame, the frame drawRectIn: draws it in;
* the composition, on both backends, at texel centres of both layers: outside
  the fused image the image's CLUT colour, opaque; over it the fused CLUT colour
  blended source-alpha over the image's, with the fused table's alpha column,
  within one level of the exact value (the blend's own rounding), for a
  float, a flipped and an opacity-table fused series; the Metal 4 pilot equal
  to Metal 3 byte for byte;
* the fusion factor: a changed alpha column uploads the fused series again and
  keeps the image's textures, and a changed image window keeps the fused ones;
  alpha 0 leaves the image, alpha 255 the fused colours;
* a colour fused series, or one with a fusion of its own, is not drawn.

`<git revision>` as an optional argument reads the sources from that revision,
the negative control.
"""
from pathlib import Path
import random
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
view_source = read('Horos/Sources/DCMView.m')
snapshot = bridge[bridge.index('- (NSDictionary *)horosPlanarSnapshot'):]
refusal = snapshot[:snapshot.index('return @{@"error": unsupported};')]
if 'blendingView' in refusal:
    failures.append('the planar snapshot still refuses a fused series')
if '(fused && pix.isRGB)' not in refusal:
    failures.append('the snapshot does not refuse a colour fused series')
attach = re.search(r'if \(!fused && view\.blendingView && !syncOnLocationImpossible && view\.isKeyView\) \{\s*'
                   r'NSDictionary \*layer = \[view\.blendingView horosPlanarSnapshotDrawnIn:view\];', snapshot)
if not attach:
    failures.append('the fused series is not attached where drawRect: draws it: key view, locations in sync')
if not re.search(r'if \(!fused && view\.blendingView && !syncOnLocationImpossible && view\.whiteBackground\) \{\s*'
                 r'memset\(rgba, 255, sizeof\(rgba\)\);', snapshot):
    failures.append('the image is not drawn white under a fusion with a white clear colour')
table = re.search(r'\[host blendingColorTables:&unused :&r :&g :&b\];\s*\[view colorTables:&alpha :&unused :&unused :&unused\];'
                  r'.*?for \(NSUInteger i = 0; i < 256; \+\+i\) \{\s*'
                  r'rgba\[4\*i\] = fminf\(255, fmaxf\(0, r\[i\] \* redFactor\)\);\s*'
                  r'rgba\[4\*i\+1\] = fminf\(255, fmaxf\(0, g\[i\] \* greenFactor\)\);\s*'
                  r'rgba\[4\*i\+2\] = fminf\(255, fmaxf\(0, b\[i\] \* blueFactor\)\);\s*'
                  r'rgba\[4\*i\+3\] = alpha \? alpha\[i\] : 255;', snapshot, re.S)
host_table = re.search(r'rgba\[4\*i\] = fminf\(255, fmaxf\(0, rT\[i\] \* redFactor\)\);\s*'
                       r'rgba\[4\*i\+1\] = fminf\(255, fmaxf\(0, gT\[i\] \* greenFactor\)\);\s*'
                       r'rgba\[4\*i\+2\] = fminf\(255, fmaxf\(0, bT\[i\] \* blueFactor\)\);\s*'
                       r'rgba\[4\*i\+3\] = currentAlphaTable\[i\];', view_source)
if not table or not host_table:
    failures.append('the fused table is not the one loadTextureIn:blending:YES builds')
for key, value in [('screenToPixel', '[view horosPixelAt:NSMakePoint(NSMinX(bounds), NSMaxY(bounds)) drawnIn:host]'),
                   ('viewSize', 'NSRect bounds = host.bounds;')]:
    if value not in snapshot:
        failures.append('the fused series\' %s is not taken in the image\'s view' % key)
draw = view_source[view_source.index('if( blendingView != nil && syncOnLocationImpossible == NO && noBlending == NO )'):]
draw = draw[:draw.index('glDisable( GL_BLEND);')]
if not re.search(r'if\( planarDrawn == NO\)\s*\{\s*if\( blendingTextureName\)\s*\[blendingView drawRectIn:', draw):
    failures.append('DCMView draws the fused series again over the Metal frame')
if failures:
    for failure in failures:
        print('FAIL:', failure)
    raise SystemExit(1)

build = root / 'build/Build/Intermediates.noindex/Horos.build'
objects = [build / configuration / 'Horos.build/Objects-normal/arm64' for configuration in ('Debug', 'Release')]
directory_of_objects = next((o for o in objects if (o / 'DCMView.o').is_file() and (o / 'PlanarHostBridge.o').is_file()), None)
if directory_of_objects is None:
    print('needs a built DCMView.o and PlanarHostBridge.o in %s' % ' or '.join(str(o) for o in objects), file=sys.stderr)
    raise SystemExit(2)
linked = [directory_of_objects / 'DCMView.o', directory_of_objects / 'PlanarHostBridge.o']

PROBE = r'''
#import <AppKit/AppKit.h>
#include <cstdio>
#include <cstdlib>
#include <cstring>

// The part of DCMView the probe touches. Ivar offsets resolve through
// DCMView.o's own symbols, so this subset reads the real layout.
@class DCMPix;
@interface DCMView : NSOpenGLView
{
    NSRect drawingFrameRect;
    float scaleValue, rotation;
    NSPoint origin;
    BOOL xFlipped, yFlipped;
}
@property NSRect drawingFrameRect;
- (NSPoint) ConvertFromUpLeftView2GL:(NSPoint) a;
- (NSPoint) ConvertFromNSView2GL:(NSPoint) a;
- (NSPoint) horosPixelAt:(NSPoint) point drawnIn:(DCMView *) host;
@end

@interface ProbeImage : NSObject
@property long pwidth, pheight;
@property double pixelRatio;
@end
@implementation ProbeImage
@end

@interface ProbeView : DCMView
{ @public CGFloat probeBacking; ProbeImage *probeImage; }
@end
@implementation ProbeView
- (NSPoint) convertPointToBacking:(NSPoint) a { return NSMakePoint( a.x * probeBacking, a.y * probeBacking); }
- (DCMPix*) curDCM { return (DCMPix*) probeImage; }
- (void) probeFrame:(NSRect) frame scale:(float) s rotation:(float) r origin:(NSPoint) o flipX:(BOOL) fx flipY:(BOOL) fy
{
    drawingFrameRect = frame; scaleValue = s; rotation = r; origin = o; xFlipped = fx; yFlipped = fy;
}
@end

int main( int argc, char **argv) { @autoreleasepool {
    unsigned seed = (unsigned) strtoul( argv[ 1], NULL, 10);
    srand( seed);
    auto uniform = []( double lo, double hi) { return lo + ( hi - lo) * ( rand() / (double) RAND_MAX); };
    long compared = 0, differing = 0, identity = 0;
    for( int trial = 0; trial < 4000; trial++)
    {
        // Never initialised and never released: only the geometry ivars are read.
        ProbeView *host = [ProbeView alloc], *fused = [ProbeView alloc];
        host->probeBacking = fused->probeBacking = trial % 2 ? 2.0 : 1.0;
        NSRect frame = NSMakeRect( 0, 0, floor( uniform( 64, 2400)), floor( uniform( 64, 1600)));
        host->probeImage = [[ProbeImage alloc] init];
        host->probeImage.pwidth = 512; host->probeImage.pheight = 512; host->probeImage.pixelRatio = 1;
        [host probeFrame: frame scale: uniform( 0.2, 6) rotation: uniform( 0, 360) origin: NSMakePoint( uniform( -300, 300), uniform( -300, 300))
                   flipX: rand() % 2 flipY: rand() % 2];
        fused->probeImage = [[ProbeImage alloc] init];
        fused->probeImage.pwidth = (long) uniform( 16, 700); fused->probeImage.pheight = (long) uniform( 16, 700);
        fused->probeImage.pixelRatio = trial % 3 ? 1.0 : uniform( 0.5, 2.5);
        // The fused view's own frame is another window's; drawRectIn: ignores it, and so must the mirror.
        [fused probeFrame: NSMakeRect( 0, 0, floor( uniform( 64, 2400)), floor( uniform( 64, 1600)))
                    scale: uniform( 0.2, 12) rotation: trial % 4 ? uniform( 0, 360) : 0
                   origin: NSMakePoint( uniform( -500, 500), uniform( -500, 500)) flipX: rand() % 2 flipY: rand() % 2];
        CGFloat b = host->probeBacking;
        NSPoint points[ 3] = { NSMakePoint( 0, frame.size.height / b), NSMakePoint( frame.size.width / b, frame.size.height / b), NSMakePoint( 0, 0) };
        for( int k = 0; k < 4; k++)
        {
            NSPoint p = k < 3 ? points[ k] : NSMakePoint( uniform( 0, frame.size.width / b), uniform( 0, frame.size.height / b));
            NSPoint mirror = [fused horosPixelAt: p drawnIn: host];
            // The host's conversion on the fused view, in the image's frame.
            NSRect own = fused.drawingFrameRect;
            fused.drawingFrameRect = frame;
            NSPoint upLeft = NSMakePoint( p.x * b, frame.size.height - p.y * b);
            NSPoint reference = [fused ConvertFromUpLeftView2GL: upLeft];
            fused.drawingFrameRect = own;
            compared++;
            if( memcmp( &mirror, &reference, sizeof mirror))
            {
                if( differing++ < 5) printf( "differs: trial %d point (%g, %g): mirror (%.17g, %.17g), host (%.17g, %.17g)\n",
                                             trial, p.x, p.y, mirror.x, mirror.y, reference.x, reference.y);
            }
            NSPoint own_image = [host horosPixelAt: p drawnIn: host], converted = [host ConvertFromNSView2GL: p];
            if( memcmp( &own_image, &converted, sizeof own_image) == 0) identity++;
        }
    }
    printf( "compared %ld differing %ld identity %ld\n", compared, differing, identity);
    return differing ? 1 : 0;
}}
'''

DRIVER = r'''
import Foundation
import Metal

func expect(_ ok: Bool, _ reason: @autoclosure () -> String) { if !ok { print("FAIL: " + reason()); exit(1) } }

let w = 41, h = 37, fw = 23, fh = 19, dx = 9, dy = 7
// Values inside CLUT bins, away from the rounding boundary: bin k plus 0.2 or 0.8.
func sample(_ k: Int, _ f: Float, level: Float, width: Float) -> Float { level - width / 2 + width * (Float(k) + f) / 255 }
func index(_ k: Int, _ f: Float) -> Int { f < 0.5 ? k : k + 1 }
let primaryBins = (0..<(w * h)).map { i in ((i % w) * 7 + (i / w) * 13) % 255 }
let primaryFractions = (0..<(w * h)).map { i in Float(i % 3 == 0 ? 0.8 : 0.2) }
let fusedBins = (0..<(fw * fh)).map { i in ((i % fw) * 11 + (i / fw) * 5 + 3) % 255 }
let fusedFractions = (0..<(fw * fh)).map { i in Float(i % 2 == 0 ? 0.2 : 0.8) }
let primaryValues = (0..<(w * h)).map { sample(primaryBins[$0], primaryFractions[$0], level: 300, width: 1400) }
let fusedValues = (0..<(fw * fh)).map { sample(fusedBins[$0], fusedFractions[$0], level: 1000, width: 2000) }
func makePrimaryCLUT() -> [UInt8] {
    var table = [UInt8]()
    for i in 0..<256 {
        let entry: [UInt8] = [UInt8(i), UInt8((i * 3) % 256), UInt8(255 - i), 255]
        table += entry
    }
    return table
}
func makeFusedColours() -> [UInt8] {
    var colours = [UInt8]()
    for i in 0..<256 {
        let entry: [UInt8] = [UInt8((i * 5) % 256), UInt8(i), UInt8((i * 11) % 256)]
        colours += entry
    }
    return colours
}
let primaryCLUT = makePrimaryCLUT()
let fusedColours = makeFusedColours()
func fusedCLUT(_ alpha: (Int) -> UInt8) -> Data {
    var table = [UInt8]()
    for i in 0..<256 {
        let entry: [UInt8] = [fusedColours[3 * i], fusedColours[3 * i + 1], fusedColours[3 * i + 2], alpha(i)]
        table += entry
    }
    return Data(table)
}
// Every alpha once: 37 is prime to 256.
let spread: (Int) -> UInt8 = { UInt8(($0 * 37 + 11) % 256) }

func floats(_ values: [Float]) -> Data { values.withUnsafeBufferPointer { Data(buffer: $0) } }

func fused(clut: Data, flipped: Bool = false, table: Data? = nil) -> NSDictionary {
    // Texel centres of the fused image under the target's pixel centres, at (dx, dy), mirrored when flipped.
    let left = flipped ? Double(fw + dx) : Double(-dx), right = flipped ? Double(fw + dx - w) : Double(w - dx)
    let layer: NSMutableDictionary = ["width": fw, "height": fh, "pixels": floats(fusedValues), "clut": clut,
        "frameIdentity": "fused", "level": 1000.0, "widthWindow": 2000.0, "isColor": false,
        "screenToPixel": [left, Double(-dy), right, Double(-dy), left, Double(h - dy)], "viewSize": [w, h], "softwareScale": 1]
    if let table {
        layer["transferFunction"] = table; layer["transferLevel"] = 1000.0; layer["transferWidth"] = 2000.0
    }
    return layer
}
func frame(fusion: NSDictionary?, level: Double = 300) throws -> PlanarFrame {
    let value: NSMutableDictionary = ["width": w, "height": h, "pixels": floats(primaryValues), "clut": Data(primaryCLUT),
        "frameIdentity": "image", "level": level, "widthWindow": 1400.0, "isColor": false,
        "screenToPixel": [0.0, 0.0, Double(w), 0.0, 0.0, Double(h)], "viewSize": [w, h], "softwareScale": 1]
    if let fusion { value["fusion"] = fusion }
    return try PlanarFrame(value)
}

@main struct Check {
    static func main() throws {
        guard let device = MTLCreateSystemDefaultDevice() else { print("skipped: no Metal device"); exit(2) }
        let metal = try PlanarMetalRenderer(device: device)
        let pilot = PlanarMetal4Renderer.isSupported(device) ? try PlanarMetal4Renderer(device: device) : nil
        var composed = 0, blended = 0, exact = 0, largest = 0

        // The opacity table's bytes for the fused values, as the host computes them (#657).
        let curve = (0..<4096).map { Float(($0 * 2654435761) % 4096) / 4095 }
        let from = Float(Double(1000) - Double(2000) / 2), ratio = Float(4096 / Double(2000))
        let tableBytes = fusedValues.map { value -> Int in
            let scaled = ratio * (value - from)
            return Int((255 * Double(curve[min(4095, max(0, Int(scaled)))])).rounded(.towardZero))
        }

        func check(_ label: String, _ frame: PlanarFrame, alpha: (Int) -> UInt8, flipped: Bool = false, table: Bool = false) throws {
            try metal.update(frame)
            let picture = [UInt8](try metal.renderBGRA(width: w, height: h))
            if let pilot {
                try pilot.update(frame)
                expect([UInt8](try pilot.renderBGRA(width: w, height: h)) == picture, "\(label): the Metal 4 pilot composes differently")
            }
            for y in 0..<h { for x in 0..<w {
                let o = (y * w + x) * 4, i = y * w + x
                let p = index(primaryBins[i], primaryFractions[i])
                let under = (Double(primaryCLUT[4 * p]), Double(primaryCLUT[4 * p + 1]), Double(primaryCLUT[4 * p + 2]))
                var expected = [under.0, under.1, under.2, 255.0]
                let sx = x - dx, sy = y - dy
                if sx >= 0, sx < fw, sy >= 0, sy < fh {
                    let j = sy * fw + (flipped ? fw - 1 - sx : sx)
                    let s = table ? tableBytes[j] : index(fusedBins[j], fusedFractions[j])
                    let a = Double(alpha(s)) / 255
                    expected = [Double(fusedColours[3 * s]) * a + under.0 * (1 - a), Double(fusedColours[3 * s + 1]) * a + under.1 * (1 - a),
                                Double(fusedColours[3 * s + 2]) * a + under.2 * (1 - a), (a * a + (1 - a)) * 255]
                    blended += 1
                } else {
                    let got = [picture[o + 2], picture[o + 1], picture[o], picture[o + 3]]
                    expect(got == [primaryCLUT[4 * p], primaryCLUT[4 * p + 1], primaryCLUT[4 * p + 2], 255],
                           "\(label): (\(x), \(y)), outside the fused image, draws \(got), not the image's CLUT colour")
                }
                let got = [Double(picture[o + 2]), Double(picture[o + 1]), Double(picture[o]), Double(picture[o + 3])]
                let difference = zip(got, expected).map { abs($0 - $1.rounded()) }.max()!
                expect(difference <= 1, "\(label): (\(x), \(y)) draws \(got), the blend is \(expected)")
                if difference == 0 { exact += 1 }
                largest = max(largest, Int(difference)); composed += 1
            } }
        }

        try check("float", try frame(fusion: fused(clut: fusedCLUT(spread))), alpha: spread)
        try check("flipped", try frame(fusion: fused(clut: fusedCLUT(spread), flipped: true)), alpha: spread, flipped: true)
        let curveData = curve.withUnsafeBufferPointer { Data(buffer: $0) }
        let tabled = try frame(fusion: fused(clut: fusedCLUT(spread), table: curveData))
        expect(tabled.fusion.first?.transfer != nil, "the fused series' opacity table was not taken")
        try check("opacity table", tabled, alpha: spread, table: true)
        try check("alpha 0", try frame(fusion: fused(clut: fusedCLUT { _ in 0 })), alpha: { _ in 0 })
        try check("alpha 255", try frame(fusion: fused(clut: fusedCLUT { _ in 255 })), alpha: { _ in 255 })

        // The fusion factor changes the alpha column only: the image's textures stay.
        let first = try PlanarTextures(try frame(fusion: fused(clut: fusedCLUT(spread))), reusing: nil, device: device)
        let moved = try PlanarTextures(try frame(fusion: fused(clut: fusedCLUT { UInt8(($0 * 3) % 256) })), reusing: first, device: device)
        expect(moved.image === first.image && moved.clut === first.clut, "moving the fusion factor uploaded the image again")
        expect(moved.fused!.clut !== first.fused!.clut, "moving the fusion factor did not upload the fused table")
        let windowed = try PlanarTextures(try frame(fusion: fused(clut: fusedCLUT { UInt8(($0 * 3) % 256) }), level: 250), reusing: moved, device: device)
        expect(windowed.fused!.image === moved.fused!.image && windowed.fused!.clut === moved.fused!.clut,
               "changing the image's window uploaded the fused series again")
        let alone = try PlanarTextures(try frame(fusion: nil), reusing: windowed, device: device)
        expect(alone.fused == nil, "the textures kept a fused series the frame no longer has")

        // Not drawn here: a colour fused series, or one fused over again.
        let colour = fused(clut: fusedCLUT(spread)).mutableCopy() as! NSMutableDictionary
        colour["isColor"] = true
        colour["pixels"] = Data(count: fw * fh * 4)
        expect((try? frame(fusion: colour)) == nil, "a colour fused series was accepted")
        let nested = fused(clut: fusedCLUT(spread)).mutableCopy() as! NSMutableDictionary
        nested["fusion"] = fused(clut: fusedCLUT(spread))
        expect((try? frame(fusion: nested)) == nil, "a fused series with a fusion of its own was accepted")

        print("PASS: \(composed) composed pixels (\(blended) under the fused series) at texel centres of both layers, float, flipped and opacity-table fused series and alpha 0 and 255, within one level of the source-alpha blend (\(exact) exact, largest \(largest))\(pilot == nil ? "" : ", the Metal 4 pilot identical"); the fusion factor re-uploads the fused series only and the image's window only the image; colour and nested fused series refused")
    }
}
'''

FRAMEWORKS = ['Foundation', 'AppKit', 'AVFoundation', 'CoreData', 'CoreMedia', 'CoreVideo', 'Accelerate', 'OpenGL',
              'QuartzCore', 'Metal', 'IOSurface', 'WebKit', 'Quartz', 'PDFKit', 'SystemConfiguration']


def objective_c_stubs():
    names = set()
    for obj in linked:
        listing = subprocess.run(['nm', '-u', str(obj)], capture_output=True, text=True, check=True).stdout
        names |= {m.group(1) for m in re.finditer(r'_OBJC_CLASS_\$_(\w+)', listing)}
    defined = set()
    for obj in linked:
        listing = subprocess.run(['nm', '-gU', str(obj)], capture_output=True, text=True, check=True).stdout
        defined |= {m.group(1) for m in re.finditer(r'_OBJC_CLASS_\$_(\w+)', listing)}
    sources = root / 'Horos/Sources'
    declared = sorted(n for n in names - defined
                      if n.startswith('Horos') or (sources / (n + '.h')).is_file() or (sources / (n + '.m')).is_file()
                      or (sources / (n + '.mm')).is_file())
    return ''.join('@interface %s : NSObject @end\n@implementation %s @end\n' % (n, n) for n in declared)


def link(directory, placeholders):
    assembly = ''.join('.globl %s\n%s: .quad 0\n' % (s, s) for s in sorted(placeholders))
    (directory / 'placeholders.s').write_text('.data\n' + assembly)
    command = ['xcrun', 'clang++', '-std=c++14', '-Wno-deprecated-declarations', '-w', '-I' + str(root / 'Horos/Sources'),
               str(directory / 'probe.mm'), str(directory / 'stubs.mm'), str(directory / 'placeholders.s'),
               *[str(o) for o in linked], '-Wl,-undefined,dynamic_lookup', '-o', str(directory / 'probe')]
    for framework in FRAMEWORKS:
        command += ['-framework', framework]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode:
        sys.stderr.write(result.stderr[-4000:])
        print('FAIL: the mapping probe does not link')
        raise SystemExit(1)


with tempfile.TemporaryDirectory(prefix='horos-planar-fusion-') as name:
    directory = Path(name)
    (directory / 'probe.mm').write_text(PROBE)
    (directory / 'stubs.mm').write_text('#import <Foundation/Foundation.h>\n' + objective_c_stubs())
    placeholders = set()
    for _ in range(300):
        link(directory, placeholders)
        try:
            run = subprocess.run([str(directory / 'probe'), str(random.randrange(1 << 30))],
                                 capture_output=True, text=True, timeout=120)
        except subprocess.TimeoutExpired:
            print('FAIL: the mapping probe did not finish in 120 s')
            raise SystemExit(1)
        missing = re.search(r"symbol not found in flat namespace '([^']+)'", run.stderr)
        if not missing:
            break
        if missing.group(1) in placeholders:
            print('cannot satisfy %s' % missing.group(1), file=sys.stderr)
            raise SystemExit(1)
        placeholders.add(missing.group(1))
    sys.stdout.write(run.stdout)
    sys.stdout.flush()
    if run.returncode:
        sys.stderr.write(run.stderr[-4000:])
        print('FAIL: the fused series\' mapping is not the host\'s conversion in the image\'s frame (exit %d)' % run.returncode)
        raise SystemExit(1)
    counts = re.search(r'compared (\d+) differing 0 identity (\d+)', run.stdout)
    if not counts or counts.group(1) != counts.group(2):
        print('FAIL: the image\'s own mapping is not ConvertFromNSView2GL:')
        raise SystemExit(1)

    sources = ['VolumeAllocation.swift', 'VolumeSession.swift', 'MPRMetalReslicer.swift', 'MetalPerformanceTrace.swift',
               'MetalComputePipelineCache.swift', 'Metal4ComputeSubmitter.swift', 'PlanarMetalRenderer.swift',
               'PlanarMetal4Renderer.swift']
    for source in sources:
        (directory / source).write_text(read('Horos/Sources/' + source))
    (directory / 'Check.swift').write_text(DRIVER)
    build_result = subprocess.run(['xcrun', 'swiftc', '-O', '-parse-as-library', '-suppress-warnings',
                                   *[str(directory / source) for source in sources], str(directory / 'Check.swift'),
                                   '-o', str(directory / 'check')])
    if build_result.returncode:
        print('FAIL: the planar renderer does not build with the fusion driver')
        raise SystemExit(1)
    result = subprocess.run([str(directory / 'check')], timeout=300)
    if result.returncode == 0:
        print('PASS: %s mapped points of a fused view equal to the host\'s ConvertFromUpLeftView2GL: in the image\'s frame, bit for bit' % counts.group(1))
    raise SystemExit(result.returncode)
