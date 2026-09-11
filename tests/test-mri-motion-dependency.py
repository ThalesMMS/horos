#!/usr/bin/env python3
"""fbrain/BTK is identified by source, license, pin and ABI; it is not a Horos plugin."""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
swift = (root / 'Horos/Sources/MRIMotionCorrection.swift').read_text(encoding='utf-8')
docs = (root / 'docs/mri-motion-correction-validation.md').read_text(encoding='utf-8')
needed = [
    'https://github.com/rousseau/fbrain',
    'CeCILL-B',
    '4486faf04a3a482541203a4621d078c9c7ca38c1',
    '2017-05-12',
    'PluginFilter',
    'filterImage:',
    'ITK',
    'VTK',
    'OpenMP',
    'arm64',
]
missing_swift = [item for item in needed if item not in swift]
missing_docs = [item for item in needed if item not in docs]
if missing_swift:
    raise SystemExit('FAIL: Swift dependency record missing ' + ', '.join(missing_swift))
if missing_docs:
    raise SystemExit('FAIL: validation doc missing ' + ', '.join(missing_docs))
if 'compatibleWithHorosPluginFilter = true' in swift.replace(' ', ''):
    raise SystemExit('FAIL: fbrain must not be marked compatible with PluginFilter')

code = r'''
import Foundation
let dep = MRIMotionDependency.fbrain
precondition(dep.name == "fbrain/BTK")
precondition(dep.sourceURL == "https://github.com/rousseau/fbrain")
precondition(dep.license == "CeCILL-B")
precondition(dep.commit == "4486faf04a3a482541203a4621d078c9c7ca38c1")
precondition(dep.lastPush.hasPrefix("2017-05-12"))
precondition(dep.language == "C++")
precondition(dep.libraries.contains("ITK"))
precondition(dep.libraries.contains("VTK"))
precondition(dep.libraries.contains("OpenMP"))
precondition(dep.compatibleWithHorosPluginFilter == false)
precondition(dep.abi.contains("C++"))
precondition(dep.horosPluginABI.contains("filterImage:"))
precondition(dep.horosPluginABI.contains("arm64"))
precondition(dep.costSummary.isEmpty == false)
print("PASS: fbrain pin and ABI mismatch are explicit")
'''
with tempfile.TemporaryDirectory(prefix='horos-mri-motion-dep-') as d:
    p = Path(d)
    (p / 'main.swift').write_text(code)
    subprocess.run([
        'xcrun', 'swiftc',
        str(root / 'Horos/Sources/MRIMotionCorrection.swift'),
        str(p / 'main.swift'), '-o', str(p / 'test')
    ], check=True)
    subprocess.run([str(p / 'test')], check=True)
