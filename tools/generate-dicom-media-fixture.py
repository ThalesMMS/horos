#!/usr/bin/env python3
"""Create a synthetic DICOM file-set for read-only media validation."""
import argparse
from pathlib import Path
import runpy
import tempfile
from pydicom.fileset import FileSet

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('destination',type=Path)
args=parser.parse_args()
args.destination.mkdir(parents=True,exist_ok=True)
if any(args.destination.iterdir()):parser.error('destination must be empty')
generator=runpy.run_path(str(Path(__file__).with_name('generate-jpeg-series-fixture.py')))
with tempfile.TemporaryDirectory(prefix='horos-media-source-') as directory:
 source=Path(directory)/'source'
 generator['generate'](source)
 media=FileSet()
 media.ID='HOROS_QA_164'
 for path in sorted(source.glob('*.dcm')):media.add(path)
 media.write(args.destination)
 assert len(FileSet(args.destination/'DICOMDIR'))==5
print('Created synthetic DICOMDIR: five objects, eight frames, two series')
