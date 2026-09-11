#!/usr/bin/env python3
"""The versioned inter-slice phantom keeps known marker positions and mm geometry."""
import math
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    import numpy
    import pydicom
except ImportError as error:
    print('need pydicom and numpy to read the generated phantom:', error, file=sys.stderr)
    sys.exit(2)

root = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='horos-interslice-fix-') as folder:
    dest = Path(folder) / 'phantom'
    subprocess.run([sys.executable, str(root / 'tools/generate-interslice-measure-fixture.py'),
                    str(dest), '--spacing', '5'], check=True)
    first = pydicom.dcmread(dest / 'slice-1.dcm')
    second = pydicom.dcmread(dest / 'slice-2.dcm')
    assert list(first.ImageOrientationPatient) == [1.0, 0.0, 0.0, 0.0, 1.0, 0.0]
    assert list(second.ImageOrientationPatient) == list(first.ImageOrientationPatient)
    assert [float(v) for v in first.ImagePositionPatient] == [0.0, 0.0, 0.0]
    assert [float(v) for v in second.ImagePositionPatient] == [0.0, 0.0, 5.0]
    pixels_a = first.pixel_array
    pixels_b = second.pixel_array
    assert pixels_a[0, 10] == 2000 and pixels_b[20, 10] == 2000
    # Pixel-center conversion used by the viewer: both markers shift by the same 0.5 px.
    a = (10 - 0.5, 0 - 0.5, 0.0)
    b = (10 - 0.5, 20 - 0.5, 5.0)
    proj = math.hypot(b[0] - a[0], b[1] - a[1])
    dist = math.hypot(proj, b[2] - a[2])
    assert abs(proj - 20.0) < 1e-9
    assert abs(dist - math.sqrt(425)) < 1e-9
    assert dist != proj
print('PASS: generated axial phantom has known markers; 20 mm proj != 3D')
