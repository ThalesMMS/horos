#!/usr/bin/env python3
"""Validate native C-GET/C-MOVE retrieval using only synthetic loopback peers.

Use a Python with pydicom, pynetdicom and numpy, after --verify. The empty output
must be outside the checkout under local-validation. This signs/launches only
HorosDevelopment.app with a private database, and stops that instance on exit.
The probe invokes the actual QueryController backend; it is not UI-click proof.
"""
from pathlib import Path
import argparse,re,numpy as np,pydicom
import json,os,plistlib,signal,socket,subprocess,time,sys
root=Path(__file__).resolve().parents[1];os.chdir(root)
parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('output',type=Path)
parser.add_argument('--protocol',choices=['get','move'],default='get')
parser.add_argument('--mode',choices=['complete','failure','cancel','cancel-before-first'],default='complete')
options=parser.parse_args();mode=options.mode;move=options.protocol=='move';run=options.output.resolve()
assert 'local-validation' in run.parts and not run.is_relative_to(root)
run.mkdir(parents=True,exist_ok=True);assert not any(run.iterdir()), 'Use an empty output directory'
app=root/'build/Development/HorosDevelopment.app';exe=app/'Contents/MacOS/Horos'
# Only the already isolated development app is stopped and re-signed.
for line in subprocess.check_output(['/bin/ps','-axo','pid=,comm='],text=True).splitlines():
 fields=line.strip().split(None,1)
 if len(fields)==2 and fields[1]==str(exe):
  os.kill(int(fields[0]),signal.SIGTERM)
  for _ in range(50):
   try:os.kill(int(fields[0]),0)
   except ProcessLookupError:break
   time.sleep(.1)
  else:raise SystemExit('Development process did not stop')
probe=run/'retrieve-probe.dylib'
subprocess.run(['xcrun','clang','-dynamiclib','-fobjc-arc','-framework','Cocoa',str(root/'tools/probe-cget-independent.m'),'-o',str(probe)],check=True)
entitlements=plistlib.loads((root/'build/Development/entitlements.plist').read_bytes())
entitlements['com.apple.security.cs.allow-dyld-environment-variables']=True
entpath=run/'probe-entitlements.plist';entpath.write_bytes(plistlib.dumps(entitlements))
subprocess.run(['/usr/bin/codesign','--force','--sign','-','--options','runtime','--entitlements',str(entpath),str(app)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
with socket.socket() as listener:
 listener.bind(('127.0.0.1',0));port=listener.getsockname()[1]
with socket.socket() as listener:
 listener.bind(('127.0.0.1',0));listener_port=listener.getsockname()[1]
server=[sys.executable,str(root/('tools/serve-cmove-fixture.py' if move else 'tools/serve-cget-fixture.py')),str(run/'peer'),'--port',str(port)]
if move:server+=['--destination-port',str(listener_port)]
if mode=='failure':server+=['--refuse','3','--refuse','6'] if move else ['--fail-instance','3']
if mode.startswith('cancel'):server+=['--instance-delay','2' if mode=='cancel' else '4']
config=run/'servers.json';config.write_text(json.dumps([{'Address':'127.0.0.1','Port':port,'AETitle':'CMOVEFIX' if move else 'CGETFIX','TransferSyntax':0,'retrieveMode':0 if move else 1,'Description':'operation0'}]))
env={**os.environ,'DYLD_INSERT_LIBRARIES':str(probe),'HOROS_CGET_INDEPENDENT_PROBE':str(config),'TMPDIR':subprocess.check_output(['/usr/bin/getconf','DARWIN_USER_TEMP_DIR'],text=True).strip()}
if mode.startswith('cancel'):
 env['HOROS_CGET_CANCEL']='1';env['HOROS_CGET_CANCEL_AFTER_SECONDS']='4' if mode=='cancel' else '2'
args=[str(exe),'-DATABASELOCATION','1','-DATABASELOCATIONURL',str(run/'db'),'-DEFAULT_DATABASELOCATION','1','-DEFAULT_DATABASELOCATIONURL',str(run/'db'),'-WebPortalDatabasePath',str(run/'web.sql')]
for key,value in {'AUTOCLEANINGSPACE':'NO','AUTOCLEANINGDATE':'NO','AUTOROUTINGACTIVATED':'NO','STORESCP':'YES' if move else 'NO','USESTORESCP':'YES' if move else 'NO','TLSStoreSCP':'NO','SingleProcessMultiThreadedListener':'YES','activateCFINDSCP':'YES','activateCGETSCP':'YES','syncDICOMNodes':'NO','publishDICOMBonjour':'NO','searchDICOMBonjour':'NO','httpXMLRPCServer':'NO','checkForUpdatesPlugins':'NO','SUEnableAutomaticChecks':'NO','AETITLE':'HOROSDEV','AEPORT':str(listener_port),'DICOMTimeout':'8','DICOMConnectionTimeout':'5'}.items():args+=['-'+key,value]
with (run/'peer.log').open('w') as peerlog,(run/'horos.log').open('w') as applog:
 peer=subprocess.Popen(server,stdout=peerlog,stderr=subprocess.STDOUT)
 application=None
 try:
  for _ in range(100):
   if (run/'peer'/('cmove-sent.json' if move else 'cget-negotiation.json')).exists():break
   if peer.poll() is not None:raise RuntimeError('Fixture peer stopped')
   time.sleep(.1)
  application=subprocess.Popen(args,env=env,stdout=applog,stderr=subprocess.STDOUT)
  for _ in range(200):
   text=(run/'horos.log').read_text(errors='replace')
   if 'CGET_INDEPENDENT_WATCHDOG' in text:break
   if application.poll() is not None:raise RuntimeError('Development app stopped')
   time.sleep(.2)
  for line in text.splitlines():
   if 'CGET_' in line:print(line,flush=True)
  check_command=[sys.executable,str(root/'tools/check-cmove-arrivals.py'),str(run/'peer'),str(run/'db')] if move else [sys.executable,str(root/'tools/check-cget-independent.py'),str(run),str(run/'peer'),'--mode',mode]
  checked=subprocess.run(check_command,capture_output=True,text=True)
  (run/'check.log').write_text(checked.stdout+checked.stderr);print(checked.stdout+checked.stderr,flush=True)
  print('RUN',str(run),flush=True)
  if checked.returncode:raise SystemExit(checked.returncode)
  if move:
   assert 'CGET_REAL_LISTENER available=1' in text and 'CGET_INDEPENDENT_WATCHDOG running=0' in text
   assert 'CGET_INDEPENDENT_EXCEPTION' not in text
   ledger=json.loads((run/'peer/cmove-sent.json').read_text());assert len(ledger['moves'])==1
   for item in ledger['timeline']:
    if 'Status' in item:item['Status']=int(item['Status'])
   sent={entry['sopInstance']:entry for entry in ledger['moves'][0]['sent']}
   stored={}
   for path in (run/'db').rglob('DATABASE.noindex/**/*.dcm'):
    ds=pydicom.dcmread(path);uid=str(ds.SOPInstanceUID);assert uid not in stored
    assert np.all(ds.pixel_array==sent[uid]['number']),path
    stored[uid]=int(getattr(ds,'NumberOfFrames',1))
   expected_counts=(6,24) if mode=='complete' else (4,11) if mode=='failure' else None
   if expected_counts:assert (len(stored),sum(stored.values()))==expected_counts
   final=[item for item in ledger['timeline'] if item['event']=='C_MOVE_RSP' and item.get('Status') not in (None,0xff00)]
   assert len(final)==1
   if mode=='complete':assert final[0]['Status']==0 and 'C-MOVE incomplete:' not in text
   elif mode=='failure':assert final[0]['Status']==0xb000 and 'C-MOVE incomplete:' in text and 'CGET_NOTICE main=1' in text
   else:
    assert (len(stored)==0 if mode=='cancel-before-first' else 0<len(stored)<6)
    assert final[0]['Status']==0xfe00 and any(item['event']=='C_CANCEL_RQ' for item in ledger['timeline'])
    end=float(re.search(r'CGET_INDEPENDENT_END operation0 ([\d.]+)',text)[1]);start=float(re.search(r'CGET_INDEPENDENT_CANCEL ([\d.]+)',text)[1]);assert 0<=end-start<7
   result=dict(protocol='C-MOVE',mode=mode,objects=len(stored),frames=sum(stored.values()),pixelsChecked=True,status=final[0]['Status'])
   (run/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result),flush=True)
 finally:
  for process in (application,peer):
   if process and process.poll() is None:
    process.terminate()
    try:process.wait(timeout=10)
    except subprocess.TimeoutExpired:process.kill();process.wait()
