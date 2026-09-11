#!/usr/bin/env python3
"""Small synthetic studies covering autorouting previous-study filters."""
import argparse,json,subprocess,sys
from pathlib import Path
import pydicom
p=argparse.ArgumentParser();p.add_argument('destination',type=Path);a=p.parse_args()
a.destination.mkdir(parents=True,exist_ok=True)
if any(a.destination.iterdir()):p.error('Use an empty destination')
manifest={}
for name,day,mod,description,patient in [('current',10,'CT','CURRENT','LOCAL-STORE'),('matching',7,'CT','CURRENT','LOCAL-STORE'),('modality',9,'MR','CURRENT','LOCAL-STORE'),('description',8,'CT','OTHER','LOCAL-STORE'),('future',11,'CT','CURRENT','LOCAL-STORE'),('other',6,'CT','CURRENT','LOCAL-STORE-OTHER')]:
 d=a.destination/name
 subprocess.run([sys.executable,str(Path(__file__).with_name('generate-store-fixture.py')),str(d),'--ct-instances','2','--us-instances','0'],check=True,capture_output=True)
 (d/'without-sop-class.dcm').unlink();(d/'manifest.json').unlink()
 ids=[]
 for f in sorted(d.glob('*.dcm')):
  ds=pydicom.dcmread(f);ds.StudyDate=f'202609{day:02d}';ds.Modality=mod;ds.StudyDescription=description;ds.StudyID='CUR' if name=='current' else name;ds.PatientID=patient
  if name=='other':ds.PatientName='QA^Other'
  if mod=='MR':ds.SOPClassUID=pydicom.uid.MRImageStorage;ds.file_meta.MediaStorageSOPClassUID=ds.SOPClassUID
  ds.save_as(f,enforce_file_format=True);ids.append(str(ds.SOPInstanceUID))
 manifest[name]=ids
(a.destination/'manifest.json').write_text(json.dumps(manifest,indent=2))
