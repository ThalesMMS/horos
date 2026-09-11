#!/usr/bin/env python3
"""Generate two synthetic studies whose XML-sensitive identifiers must stay literal."""
import argparse
import json
from pathlib import Path
import runpy
import uuid
import pydicom

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('output', type=Path)
output = parser.parse_args().output
output.mkdir(parents=True, exist_ok=True)
if any(output.iterdir()):
    raise SystemExit('Use an empty output directory')
generate = runpy.run_path(str(Path(__file__).with_name('generate-jpeg-series-fixture.py')))['generate']
cases = []
for index, patient in enumerate(('QA <raw> & \' " é Тест', 'QA literal &amp; &lt; &#39; &quot;')):
    folder = output / f'case-{index}'
    generate(folder)
    def uid(name):
        return '2.25.' + str(uuid.uuid5(uuid.NAMESPACE_URL, f'horos-xmlrpc-592-{index}-{name}').int)
    for path in sorted(folder.glob('*.dcm')):
        ds = pydicom.dcmread(path)
        ds.SpecificCharacterSet = 'ISO_IR 192'
        ds.PatientID = patient
        ds.StudyInstanceUID = uid('study')
        ds.SeriesInstanceUID = uid(str(ds.SeriesNumber))
        ds.SOPInstanceUID = ds.file_meta.MediaStorageSOPInstanceUID = uid(path.name)
        ds.SeriesDescription = 'QA <series> &amp; é Тест'
        ds.save_as(path, enforce_file_format=True)
    cases.append({'patientID': patient, 'studyUID': uid('study'), 'seriesUID': uid('1'),
                  'seriesName': 'QA <series> &amp; é Тест'})
(output / 'expected.json').write_text(json.dumps(cases, ensure_ascii=False, indent=2))
print('Generated two synthetic studies: 10 files, 16 frames; expected.json contains their identities')
