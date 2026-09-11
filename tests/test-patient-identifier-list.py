#!/usr/bin/env python3
"""Several patient identifiers in one field become one query each.

People type a list of patient identifiers into the one field, separated by
commas. DICOM has no list: a C-FIND identifier carries one value per key, so the
comma was part of the value and the query asked for a patient whose ID contains
commas - which matches nothing. Measured against a loopback C-FIND SCP holding
four patients:

    PatientID=LOCAL-ISOLATION-01,LOCAL-ISOLATION-03   ->  0 studies
    PatientID=LOCAL-ISOLATION-01                      ->  1 study
    PatientID=LOCAL-ISOLATION-03                      ->  1 study

The splitting is Swift and is compiled and run here; the query that uses it is
checked in source.
"""
from pathlib import Path
import re
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
failures = []
parser = root / 'Horos/Sources/PatientIdentifierList.swift'
controller = (root / 'Horos/Sources/QueryController.mm').read_bytes().decode('latin1')

DRIVER = r'''
import Foundation

func emit(_ key: String, _ value: String) { print(key + "\t" + value) }
func list(_ text: String?) -> String {
    return PatientIdentifierList.identifiers(in: text).joined(separator: "|")
}

emit("comma", list("A,B,C"))
emit("semicolon", list("A;B"))
emit("newline", list("A\nB\r\nC"))
emit("tab", list("A\tB"))
// A space is not a separator: identifiers contain them in some systems, and one
// value is far more common than a list.
emit("space", list("A B"))
emit("spaced", list(" A , B "))
emit("empties", list("A,,B,"))
emit("repeats", list("A,B,A"))
emit("single", list("A"))
emit("none", list(""))
emit("nil", list(nil))
// A wildcard is a single query, not a list.
emit("wildcard", list("AB*"))

emit("severalYes", PatientIdentifierList.namesSeveral("A,B") ? "yes" : "no")
emit("severalNo", PatientIdentifierList.namesSeveral("A") ? "yes" : "no")
emit("severalTrailing", PatientIdentifierList.namesSeveral("A,") ? "yes" : "no")

let many = (1...150).map { "ID\($0)" }.joined(separator: ",")
emit("limit", String(PatientIdentifierList.identifiers(in: many).count))
emit("limitSummary", PatientIdentifierList.summary(forText: many))
emit("repeatSummary", PatientIdentifierList.summary(forText: "A,B,A"))
emit("plainSummary", PatientIdentifierList.summary(forText: "A"))
'''

results = {}
swiftc = subprocess.run(['xcrun', '--sdk', 'macosx', '-f', 'swiftc'], capture_output=True, text=True)
if swiftc.returncode != 0:
    failures.append('no swiftc here: %s' % (swiftc.stderr or '').strip())
else:
    with tempfile.TemporaryDirectory(prefix='horos-identifiers-') as directory:
        # Top-level statements are only allowed in a file called main.swift.
        (Path(directory) / 'main.swift').write_text(DRIVER)
        binary = Path(directory) / 'identifiers'
        built = subprocess.run(['xcrun', '--sdk', 'macosx', 'swiftc', '-o', str(binary),
                                str(parser), str(Path(directory) / 'main.swift')],
                               capture_output=True, text=True)
        if built.returncode != 0:
            failures.append('the parser does not compile:\n%s' % built.stderr[-1500:])
        else:
            run = subprocess.run([str(binary)], capture_output=True, text=True)
            if run.returncode != 0:
                failures.append('the parser driver failed: %s' % run.stderr[-800:])
            for line in run.stdout.splitlines():
                key, _, value = line.partition('\t')
                results[key] = value

if results:
    expected = {
        'comma': 'A|B|C', 'semicolon': 'A|B', 'newline': 'A|B|C', 'tab': 'A|B',
        'space': 'A B', 'spaced': 'A|B', 'empties': 'A|B', 'repeats': 'A|B',
        'single': 'A', 'none': '', 'nil': '', 'wildcard': 'AB*',
        'severalYes': 'yes', 'severalNo': 'no', 'severalTrailing': 'no',
        'limit': '100', 'plainSummary': '1 identifier',
    }
    for key, value in expected.items():
        if results.get(key) != value:
            failures.append('%s is %r, expected %r' % (key, results.get(key), value))
    if 'beyond the limit of 100' not in results.get('limitSummary', ''):
        failures.append('the limit is not reported: %r' % results.get('limitSummary'))
    if 'repeated' not in results.get('repeatSummary', ''):
        failures.append('a repeat is not reported: %r' % results.get('repeatSummary'))

# --- the query -----------------------------------------------------------------
at = controller.find('+ (NSMutableArray*) queryStudiesForFilters:')
if at < 0:
    failures.append('queryStudiesForFilters: is gone')
else:
    body = controller[at:at + 3000]
    for expected, missing in (
            ('HorosPatientIdentifierList namesSeveralIdentifiers:',
             'the field is not tested for being a list'),
            ('HorosPatientIdentifierList identifiersInText:',
             'the list is not split into identifiers'),
            ('QueryController queryStudiesForFilters: one servers:',
             'the identifiers are not queried one at a time'),
            ('mergeStudies: found into: combined',
             'the results of the several queries are not combined'),
            ('isCancelled', 'a list of identifiers cannot be cancelled part way')):
        if expected not in body:
            failures.append(missing)
    # The single-identifier query must be exactly that: one key, one value.
    if 'removeObjectForKey: PatientID' not in body or 'removeObjectForKey: @"patientID"' not in body:
        failures.append('the per-identifier query can carry the whole list as well')

# One merge, used by both the per-server loop and the per-identifier loop, so a
# study found twice is one row either way.
if controller.count('+ (void) mergeStudies:') != 1:
    failures.append('there is not exactly one place that merges duplicate studies')
if controller.count('QueryController mergeStudies:') != 2:
    failures.append('the merge is not shared between the server loop and the identifier loop')

for failure in failures:
    print('FAIL: %s' % failure)
if failures:
    sys.exit(1)
print('ok: a field naming several patient identifiers becomes one query each, combined without '
      'duplicates and interruptible, and one identifier is still one query')
