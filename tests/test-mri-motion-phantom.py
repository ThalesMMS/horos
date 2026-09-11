#!/usr/bin/env python3
"""The motion phantom generator writes a known-shift stack and refuses a dirty folder."""
from pathlib import Path
import json
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
generator = root / 'tools/generate-mri-motion-phantom.py'
if not generator.is_file():
    raise SystemExit('FAIL: tools/generate-mri-motion-phantom.py is missing')

with tempfile.TemporaryDirectory(prefix='horos-mri-motion-ph-') as d:
    out = Path(d) / 'phantom'
    build = subprocess.run(
        [sys.executable, str(generator), str(out), '--size', '32', '--radius', '7'],
        capture_output=True, text=True)
    if build.returncode:
        print(build.stderr.strip()[-1500:], file=sys.stderr)
        raise SystemExit('FAIL: phantom generator failed')
    manifest = json.loads((out / 'manifest.json').read_text())
    for key in ('width', 'height', 'spacing_mm', 'center', 'radius', 'shifts_px',
                'foreground', 'background', 'slices', 'method', 'adopted'):
        if key not in manifest:
            raise SystemExit(f'FAIL: manifest missing {key}')
    if manifest['width'] != 32 or manifest['height'] != 32:
        raise SystemExit('FAIL: phantom size is not the requested 32')
    if manifest['adopted'] is not False:
        raise SystemExit('FAIL: phantom must not claim fbrain adoption')
    if manifest['method'] != 'ncc-integer':
        raise SystemExit('FAIL: phantom method must match the PoC')
    if manifest['shifts_px'][0] != [0, 0]:
        raise SystemExit('FAIL: first slice must be the unshifted reference')
    if len(manifest['slices']) != len(manifest['shifts_px']):
        raise SystemExit('FAIL: slice files and shifts disagree')
    for relative, shift in zip(manifest['slices'], manifest['shifts_px']):
        pgm = out / relative
        if not pgm.is_file():
            raise SystemExit(f'FAIL: missing {relative}')
        lines = pgm.read_text().splitlines()
        if lines[0] != 'P2':
            raise SystemExit(f'FAIL: {relative} is not an ASCII PGM')
        dims = [int(part) for part in lines[2].split()]
        if dims != [32, 32]:
            raise SystemExit(f'FAIL: {relative} dimensions {dims}')
        pixels = [int(part) for part in ' '.join(lines[4:]).split()]
        if len(pixels) != 32 * 32:
            raise SystemExit(f'FAIL: {relative} pixel count {len(pixels)}')
        # The bright disk must move with the recorded shift.
        cx, cy = manifest['center']
        dx, dy = shift
        x = int(round(cx + dx))
        y = int(round(cy + dy))
        if pixels[y * 32 + x] < manifest['foreground'] / 2:
            raise SystemExit(f'FAIL: disk is not at the shifted centre of {relative}')
    dirty = subprocess.run(
        [sys.executable, str(generator), str(out)],
        capture_output=True, text=True)
    if dirty.returncode == 0:
        raise SystemExit('FAIL: generator overwrote a non-empty folder')

print('PASS: synthetic motion phantom records known shifts and stays local')
