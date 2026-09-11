#!/usr/bin/env python3
"""Audit every executable a built bundle ships (#385 release gate).

Reports, for each Mach-O inside the bundle, the architectures it carries and
whether it is signed; and, for the bundle itself, the minimum system version,
the update feed and the code-signing flags. Reads only; it signs nothing and
changes nothing.

    python3 tools/audit-release-bundle.py path/to/Horos.app [--json OUT]
"""
import argparse
import json
import plistlib
import re
import subprocess
from pathlib import Path

MACHO = (b'\xcf\xfa\xed\xfe', b'\xce\xfa\xed\xfe', b'\xca\xfe\xba\xbe', b'\xbe\xba\xfe\xca')

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('bundle', type=Path)
parser.add_argument('--json', type=Path, default=None)
parser.add_argument('--expect-arch', default='arm64')
args = parser.parse_args()
if not (args.bundle / 'Contents').is_dir():
    parser.error('not an application bundle: ' + str(args.bundle))

info = plistlib.loads((args.bundle / 'Contents/Info.plist').read_bytes())
report = {
    'bundle': str(args.bundle),
    'identifier': info.get('CFBundleIdentifier', ''),
    'version': info.get('CFBundleShortVersionString', ''),
    'minimumSystemVersion': info.get('LSMinimumSystemVersion', ''),
    'updateFeed': info.get('SUFeedURL', ''),
    'automaticChecks': info.get('SUEnableAutomaticChecks', None),
    'binaries': [],
}

def archs(path):
    result = subprocess.run(['lipo', '-archs', str(path)], capture_output=True, text=True)
    return result.stdout.split()

def signature(path):
    result = subprocess.run(['codesign', '-dv', str(path)], capture_output=True, text=True)
    text = result.stdout + result.stderr
    if 'code object is not signed' in text:
        return {'signed': False, 'authority': '', 'flags': ''}
    authority = re.search(r'^Authority=(.+)$', text, re.M)
    flags = re.search(r'^CodeDirectory .*flags=(\S+)', text, re.M)
    return {'signed': True,
            'authority': authority.group(1) if authority else ('adhoc' if 'adhoc' in text else ''),
            'flags': flags.group(1) if flags else ''}

for path in sorted(args.bundle.rglob('*')):
    if not path.is_file() or path.is_symlink():
        continue
    try:
        head = path.open('rb').read(4)
    except OSError:
        continue
    if head not in MACHO:
        continue
    found = archs(path)
    report['binaries'].append({
        'path': str(path.relative_to(args.bundle)),
        'archs': found,
        'hasExpected': args.expect_arch in found,
        'foreignOnly': bool(found) and args.expect_arch not in found,
        **signature(path),
    })

report['binaryCount'] = len(report['binaries'])
report['withExpectedArch'] = sum(item['hasExpected'] for item in report['binaries'])
report['foreignOnly'] = [item['path'] for item in report['binaries'] if item['foreignOnly']]
report['unsigned'] = [item['path'] for item in report['binaries'] if not item['signed']]
report['architectures'] = sorted({arch for item in report['binaries'] for arch in item['archs']})

if args.json:
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(report, indent=1) + '\n')
print(json.dumps({k: v for k, v in report.items() if k != 'binaries'}, indent=1))
