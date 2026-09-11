#!/usr/bin/env python3
"""A patient with no date of birth is not given one.

`+[DicomFile patientUID:]` built the key a study is matched on from the name, the
identifier and the date of birth. When there was no date of birth it ran

    patientBirthDate = [Horos:[NSDate dateWithTimeIntervalSinceReferenceDate:
        [[src valueForKey:@"patientBirthDate"] timeIntervalSinceReferenceDate]]
        descriptionWithCalendarFormat:@"%Y%m%d"];

on `nil`, and `[nil timeIntervalSinceReferenceDate]` is 0 — so the missing date
became 2001-01-01, and, formatted in local time, **2000-12-31** anywhere west of
UTC. Measured: one study of four instances, two carrying a date of birth and two
not, imported in two batches, became two patients — `DOE JOHN-P66-19800101` and
`DOE JOHN-P66-20001231` — and a machine in another time zone would have produced
a different second key for the same files.
"""
from pathlib import Path
import re
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
failures = []
identity = root / 'Horos/Sources/PatientIdentity.swift'
dicomfile = (root / 'Horos/Sources/DicomFile.mm').read_bytes().decode('latin1')
database = (root / 'Horos/Sources/DicomDatabase.mm').read_bytes().decode('latin1')

DRIVER = '''
import Foundation

func emit(_ key: String, _ value: String) { print("\\(key)\\t\\(value)") }

emit("same", PatientIdentity.difference(betweenUID: "DOE JOHN-P66-19800101",
                                        andUID: "DOE JOHN-P66-19800101"))
emit("birth", PatientIdentity.difference(betweenUID: "DOE JOHN-P66-",
                                         andUID: "DOE JOHN-P66-19800101"))
emit("id", PatientIdentity.difference(betweenUID: "DOE JOHN-P66-19800101",
                                      andUID: "DOE JOHN-P67-19800101"))
emit("name", PatientIdentity.difference(betweenUID: "DOE JOHN-P66-19800101",
                                        andUID: "DOE JANE-P66-19800101"))
// A patient identifier is free to contain the separator; the birth date is the
// last part and the name the first, so the middle is whatever is left.
emit("hyphenated-id", PatientIdentity.difference(betweenUID: "DOE JOHN-A-1-19800101",
                                                 andUID: "DOE JOHN-A-2-19800101"))
emit("carries", PatientIdentity.uidCarriesABirthDate("DOE JOHN-P66-20001231") ? "yes" : "no")
emit("carries-not", PatientIdentity.uidCarriesABirthDate("DOE JOHN-P66-") ? "yes" : "no")
emit("stripped", PatientIdentity.uidWithoutBirthDate("DOE JOHN-P66-20001231"))
emit("stripped-hyphen", PatientIdentity.uidWithoutBirthDate("DOE JOHN-A-1-20001231"))
emit("stripped-twice", PatientIdentity.uidWithoutBirthDate(
        PatientIdentity.uidWithoutBirthDate("DOE JOHN-P66-20001231")))
'''

results = {}
if not identity.exists():
    failures.append('there is no patient identity type')
else:
    swiftc = subprocess.run(['xcrun', '--sdk', 'macosx', '-f', 'swiftc'], capture_output=True, text=True)
    if swiftc.returncode != 0:
        failures.append('no swiftc here: %s' % (swiftc.stderr or '').strip())
    else:
        with tempfile.TemporaryDirectory(prefix='horos-identity-') as directory:
            # Top-level statements are only allowed in a file called main.swift.
            (Path(directory) / 'main.swift').write_text(DRIVER)
            binary = Path(directory) / 'identity'
            built = subprocess.run(['xcrun', '--sdk', 'macosx', 'swiftc', '-o', str(binary),
                                    str(identity), str(Path(directory) / 'main.swift')],
                                   capture_output=True, text=True)
            if built.returncode != 0:
                failures.append('the identity type does not compile:\n%s' % built.stderr[-1500:])
            else:
                run = subprocess.run([str(binary)], capture_output=True, text=True)
                if run.returncode != 0:
                    failures.append('the driver failed: %s' % run.stderr[-800:])
                for line in run.stdout.splitlines():
                    key, _, value = line.partition('\t')
                    results[key] = value

if results:
    expected = {
        'same': 'nothing: the identifiers are the same',
        'birth': 'date of birth (none) versus "19800101"',
        'id': 'patient ID "P66" versus "P67"',
        'name': 'name "DOE JOHN" versus "DOE JANE"',
        'hyphenated-id': 'patient ID "A-1" versus "A-2"',
        'carries': 'yes', 'carries-not': 'no',
        'stripped': 'DOE JOHN-P66-',
        'stripped-hyphen': 'DOE JOHN-A-1-',
        'stripped-twice': 'DOE JOHN-P66-',
    }
    for key, want in expected.items():
        got = results.get(key)
        if got != want:
            failures.append('%s: %r, expected %r' % (key, got, want))

# --- the key itself must not invent a date -----------------------------------
at = dicomfile.find('+ (NSString*) patientUID: (id) src')
window = dicomfile[at:at + 1800] if at >= 0 else ''
if not window:
    failures.append('+[DicomFile patientUID:] is gone')
else:
    if 'isKindOfClass: [NSDate class]' not in window:
        failures.append('a missing date of birth is still turned into a date, so a study splits '
                        'as soon as one instance carries the date and another does not')
    if 'dateWithTimeIntervalSinceReferenceDate' in window and 'if( [birthDate' not in window:
        failures.append('the date is still formatted unconditionally')

# --- the split has to say what differs ---------------------------------------
if 'differenceBetweenUID' not in database:
    failures.append('a study that splits still prints two identifiers side by side and leaves '
                    'the reader to work out which tag produced the difference')

# --- and the invented dates already stored have to go ------------------------
if 'repairFabricatedPatientIdentifiersInContext' not in database:
    failures.append('studies whose stored identifier carries an invented date are left alone, so '
                    'every instance of that patient arriving from now on lands in a third study')
at = database.find('+(void)repairFabricatedPatientIdentifiersInContext:(NSManagedObjectContext*)context {')
window = database[at:at + 1800] if at >= 0 else ''
if window and 'dateOfBirth == nil' not in window:
    failures.append('the repair does not restrict itself to studies that have no date of birth, '
                    'so it would strip real ones')

for failure in failures:
    print('FAIL: %s' % failure)
if failures:
    sys.exit(1)
print('ok: a missing date of birth stays missing, a split says which tag differs, and the '
      'invented dates already stored are taken back out')
