#!/usr/bin/env python3
"""Everything a CD brings in is offered to the routing, and losses are named.

The report is of a CD being imported and only part of it reaching the PACS. The
routing decided what to send by walking the queued rows and skipping any whose
file was not on disk:

    if( [[NSFileManager defaultManager] fileExistsAtPath: [objectToSend valueForKey: @"completePath"]])

with no else. A row whose file has gone, and a row that has gone from the
database between queueing and sending, both dropped out of the send without a
word - which is exactly what a partial delivery looks like from the far end.

The fixture generator is exercised here; the reporting is checked in source, and
was measured against a running build (see the validation document).
"""
from pathlib import Path
import json
import re
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
failures = []
routing = (root / 'Horos/Sources/DicomDatabase+Routing.mm').read_bytes().decode('latin1')

# --- the queue says what it left behind --------------------------------------
at = routing.find('NSArray* objectsToSend = [self objectsWithIDs:objectIDs];')
if at < 0:
    failures.append('the queue no longer resolves its object IDs')
else:
    window = routing[at:at + 700]
    if 'no longer in the database' not in window:
        failures.append('a queued row that has gone from the database is dropped silently')

if 'the file is not there' not in routing:
    failures.append('a queued image whose file has gone is dropped silently')
if 'were not sent because their files are not there' not in routing:
    failures.append('the queue does not say how many images it could not send')

# The skip is still a skip - the send must not be attempted for a missing file.
if not re.search(r'fileExistsAtPath: \[objectToSend valueForKey: @"completePath"\]\] == NO', routing):
    failures.append('the missing-file test no longer guards the send')

# --- the fixture ---------------------------------------------------------------
def interpreter():
    for candidate in [sys.executable] + [str(p) for p in
                                         Path('/private/tmp').glob('*/*/*/scratchpad/*venv*/bin/python')]:
        if subprocess.run([candidate, '-c', 'import pydicom'], capture_output=True).returncode == 0:
            return candidate
    return None


python = interpreter()
if python is None:
    failures.append("no interpreter here has pydicom. Create one with:\n"
                    "  python3 -m venv /tmp/horos-dicom-venv\n"
                    "  /tmp/horos-dicom-venv/bin/python -m pip install 'pydicom>=3,<4'")
else:
    with tempfile.TemporaryDirectory(prefix='horos-cd-') as directory:
        destination = Path(directory) / 'cd'
        built = subprocess.run([python, str(root / 'tools/generate-cd-fixture.py'), str(destination),
                                '--modalities', 'CT,MR,CR', '--instances', '2'],
                               capture_output=True, text=True)
        if built.returncode != 0:
            failures.append('the CD fixture does not generate: %s' % built.stderr[-600:])
        else:
            manifest = json.loads((destination / 'manifest.json').read_text())
            if len(manifest['instances']) != 6:
                failures.append('the fixture holds %d instances, expected 6'
                                % len(manifest['instances']))
            if sorted(set(manifest['series'].values())) != ['CR', 'CT', 'MR']:
                failures.append('the fixture is not three modalities: %s'
                                % sorted(set(manifest['series'].values())))
            # Everything on the disc is in its DICOMDIR, which is what makes the
            # comparison disc/database/destination meaningful.
            check = subprocess.run(
                [python, '-c',
                 'import sys, json\n'
                 'from pydicom.fileset import FileSet\n'
                 'from pydicom import dcmread\n'
                 'fs = FileSet(sys.argv[1])\n'
                 'print(json.dumps(sorted(str(i.SOPInstanceUID) for i in fs)))',
                 str(destination / 'disc' / 'DICOMDIR')], capture_output=True, text=True)
            if check.returncode != 0:
                failures.append('the generated DICOMDIR does not read back: %s'
                                % check.stderr[-400:])
            else:
                on_disc = set(json.loads(check.stdout))
                if on_disc != set(manifest['instances']):
                    failures.append('the DICOMDIR and the manifest disagree: %d vs %d'
                                    % (len(on_disc), len(manifest['instances'])))
                else:
                    print('ok: the CD fixture writes a DICOMDIR holding every instance it lists')

for failure in failures:
    print('FAIL: %s' % failure)
if failures:
    sys.exit(1)
print('ok: an image the routing cannot send because its file or its row has gone is named, '
      'instead of quietly reducing what reaches the destination')
