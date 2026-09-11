#!/usr/bin/env python3
"""Create one synthetic study and an existing RTF for native report attachment QA."""
import argparse
import runpy
import uuid
from pathlib import Path

def generate(output):
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        raise ValueError('Use an empty output directory')
    fixture = runpy.run_path(str(Path(__file__).with_name('generate-jpeg-series-fixture.py')))
    image_dir = output / 'dicom'
    image_dir.mkdir()
    image = image_dir / 'study.dcm'
    ds = fixture['dataset'](image, 'report-attachment', False)
    def uid(name):
        return '2.25.' + str(uuid.uuid5(uuid.NAMESPACE_URL, 'horos-report-attachment-' + name).int)
    ds.StudyInstanceUID = uid('study')
    ds.SeriesInstanceUID = uid('series')
    ds.SOPInstanceUID = ds.file_meta.MediaStorageSOPInstanceUID = uid('instance')
    ds.PatientName = 'QA^ReportAttachment'
    ds.PatientID = 'LOCAL-REPORT-131'
    ds.StudyDescription = 'Existing Report Acceptance'
    ds.SeriesDescription = 'Synthetic Report Study'
    ds.StudyID = 'REPORT131'
    ds.InstanceNumber = 1
    ds.PixelData = fixture['frame'](0)
    ds.save_as(image, enforce_file_format=True)
    (output / 'existing-report.rtf').write_bytes(b'{\\rtf1\\ansi Horos QA existing report 131.\\par Original imported document; no generated template.}')

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    generate(parser.parse_args().output)
