#!/usr/bin/env python3
"""Validate real DICOM codec writes and preservation under filesystem failures.
Usage: python test-dicom-codec-write-result.py HELPER SYNTHETIC_DICOM
Requires pydicom; only temporary copies are converted.
"""
from pathlib import Path
import plistlib,shutil,subprocess,sys,tempfile
import sys
# Nothing below can run without the helper and the fixture; say so
# before looking for an interpreter that has pydicom.
if len(sys.argv) < 3:
    print('skipped: needs the built Decompress helper and a synthetic DICOM: HELPER SYNTHETIC_DICOM', file=sys.stderr)
    raise SystemExit(2)
# Re-run under an interpreter that has pydicom when this one does not, so the
# test measures the product rather than the machine it was started on.
try:
    import pydicom  # noqa: F401
except ModuleNotFoundError:
    import os
    import subprocess as _subprocess
    from pathlib import Path as _Path
    for _candidate in _Path('/private/tmp').glob('*/*/*/scratchpad/*venv*/bin/python'):
        if _subprocess.run([str(_candidate), '-c', 'import pydicom'],
                           capture_output=True).returncode == 0:
            os.execv(str(_candidate), [str(_candidate), __file__] + sys.argv[1:])
    raise SystemExit("this test needs pydicom. Create an interpreter with it:\n"
                     "  python3 -m venv /tmp/horos-dicom-venv\n"
                     "  /tmp/horos-dicom-venv/bin/python -m pip install 'pydicom>=3,<4' numpy")
import pydicom
helper=Path(sys.argv[1]).resolve();fixture=Path(sys.argv[2]).resolve()
original=fixture.read_bytes();expected=pydicom.dcmread(fixture)
with tempfile.TemporaryDirectory(prefix='horos-codec-write-') as folder:
 root=Path(folder);settings=root/'settings.plist'
 settings.write_bytes(plistlib.dumps({'DecompressMoveIfFail':False}))
 for mode in ('compress','decompressList'):
  for case in ('in-place','new','replace','blocked-target','missing-parent','read-only'):
   work=root/(mode+'-'+case);work.mkdir()
   source=work/'source.dcm';source.write_bytes(original)
   dest=work/'destination';dest.mkdir();output=dest/source.name
   if case in ('replace','read-only'):output.write_bytes(b'previous destination')
   if case=='blocked-target':output.mkdir();(output/'keep').write_bytes(b'keep')
   if case=='missing-parent':dest=dest/'missing';output=dest/source.name
   if case=='in-place':output=source
   if case=='read-only':dest.chmod(0o555)
   try:
    result=subprocess.run([str(helper),'sameAsDestination' if case=='in-place' else str(dest),'SettingsPlist',str(settings),mode,str(source)],capture_output=True,timeout=60)
   finally:
    if case=='read-only':dest.chmod(0o755)
   failed=case in ('blocked-target','missing-parent','read-only')
   assert (result.returncode!=0)==failed,(mode,case,result.returncode,result.stderr)
   if failed:
    assert source.read_bytes()==original,(mode,case,'source changed')
    if case=='blocked-target':assert (output/'keep').read_bytes()==b'keep'
    if case=='read-only':assert output.read_bytes()==b'previous destination'
   else:
    actual=pydicom.dcmread(output);assert actual.SOPInstanceUID==expected.SOPInstanceUID
    if case!='in-place':assert not source.exists()
    if mode=='compress':
     decoded=subprocess.run([str(helper),'sameAsDestination','SettingsPlist',str(settings),'decompressList',str(output)],capture_output=True,timeout=60)
     assert decoded.returncode==0
     actual=pydicom.dcmread(output)
    assert actual.PixelData==expected.PixelData
   assert not list(work.rglob('.horos-codec-*'))
   print(f'PASS {mode}/{case}')
assert fixture.read_bytes()==original
