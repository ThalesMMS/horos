#!/usr/bin/env python3
"""A cropped image is the rectangle asked for, and says where that rectangle is.

Cutting a rectangle out of a DICOM image and leaving Image Position (Patient)
alone puts the crop where the whole image was, so every measurement, reformat and
fusion against it is out by the offset of the corner. The position of the new
first pixel is the old position plus the two in-plane directions, each travelled
by the number of pixels dropped times the spacing along that direction.

The two names are easy to swap and the result still looks plausible, so they are
stated here as well as in the code: Image Orientation (Patient) gives the
direction of increasing column index first and of increasing row index second,
while Pixel Spacing gives the distance between rows first and between columns
second.

The arithmetic is checked here against an independent calculation. The writer is
only checked for the pieces being present: a text check cannot tell a branch that
runs from one that was disabled, so what the written file actually contains was
measured against the running application and read back with pydicom - see
docs/cropped-series-export.md.
"""
from pathlib import Path
import re
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
failures = []

writer = (root / 'Horos/Sources/DicomFileDCMTKCategory.mm').read_bytes().decode('latin1')
at = writer.find('+ (BOOL) writeCropOfFile:')
body = writer[at:writer.find('#endif  // HOROS_KEYWORD_SPELLINGS', at)] if at >= 0 else ''
if not body:
    failures.append('the crop writer is gone')
else:
    for wanted, why in (
        ('HorosCroppedImageGeometry positionForPosition:', 'nothing works out where the crop sits'),
        ('putAndInsertString( DCM_ImagePositionPatient', 'the crop keeps the position of the whole image'),
        ('DCM_Rows, cropHeight', 'Rows is not set to the rectangle'),
        ('DCM_Columns, cropWidth', 'Columns is not set to the rectangle'),
        ('dcmGenerateUniqueIdentifier', 'the derived instance keeps the identity of the original'),
        ('DCM_SourceImageSequence', 'nothing says which image this came from'),
        ('DERIVED', 'the derived instance is not marked as one'),
        ('isEncapsulated', 'compressed pixel data would be cut up as though it were pixels'),
    ):
        if wanted not in body:
            failures.append('%s (%s missing)' % (why, wanted))
    # It writes somewhere else, and the source is only ever read.
    if 'saveFile( [destination' not in body:
        failures.append('the writer does not save to the destination it was given')
    if re.search(r'saveFile\(\s*\[source', body):
        failures.append('the writer saves over the source')

for failure in failures:
    print('FAIL: %s' % failure)
reported = len(failures)

main = r'''import Foundation

func numbers(_ values: [Double]) -> [NSNumber] { values.map { NSNumber(value: $0) } }
func close(_ a: [NSNumber]?, _ b: [Double], _ what: String) {
    guard let a = a, a.count == b.count else { preconditionFailure("\(what): \(String(describing: a))") }
    for (x, y) in zip(a.map { $0.doubleValue }, b) {
        precondition(abs(x - y) < 1e-9, "\(what): \(a.map { $0.doubleValue }) against \(b)")
    }
}

// An axial image at the usual corner, 1 mm pixels: the crop moves by the pixels
// dropped, in millimetres.
let axial = numbers([-128, -128, 73])
let identity = numbers([1, 0, 0, 0, 1, 0])
let oneMillimetre = numbers([1, 1])
close(CroppedImageGeometry.position(position: axial, orientation: identity,
                                    spacing: oneMillimetre, column: 40, row: 30),
      [-88, -98, 73], "1 mm pixels")
close(CroppedImageGeometry.position(position: axial, orientation: identity,
                                    spacing: oneMillimetre, column: 0, row: 0),
      [-128, -128, 73], "no crop is no move")

// Spacing is between rows first, between columns second - so an image with
// different spacings moves differently along each axis, and swapping the two
// gives a different answer. This is the case that catches the swap.
let apart = numbers([0.5, 2.0])          // 0.5 mm between rows, 2 mm between columns
close(CroppedImageGeometry.position(position: axial, orientation: identity,
                                    spacing: apart, column: 10, row: 10),
      [-128 + 10 * 2.0, -128 + 10 * 0.5, 73], "spacing is rows first")

// Orientation is the column direction first. A sagittal image moves along Y and Z.
let sagittal = numbers([0, 1, 0, 0, 0, -1])
close(CroppedImageGeometry.position(position: numbers([10, -100, 50]), orientation: sagittal,
                                    spacing: numbers([1, 1]), column: 20, row: 5),
      [10, -80, 45], "sagittal")

// Geometry it cannot use is refused rather than guessed at.
precondition(CroppedImageGeometry.position(position: numbers([0, 0]), orientation: identity,
                                           spacing: oneMillimetre, column: 1, row: 1) == nil)
precondition(CroppedImageGeometry.position(position: axial, orientation: numbers([1, 0, 0]),
                                           spacing: oneMillimetre, column: 1, row: 1) == nil)
precondition(CroppedImageGeometry.position(position: axial, orientation: identity,
                                           spacing: numbers([Double.nan, 1]), column: 1, row: 1) == nil)

// A rectangle is brought inside the image rather than reading past its end.
func rect(_ c: Int, _ r: Int, _ w: Int, _ h: Int) -> [Int] {
    CroppedImageGeometry.rectangleInside(columns: 256, rows: 256, column: c, row: r,
                                         width: w, height: h).map { $0.intValue }
}
precondition(rect(40, 30, 100, 80) == [40, 30, 100, 80])
precondition(rect(200, 200, 100, 100) == [200, 200, 56, 56], "\(rect(200, 200, 100, 100))")
precondition(rect(-10, -10, 20, 20) == [0, 0, 10, 10], "\(rect(-10, -10, 20, 20))")
precondition(rect(300, 300, 10, 10) == [256, 256, 0, 0])
precondition(rect(0, 0, 0, 0) == [0, 0, 0, 0])
precondition(rect(10, 10, -5, -5) == [10, 10, 0, 0])

print("PASS: the crop moves by the pixels dropped, and its rectangle stays inside the image")
'''

with tempfile.TemporaryDirectory(prefix='horos-crop-') as tmp:
    p = Path(tmp)
    (p / 'main.swift').write_text(main)
    build = subprocess.run(['swiftc', str(root / 'Horos/Sources/CroppedImageGeometry.swift'),
                            str(p / 'main.swift'), '-o', str(p / 'test')],
                           capture_output=True, text=True)
    if build.returncode:
        print(build.stderr.strip()[-2000:])
        sys.exit('the crop geometry did not compile')
    checks = subprocess.run([str(p / 'test')], capture_output=True, text=True)
    print((checks.stdout + checks.stderr).strip())
    if checks.returncode:
        failures.append('the crop geometry does not put the rectangle where it belongs')

for failure in failures[reported:]:
    print('FAIL: %s' % failure)
if failures:
    sys.exit(1)
print('ok: a crop is the rectangle asked for, at the position that rectangle has')
