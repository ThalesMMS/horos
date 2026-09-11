#!/usr/bin/env python3
"""A path that cannot be used is refused before it reaches the scanner.

Every crash report gathered under this heading ends in `strlen` inside
`+[DicomFile isDICOMFile:compressed:image:]`. The method built its argument like
this:

    filenames.push_back( std::string([filePath UTF8String]) );

`-UTF8String` returns NULL for a nil path, and for a name holding characters it
cannot encode. `std::string(NULL)` reads until it finds a zero byte - that is the
strlen - and the `try { } catch (...)` around it cannot catch a segmentation
fault.

Nothing that is not a usable path can be a DICOM file, so the method now says so
and returns.
"""
from pathlib import Path
import re
import sys

root = Path(__file__).resolve().parents[1]
failures = []
source = (root / 'Horos/Sources/DicomFile.mm').read_bytes().decode('latin1')

at = source.find('+ (BOOL) isDICOMFile:(NSString *) filePath compressed:(BOOL*) compressed image:(BOOL*) image')
if at < 0:
    failures.append('the method the crash reports name is gone')
else:
    opening = source.index('{', at)
    depth, index, body = 0, opening, ''
    while index < len(source):
        if source[index] == '{':
            depth += 1
        elif source[index] == '}':
            depth -= 1
            if depth == 0:
                body = source[opening:index + 1]
                break
        index += 1

    guard = body.find('UTF8String')
    scanner = body.find('gdcm::Scanner')
    if guard < 0:
        failures.append('the path is no longer converted, so this test is looking at the wrong thing')
    elif scanner >= 0 and guard > scanner:
        failures.append('the path is converted after the scanner is set up, so a nil path still '
                        'reaches it')
    if not re.search(r'if\s*\(\s*filePathC == NULL \|\| \*filePathC == 0\s*\)', body):
        failures.append('nothing checks the converted path for NULL or emptiness')
    if 'return NO' not in body[:body.find('gdcm::Scanner') if 'gdcm::Scanner' in body else len(body)]:
        failures.append('an unusable path is not refused before the scanner')
    # And neither scan may build its string from the unchecked expression again.
    if 'std::string([filePath UTF8String])' in body:
        failures.append('a scan still builds its filename from the unchecked conversion')
    if body.count('std::string( filePathC)') != 2:
        failures.append('the two scans do not both use the checked pointer')
    # A path that is not nil but cannot be encoded is worth a line: it means a
    # file exists that this cannot look at.
    window = body[:body.find('gdcm::Scanner')] if 'gdcm::Scanner' in body else body
    if 'NSLog' not in window:
        failures.append('a path that exists but cannot be used is refused silently')

for failure in failures:
    print('FAIL: %s' % failure)
if failures:
    sys.exit(1)
print('ok: a nil or unencodable path is refused before the GDCM scanner is given it, and both '
      'scans use the checked pointer')
