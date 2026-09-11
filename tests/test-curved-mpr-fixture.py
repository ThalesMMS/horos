#!/usr/bin/env python3
"""Shared volume-geometry fixtures classify as isotropic, anisotropic, incomplete or invalid."""
from pathlib import Path
import subprocess
import sys
import tempfile
root = Path(__file__).resolve().parents[1]
try:
    import numpy  # noqa: F401
    import pydicom
except ImportError:
    print('needs pydicom and numpy to generate the shared volume fixture', file=sys.stderr)
    sys.exit(2)

destination = Path(tempfile.mkdtemp(prefix='horos-curved-mpr-fixture-'))
subprocess.run([
    sys.executable, str(root / 'tools/generate-volume-geometry-fixture.py'),
    str(destination), '--also-isotropic'
], check=True)


def series_files(prefix):
    return sorted(destination.glob(prefix + '-*.dcm'))


def diagnose(files, orientation_count):
    first = pydicom.dcmread(str(files[0]), stop_before_pixels=True)
    zs = []
    for path in files:
        ds = pydicom.dcmread(str(path), stop_before_pixels=True)
        zs.append(float(ds.ImagePositionPatient[2]))
    code = r'''
import Foundation
let zs: [NSNumber] = [%s]
let phase = CurvedMPRPathSession.diagnoseVolume(
    pixelSpacingX: %s, spacingY: %s, slicePositions: zs, orientationCount: %d)
print(phase)
''' % (', '.join(str(z) for z in zs),
       float(first.PixelSpacing[0]), float(first.PixelSpacing[1]),
       orientation_count)
    with tempfile.TemporaryDirectory(prefix='horos-curved-mpr-phase-') as d:
        p = Path(d)
        (p / 'main.swift').write_text(code)
        subprocess.run([
            'xcrun', 'swiftc',
            str(root / 'Horos/Sources/CurvedMPRPath.swift'),
            str(p / 'main.swift'), '-o', str(p / 'test')
        ], check=True)
        return subprocess.check_output([str(p / 'test')], text=True).strip()

cases = [
    ('isotropic', 1, 'isotropic'),
    ('regular', 1, 'anisotropic'),
    ('gap', 1, 'incomplete'),
    ('tilted', 2, 'invalid'),
]
for prefix, orientations, want in cases:
    files = series_files(prefix)
    if not files:
        print('FAIL: missing generated series', prefix, file=sys.stderr)
        sys.exit(1)
    got = diagnose(files, orientations)
    if got != want:
        print('FAIL:', prefix, 'got', got, 'want', want, file=sys.stderr)
        sys.exit(1)
print('PASS: shared fixtures diagnose isotropic, anisotropic, incomplete and invalid')
