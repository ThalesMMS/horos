#!/usr/bin/env python3
"""The delta manifest describes the repository it ships with (#610).

`docs/donor-delta3-manifest.json` records which origin commits were read,
which workbench commits carry the adoption, what each delivery decided and what
stands behind it. It is written for a possible later incorporation, and a
record that drifts from the tree is worse than none: this regenerates it and
compares.
"""
from pathlib import Path
import json
import subprocess

root = Path(__file__).resolve().parents[1]
manifest = root / 'docs/donor-delta3-manifest.json'
failures = []

if not manifest.exists():
    failures.append('the delta manifest is missing')
else:
    record = json.loads(manifest.read_text())
    if record.get('published') is not False:
        failures.append('the manifest claims the delta was published; this phase does not push anything')
    for delivery in record.get('deliveries', []):
        for path in delivery.get('sources', []) + delivery.get('tests', []) + [delivery.get('document', '')]:
            if path and not (root / path).exists():
                failures.append('#%s names %s, which is not in the tree' % (delivery['issue'], path))
    issues = sorted(delivery['issue'] for delivery in record.get('deliveries', []))
    if issues != list(range(603, 611)):
        failures.append('the manifest does not cover #603 to #610: %s' % issues)
    if not record.get('excluded'):
        failures.append('the manifest records nothing as excluded, which cannot be right')
    check = subprocess.run(['python3', str(root / 'tools/write-delta3-manifest.py'), '--check'],
                           capture_output=True, text=True)
    if check.returncode != 0:
        failures.append((check.stdout + check.stderr).strip() or 'the manifest does not match the repository')

if failures:
    for failure in failures:
        print('FAIL:', failure)
    raise SystemExit(1)
print('ok: the delta manifest matches the tree it describes')
