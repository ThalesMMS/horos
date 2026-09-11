#!/usr/bin/env python3
"""Receive synthetic C-STOREs and cancel the native Horos C-MOVE server."""
import argparse
import json
import time
from pathlib import Path
from pydicom.dataset import Dataset
from pynetdicom import AE, evt
from pynetdicom.sop_class import (StudyRootQueryRetrieveInformationModelMove,
    CTImageStorage, MRImageStorage, UltrasoundImageStorage, UltrasoundMultiFrameImageStorage)
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('record',type=Path,help='synthetic fixture cmove-sent.json')
p.add_argument('output',type=Path)
p.add_argument('--complete',action='store_true')
p.add_argument('--retry',action='store_true',help='retrieve again on the same association after cancellation')
args=p.parse_args();args.output.mkdir(parents=True,exist_ok=True)
fixture=json.loads(args.record.read_text());timeline=[];received=[];responses=[];cancelled=False
association=None
started_at=time.time()

def stamp(name,**fields):
    timeline.append(dict(event=name,time=time.monotonic(),**fields))

def store(event):
    global cancelled
    ds=event.dataset;ds.file_meta=event.file_meta
    stamp('store-start',sop=str(ds.SOPInstanceUID))
    if not args.complete and not cancelled:
        cancelled=True
        association.send_c_cancel(1,query_model=StudyRootQueryRetrieveInformationModelMove)
        stamp('cancel-sent')
        # Hold the first C-STORE response so cancel is requested during a subop.
        time.sleep(.3)
    ds.save_as(args.output/(str(ds.SOPInstanceUID)+'.dcm'),enforce_file_format=True)
    received.append(str(ds.SOPInstanceUID));stamp('store-ack',sop=str(ds.SOPInstanceUID))
    return 0

def released(event):stamp('store-association-released')
receiver=AE(ae_title='CANCELDEST')
for sop in [CTImageStorage,MRImageStorage,UltrasoundImageStorage,UltrasoundMultiFrameImageStorage]:
    receiver.add_supported_context(sop)
server=receiver.start_server(('127.0.0.1',11274),block=False,evt_handlers=[(evt.EVT_C_STORE,store),(evt.EVT_RELEASED,released)])
requestor=AE(ae_title='CANCELSCU');requestor.dimse_timeout=15
requestor.add_requested_context(StudyRootQueryRetrieveInformationModelMove)
try:
    association=requestor.associate('127.0.0.1',11272,ae_title='HOROSDEV')
    assert association.is_established
    query=Dataset();query.QueryRetrieveLevel='STUDY';query.StudyInstanceUID=fixture['study']
    for request_id in range(1, 3 if args.retry else 2):
        for status,identifier in association.send_c_move(query,'CANCELDEST',StudyRootQueryRetrieveInformationModelMove,msg_id=request_id):
            response={e.keyword:int(e.value) for e in status}
            responses.append(response);stamp('move-response',request=request_id,**response)
        stamp('operation-complete',request=request_id)
    association.release();stamp('move-association-released',released=association.is_released)
finally:
    if association is not None and association.is_established:association.abort()
    server.shutdown()
    result=dict(startedAt=started_at,received=received,responses=responses,timeline=timeline)
    (args.output/'result.json').write_text(json.dumps(result,indent=2))
print(json.dumps(result,indent=2))
