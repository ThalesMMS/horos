#!/usr/bin/env python3
"""Run the built helper's no-conversion relocation branches on temporary files.
Usage: python test-dicom-codec-relocation.py HELPER SYNTHETIC_DICOM
"""
from pathlib import Path
import plistlib,subprocess,sys,tempfile
if len(sys.argv) < 3:
    print('skipped: needs the built Decompress helper and a synthetic DICOM: HELPER SYNTHETIC_DICOM', file=sys.stderr)
    raise SystemExit(2)
helper=Path(sys.argv[1]).resolve();fixture=Path(sys.argv[2]).resolve();original=fixture.read_bytes()
with tempfile.TemporaryDirectory(prefix='horos-codec-relocation-') as folder:
 root=Path(folder)
 for mode in ('uncompressed','already-compressed','invalid-fallback'):
  settings=root/(mode+'.plist')
  codec=[{'modality':'default','compression':1 if mode=='uncompressed' else 3,'quality':0}]
  settings.write_bytes(plistlib.dumps({'CompressionSettings':codec,'CompressionSettingsLowRes':codec,'DecompressMoveIfFail':mode=='invalid-fallback'}))
  payload=original
  if mode=='already-compressed':
   seed=root/'seed.dcm';seed.write_bytes(original)
   subprocess.run([str(helper),'sameAsDestination','SettingsPlist',str(settings),'compress',str(seed)],check=True,capture_output=True)
   payload=seed.read_bytes();assert payload!=original
  if mode=='invalid-fallback':payload=b'Invalid test input\n'
  for case in ('new','replace','blocked-target','missing-parent','read-only','same-path'):
   work=root/(mode+'-'+case);work.mkdir();source=work/'source.dcm';source.write_bytes(payload)
   destination=work/'destination';destination.mkdir();output=destination/source.name
   if case in ('replace','read-only'):output.write_bytes(b'old destination')
   if case=='blocked-target':output.mkdir();(output/'keep').write_bytes(b'keep')
   if case=='missing-parent':destination=destination/'missing';output=destination/source.name
   if case=='same-path':destination=work;output=source
   if case=='read-only':destination.chmod(0o555)
   try:
    result=subprocess.run([str(helper),str(destination),'SettingsPlist',str(settings),'compress',str(source)],capture_output=True,timeout=60)
   finally:
    if case=='read-only':destination.chmod(0o755)
   failed=case in ('blocked-target','missing-parent','read-only')
   assert (result.returncode!=0)==(failed or mode=='invalid-fallback'),(mode,case,result.returncode,result.stderr)
   if failed:
    assert source.read_bytes()==payload
    if case=='blocked-target':assert (output/'keep').read_bytes()==b'keep'
    if case=='read-only':assert output.read_bytes()==b'old destination'
   else:
    assert output.read_bytes()==payload
    assert source.exists()==(case=='same-path')
   assert not list(work.rglob('.horos-move-*'))
   print(f'PASS {mode}/{case}')
assert fixture.read_bytes()==original
