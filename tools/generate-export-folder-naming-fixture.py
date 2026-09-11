#!/usr/bin/env python3
"""Generate only synthetic DICOM: missing study fields and homonymous series."""
from pathlib import Path
import subprocess
import sys
import pydicom

if len(sys.argv) != 2:
    raise SystemExit('usage: generate-export-folder-naming-fixture.py EMPTY_DIRECTORY')
destination = Path(sys.argv[1])
subprocess.run([sys.executable, str(Path(__file__).with_name('generate-jpeg-series-fixture.py')), str(destination)], check=True)
for path in destination.glob('*.dcm'):
    dataset = pydicom.dcmread(path)
    dataset.PatientName = 'QA^FolderNaming'
    dataset.PatientID = 'QA/FOLDER:126'
    dataset.StudyDescription = ':'
    dataset.StudyID = ''
    dataset.SeriesDescription = 'Same:Series'
    dataset.SeriesNumber = 1
    dataset.save_as(path, enforce_file_format=True)
