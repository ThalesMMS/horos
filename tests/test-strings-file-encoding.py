#!/usr/bin/env python3
"""Every .strings file has to decode with the encoding the project declares.

`builtin-copyStrings` is told the encoding from the project's `fileEncoding`,
and it does not guess. For UTF-16 (`fileEncoding = 10`) Foundation reads a
byte-order mark, and without one it falls back to big-endian, so a UTF-16LE
file that lost its mark stops decoding and the whole target fails to build:

    en.lproj/Localizable.strings:1:1: error: could not decode input file
    using specified encoding: Unicode (UTF-16)

That is easy to reintroduce, because a script that rewrites the catalogue
produces a file that every editor and `python3` still read correctly.
"""
from pathlib import Path
import re
import sys

root = Path(__file__).resolve().parents[1]
failures = []

ENCODINGS = {'4': 'utf-8', '10': 'utf-16', '30': 'utf-8'}  # NSUTF8 / NSUTF16 / NSMacOSRoman-era ids in use here

project = (root / 'Horos.xcodeproj/project.pbxproj').read_text(encoding='utf-8', errors='replace')
references = re.findall(
    r'isa = PBXFileReference;[^}]*?fileEncoding = (\d+);[^}]*?'
    r'lastKnownFileType = text\.plist\.strings;[^}]*?path = ("?)([^";]+)\2;',
    project)

if not references:
    failures.append('no .strings file reference with an explicit fileEncoding was found')

checked = 0
for encoding_id, _quote, path in references:
    matches = sorted(root.glob('**/' + path))
    matches = [m for m in matches if 'build/' not in str(m.relative_to(root))]
    if not matches:
        failures.append('%s is declared in the project but missing from the checkout' % path)
        continue
    for source in matches:
        checked += 1
        data = source.read_bytes()
        relative = source.relative_to(root)
        if encoding_id == '10':
            if data[:2] not in (b'\xff\xfe', b'\xfe\xff'):
                failures.append('%s is declared UTF-16 but has no byte-order mark, so '
                                'builtin-copyStrings reads it as big-endian and fails' % relative)
                continue
            try:
                data.decode('utf-16')
            except UnicodeDecodeError as exc:
                failures.append('%s does not decode as UTF-16: %s' % (relative, exc))
        else:
            codec = ENCODINGS.get(encoding_id)
            if codec is None:
                failures.append('%s declares fileEncoding %s, which this check does not know'
                                % (relative, encoding_id))
                continue
            try:
                data.decode(codec)
            except UnicodeDecodeError as exc:
                failures.append('%s does not decode as %s: %s' % (relative, codec, exc))

# The other catalogues carry no declared encoding, so Xcode sniffs them; they
# still have to be readable as one of the two encodings it can sniff.
for source in sorted((root / 'Horos/Resources').glob('*.lproj/Localizable.strings')):
    data = source.read_bytes()
    relative = source.relative_to(root)
    if data[:2] in (b'\xff\xfe', b'\xfe\xff'):
        try:
            data.decode('utf-16')
        except UnicodeDecodeError as exc:
            failures.append('%s starts with a UTF-16 mark but does not decode: %s' % (relative, exc))
    else:
        try:
            data.decode('utf-8')
        except UnicodeDecodeError as exc:
            failures.append('%s has no byte-order mark and is not UTF-8: %s' % (relative, exc))

if checked == 0:
    failures.append('no declared .strings file was actually checked')

if failures:
    for item in failures:
        print('FAIL:', item, file=sys.stderr)
    sys.exit(1)
print('PASS: %d declared .strings file(s) decode with the declared encoding' % checked)
