#!/usr/bin/env python3
"""#375/A214: an allocation that fails says what was too big, not "upgrade".

A214 asks that limit dimensions either render or produce an explicit diagnosis or
fallback — never a silent black film, and never a forced reduction.

Every allocation guard in front of the 3D engine, the reslicing, the resampling,
the ITK operations and the Path Assistant used to fail with a dialogue titled
**"32-bit"** telling the operator to *upgrade to OsiriX 64-bit or OsiriX MD*, with
a second button that opened a page about a 64-bit build. On this arm64-only,
64-bit-only product (#369, #370) that is false, unactionable, names another
application, and says nothing about what was actually too large.
"""
from pathlib import Path
import re
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
failures = []

source = root / 'Horos/Sources/VolumeAllocation.swift'
if not source.is_file():
    failures.append('Horos/Sources/VolumeAllocation.swift is missing')
else:
    driver = r'''
import Foundation

@main struct Check {
    static func main() {
        typealias A = VolumeAllocation

        precondition(A.byteCount(width: 512, height: 512, slices: 200, bytesPerVoxel: 3) == 157286400)
        precondition(A.byteCount(width: 0, height: 512, slices: 200, bytesPerVoxel: 3) == 0)
        precondition(A.byteCount(width: -1, height: 512, slices: 200, bytesPerVoxel: 3) == 0)
        // A wrapped product would ask for a small buffer, get it, and fail later
        // as a black frame -- the outcome the criterion refuses.
        precondition(A.byteCount(width: Int.max, height: 2, slices: 2, bytesPerVoxel: 2) == Int.max)
        precondition(A.byteCount(width: 1 << 40, height: 1 << 40, slices: 2, bytesPerVoxel: 2) == Int.max)

        precondition(A.describe(byteCount: 0) == "0 bytes")
        precondition(A.describe(byteCount: 512) == "512 bytes")
        precondition(A.describe(byteCount: 157286400) == "150 MB")   // %.0f above 100
        precondition(A.describe(byteCount: 1 << 30) == "1.0 GB")
        precondition(A.describe(byteCount: Int.max).contains("address"))

        precondition(A.describeMatrix(width: 512, height: 512, slices: 200) == "512 × 512 × 200")
        print("rule ok")
    }
}
'''
    with tempfile.TemporaryDirectory(prefix='horos-allocation-') as folder:
        path = Path(folder)
        (path / 'Check.swift').write_text(driver)
        build = subprocess.run(['xcrun', 'swiftc', '-parse-as-library', str(source),
                                str(path / 'Check.swift'), '-o', str(path / 'check')],
                               capture_output=True, text=True)
        if build.returncode:
            failures.append('the helper does not compile: %s' % build.stderr.strip().splitlines()[-3:])
        else:
            run = subprocess.run([str(path / 'check')], capture_output=True, text=True)
            if run.returncode:
                failures.append('the helper does not answer: %s' % run.stderr.strip())

# No host source may still claim this is a 32-bit build, advise another product,
# or offer the download page from a failure.
trees = [root / 'Horos/Sources', root / 'Nitrogen/Sources']
offenders = {'title': [], 'upgrade': [], 'page': []}
for tree in trees:
    for path in sorted(tree.rglob('*')):
        if path.suffix not in {'.m', '.mm', '.h', '.swift'}:
            continue
        text = path.read_bytes().decode('latin1')
        for number, line in enumerate(text.split('\n'), 1):
            where = '%s:%d' % (path.name, number)
            if re.search(r'NSLocalizedString\(\s*@"32-bit"', line):
                offenders['title'].append(where)
            if re.search(r'Upgrade to (OsiriX|Horos) 64-bit', line):
                offenders['upgrade'].append(where)
            if 'osirix64bit:' in line and 'AppController' not in path.name:
                offenders['page'].append(where)

if offenders['title']:
    failures.append('alerts still titled "32-bit": %s' % ', '.join(offenders['title']))
if offenders['upgrade']:
    failures.append('alerts still advise upgrading to a 64-bit build: %s' % ', '.join(offenders['upgrade']))
if offenders['page']:
    failures.append('failures still open the 64-bit download page: %s' % ', '.join(offenders['page']))

# The 3D engine guard is the one that can name the size, and must.
vr = (root / 'Horos/Sources/VRController.mm').read_bytes().decode('latin1')
if 'HorosVolumeAllocation' not in vr:
    failures.append('the 3D engine memory test must ask HorosVolumeAllocation for the size')
if 'describeMatrixWithWidth' not in vr or 'describeByteCount' not in vr:
    failures.append('the 3D engine diagnosis must name the matrix and the size that was refused')
if re.search(r'malloc\(\s*\[firstObject pwidth\]\s*\*', vr):
    failures.append('the 3D engine memory test still multiplies the size itself')

# And nothing may be reduced without saying so: every new message says it.
said = 0
for tree in trees:
    for path in sorted(tree.rglob('*')):
        if path.suffix in {'.m', '.mm'}:
            said += path.read_bytes().decode('latin1').count('Nothing was reduced silently')
if said < 7:
    failures.append('the diagnoses must say that nothing was reduced silently; found %d' % said)

project = (root / 'Horos.xcodeproj/project.pbxproj').read_text()
if 'VolumeAllocation.swift in Sources' not in project:
    failures.append('VolumeAllocation.swift is not compiled into the Horos target')

if failures:
    print('FAIL:')
    for item in failures:
        print(' ', item)
    raise SystemExit(1)

print('PASS: no allocation failure claims a 32-bit build or points at another product, and the 3D '
      'engine names the matrix and the size it could not get')
