#!/usr/bin/env python3
"""A query naming several UIDs at once keeps them several.

Several values in one attribute, separated by `\\`, is UID List matching
(PS3.4 C.2.2.2.2). The value has to survive everything between the field and the
wire: the trimming the query does, the splitting the patient-identifier field
does, and the dictionary the filters travel in.

Measured against `tools/serve-cfind-fixture.py`, which records the identifier
exactly as it arrives and answers with UID List matching:

    asked 2 UIDs  -> 2 studies
    asked 1 known + 1 unknown -> 1 study
    asked 3 UIDs  -> 3 studies

with the identifier arriving as a two- or three-valued `StudyInstanceUID`, not as
one long string. This pins the parts of that path that a change could break.
"""
from pathlib import Path
import re
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
failures = []
controller = (root / 'Horos/Sources/QueryController.mm').read_bytes().decode('latin1')
array = (root / 'Horos/Sources/QueryArrayController.mm').read_bytes().decode('latin1')
identifiers = root / 'Horos/Sources/PatientIdentifierList.swift'

DRIVER = '''
import Foundation

func emit(_ key: String, _ value: String) { print("\\(key)\\t\\(value)") }

// The patient-identifier field splits a list on its own separators. The DICOM
// one is not among them: a value holding it is one value, and stays one.
let list = PatientIdentifierList.identifiers(in: "1.2.3\\\\4.5.6")
emit("backslash.count", "\\(list.count)")
emit("backslash.first", list.first ?? "")

// The separators it does split on, unchanged.
emit("comma", PatientIdentifierList.identifiers(in: "A,B").joined(separator: "|"))
emit("semicolon", PatientIdentifierList.identifiers(in: "A;B").joined(separator: "|"))
emit("newline", PatientIdentifierList.identifiers(in: "A\\nB").joined(separator: "|"))
// A space is part of a name or an identifier, not a separator.
emit("space", PatientIdentifierList.identifiers(in: "A B").joined(separator: "|"))
'''

results = {}
if not identifiers.exists():
    failures.append('the patient identifier list is gone')
else:
    swiftc = subprocess.run(['xcrun', '--sdk', 'macosx', '-f', 'swiftc'], capture_output=True, text=True)
    if swiftc.returncode != 0:
        failures.append('no swiftc here: %s' % (swiftc.stderr or '').strip())
    else:
        with tempfile.TemporaryDirectory(prefix='horos-uidlist-') as directory:
            # Top-level statements are only allowed in a file called main.swift.
            (Path(directory) / 'main.swift').write_text(DRIVER)
            binary = Path(directory) / 'uidlist'
            built = subprocess.run(['xcrun', '--sdk', 'macosx', 'swiftc', '-o', str(binary),
                                    str(identifiers), str(Path(directory) / 'main.swift')],
                                   capture_output=True, text=True)
            if built.returncode != 0:
                failures.append('the identifier list does not compile:\n%s' % built.stderr[-1500:])
            else:
                run = subprocess.run([str(binary)], capture_output=True, text=True)
                if run.returncode != 0:
                    failures.append('the driver failed: %s' % run.stderr[-800:])
                for line in run.stdout.splitlines():
                    key, _, value = line.partition('\t')
                    results[key] = value

if results:
    expected = {
        'backslash.count': '1', 'backslash.first': '1.2.3\\4.5.6',
        'comma': 'A|B', 'semicolon': 'A|B', 'newline': 'A|B', 'space': 'A B',
    }
    for key, want in expected.items():
        got = results.get(key)
        if got != want:
            failures.append('%s: %r, expected %r' % (key, got, want))

# --- nothing between the field and the wire may split on the DICOM separator --
code = re.sub(r'//[^\n]*', '', controller) + re.sub(r'//[^\n]*', '', array)
if re.search(r'componentsSeparatedByString:\s*@"\\\\\\\\"', code):
    failures.append('something in the query path splits a filter on the DICOM value separator, '
                    'which turns a list of UIDs into separate queries or into nothing')

# --- and the trim must stay a whitespace trim --------------------------------
at = controller.find('+ (NSArray*) queryStudyInstanceUID:(NSString*) an server: (NSDictionary*) aServer showErrors:')
window = controller[at:at + 900] if at >= 0 else ''
if not window:
    failures.append('+queryStudyInstanceUID:server:showErrors: is gone')
else:
    if 'whitespaceAndNewlineCharacterSet' not in window:
        failures.append('the trim applied to a study UID filter is no longer a whitespace trim; '
                        'anything wider would eat the separator')
    if 'addFilter:filterValue forDescription:@"StudyInstanceUID"' not in window:
        failures.append('the value is no longer passed through as one filter')

# --- the filter has to reach the query unchanged -----------------------------
at = array.find('- (void)addFilter:(id)filter forDescription:(NSString *)description')
window = array[at:at + 700] if at >= 0 else ''
if window and 'setObject:filter forKey:description' not in window:
    failures.append('a filter value is transformed on its way into the query dictionary')

for failure in failures:
    print('FAIL: %s' % failure)
if failures:
    sys.exit(1)
print('ok: a filter holding several UIDs separated by the DICOM separator is kept whole on its '
      'way to the query')
