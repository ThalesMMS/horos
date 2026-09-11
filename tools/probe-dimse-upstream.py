#!/usr/bin/env python3
"""Exercise the built development listener with a new synthetic, isolated study.

This is an opt-in native integration tool, not a unit test. Requires pydicom,
pynetdicom, numpy and imagecodecs, and the app prepared by --verify. It only
launches/stops HorosDevelopment.app and writes under an empty local-validation
directory outside the checkout. It does not use a configured remote node.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import time
import numpy as np
import imagecodecs
from pydicom.encaps import generate_frames
import pydicom
from pydicom.dataset import Dataset
from pydicom.uid import generate_uid
from pynetdicom import AE, evt, build_role
from pynetdicom.sop_class import (Verification, StudyRootQueryRetrieveInformationModelFind as FIND,
    StudyRootQueryRetrieveInformationModelGet as GET, StudyRootQueryRetrieveInformationModelMove as MOVE)

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('output', type=Path)
parser.add_argument('--fork-listener', action='store_true', help='exercise the existing process-per-association mode')
args = parser.parse_args(); run = args.output.resolve()
assert 'local-validation' in run.parts and not run.is_relative_to(ROOT)
run.mkdir(parents=True, exist_ok=True); assert not any(run.iterdir()), 'Use an empty output directory'
app = ROOT/'build/Development/HorosDevelopment.app/Contents/MacOS/Horos'
assert app.is_file(), 'Run script/build_and_run.sh --verify first'
spec = importlib.util.spec_from_file_location('fixture', ROOT/'tools/generate-dimse-matrix-fixture.py')
generator = importlib.util.module_from_spec(spec); spec.loader.exec_module(generator)
manifest = generator.generate(run/'input'); expected = {e['uid']: e for e in manifest['instances']}
classes = sorted({e['sopClass'] for e in expected.values()})
syntaxes = sorted({e['syntax'] for e in expected.values()})
results = []; operation = {}; application = None

def record(name, **values):
    item = dict(case=name, **values); results.append(item)
    (run/'result.json').write_text(json.dumps(results, indent=2) + '\n')
    print(json.dumps({k: v for k, v in item.items() if k != 'responses'}), flush=True)

def stop_development():
    for line in subprocess.check_output(['/bin/ps', '-axo', 'pid=,comm='], text=True).splitlines():
        fields = line.strip().split(None, 1)
        if len(fields) != 2 or fields[1] != str(app): continue
        pid = int(fields[0]); os.kill(pid, signal.SIGTERM)
        for _ in range(50):
            try: os.kill(pid, 0)
            except ProcessLookupError: break
            time.sleep(.1)
        else: raise RuntimeError('Development app did not stop')

def stored(event):
    ds = event.dataset; ds.file_meta = event.file_meta; uid = str(ds.SOPInstanceUID)
    assert uid in expected, uid
    if uid == operation.get('fail'):
        operation['refused'].append(uid); return 0xA700
    if operation.get('cancel') and not operation.get('cancelledAt'):
        operation['cancelledAt'] = time.monotonic()
        operation['association'].send_c_cancel(operation['messageID'], query_model=operation['model'])
        time.sleep(.3)  # cancel while this store sub-operation is still waiting
    target = operation['directory'] / (uid + '.dcm')
    assert uid not in operation['received'], 'Duplicate UID in one retrieve'
    ds.save_as(target, enforce_file_format=True)
    operation['received'].append(uid)
    return 0

destination = AE(ae_title='MATRIXDEST')
for sop in classes: destination.add_supported_context(sop, syntaxes)
receiver = destination.start_server(('127.0.0.1', 0), block=False, evt_handlers=[(evt.EVT_C_STORE, stored)])
dest_port = receiver.server_address[1]
with socket.socket() as reservation:
    reservation.bind(('127.0.0.1', 0)); port = reservation.getsockname()[1]

def connect(host='127.0.0.1', storage=False, get=False):
    ae = AE(ae_title='MATRIXSCU'); ae.acse_timeout = 5; ae.dimse_timeout = 12; ae.network_timeout = 15
    for sop in (Verification, FIND, GET, MOVE): ae.add_requested_context(sop)
    roles = []
    if storage or get:
        for sop in classes:
            # Separate contexts retain each accepted native/compressed encoding.
            for syntax in syntaxes: ae.add_requested_context(sop, syntax)
            if get: roles.append(build_role(sop, scu_role=False, scp_role=True))
    association = ae.associate(host, port, ae_title='HOROSDEV', ext_neg=roles,
                               evt_handlers=[(evt.EVT_C_STORE, stored)])
    assert association.is_established, 'Native listener did not accept the association'
    return association

def query():
    ds = Dataset(); ds.QueryRetrieveLevel = 'STUDY'; ds.StudyInstanceUID = manifest['study']; return ds

def inventory(association):
    ds = query(); ds.QueryRetrieveLevel = 'IMAGE'; ds.SeriesInstanceUID = ''; ds.SOPInstanceUID = ''; ds.SOPClassUID = ''
    found = []
    for status, identifier in association.send_c_find(ds, FIND):
        assert status is not None and 'Status' in status
        if int(status.Status) in (0xFF00, 0xFF01): found.append(str(identifier.SOPInstanceUID))
        else: assert status.Status == 0, status
    assert len(found) == len(set(found)), 'C-FIND duplicates SOP Instance UIDs'
    return set(found)

def retrieve(association, name, move=False, fail=None, incompatible=False, message_id=1, cancel=False):
    global operation
    folder = run/name; folder.mkdir()
    operation = dict(directory=folder, received=[], refused=[], fail=fail, cancel=cancel, association=association, messageID=message_id, model=MOVE if move else GET)
    responses = []
    iterator = association.send_c_move(query(), 'MATRIXDEST', MOVE, msg_id=message_id) if move else association.send_c_get(query(), GET, msg_id=message_id)
    for status, identifier in iterator:
        assert status is not None and 'Status' in status, 'Missing DIMSE terminal status'
        values = {e.keyword: int(e.value) for e in status if e.VR in ('US', 'UL')}
        responses.append(values)
    assert responses and responses[-1]['Status'] not in (0xFF00, 0xFF01), responses
    received = set(operation['received'])
    wanted = set() if incompatible else set(expected) - ({fail} if fail else set())
    if cancel:
        assert received < set(expected) and received, (name, received)
        assert 0 <= time.monotonic() - operation['cancelledAt'] < 7
    else:
        assert received == wanted, (name, received, wanted, responses)
    assert responses[-1]['Status'] == (0xFE00 if cancel else 0xA702 if incompatible else 0xB000 if fail else 0), responses
    for uid in received:
        ds = pydicom.dcmread(folder/(uid+'.dcm')); source = pydicom.dcmread(run/'input'/expected[uid]['file'])
        assert str(ds.SOPClassUID) == expected[uid]['sopClass']
        assert int(getattr(ds, 'NumberOfFrames', 1)) == expected[uid]['frames']
        if 'PixelData' in source:
            if str(ds.file_meta.TransferSyntaxUID) == '1.2.840.10008.1.2.4.80':
                frames = [imagecodecs.jpegls_decode(frame) for frame in generate_frames(ds.PixelData, number_of_frames=expected[uid]['frames'])]
                pixels = np.stack(frames) if len(frames) > 1 else frames[0]
            else:
                pixels = ds.pixel_array
            assert hashlib.sha256(pixels.astype('<u2').tobytes()).hexdigest() == expected[uid]['pixelSHA256'], (name, uid)
        else:
            assert ds.ContentSequence[0].TextValue == source.ContentSequence[0].TextValue
    record(name, objects=len(received), frames=sum(expected[uid]['frames'] for uid in received),
           status=responses[-1]['Status'], pixelsAndSRChecked=True, responses=responses)

try:
    stop_development()
    options = dict(DATABASELOCATION='1', DATABASELOCATIONURL=str(run/'db'), DEFAULT_DATABASELOCATION='1',
        DEFAULT_DATABASELOCATIONURL=str(run/'db'), WebPortalDatabasePath=str(run/'web.sql'),
        AUTOCLEANINGSPACE='NO', AUTOCLEANINGDATE='NO', AUTOROUTINGACTIVATED='NO', STORESCP='YES', USESTORESCP='YES',
        TLSStoreSCP='NO', publishDICOMBonjour='NO', searchDICOMBonjour='NO', syncDICOMNodes='NO',
        httpXMLRPCServer='NO', checkForUpdatesPlugins='NO', SUEnableAutomaticChecks='NO',
        AETITLE='HOROSDEV', AEPORT=str(port), DICOMTimeout='12', DICOMConnectionTimeout='5',
        SingleProcessMultiThreadedListener='NO' if args.fork_listener else 'YES', activateCFINDSCP='YES', activateCGETSCP='YES', ListenerCompressionSettings='0',
        SERVERS='({Address="127.0.0.1";Port='+str(dest_port)+';AETitle=MATRIXDEST;Activated=1;Send=1;QueryRetrieve=1;retrieveMode=0;TransferSyntax=0;Description="Synthetic receiver";})')
    command = [str(app)]
    for key, value in options.items(): command += ['-'+key, value]
    env = dict(os.environ, TMPDIR=subprocess.check_output(['/usr/bin/getconf', 'DARWIN_USER_TEMP_DIR'], text=True).strip())
    with (run/'horos.log').open('w') as log:
        application = subprocess.Popen(command, env=env, stdout=log, stderr=subprocess.STDOUT)
    for _ in range(100):
        if application.poll() is not None: raise RuntimeError('Native app stopped at startup')
        try:
            with socket.create_connection(('127.0.0.1', port), timeout=.1): break
        except OSError: time.sleep(.2)
    # A TCP readiness probe is not DICOM evidence; all following checks negotiate.
    for host in ('127.0.0.1', '::1'):
        association = connect(host); status = association.send_c_echo(); assert status.Status == 0
        association.release(); record('echo', host=host, status=0)
    association = connect(storage=True)
    for entry in expected.values():
        ds = pydicom.dcmread(run/'input'/entry['file']); status = association.send_c_store(ds)
        assert status.Status == 0, (entry['file'], status)
    association.release(); record('store', objects=len(expected), syntaxes=syntaxes)
    deadline = time.monotonic() + 45
    while True:
        association = connect(); found = inventory(association); association.release()
        if found == set(expected): break
        if time.monotonic() >= deadline: raise AssertionError(('Persisted inventory incomplete', found, set(expected)))
        time.sleep(.5)
    record('find-persisted', objects=len(found))
    # Refuse publication after receiving a valid dataset, keep its TEMP file,
    # and demonstrate a later successful retry with an unrelated synthetic UID.
    incoming = next((run/'db').rglob('INCOMING.noindex'))
    temporary = next((run/'db').rglob('TEMP.noindex'))
    extra = pydicom.dcmread(run/'input'/manifest['instances'][0]['file'])
    extra.SOPInstanceUID = generate_uid(); extra.StudyInstanceUID = generate_uid(); extra.SeriesInstanceUID = generate_uid()
    extra.file_meta.MediaStorageSOPInstanceUID = extra.SOPInstanceUID
    permissions = incoming.stat().st_mode & 0o777
    association = connect(storage=True)
    try:
        incoming.chmod(0o500)
        refusal = association.send_c_store(extra)
        assert refusal.Status == 0xA700, refusal
    finally:
        incoming.chmod(permissions)
        association.release()
    kept = [path for path in temporary.glob('*.dcm') if str(pydicom.dcmread(path, stop_before_pixels=True).SOPInstanceUID) == str(extra.SOPInstanceUID)]
    assert len(kept) == 1, 'Complete file was lost after failed publication'
    assert np.array_equal(pydicom.dcmread(kept[0]).pixel_array, extra.pixel_array)
    association = connect(storage=True)
    try: assert association.send_c_store(extra).Status == 0
    finally: association.release()
    record('store-unwritable-and-retry', refusal=0xA700, completeTemporaryPreserved=True, retry=0)
    association = connect(get=True)
    try:
        retrieve(association, 'get-cancel-during-store', message_id=9, cancel=True)
        retrieve(association, 'get-first', message_id=10)
        retrieve(association, 'get-same-association', message_id=11)
        retrieve(association, 'get-partial-refusal', fail=next(iter(expected)), message_id=12)
        retrieve(association, 'get-retry-after-refusal', message_id=13)
    finally: association.release()
    association = connect()
    try:
        retrieve(association, 'get-no-storage-context', incompatible=True)
        retrieve(association, 'move-cancel-during-store', move=True, message_id=2, cancel=True)
        retrieve(association, 'move-complete', move=True, message_id=3)
    finally: association.release()
    association = connect(get=True)
    try: retrieve(association, 'get-reconnected')
    finally: association.release()
    for entry in expected.values():
        assert hashlib.sha256((run/'input'/entry['file']).read_bytes()).hexdigest() == entry['sha256']
    record('source-preserved', objects=len(expected))
finally:
    receiver.shutdown()
    if application and application.poll() is None:
        application.terminate()
        try: application.wait(timeout=10)
        except subprocess.TimeoutExpired: application.kill(); application.wait()
