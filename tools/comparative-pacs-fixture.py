#!/usr/bin/env python3
"""Synthetic local/prior studies and a loopback PACS with deliberately broad C-FIND results.
Requires pydicom 3.0.2 and pynetdicom 3.0.4. Uses only generated synthetic fixtures.
"""
import argparse
import json
from pathlib import Path
import uuid
from pydicom.dataset import FileDataset, FileMetaDataset, Dataset
from pydicom import dcmread
from pydicom.uid import MRImageStorage, ExplicitVRLittleEndian
from pynetdicom import AE, evt
from pynetdicom.sop_class import Verification, StudyRootQueryRetrieveInformationModelFind as FIND, StudyRootQueryRetrieveInformationModelGet as GET

def uid(value):
    return '2.25.' + str(uuid.uuid5(uuid.NAMESPACE_URL, 'urn:horos:comparative-pacs:' + value).int)

def generate(root):
    if root.exists() and any(root.iterdir()):
        raise ValueError('Generate into an empty directory')
    cases=[('current','A','20000101','20260907',20,'local'),
           ('local-good','A','20000101','20260901',40,'local'),
           ('local-other','A-B','20000101','20260906',60,'local'),
           ('remote-good','A','20000101','20260905',80,'remote'),
           ('remote-other','A-B','20000101','20260906',100,'remote'),
           ('remote-birth','A','19900101','20260906',120,'remote')]
    for name,patient,birth,date,pixel,location in cases:
        folder=root/location;folder.mkdir(parents=True,exist_ok=True)
        for image in (1,2):
            meta=FileMetaDataset();meta.TransferSyntaxUID=ExplicitVRLittleEndian
            meta.MediaStorageSOPClassUID=MRImageStorage;meta.MediaStorageSOPInstanceUID=uid(f'{name}-{image}')
            ds=FileDataset(str(folder/f'{name}-{image}.dcm'),{},file_meta=meta,preamble=b'\0'*128)
            ds.SOPClassUID=MRImageStorage;ds.SOPInstanceUID=meta.MediaStorageSOPInstanceUID
            ds.PatientName='QA^Comparative';ds.PatientID=patient;ds.PatientBirthDate=birth
            ds.StudyInstanceUID=uid(name);ds.SeriesInstanceUID=uid(name+'-series');ds.FrameOfReferenceUID=uid(name+'-frame')
            ds.StudyDate=ds.SeriesDate=ds.ContentDate=ds.AcquisitionDate=date
            ds.StudyTime=ds.SeriesTime=ds.ContentTime=ds.AcquisitionTime='120000'
            ds.StudyDescription='Comparative Patient Acceptance';ds.StudyID=name
            ds.SeriesDescription=name;ds.SeriesNumber=1;ds.InstanceNumber=image;ds.Modality='MR'
            ds.ImageType=['ORIGINAL','PRIMARY','OTHER'];ds.Rows=ds.Columns=32
            ds.SamplesPerPixel=1;ds.PhotometricInterpretation='MONOCHROME2'
            ds.BitsAllocated=ds.BitsStored=16;ds.HighBit=15;ds.PixelRepresentation=0
            ds.PixelSpacing=[1,1];ds.ImagePositionPatient=[0,0,image-1];ds.ImageOrientationPatient=[1,0,0,0,1,0];ds.SliceThickness=1
            ds.WindowCenter=80;ds.WindowWidth=160;ds.PixelData=(pixel+image).to_bytes(2,'little')*1024
            ds.save_as(ds.filename,enforce_file_format=True)
    print('Current study:',uid('current'))

def serve(root,port):
    images=[dcmread(p) for p in sorted((root/'remote').glob('*.dcm'))]
    expected={uid(f'{name}-{image}') for name in ('remote-good','remote-other','remote-birth') for image in (1,2)}
    if len(images)!=6 or {str(d.SOPInstanceUID) for d in images}!=expected or any(str(d.PatientName)!='QA^Comparative' for d in images):
        raise ValueError('Serve only the generated synthetic fixture set')
    state={'find':[],'get':[],'sent':[]}
    def record(): (root/'pacs-results.json').write_text(json.dumps(state,indent=2)+'\n')
    def find(event):
        query=event.identifier;level=str(query.QueryRetrieveLevel)
        state['find'].append({k:str(getattr(query,k,'')) for k in ('QueryRetrieveLevel','PatientID','PatientBirthDate','StudyInstanceUID')});record()
        selected=images
        if level!='STUDY':
            selected=[d for d in images if d.StudyInstanceUID==query.StudyInstanceUID]
        seen=set()
        for d in selected:
            key=d.StudyInstanceUID if level=='STUDY' else d.SeriesInstanceUID
            if key in seen:continue
            seen.add(key);out=Dataset();out.QueryRetrieveLevel=level
            for k in ('PatientName','PatientID','PatientBirthDate','StudyInstanceUID','StudyDate','StudyTime','StudyDescription','StudyID'):
                setattr(out,k,getattr(d,k))
            out.ModalitiesInStudy='MR';out.NumberOfStudyRelatedInstances=2;out.NumberOfStudyRelatedSeries=1
            if level!='STUDY':
                for k in ('SeriesInstanceUID','SeriesDescription','SeriesNumber','Modality'):setattr(out,k,getattr(d,k))
                out.NumberOfSeriesRelatedInstances=2
            yield 0xFF00,out
    def get(event):
        query=event.identifier
        state['get'].append({k:str(getattr(query,k,'')) for k in ('QueryRetrieveLevel','StudyInstanceUID','SeriesInstanceUID')});record()
        selected=images
        for k in ('StudyInstanceUID','SeriesInstanceUID'):
            value=getattr(query,k,'')
            if value:selected=[d for d in selected if str(getattr(d,k)) in str(value).split('\\')]
        yield len(selected)
        for d in selected:
            if event.is_cancelled:yield 0xFE00,None;return
            state['sent'].append({'study':str(d.StudyInstanceUID),'patient':str(d.PatientID),'birth':str(d.PatientBirthDate),'sop':str(d.SOPInstanceUID)});record()
            yield 0xFF00,d
    ae=AE(ae_title='HOROSCOMPARE')
    for context in (Verification,FIND,GET):ae.add_supported_context(context)
    ae.add_supported_context(MRImageStorage,scu_role=False,scp_role=True)
    record();print(f'Comparative PACS ready on 127.0.0.1:{port}',flush=True)
    ae.start_server(('127.0.0.1',port),evt_handlers=[(evt.EVT_C_FIND,find),(evt.EVT_C_GET,get)])

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('root',type=Path);p.add_argument('--generate',action='store_true');p.add_argument('--port',type=int,default=11124)
    args=p.parse_args()
    if not 1024<=args.port<=65535:p.error('Use an unprivileged TCP port')
    if args.generate:generate(args.root)
    else:serve(args.root,args.port)
