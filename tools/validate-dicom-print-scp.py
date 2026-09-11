#!/usr/bin/env python3
"""Exercise bundled DCMTK printing against a loopback-only synthetic Print SCP."""
import argparse
import ast
import json
import os
from pathlib import Path
import re
import runpy
import subprocess
import numpy as np
from pydicom.dataset import Dataset
from pydicom.uid import generate_uid, ImplicitVRLittleEndian
from pynetdicom import AE, evt
from pynetdicom.sop_class import BasicGrayscalePrintManagementMeta, BasicFilmBox, BasicGrayscaleImageBox, Verification

ROOT = Path(__file__).resolve().parent.parent

def config_template():
    source=(ROOT/'DICOMPrint/AYDicomPrintWindowController.mm').read_bytes().decode('latin1')
    literal=re.search(r'DCMTK_PRINTER_CONFIG_TEMPLATE = @(".*?");',source,re.S).group(1)
    return ast.literal_eval(literal.replace('\\\n',''))

def capture_server(columns,rows,reject="",port=0,output=None):
    captured={'film_boxes':[],'images':[],'actions':0,'associations':[],'film_sessions':[]}
    boxes={}
    def accepted(event):
        captured['associations'].append([{'abstract_syntax':str(context.abstract_syntax), 'transfer_syntax':[str(syntax) for syntax in context.transfer_syntax]} for context in event.assoc.accepted_contexts])
        if output: (output/'received.json').write_text(json.dumps(captured,indent=2))
    def create(event):
        data=event.attribute_list
        response=Dataset();response.AffectedSOPInstanceUID=generate_uid()
        if event.request.AffectedSOPClassUID==BasicFilmBox:
            captured['film_boxes'].append({key:str(data.get(key,'')) for key in ['ImageDisplayFormat','FilmSizeID','FilmOrientation','MagnificationType']})
            if output: (output/'received.json').write_text(json.dumps(captured,indent=2))
            if reject=='film': return 0x0106,None
            refs=[]
            for position in range(1,columns*rows+1):
                ref=Dataset();ref.ReferencedSOPClassUID=BasicGrayscaleImageBox;ref.ReferencedSOPInstanceUID=generate_uid();boxes[str(ref.ReferencedSOPInstanceUID)]=position;refs.append(ref)
            response.ReferencedImageBoxSequence=refs
        else:
            captured['film_sessions'].append({key:str(data.get(key,'')) for key in ['NumberOfCopies','PrintPriority','MediumType','FilmDestination']})
        return 0x0000,response
    def set_image(event):
        data=event.modification_list
        pixel=data.BasicGrayscaleImageSequence[0]
        dtype='<u2' if pixel.BitsAllocated==16 else 'u1'
        array=np.frombuffer(pixel.PixelData,dtype=dtype).reshape(int(pixel.Rows),int(pixel.Columns))
        captured['images'].append({'position':int(data.ImageBoxPosition),'referenced_position':boxes[str(event.request.RequestedSOPInstanceUID)],'rows':int(pixel.Rows),'columns':int(pixel.Columns),'bits':int(pixel.BitsStored),'sample':int(array[8,8]),'minimum':int(array.min()),'maximum':int(array.max()),'top_left':int(array[1,1]),'bottom_right':int(array[-2,-2])})
        if output:
            np.save(output/f'image-{len(captured["images"]):03d}.npy',array)
            (output/'received.json').write_text(json.dumps(captured,indent=2))
        return (0xC605 if reject=='image' else 0x0000),None
    def action(event):
        captured['actions']+=1
        if output: (output/'received.json').write_text(json.dumps(captured,indent=2))
        return (0xC600 if reject=='action' else 0x0000),None
    def get_printer(event):
        data=Dataset();data.PrinterStatus='NORMAL';data.PrinterStatusInfo='NORMAL';data.PrinterName='LOOPBACK QA'
        return 0x0000,data
    ae=AE(ae_title='PRINTQA');ae.add_supported_context(BasicGrayscalePrintManagementMeta,[ImplicitVRLittleEndian])
    ae.add_supported_context(Verification,[ImplicitVRLittleEndian])
    server=ae.start_server(('127.0.0.1',port),block=False,evt_handlers=[(evt.EVT_ACCEPTED,accepted),(evt.EVT_C_ECHO,lambda event:0x0000),(evt.EVT_N_CREATE,create),(evt.EVT_N_SET,set_image),(evt.EVT_N_ACTION,action),(evt.EVT_N_GET,get_printer),(evt.EVT_N_DELETE,lambda event:0x0000)])
    return server,captured

def validate(resources, output):
    output.mkdir(parents=True,exist_ok=True)
    if any(output.iterdir()): raise ValueError('Use an empty output directory')
    resources=resources.resolve();output=output.resolve()
    fixture=runpy.run_path(str(ROOT/'tools/generate-jpeg-series-fixture.py'))
    env=os.environ.copy();env['DCMDICTPATH']=str(resources/'dicom.dic')
    results=[]
    for columns,rows,reject in [(6,4,''),(6,5,''),(6,5,'film'),(6,5,'image'),(6,5,'action')]:
        name=f'{columns}x{rows}'+('-rejected-'+reject if reject else '')
        job=output/name;job.mkdir();(job/'database').mkdir()
        server,captured=capture_server(columns,rows,reject)
        try:
            values={'PRINTER_AETITLE':'PRINTQA','HOST':'127.0.0.1','PORT':str(server.server_address[1]),'HOROS_AETITLE':'HOROSQA','COLUMNS':str(columns),'ROWS':str(rows),'FILM_DESTINATION':'PROCESSOR','FILM_SIZE':'14INX17IN','MEDIUM_TYPE':'PAPER','MAGNIFICATION_TYPE':'BILINEAR'}
            config=config_template()
            for key,value in values.items():config=config.replace('{{'+key+'}}',value)
            (job/'print.cfg').write_text(config)
            images=[]
            for index in range(columns*rows):
                path=job/f'image-{index+1:02d}.dcm';ds=fixture['dataset'](path,f'print-{name}-{index}',False)
                ds.PatientName='QA^Print';ds.PatientID='LOCAL-PRINT-QA';ds.Rows=32;ds.Columns=64;ds.InstanceNumber=index+1
                # The center patch encodes ordinal; asymmetric markers reveal orientation.
                pixels=np.full((32,64),20+index*5,dtype=np.uint8);pixels[0:4,0:4]=0;pixels[-4:,-4:]=255
                segments={'0':'abcdef','1':'bc','2':'abged','3':'abgcd','4':'fgbc','5':'afgcd','6':'afgecd','7':'abc','8':'abcdefg','9':'abfgcd'}
                for digit_index,digit in enumerate(f'{index+1:02d}'):
                    x=30+digit_index*12;y=7
                    bars={'a':(0,0,2,8),'b':(0,6,9,2),'c':(8,6,9,2),'d':(15,0,2,8),'e':(8,0,9,2),'f':(0,0,9,2),'g':(7,0,2,8)}
                    for segment in segments[digit]:
                        dy,dx,h,w=bars[segment];pixels[y+dy:y+dy+h,x+dx:x+dx+w]=255
                ds.PixelData=pixels.tobytes();ds.save_as(path,enforce_file_format=True);images.append(str(path))
            prep=[str(resources/'dcmpsprt'),'-c','print.cfg','--printer','PRINTSCP','--layout',str(columns),str(rows),'--filmsize','14INX17IN','--magnification','BILINEAR','--border','BLACK','--empty-image','BLACK','--no-trim','--portrait',*images]
            with (job/'prepare.log').open('w') as log:subprocess.run(prep,cwd=job,env=env,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=60)
            states=sorted((job/'database').glob('SP_*'));assert len(states)==1,states
            send=[str(resources/'dcmprscu'),'-c','print.cfg','--printer','PRINTSCP','--copies','1','--priority','MED','--destination','PROCESSOR','--medium-type','PAPER',*[str(p) for p in states]]
            with (job/'send.log').open('w') as log:process=subprocess.run(send,cwd=job,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=60)
            captured['exit_status']=process.returncode
            (job/'received.json').write_text(json.dumps(captured,indent=2))
            assert captured['associations']==[[{'abstract_syntax':str(BasicGrayscalePrintManagementMeta),'transfer_syntax':[str(ImplicitVRLittleEndian)]}]],captured
            assert captured['film_sessions']==[{'NumberOfCopies':'1','PrintPriority':'MED','MediumType':'PAPER','FilmDestination':'PROCESSOR'}],captured
            assert captured['film_boxes'],captured
            film=captured['film_boxes'][0]
            assert film['ImageDisplayFormat']==f'STANDARD\\{columns},{rows}',film
            assert film['FilmSizeID']=='14INX17IN' and film['FilmOrientation']=='PORTRAIT',film
            if reject:
                assert process.returncode!=0,captured
                if reject=='film': assert not captured['images'] and not captured['actions'],captured
                if reject=='image': assert len(captured['images'])==1 and not captured['actions'],captured
                if reject=='action': assert len(captured['images'])==columns*rows and captured['actions']==1,captured
            else:
                assert process.returncode==0 and len(captured['images'])==columns*rows and captured['actions']==1,captured
                for index,image in enumerate(captured['images']):
                    assert image['position']==image['referenced_position']==index+1,image
                    assert (image['rows'],image['columns'])==(32,64),image
                    assert image['sample']==20+index*5 and image['top_left']==0 and image['bottom_right']==255,image
                samples=[x['sample'] for x in captured['images']]
                assert all(a<b for a,b in zip(samples,samples[1:])),samples
            (job/'received.json').write_text(json.dumps(captured,indent=2))
            results.append({'case':name,**captured})
            print('PASS:',name,'images',len(captured['images']),'exit',process.returncode)
        finally:
            server.shutdown()
    (output/'summary.json').write_text(json.dumps(results,indent=2))

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('resources',type=Path)
    parser.add_argument('output',type=Path)
    parser.add_argument('--serve',action='store_true',help='Listen for the native Horos print UI until interrupted')
    parser.add_argument('--port',type=int,default=15962)
    parser.add_argument('--columns',type=int,default=2)
    parser.add_argument('--rows',type=int,default=2)
    parser.add_argument('--reject', choices=['film','image','action'], default='', help='Reject one protocol stage in native serve mode')
    args=parser.parse_args()
    if args.serve:
        import time
        args.output.mkdir(parents=True,exist_ok=True)
        if any(args.output.iterdir()): raise ValueError('Use an empty output directory')
        server,captured=capture_server(args.columns,args.rows,reject=args.reject,port=args.port,output=args.output)
        print(f'Print SCP listening only on 127.0.0.1:{args.port}',flush=True)
        try:
            while True: time.sleep(1)
        except KeyboardInterrupt: pass
        finally: server.shutdown()
    else: validate(args.resources,args.output)
