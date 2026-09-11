#!/usr/bin/env python3
"""Opt-in native concurrent C-STORE validation with synthetic local fixtures.

Run with a Python containing pydicom, pynetdicom, numpy and imagecodecs, after
script/build_and_run.sh --verify. Output must be an empty local-validation folder
outside the checkout. This signs only the isolated development app for the
versioned diagnostic probe, and uses only two loopback peers.
"""
from pathlib import Path
import argparse,sys,re
import pydicom,numpy as np,imagecodecs
from pydicom.encaps import generate_frames
import os,subprocess,plistlib,json,time,signal,socket,hashlib
root=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('output',type=Path)
parser.add_argument('--syntax-b', choices=('jpeg', 'jpeg2000', 'jpegls'), default='jpeg')
parser.add_argument('--jpeg2000', action='store_true', help='Include single/multiframe JPEG2000 source files')
options=parser.parse_args();run=options.output.resolve()
assert 'local-validation' in run.parts and not run.is_relative_to(root)
run.mkdir(parents=True,exist_ok=True);assert not any(run.iterdir()), 'Use an empty output directory'
os.chdir(root)
py=Path(sys.executable);app=root/'build/Development/HorosDevelopment.app';exe=app/'Contents/MacOS/Horos'
assert exe.is_file(), 'Run script/build_and_run.sh --verify first'
subprocess.run([str(py),'tools/generate-dimse-matrix-fixture.py',str(run/'input')]+(['--jpeg2000'] if options.jpeg2000 else []),stdout=subprocess.DEVNULL,check=True)
manifest=json.loads((run/'input/manifest.json').read_text());inputs=[str(run/'input'/e['file']) for e in manifest['instances']];(run/'invalid.dcm').write_bytes(b'Invalid synthetic DICOM for per-file diagnosis')
count=len(inputs);frames=sum(e['frames'] for e in manifest['instances'])
batches=[inputs[:2]+[str(run/'invalid.dcm'),str(run/'absent.dcm')]+inputs[2:],inputs]
(run/'inputs.json').write_text(json.dumps(batches))
for line in subprocess.check_output(['/bin/ps','-axo','pid=,comm='],text=True).splitlines():
 fields=line.strip().split(None,1)
 if len(fields)==2 and fields[1]==str(exe):raise RuntimeError('Another development validation is still active')
for port in (11320,11321):
 with socket.socket() as reservation:reservation.bind(('127.0.0.1',port))
probe=run/'store-probe.dylib';subprocess.run(['xcrun','clang','-dynamiclib','-fobjc-arc','-framework','Cocoa','tools/probe-parallel-stores.m','-o',str(probe)],check=True)
ent=plistlib.loads((root/'build/Development/entitlements.plist').read_bytes());ent['com.apple.security.cs.allow-dyld-environment-variables']=True
entpath=run/'store-entitlements.plist';entpath.write_bytes(plistlib.dumps(ent));subprocess.run(['codesign','--force','--sign','-','--options','runtime','--entitlements',str(entpath),str(app)],check=True,stderr=subprocess.DEVNULL)
processes=[];opened=[]
try:
 for i in range(2):
  args=[str(py),'tools/serve-store-fixture.py',str(run/f'peer-{i}'),'--port',str(11320+i),'--aetitle','STORE_B' if i else 'STORE_A','--store-to',str(run/f'received-{i}'),'--store-delay','.2']
  for sop in sorted({e['sopClass'] for e in manifest['instances']}):args+=['--accept',sop]
  log=(run/f'peer-{i}.log').open('w');opened.append(log);processes.append(subprocess.Popen(args,stdout=log,stderr=subprocess.STDOUT))
 for _ in range(100):
  if all((run/f'peer-{i}/store-results.json').exists() for i in range(2)):break
  time.sleep(.1)
 args=[str(exe)]
 for key,value in {'DATABASELOCATION':'1','DATABASELOCATIONURL':str(run/'db'),'DEFAULT_DATABASELOCATION':'1','DEFAULT_DATABASELOCATIONURL':str(run/'db'),'WebPortalDatabasePath':str(run/'web.sql'),'AUTOCLEANINGSPACE':'NO','AUTOCLEANINGDATE':'NO','AUTOROUTINGACTIVATED':'NO','STORESCP':'NO','USESTORESCP':'NO','publishDICOMBonjour':'NO','searchDICOMBonjour':'NO','httpXMLRPCServer':'NO','checkForUpdatesPlugins':'NO','SUEnableAutomaticChecks':'NO','AETITLE':'HOROSDEV','DICOMTimeout':'10','DICOMConnectionTimeout':'5','useDCMTKForJP2K':'YES'}.items():args+=['-'+key,value]
 env=dict(os.environ,DYLD_INSERT_LIBRARIES=str(probe),HOROS_STORE_PROBE=str(run),HOROS_STORE_SYNTAX_B=str({'jpeg':5,'jpeg2000':1,'jpegls':13}[options.syntax_b]),TMPDIR=subprocess.check_output(['/usr/bin/getconf','DARWIN_USER_TEMP_DIR'],text=True).strip())
 log=(run/'horos.log').open('w');opened.append(log);processes.append(subprocess.Popen(args,env=env,stdout=log,stderr=subprocess.STDOUT))
 for _ in range(250):
  text=(run/'horos.log').read_text(errors='replace')
  if 'PARALLEL_STORE_WATCHDOG' in text:break
  time.sleep(.2)
 for line in text.splitlines():
  if 'PARALLEL_STORE_' in line:print(line,flush=True)
 assert text.count('PARALLEL_STORE_WATCHDOG running=0')==2 and 'running=1' not in text
 paths=json.loads((run/'report-paths.json').read_text());assert all(sorted(paths[str(i)])==sorted(batches[i]) for i in range(2))
 durations={}
 for match in re.finditer(r'PARALLEL_STORE_(START|END) (\d) ([\d.]+)(?: sent=(\d+) failed=(\d+))?',text):
  phase,i,stamp,sent,failed=match.groups();durations.setdefault(i,{})[phase]=float(stamp)
  if phase=='END':assert (int(sent),int(failed))==((count,2) if i=='0' else (count,0))
 assert max(v['START'] for v in durations.values())<min(v['END'] for v in durations.values()), 'Sends did not overlap'
 for i in range(2):
  data=json.loads((run/f'peer-{i}/store-results.json').read_text())
  assert not data['refused'] and len(data['stored'])==count,data
  assert {e['sop_instance'] for e in data['stored']}=={e['uid'] for e in manifest['instances']}
  identity=json.loads((root/'docs/dcmtk-dimse-catalog.json').read_text())['compiled_library']['implementation_class_uid']
  assert len(data['associations'])==1 and data['associations'][0]['implementation_class_uid']==identity
  for entry in manifest['instances']:
   ds=pydicom.dcmread(run/f'received-{i}'/(entry['uid']+'.dcm'))
   assert int(getattr(ds,'NumberOfFrames',1))==entry['frames']
   if entry['pixelSHA256'] is None:
    assert ds.ContentSequence[0].TextValue=='Synthetic report: comunicação íntegra.'
   else:
    decoder={'1.2.840.10008.1.2.4.80':imagecodecs.jpegls_decode,'1.2.840.10008.1.2.4.70':imagecodecs.jpeg_decode,'1.2.840.10008.1.2.4.90':imagecodecs.jpeg2k_decode}.get(str(ds.file_meta.TransferSyntaxUID))
    pixels=np.stack([decoder(frame) for frame in generate_frames(ds.PixelData)]) if decoder else ds.pixel_array
    assert hashlib.sha256(pixels.astype('<u2').tobytes()).hexdigest()==entry['pixelSHA256'],(i,entry['file'])
 for e in manifest['instances']:assert hashlib.sha256((run/'input'/e['file']).read_bytes()).hexdigest()==e['sha256']
 result=dict(case='native-concurrent-store',objectsPerPeer=count,framesPerPeer=frames,syntaxB=options.syntax_b,invalidInputsReported=2,pixelsChecked=True,sourcesUnchanged=True,overlap=True)
 (run/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result),flush=True)
 print('RUN',run,flush=True)
finally:
 for process in reversed(processes):
  if process.poll() is None:
   process.terminate()
   try:process.wait(timeout=8)
   except subprocess.TimeoutExpired:process.kill();process.wait()
 for file in opened:file.close()
