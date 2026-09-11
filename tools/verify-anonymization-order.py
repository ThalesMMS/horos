#!/usr/bin/env python3
"""Check the documented synthetic CT export/reimport round trip independently of filenames."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
import pydicom

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('source',type=Path)
parser.add_argument('exported',type=Path)
parser.add_argument('reimported',type=Path)
parser.add_argument('source_hashes',type=Path)
args=parser.parse_args()
def load(directory):
    result={}
    for path in directory.rglob('*.dcm'):
        ds=pydicom.dcmread(path)
        key=int(ds.InstanceNumber)
        assert key not in result, 'Duplicate instance'
        result[key]=ds
    assert sorted(result)==list(range(1,13))
    return result
source=load(args.source)
assert [int(pydicom.dcmread(p,stop_before_pixels=True).InstanceNumber) for p in sorted(args.source.glob('*.dcm'))]==list(range(12,0,-1))
keys=['ImagePositionPatient','ImageOrientationPatient','PixelSpacing','SliceThickness','SpacingBetweenSlices','SliceLocation','RescaleSlope','RescaleIntercept','Rows','Columns','BitsAllocated','BitsStored','PixelRepresentation','FrameOfReferenceUID','StudyInstanceUID','SeriesInstanceUID','SOPInstanceUID']
for label,directory in [('exported',args.exported),('reimported',args.reimported)]:
    result=load(directory)
    for number,ds in result.items():
        before=source[number]
        assert ds.PatientID=='ANON-ORDER-140' and str(ds.PatientName)=='QA^AnonymousOrder'
        for key in keys: assert getattr(ds,key)==getattr(before,key),(number,key)
        assert np.array_equal(ds.pixel_array,before.pixel_array),number
        assert float(ds.ImagePositionPatient[2])==(number-1)*2.5
    print(f'PASS {label}: 12 unique instances; selected identity fields replaced; UIDs, geometry, rescale and pixels unchanged')
hashes=json.loads(args.source_hashes.read_text())
assert hashes and all(hashlib.sha256(Path(path).read_bytes()).hexdigest()==digest for path,digest in hashes.items())
print(f'PASS {len(hashes)} original source files unchanged; source lexical order deliberately reversed')
