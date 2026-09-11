#!/usr/bin/env python3
"""Exercise real helper extraction with temporary archives; argument: HELPER."""
from pathlib import Path
import subprocess,sys,tempfile,zipfile
if len(sys.argv) < 2:
    print('skipped: needs the built Decompress helper: HELPER', file=sys.stderr)
    raise SystemExit(2)
helper=Path(sys.argv[1]).resolve()
with tempfile.TemporaryDirectory(prefix='horos-extraction-') as folder:
 root=Path(folder)
 for mode in ('compress','decompressList'):
  for case in ('new','existing-directory','existing-file','invalid','read-only','same-path'):
   work=root/(mode+'-'+case);work.mkdir();source=work/'test.zip'
   with zipfile.ZipFile(source,'w') as z:z.writestr('nested/test.txt',b'extracted bytes')
   if case=='invalid':source.write_bytes(b'Invalid archive')
   original=source.read_bytes();dest=work/'destination';dest.mkdir();output=dest/source.name
   if case in ('existing-directory','invalid'):output.mkdir();(output/'keep').write_bytes(b'keep')
   if case=='existing-file':output.write_bytes(b'old')
   if case=='same-path':dest=work;output=source
   if case=='read-only':dest.chmod(0o555)
   try:r=subprocess.run([str(helper),str(dest),mode,str(source)],capture_output=True,timeout=60)
   finally:
    if case=='read-only':dest.chmod(0o755)
   failed=case in ('invalid','read-only')
   assert (r.returncode!=0)==failed,(mode,case,r.returncode,r.stderr)
   if failed:
    if case=='invalid':
     assert Path(str(output)+'.horos-unexpanded').read_bytes()==original
     assert not source.exists()
     assert (output/'keep').read_bytes()==b'keep'
    else:assert source.read_bytes()==original
   else:
    assert (output/'nested/test.txt').read_bytes()==b'extracted bytes'
    assert not (output/'keep').exists()
    if case!='same-path':assert not source.exists()
   assert not list(work.rglob('.horos-extract-*'))
   print('PASS',mode,case)
