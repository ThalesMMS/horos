#!/usr/bin/env python3
"""Fused PET/CT orthogonal-MPR export has distinct pixels and geometry per slice.

The series path used to capture GL_FRONT after NSDisableScreenUpdates, so every
frame of a fusion export was the first image. Isolated CT/PET walk the buffer
in memory and therefore already change. A production change that went back to
that screen capture, mixed two slices into one digest, or copied the first
Image Position onto the rest would fail here.

The arithmetic is the fixture in tools/generate-fusion-window-fixture.py: a
registered 32×32 CT/PT pair whose value at (x, y, z) is x+2y+3z and
500+3x+y+5z. Windowing is the fixture WL/WW. Alignment is checked by sampling a
PET volume that is shifted four millimetres along X: the overlay at a CT pixel
is the PET sample whose patient coordinate matches, not the PET sample with
the same index.
"""
from pathlib import Path
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
failures = []

source = (root / 'Horos/Sources/OrthogonalMPRPETCTViewer.m').read_bytes().decode('latin1')
export_at = source.find('- (NSDictionary*) exportDICOMFileInt :(BOOL) screenCapture view:(DCMView*) curView')
end_at = source.find('-(IBAction) endExportDICOMFileSettings:', export_at)
export_body = source[export_at:end_at] if export_at >= 0 else ''
if not export_body:
    failures.append('PET/CT orthogonal export of a named view is gone')
else:
    for wanted, why in (
        ('HorosOrthogonalFusionSliceExport', 'fusion series still goes through the OpenGL front buffer'),
        ('sliceFromPrimary:', 'nothing builds a fused frame from the two layers in memory'),
        ('blendingView', 'the fusion path does not look at the PET overlay'),
        ('pixelRGB', 'the fused RGB is never given to the DICOM writer'),
        ('setPosition:', 'Image Position (Patient) is not taken from the fused slice'),
        ('setSlicePosition:', 'Slice Location is not taken from the fused slice'),
        ('setOrientation:', 'Image Orientation (Patient) is not taken from the fused slice'),
    ):
        if wanted not in export_body:
            failures.append('%s (%s missing)' % (why, wanted))
    start = export_body.find('blendingView')
    helper = export_body.find('HorosOrthogonalFusionSliceExport', start)
    raw = export_body.find('getRawPixelsWidth:', start)
    if helper < 0:
        failures.append('the blending branch never calls the fusion helper')
    elif 0 <= raw < helper:
        failures.append('the blending branch still captures pixels before the fusion helper runs')

series_at = source.find('-(IBAction) endExportDICOMFileSettings:')
if series_at < 0:
    failures.append('the PET/CT series export action is gone')
else:
    series = source[series_at:source.find('- (void) exportDICOMFile:', series_at)]
    if 'exportDICOMFileInt: NO' not in series and 'exportDICOMFileInt:NO' not in series:
        failures.append('series export still forces screen capture of every frame')

writer = (root / 'Horos/Sources/DICOMExport.mm').read_bytes().decode('latin1')
pos_block = writer[writer.find('delete dataset->remove( DCM_ImagePositionPatient'):writer.find('delete dataset->remove( DCM_SliceLocation')]
if 'positionSet' not in writer or 'position[ 0] != 0' in pos_block:
    failures.append('Image Position (Patient) is omitted when the fused origin is at 0,0,0')

for failure in failures:
    print('FAIL: %s' % failure)

main = r'''import Foundation
import CryptoKit

func floats(_ values: [Float]) -> Data {
    values.withUnsafeBufferPointer { Data(buffer: $0) }
}
func numbers(_ values: [Double]) -> [NSNumber] { values.map { NSNumber(value: $0) } }
func grayLUT() -> Data {
    var bytes = [UInt8](repeating: 0, count: 768)
    for i in 0..<256 {
        bytes[i * 3] = UInt8(i)
        bytes[i * 3 + 1] = UInt8(i)
        bytes[i * 3 + 2] = UInt8(i)
    }
    return Data(bytes)
}
func layer(width: Int, height: Int, origin: [Double], orientation: [Double],
            spacing: [Double], location: Double, thickness: Double,
            windowCenter: Double, windowWidth: Double, samples: [Float]) -> OrthogonalFusionLayer {
    let layer = OrthogonalFusionLayer()
    layer.samples = floats(samples)
    layer.width = width
    layer.height = height
    layer.origin = numbers(origin)
    layer.orientation = numbers(orientation)
    layer.spacing = numbers(spacing)
    layer.sliceLocation = location
    layer.sliceThickness = thickness
    layer.windowCenter = windowCenter
    layer.windowWidth = windowWidth
    return layer
}
func ctValue(x: Int, y: Int, z: Int) -> Float { Float(x + 2 * y + 3 * z) }
func ptValue(x: Int, y: Int, z: Int) -> Float { Float(500 + 3 * x + y + 5 * z) }
func plane(width: Int, height: Int, z: Int, pet: Bool) -> [Float] {
    (0..<height).flatMap { y in (0..<width).map { x in pet ? ptValue(x: x, y: y, z: z) : ctValue(x: x, y: y, z: z) } }
}

let axial = [1.0, 0, 0, 0, 1, 0, 0, 0, 1]
let spacing = [1.0, 1.0]
let lut = grayLUT()

precondition(OrthogonalFusionSliceExport.windowedByte(value: 40, windowCenter: 100, windowWidth: 0) == 0)
precondition(OrthogonalFusionSliceExport.windowedByte(value: 0, windowCenter: 100, windowWidth: 200) == 0)
let mid = OrthogonalFusionSliceExport.windowedByte(value: 100, windowCenter: 100, windowWidth: 200)
precondition(mid == 128 || mid == 127)
precondition(OrthogonalFusionSliceExport.windowedByte(value: 200, windowCenter: 100, windowWidth: 200) == 255)
precondition(OrthogonalFusionSliceExport.windowedByte(value: -50, windowCenter: 100, windowWidth: 200) == 0)
precondition(OrthogonalFusionSliceExport.windowedByte(value: 400, windowCenter: 100, windowWidth: 200) == 255)

func ints(_ values: [NSNumber]) -> [Int] { values.map { $0.intValue } }
precondition(ints(OrthogonalFusionSliceExport.sliceIndices(from: 0, to: 4, interval: 1)) == [0, 1, 2, 3])
precondition(ints(OrthogonalFusionSliceExport.sliceIndices(from: 3, to: 0, interval: 1)) == [0, 1, 2])
precondition(ints(OrthogonalFusionSliceExport.sliceIndices(from: 0, to: 6, interval: 2)) == [0, 2, 4])
precondition(ints(OrthogonalFusionSliceExport.sliceIndices(from: 0, to: 3, interval: 0)) == [0, 1, 2])
precondition(ints(OrthogonalFusionSliceExport.sliceIndices(from: 0, to: 0, interval: 1)).isEmpty)

var digests: [String] = []
var origins: [[Double]] = []
var locations: [Double] = []
for (instance, z) in ints(OrthogonalFusionSliceExport.sliceIndices(from: 0, to: 4, interval: 1)).enumerated() {
    let primary = layer(width: 32, height: 32, origin: [10, 20, Double(z)], orientation: axial,
                         spacing: spacing, location: Double(z), thickness: 1,
                         windowCenter: 100, windowWidth: 200, samples: plane(width: 32, height: 32, z: z, pet: false))
    let secondary = layer(width: 32, height: 32, origin: [10, 20, Double(z)], orientation: axial,
                           spacing: spacing, location: Double(z), thickness: 1,
                           windowCenter: 600, windowWidth: 400, samples: plane(width: 32, height: 32, z: z, pet: true))
    guard let frame = OrthogonalFusionSliceExport.slice(fromPrimary: primary, secondary: secondary,
                                                          lut: lut, blendingFactor: 0, instanceNumber: instance + 1)
    else { preconditionFailure("slice \(z)") }
    precondition(frame.width == 32 && frame.height == 32)
    precondition(frame.pixelRGB.count == 32 * 32 * 3)
    precondition(frame.instanceNumber == instance + 1)
    precondition(abs(frame.sliceThickness - 1) < 1e-9)
    precondition(frame.orientation.map { $0.doubleValue } == axial)
    precondition(frame.spacing.map { $0.doubleValue } == spacing)
    digests.append(frame.digest)
    origins.append(frame.origin.map { $0.doubleValue })
    locations.append(frame.sliceLocation)
    let hashed = SHA256.hash(data: frame.pixelRGB).map { String(format: "%02x", $0) }.joined()
    precondition(frame.digest == hashed, "digest is not SHA-256 of the RGB")
}

precondition(Set(digests).count == 4, "fused frames share pixels: \(digests)")
precondition(Set(origins.map { $0[2] }).count == 4, "fused frames share Image Position Z")
precondition(locations == [0, 1, 2, 3], "Slice Location \(locations)")
precondition(origins.map { $0[0] } == [10, 10, 10, 10])
precondition(origins.map { $0[1] } == [20, 20, 20, 20])
precondition(origins.map { $0[2] } == [0, 1, 2, 3])

let again = OrthogonalFusionSliceExport.slice(
    fromPrimary: layer(width: 32, height: 32, origin: [10, 20, 1], orientation: axial,
                       spacing: spacing, location: 1, thickness: 1,
                       windowCenter: 100, windowWidth: 200, samples: plane(width: 32, height: 32, z: 1, pet: false)),
    secondary: layer(width: 32, height: 32, origin: [10, 20, 1], orientation: axial,
                     spacing: spacing, location: 1, thickness: 1,
                     windowCenter: 600, windowWidth: 400, samples: plane(width: 32, height: 32, z: 1, pet: true)),
    lut: lut, blendingFactor: 0, instanceNumber: 2)!
precondition(again.digest == digests[1])

let first = OrthogonalFusionSliceExport.slice(
    fromPrimary: layer(width: 32, height: 32, origin: [10, 20, 0], orientation: axial,
                       spacing: spacing, location: 0, thickness: 1,
                       windowCenter: 100, windowWidth: 200, samples: plane(width: 32, height: 32, z: 0, pet: false)),
    secondary: layer(width: 32, height: 32, origin: [10, 20, 0], orientation: axial,
                     spacing: spacing, location: 0, thickness: 1,
                     windowCenter: 600, windowWidth: 400, samples: plane(width: 32, height: 32, z: 0, pet: true)),
    lut: lut, blendingFactor: 0, instanceNumber: 1)!
let ct00 = OrthogonalFusionSliceExport.windowedByte(value: Double(ctValue(x: 0, y: 0, z: 0)),
                                                     windowCenter: 100, windowWidth: 200)
let pt00 = OrthogonalFusionSliceExport.windowedByte(value: Double(ptValue(x: 0, y: 0, z: 0)),
                                                     windowCenter: 600, windowWidth: 400)
let mixed = Int((Double(ct00) + Double(pt00)) / 2)
let firstRGB = [UInt8](first.pixelRGB)
precondition(abs(Int(firstRGB[0]) - mixed) <= 1, "linear fusion R \(firstRGB[0]) against \(mixed)")
precondition(firstRGB[0] == firstRGB[1] && firstRGB[1] == firstRGB[2], "identity LUT keeps gray")

let shifted = OrthogonalFusionSliceExport.slice(
    fromPrimary: layer(width: 32, height: 32, origin: [10, 20, 0], orientation: axial,
                       spacing: spacing, location: 0, thickness: 1,
                       windowCenter: 100, windowWidth: 200, samples: plane(width: 32, height: 32, z: 0, pet: false)),
    secondary: layer(width: 32, height: 32, origin: [14, 20, 0], orientation: axial,
                     spacing: spacing, location: 0, thickness: 1,
                     windowCenter: 600, windowWidth: 400, samples: plane(width: 32, height: 32, z: 0, pet: true)),
    lut: lut, blendingFactor: 0, instanceNumber: 1)!
let shiftedRGB = [UInt8](shifted.pixelRGB)
let emptyMix = Int(Double(ct00) / 2)
precondition(abs(Int(shiftedRGB[0]) - emptyMix) <= 1, "unaligned left edge mixes empty PET, got \(shiftedRGB[0])")
let alignedMix = Int((Double(OrthogonalFusionSliceExport.windowedByte(value: Double(ctValue(x: 4, y: 0, z: 0)),
                                                                     windowCenter: 100, windowWidth: 200))
                       + Double(pt00)) / 2)
precondition(abs(Int(shiftedRGB[4 * 3]) - alignedMix) <= 1,
             "shifted PET at column 4: \(shiftedRGB[4 * 3]) against \(alignedMix)")
precondition(shifted.digest != first.digest, "a spatial shift must change the fused pixels")

var smallPET = [Float](repeating: 0, count: 16 * 16)
for y in 0..<16 {
    for x in 0..<16 { smallPET[y * 16 + x] = ptValue(x: x * 2, y: y * 2, z: 0) }
}
let resampled = OrthogonalFusionSliceExport.slice(
    fromPrimary: layer(width: 32, height: 32, origin: [10, 20, 0], orientation: axial,
                       spacing: spacing, location: 0, thickness: 1,
                       windowCenter: 100, windowWidth: 200, samples: plane(width: 32, height: 32, z: 0, pet: false)),
    secondary: layer(width: 16, height: 16, origin: [10, 20, 0], orientation: axial,
                     spacing: [2, 2], location: 0, thickness: 1,
                     windowCenter: 600, windowWidth: 400, samples: smallPET),
    lut: lut, blendingFactor: 0, instanceNumber: 1)!
precondition(resampled.width == 32 && resampled.pixelRGB.count == 32 * 32 * 3)
precondition(resampled.digest != first.digest)

print("PASS: fused PET/CT frames have distinct SHA-256 pixels and Image Position per slice, with PET sampled in patient space")
'''

with tempfile.TemporaryDirectory(prefix='horos-fusion-export-') as tmp:
    p = Path(tmp)
    (p / 'main.swift').write_text(main)
    swift = root / 'Horos/Sources/OrthogonalFusionSliceExport.swift'
    if not swift.is_file():
        print('FAIL: the fusion export helper is missing')
        raise SystemExit(1)
    compile = subprocess.run(
        ['xcrun', 'swiftc', '-swift-version', '5',
         str(swift), str(p / 'main.swift'), '-framework', 'Foundation',
         '-framework', 'CryptoKit', '-o', str(p / 'test')],
        cwd=p, capture_output=True, text=True)
    if compile.returncode != 0:
        sys.stderr.write(compile.stdout + compile.stderr)
        print('FAIL: fusion export helper did not compile')
        raise SystemExit(1)
    run = subprocess.run([str(p / 'test')], capture_output=True, text=True)
    sys.stdout.write(run.stdout)
    sys.stderr.write(run.stderr)
    if run.returncode != 0:
        raise SystemExit(run.returncode)

if failures:
    raise SystemExit(1)
