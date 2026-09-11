#!/usr/bin/env python3
"""Menu titles built in code must be catalog keys in every localized catalog."""
from pathlib import Path
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
tool = root / 'tools/collect-menu-strings.py'

# A title the sources pass to NSLocalizedString is invisible to the nib
# generator, and the English catalog never needs it, so nothing else reports
# that it stayed English in Italian and Spanish.
subprocess.run([sys.executable, str(tool), '--check'], check=True)

listed = subprocess.check_output([sys.executable, str(tool)], text=True).splitlines()
titles = {line.split('\t')[0] for line in listed if line}
assert 'Export ROIs as JSON...' in titles, 'Objective-C menu titles are not being collected'
assert 'Automatic Cleanup Preview' in titles, 'Swift window titles are not being collected'
assert 'Network Access…' in titles, 'A UTF-8 ellipsis must survive collection'
assert 'TBD' not in titles, 'A commented-out menu item builds nothing'
assert 'iPhoto' not in titles, 'Product names are exempt'
print(f'PASS: {len(titles)} code-built menu titles present in the Italian and Spanish catalogs')
