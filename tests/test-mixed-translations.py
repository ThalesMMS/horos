#!/usr/bin/env python3
"""No catalog value is half English (#638).

Some Spanish entries had been made by replacing words one at a time: "The remote
database index está empty.", "Sin se puede decompress images in a distant database."
The sentence stayed half English, and sometimes said the opposite of the original.

`tools/inventory-mixed-translations.py` reports a value that carries an English word
no Spanish sentence has. It runs here over the Spanish catalog; against the catalog
before the translation pass it reported 436 of its 2787 entries.

The Italian catalog is not checked: Italian shares the short words the inventory
looks for ("in", "a", "e"), so the same list says nothing there.
"""
from pathlib import Path
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
run = subprocess.run([sys.executable, str(root / 'tools/inventory-mixed-translations.py'),
                      '--language', 'es', '--check'], capture_output=True, text=True)
if run.returncode != 0:
    print((run.stdout + run.stderr).strip()[-3000:])
    raise SystemExit(1)
print(run.stdout.strip().splitlines()[-1])
