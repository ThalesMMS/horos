#!/usr/bin/env python3
"""#374/A225: the Y reslice cache is read the way it was written.

A225 asks that an isotropic ramp phantom not gain hatching when navigated
repeatedly or reoriented, and that strides, initialisation and cache be audited
before a cause is assigned.

The audit found one. The Y reslice keeps a **transposed** copy of every source
image, so a column of the source — a row of the resliced image — is contiguous:
the filling operation lays down `height` consecutive values for each of the
`width` columns. That layout was then written out again at each of the two
places that read it back, and one of them multiplied by the wrong side:

    srcP = Ycache + y*newTotal*newX + i * w;         // height: right
    srcP = Ycache + y*newTotal*newX + i * newTotal;  // width: wrong

On a square image the two are identical and nothing shows, which is why a
512 × 512 series never revealed it. On any other, the second walks the cache at
the wrong stride — hatching — and for a column near the end it reads past the
slice, and past the buffer on the last one.

`HorosResliceCacheLayout` states the layout once. This checks it, and checks that
all three sites ask.
"""
from pathlib import Path
import re
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
failures = []

source = root / 'Horos/Sources/ResliceCacheLayout.swift'
if not source.is_file():
    failures.append('Horos/Sources/ResliceCacheLayout.swift is missing')
else:
    driver = r'''
import Foundation

@main struct Check {
    static func main() {
        typealias L = ResliceCacheLayout

        // Every voxel of a non-square volume has its own place, and they fill
        // the cache exactly. A wrong stride collides or overruns; this would
        // catch either.
        for (width, height, slices) in [(7, 5, 3), (5, 7, 3), (512, 384, 2), (1, 9, 4), (9, 1, 4)] {
            let total = L.elementCount(width: width, height: height, slices: slices)
            precondition(total == width * height * slices)
            var seen = Set<Int>()
            for slice in 0..<slices {
                for column in 0..<width {
                    precondition(L.columnFits(slice: slice, column: column,
                                              width: width, height: height, slices: slices))
                    for row in 0..<height {
                        let at = L.offset(slice: slice, column: column, row: row,
                                          width: width, height: height)
                        precondition(at >= 0 && at < total)
                        precondition(seen.insert(at).inserted, "collision at \(at)")
                    }
                }
            }
            precondition(seen.count == total)
        }

        // Columns are height apart. The stride that was wrong used width, which
        // is the same number only on a square image -- which is why this went
        // unseen.
        precondition(L.columnOffset(column: 3, height: 5) == 15)
        precondition(L.columnOffset(column: 3, height: 5) != 3 * 7)
        precondition(L.columnOffset(column: 3, height: 9) == 3 * 9)

        // And the wrong stride really does leave the buffer on a wide image:
        // the last column of a 512 x 384 slice would start at 511*512 = 261632
        // and read 384 past it, against a slice of 196608.
        let wide = L.elementCount(width: 512, height: 384, slices: 1)
        precondition(511 * 512 + 384 > wide)
        precondition(L.offset(slice: 0, column: 511, row: 383, width: 512, height: 384) < wide)

        // A degenerate size answers zero rather than a negative allocation.
        precondition(L.elementCount(width: 0, height: 5, slices: 3) == 0)
        precondition(L.elementCount(width: 5, height: 5, slices: 0) == 0)
        precondition(!L.columnFits(slice: 0, column: 5, width: 5, height: 5, slices: 1))
        precondition(!L.columnFits(slice: 0, column: -1, width: 5, height: 5, slices: 1))
        print("layout ok")
    }
}
'''
    with tempfile.TemporaryDirectory(prefix='horos-reslice-layout-') as folder:
        path = Path(folder)
        (path / 'Check.swift').write_text(driver)
        build = subprocess.run(['xcrun', 'swiftc', '-parse-as-library', str(source),
                                str(path / 'Check.swift'), '-o', str(path / 'check')],
                               capture_output=True, text=True)
        if build.returncode:
            failures.append('the layout does not compile: %s' % build.stderr.strip().splitlines()[-3:])
        else:
            run = subprocess.run([str(path / 'check')], capture_output=True, text=True)
            if run.returncode:
                failures.append('the layout does not hold: %s' % run.stderr.strip())

reslice = (root / 'Horos/Sources/OrthogonalReslice.m').read_bytes().decode('latin1')

if 'HorosResliceCacheLayout' not in reslice:
    failures.append('OrthogonalReslice.m must ask HorosResliceCacheLayout for the cache layout')
# The fill, the two reads and the allocation: four sites.
if reslice.count('HorosResliceCacheLayout') < 5:
    failures.append('every site that indexes or sizes the cache must ask the layout: fill, both '
                    'reads and the allocation')
# The formulas must not come back.
if re.search(r'Ycache\s*\+\s*\w+\s*\*\s*\w+\s*\*\s*\w+', reslice):
    failures.append('the slice base is computed again instead of asked for')
if re.search(r'i\s*\*\s*newTotal', reslice):
    failures.append('a column offset is multiplied by the width again; that is the defect')
if re.search(r'malloc\(\s*newTotal\s*\*\s*newY\s*\*\s*newX', reslice):
    failures.append('the allocation computes the size itself')
# Both reads must still be there: the fix is one stride, not one branch removed.
if reslice.count('columnOffsetForColumn') != 2:
    failures.append('both cached read branches must ask for the column offset')
if reslice.count('memcpy') < 4:
    failures.append('the reslice no longer copies rows; this is not the same method')

project = (root / 'Horos.xcodeproj/project.pbxproj').read_text()
if 'ResliceCacheLayout.swift in Sources' not in project:
    failures.append('ResliceCacheLayout.swift is not compiled into the Horos target')

if failures:
    print('FAIL:')
    for item in failures:
        print(' ', item)
    raise SystemExit(1)

print('PASS: the Y reslice cache is transposed, columns are height apart, and the fill, both reads '
      'and the allocation all ask the same layout')
