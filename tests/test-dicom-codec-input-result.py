#!/usr/bin/env python3
"""Run a built codec helper against disposable valid and unreadable inputs.

Usage: python test-dicom-codec-input-result.py HELPER SYNTHETIC_DICOM [jpeg2000|default]
Requires pydicom. The supplied fixture is copied and never modified.
"""
from pathlib import Path
import plistlib,shutil,subprocess,sys,tempfile
import sys
# Nothing below can run without the helper and the fixture; say so
# before looking for an interpreter that has pydicom.
if len(sys.argv) < 3:
    print('skipped: needs the built Decompress helper and a synthetic DICOM: HELPER SYNTHETIC_DICOM [jpeg2000|default]', file=sys.stderr)
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
helper=Path(sys.argv[1]).resolve()
fixture=Path(sys.argv[2]).resolve()
codec_mode=sys.argv[3] if len(sys.argv)>3 else 'jpeg'
if codec_mode not in ('jpeg','jpeg2000','default'):raise SystemExit('Unknown codec mode')
jpeg2000=codec_mode!='jpeg'
original=fixture.read_bytes()
expected=pydicom.dcmread(fixture)
with tempfile.TemporaryDirectory(prefix='horos-codec-input-') as folder:
 root=Path(folder)
 settings=root/'settings.plist'
 codec=[{'modality':'default','compression':3 if jpeg2000 else 2,'quality':0}]
 options={'DecompressMoveIfFail':False}
 if codec_mode!='default':options.update(CompressionSettings=codec,CompressionSettingsLowRes=codec)
 settings.write_bytes(plistlib.dumps(options))
 for mode in ('compress','decompressList'):
  for case in ('valid','missing','invalid','invalid-valid','valid-invalid'):
   case_dir=root/(mode+'-'+case);case_dir.mkdir()
   valid=case_dir/'valid.dcm';shutil.copyfile(fixture,valid)
   invalid=case_dir/'invalid.dcm';invalid.write_bytes(b'Invalid test input\n')
   missing=case_dir/'missing.dcm'
   paths={'valid':[valid],'missing':[missing],'invalid':[invalid],
          'invalid-valid':[invalid,valid],'valid-invalid':[valid,invalid]}[case]
   result=subprocess.run([str(helper),'sameAsDestination','SettingsPlist',str(settings),mode,*map(str,paths)],capture_output=True,timeout=60)
   if (result.returncode==0)!=(case=='valid'):
    raise AssertionError(f'{mode}/{case}: unexpected exit {result.returncode}: {result.stderr.decode(errors="replace")}')
   assert invalid.read_bytes()==b'Invalid test input\n'
   assert not missing.exists()
   if valid in paths:
    actual=pydicom.dcmread(valid)
    assert actual.SOPInstanceUID==expected.SOPInstanceUID
    assert actual.Rows==expected.Rows and actual.Columns==expected.Columns
    if mode=='compress':
     assert actual.file_meta.TransferSyntaxUID==('1.2.840.10008.1.2.4.90' if jpeg2000 else '1.2.840.10008.1.2.4.70')
     decoded=subprocess.run([str(helper),'sameAsDestination','SettingsPlist',str(settings),'decompressList',str(valid)],capture_output=True,timeout=60)
     assert decoded.returncode==0
     actual=pydicom.dcmread(valid)
    assert actual.PixelData==expected.PixelData
   print(f'PASS {mode}/{case}: exit {result.returncode}')
assert fixture.read_bytes()==original
