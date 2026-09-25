#!/usr/bin/env python3
"""The Query/Retrieve log does not carry patient names, identifiers or accession numbers.

`NSLog` goes to the unified system log: every process of the user can read it,
and it travels in sysdiagnose reports. The Query/Retrieve code wrote into it the
patient identifier of every entry of a list query, the whole of a `DicomStudy`
(whose description lists its attributes), the patient name typed ahead in the
results, and the description, patient ID and accession number of everything it
auto-retrieved; the C-FIND summary wrote the value of every key it sent, and
the XML-RPC `Retrieve` wrote its whole filter when it found nothing.

The C-FIND summary is worth keeping - it is how one tells a node that ignored an
attribute from a query that never sent it - so its values now go through
`HorosQueryLog`, which writes technical values (modality, dates, UIDs) as they
are and every other value as its shape. That helper is compiled and run here;
the log calls of the Query/Retrieve sources are checked in source.
"""
from pathlib import Path
import re
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
failures = []
helper = root / 'Horos/Sources/QueryLog.swift'
sources = ['XMLRPCMethods.mm', 'QueryController.mm', 'DCMTKQueryNode.mm', 'DCMTKStudyQueryNode.mm',
           'DCMTKSeriesQueryNode.mm', 'DCMTKImageQueryNode.mm', 'DCMTKRootQueryNode.mm']

DRIVER = r'''
import Foundation

func emit(_ key: String, _ value: String) { print(key + "\t" + value) }

emit("name", QueryLog.term(key: "PatientsName", value: "DOE^JOHN"))
emit("nameWildcard", QueryLog.term(key: "PatientsName", value: "DO*"))
emit("id", QueryLog.term(key: "PatientID", value: "1"))
emit("accession", QueryLog.term(key: "AccessionNumber", value: "A123"))
emit("custom", QueryLog.term(key: "InstitutionName", value: "General"))
emit("birth", QueryLog.term(key: "PatientBirthDate", value: Date(timeIntervalSince1970: 0)))
emit("none", QueryLog.term(key: "PatientID", value: nil))
emit("null", QueryLog.term(key: "PatientID", value: NSNull()))
emit("modality", QueryLog.term(key: "ModalitiesinStudy", value: "CT\\MR"))
emit("level", QueryLog.term(key: "QueryRetrieveLevel", value: "STUDY"))
emit("uid", QueryLog.term(key: "StudyInstanceUID", value: "1.2.3"))
emit("date", QueryLog.term(key: "StudyDate", value: "20260101-20260131"))
emit("noKey", QueryLog.describe("DOE", forKey: nil))
emit("retrieve", QueryLog.describeRetrieveParameters([
    "serverName": "PACS", "retrieveMode": "1",
    "filterKey": "PatientID", "filterValue": "ID-1,ID-2",
    "filterKey2": "StudyDate", "filterValue2": "20260101"]))
'''

results = {}
swiftc = subprocess.run(['xcrun', '--sdk', 'macosx', '-f', 'swiftc'], capture_output=True, text=True)
if swiftc.returncode != 0:
    failures.append('no swiftc here: %s' % (swiftc.stderr or '').strip())
else:
    with tempfile.TemporaryDirectory(prefix='horos-query-log-') as directory:
        # Top-level statements are only allowed in a file called main.swift.
        (Path(directory) / 'main.swift').write_text(DRIVER)
        binary = Path(directory) / 'querylog'
        built = subprocess.run(['xcrun', '--sdk', 'macosx', 'swiftc', '-o', str(binary),
                                str(helper), str(Path(directory) / 'main.swift')],
                               capture_output=True, text=True)
        if built.returncode != 0:
            failures.append('the helper does not compile:\n%s' % built.stderr[-1500:])
        else:
            run = subprocess.run([str(binary)], capture_output=True, text=True)
            if run.returncode != 0:
                failures.append('the helper driver failed: %s' % run.stderr[-800:])
            for line in run.stdout.splitlines():
                key, _, value = line.partition('\t')
                results[key] = value

if results:
    expected = {
        'name': 'PatientsName=<8 characters>',
        'nameWildcard': 'PatientsName=<3 characters, wildcard>',
        'id': 'PatientID=<1 character>',
        'accession': 'AccessionNumber=<4 characters>',
        'custom': 'InstitutionName=<7 characters>',
        'none': 'PatientID=<none>',
        'null': 'PatientID=<none>',
        'modality': 'ModalitiesinStudy=CT\\MR',
        'level': 'QueryRetrieveLevel=STUDY',
        'uid': 'StudyInstanceUID=1.2.3',
        'date': 'StudyDate=20260101-20260131',
        'noKey': '<3 characters>',
        'retrieve': 'serverName=PACS, retrieveMode=1, PatientID=<9 characters>, StudyDate=20260101',
    }
    for key, value in expected.items():
        if results.get(key) != value:
            failures.append('%s is %r, expected %r' % (key, results.get(key), value))
    birth = results.get('birth', '')
    if '1970' in birth or '1969' in birth or not birth.startswith('PatientBirthDate=<'):
        failures.append('a birth date that is not a string is written: %r' % birth)

# --- the log calls -------------------------------------------------------------
# What a log argument must not be: an accessor for a patient attribute, the text
# typed into the results, a raw filter value, or a whole study, node or filter
# dictionary (their descriptions carry the rest).
FORBIDDEN_ACCESSOR = re.compile(
    r'patientID|accessionNumber|theDescription|dateOfBirth|\bname\b|pressedKeys|customValue')
FORBIDDEN_BARE = {'study', 'item', 'identifier', 'value', 's', 'd', 'object', 'filters',
                  'paramDict'}
LOG = re.compile(r'NSLog\s*\(\s*@"((?:[^"\\]|\\.)*)"(.*)$')
# Arguments that look like patient data and are not: a list summary that counts
# identifiers, and a column identifier of the results table.
ALLOWED_ARGUMENT = ('HorosQueryLog', 'summaryForText:')
ALLOWED_FORMAT = ('QR: item not found',)


def arguments(rest):
    """The top-level arguments after the format string of one NSLog line."""
    rest = rest.strip()
    if not rest.startswith(','):
        return []
    parts, depth, current = [], 0, ''
    for character in rest[1:]:
        if character in '([':
            depth += 1
        elif character in ')]':
            if depth == 0:
                break
            depth -= 1
        if character == ',' and depth == 0:
            parts.append(current.strip())
            current = ''
        else:
            current += character
    parts.append(current.strip())
    return parts


for name in sources:
    text = (root / 'Horos/Sources' / name).read_bytes().decode('latin1')
    for number, line in enumerate(text.splitlines(), 1):
        if line.lstrip().startswith('//'):
            continue
        match = LOG.search(line)
        if not match:
            continue
        if any(allowed in match.group(1) for allowed in ALLOWED_FORMAT):
            continue
        for argument in arguments(match.group(2)):
            if any(allowed in argument for allowed in ALLOWED_ARGUMENT):
                continue
            if FORBIDDEN_ACCESSOR.search(argument) or argument in FORBIDDEN_BARE:
                failures.append('%s:%d logs %r' % (name, number, argument))

# A node's description is what `%@` writes for it anywhere in the log.
for name in ('DCMTKQueryNode.mm', 'DCMTKImageQueryNode.mm'):
    text = (root / 'Horos/Sources' / name).read_bytes().decode('latin1')
    at = text.find('- (NSString*) description')
    body = text[at:text.find('}', at)] if at >= 0 else ''
    if not body:
        failures.append('%s has no description to check' % name)
    elif re.search(r'_name|_accessionNumber|_patientID|_date\b|_birthdate', body):
        failures.append('the description of %s carries patient data' % name)
    elif '_uid' not in body:
        failures.append('the description of %s no longer names the node by UID' % name)

# The C-FIND summary still says what was asked, through the helper.
node = (root / 'Horos/Sources/DCMTKQueryNode.mm').read_bytes().decode('latin1')
if node.count('HorosQueryLog termWithKey:') < 2 or 'C-FIND asks for' not in node:
    failures.append('the C-FIND summary no longer lists its terms through HorosQueryLog')

for failure in failures:
    print('FAIL: %s' % failure)
if failures:
    sys.exit(1)
print('ok: the Query/Retrieve log names keys, shapes, counts and UIDs, never a patient name, '
      'identifier, accession number or birth date')
