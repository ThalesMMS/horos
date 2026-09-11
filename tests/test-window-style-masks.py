#!/usr/bin/env python3
"""Verify no shipped nib declares the deprecated textured window or a forbidden content border."""
from pathlib import Path
import plistlib,subprocess,sys,tempfile
root=Path(__file__).resolve().parents[1]
nibs=sorted((root/'Horos/Resources').glob('*.lproj/*.xib'))
assert nibs, 'no localized nibs found'
textured=[n for n in nibs if b'texturedBackground' in n.read_bytes()]
assert not textured, 'textured window masks remain: '+', '.join(n.name for n in textured)
# A regular-border window with an explicit content border raises at runtime; AppKit
# only supported that pairing on textured windows.
bordered=[n for n in nibs if b'<contentBorderThickness' in n.read_bytes()]
assert not bordered, 'explicit content borders remain: '+', '.join(str(n) for n in bordered)
if not (root/'Horos/Resources/en.lproj/Viewer.xib').exists():
    sys.exit(2)
try:
    subprocess.run(['xcrun','--find','ibtool'],check=True,capture_output=True)
except (subprocess.CalledProcessError,FileNotFoundError):
    print('skipped: needs ibtool: IBTOOL'); sys.exit(2)
# ibtool refuses the forbidden pairing, so compiling is the check that matters.
checked=[]
with tempfile.TemporaryDirectory(prefix='horos-style-masks-') as tmp:
    for nib in nibs:
        out=Path(tmp)/(nib.parent.name+'-'+nib.stem+'.nib')
        result=subprocess.run(['ibtool','--errors','--compile',str(out),str(nib)],capture_output=True)
        report=plistlib.loads(result.stdout) if result.stdout.startswith(b'<?xml') else {}
        errors=report.get('com.apple.ibtool.document.errors') or {}
        assert result.returncode==0 and not errors, f'{nib} did not compile: {errors}'
        checked.append(nib.name)
print(f'PASS: {len(checked)} nibs compile with no textured mask and no explicit content border')
