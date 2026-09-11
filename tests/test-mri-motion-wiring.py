#!/usr/bin/env python3
"""Motion MRI PoC is in the app target and does not touch other fronts or fbrain."""
from pathlib import Path

root = Path(__file__).resolve().parents[1]
pbx = (root / 'Horos.xcodeproj/project.pbxproj').read_text(encoding='utf-8')
if 'MRIMotionCorrection.swift in Sources' not in pbx:
    raise SystemExit('FAIL: MRIMotionCorrection.swift is not in the app target')
if 'MRIMotionCorrection.swift */' not in pbx:
    raise SystemExit('FAIL: MRIMotionCorrection.swift has no file reference')

xib = (root / 'Horos/Resources/en.lproj/Viewer.xib').read_text(encoding='latin1', errors='replace')
for needle in ('MRIMotion', 'fbrain', 'Baby Brain', 'motion correction'):
    if needle.lower() in xib.lower():
        raise SystemExit('FAIL: Viewer.xib must stay untouched by motion MRI')

forbidden = [
    'Horos/Sources/ViewerReferenceLines.swift',
    'Horos/Sources/ViewerReferenceLines.m',
    'Horos/Sources/MailDraftComposer.swift',
    'Horos/Sources/QuicktimeExport.m',
    'Horos/Sources/QuicktimeExport.h',
]
for relative in forbidden:
    path = root / relative
    if not path.is_file():
        continue
    text = path.read_text(encoding='latin1', errors='replace')
    if 'MRIMotion' in text or 'fbrain' in text:
        raise SystemExit(f'FAIL: {relative} must not take motion MRI code')

vendored = [
    root / 'fbrain',
    root / 'BTK',
    root / 'Horos/Sources/fbrain',
    root / 'Horos/Plugins/fbrain',
]
if any(path.exists() for path in vendored):
    raise SystemExit('FAIL: fbrain/BTK must not be vendored')

manager = (root / 'Horos/Sources/PluginManager.m').read_text(encoding='latin1', errors='replace')
if 'fbrain' in manager or 'MRIMotionCorrection' in manager:
    raise SystemExit('FAIL: PluginManager must not register an MRI motion plugin')

print('PASS: motion MRI is a Swift PoC in the app target, not a vendored plugin')
