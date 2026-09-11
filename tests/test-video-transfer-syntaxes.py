#!/usr/bin/env python3
"""A video instance the viewer cannot decode is still kept, not deleted.

`-[DicomFile isDICOMFile:compressed:image:]` asks GDCM's scanner for the Series
UID, and a file whose transfer syntax GDCM does not know is not a key in that
scan. The importer then calls it "not a DICOM file this database can index" and,
with DELETEFILELISTENER, deletes it. The vendored GDCM's table stopped at
1.2.840.10008.1.2.4.103, so every HEVC instance - and every MPEG-4 AVC instance
at Level 4.2 - that arrived in the incoming folder was destroyed. A file the
viewer cannot draw is not a file it may throw away.

The five syntaxes are in the table now, and the checks below are the ones that
can run without the built library: they read the vendored source. Give
GDCM_INSTALL_DIR to also compile against the library and ask it directly.

Usage: python test-video-transfer-syntaxes.py [GDCM_INSTALL_DIR]
       GDCM_INSTALL_DIR is build/.../GDCM.build/Install, holding include/ and wlib/
"""
from pathlib import Path
import re
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
failures = []

ADDED = [
    ('1.2.840.10008.1.2.4.104', 'MPEG4AVCH264HighProfileLevel4_2For2DVideo'),
    ('1.2.840.10008.1.2.4.105', 'MPEG4AVCH264HighProfileLevel4_2For3DVideo'),
    ('1.2.840.10008.1.2.4.106', 'MPEG4AVCH264StereoHighProfileLevel4_2'),
    ('1.2.840.10008.1.2.4.107', 'HEVCH265MainProfileLevel5_1'),
    ('1.2.840.10008.1.2.4.108', 'HEVCH265Main10ProfileLevel5_1'),
]

header = (root / 'GDCM/Source/DataStructureAndEncodingDefinition/gdcmTransferSyntax.h').read_text()
source = (root / 'GDCM/Source/DataStructureAndEncodingDefinition/gdcmTransferSyntax.cxx').read_text()

# The table is indexed by the enum, so the two have to agree in order as well as
# in content: a string in the wrong place renames somebody else's syntax.
enum = re.search(r'typedef enum \{([^}]*)\} TSType;', header, re.S)
if not enum:
    failures.append('the transfer syntax enum is gone')
else:
    names = [n.strip().rstrip(',').split('=')[0].strip() for n in enum.group(1).split('\n')
             if n.strip() and not n.strip().startswith('//')]
    names = [n for n in names if n and n != 'TS_END']
    strings = re.findall(r'^  "([^"]+)",', source, re.M)
    strings = [s for s in strings if s != 'Unknown Transfer Syntax']
    if len(names) != len(strings):
        failures.append('%d enum entries against %d strings: the table no longer lines up'
                        % (len(names), len(strings)))
    else:
        for uid, name in ADDED:
            if name not in names:
                failures.append('the enum has no %s' % name)
            elif strings[names.index(name)] != uid:
                failures.append('%s is paired with %s, not %s'
                                % (name, strings[names.index(name)], uid))

# Encapsulated, lossy, and not lossless - the same three answers the syntaxes
# beside them already gave.
for predicate, expected in (('IsLossy', True), ('IsLossless', False), ('IsEncapsulated', True)):
    at = source.find('TransferSyntax::%s()' % predicate)
    body = source[at:source.index('\n}', at)] if at >= 0 else ''
    if not body:
        failures.append('%s is gone' % predicate)
        continue
    for uid, name in ADDED:
        if name not in body:
            failures.append('%s does not answer for %s' % (predicate, name))

# And the generator can write both HEVC syntaxes, or there is nothing to import.
generator = (root / 'tools/generate-mpeg4-fixture.py').read_text()
for uid in ('1.2.840.10008.1.2.4.107', '1.2.840.10008.1.2.4.108'):
    if uid not in generator:
        failures.append('tools/generate-mpeg4-fixture.py cannot write %s' % uid)

for failure in failures:
    print('FAIL: %s' % failure)
reported = len(failures)

if len(sys.argv) < 2:
    if failures:
        sys.exit(1)
    print('skipped: give GDCM_INSTALL_DIR to ask the built library itself', file=sys.stderr)
    print('ok: the vendored GDCM names every video transfer syntax the viewer refuses')
    raise SystemExit(2)

install = Path(sys.argv[1]).resolve()
program = r'''
#include "gdcmTransferSyntax.h"
#include <cstdio>
int main() {
  int bad = 0;
  for (int i = 100; i <= 108; i++) {
    char uid[64];
    snprintf(uid, sizeof uid, "1.2.840.10008.1.2.4.%d", i);
    gdcm::TransferSyntax ts = gdcm::TransferSyntax::GetTSType(uid);
    bool ok = ts.IsValid() && ts.IsEncapsulated() && ts.IsLossy() && !ts.IsLossless()
              && ts.IsExplicit();
    printf("%-28s valid=%d encapsulated=%d lossy=%d explicit=%d\n", uid,
           ts.IsValid(), ts.IsValid() && ts.IsEncapsulated(),
           ts.IsValid() && ts.IsLossy(), ts.IsValid() && ts.IsExplicit());
    if (!ok) bad++;
  }
  return bad;
}
'''
with tempfile.TemporaryDirectory(prefix='horos-video-ts-') as tmp:
    p = Path(tmp)
    (p / 'ask.cxx').write_text(program)
    build = subprocess.run(['clang++', '-std=c++17', '-I', str(install / 'include/GDCM'),
                            str(p / 'ask.cxx'), str(install / 'wlib/libGDCM.a'),
                            '-lz', '-lexpat', '-framework', 'CoreFoundation',
                            '-o', str(p / 'ask')], capture_output=True, text=True)
    if build.returncode:
        print(build.stderr.strip()[-1500:])
        sys.exit('the question did not compile against %s' % install)
    answer = subprocess.run([str(p / 'ask')], capture_output=True, text=True)
    print(answer.stdout.strip())
    if answer.returncode:
        failures.append('%d of the nine video syntaxes are still not known to the built library'
                        % answer.returncode)

for failure in failures[reported:]:
    print('FAIL: %s' % failure)
if failures:
    sys.exit(1)
print('ok: the built GDCM knows every video transfer syntax, so none of them is deleted on import')
