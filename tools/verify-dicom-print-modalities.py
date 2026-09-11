#!/usr/bin/env python3
"""Compare native synthetic US/CR print negotiation, film settings and prepared pixels."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
import pydicom
from pydicom.uid import UltrasoundImageStorage, ComputedRadiographyImageStorage

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('fixture',type=Path)
parser.add_argument('us_capture',type=Path)
parser.add_argument('cr_capture',type=Path)
args=parser.parse_args()
expected_associations=[[{'abstract_syntax':'1.2.840.10008.1.1','transfer_syntax':['1.2.840.10008.1.2']}],[{'abstract_syntax':'1.2.840.10008.5.1.1.9','transfer_syntax':['1.2.840.10008.1.2']}]]
for modality,directory,sop,bits in [('US',args.us_capture,UltrasoundImageStorage,8),('CR',args.cr_capture,ComputedRadiographyImageStorage,12)]:
    source=pydicom.dcmread(args.fixture/modality/'image.dcm')
    assert source.Modality==modality and source.SOPClassUID==sop and source.BitsStored==bits
    received=json.loads((directory/'received.json').read_text())
    assert received['associations']==expected_associations
    assert received['film_sessions']==[{'NumberOfCopies':'1','PrintPriority':'HIGH','MediumType':'BLUE FILM','FilmDestination':'PROCESSOR'}]
    assert received['film_boxes']==[{'ImageDisplayFormat':'STANDARD\\1,1','FilmSizeID':'8INX10IN','FilmOrientation':'PORTRAIT','MagnificationType':'NONE'}]
    assert len(received['images'])==received['actions']==1
    assert received['images'][0]['position']==received['images'][0]['referenced_position']==1
    prepared=json.loads((directory/'prepared.json').read_text())
    assert prepared['sop_class']=='1.2.840.10008.5.1.4.1.1.7' and prepared['bits_stored']==8
    image=np.load(directory/'image-001.npy')
    assert np.array_equal(image,np.load(directory/'baseline.npy')) and np.unique(image).size>64
    print(f'PASS {modality}: source {bits}-bit, prepared SC 8-bit; expected negotiation/film session; exact prepared pixels and one Print action')
assert not np.array_equal(np.load(args.us_capture/'image-001.npy'),np.load(args.cr_capture/'image-001.npy'))
hashes=json.loads((args.us_capture/'source-hashes.json').read_text())
assert hashes and all(hashlib.sha256(Path(path).read_bytes()).hexdigest()==value for path,value in hashes.items())
print(f'PASS: distinct US/CR output and {len(hashes)} unchanged original files; no physical Agfa compatibility claim')
