#!/usr/bin/env python3
"""Generated ROI-volume phantoms keep IPP geometry and known square areas."""
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


def trapezoid(areas, positions):
    volume = 0.0
    for previous, current in zip(zip(areas, positions), zip(areas[1:], positions[1:])):
        volume += abs(current[1] - previous[1]) / 10.0 * (previous[0] + current[0]) / 2.0
    return volume


def square_area(pixels, value=2000):
    return float(numpy.count_nonzero(pixels == value)) / 100.0


with tempfile.TemporaryDirectory(prefix='horos-roi-volume-fix-') as folder:
    dest = Path(folder) / 'phantom'
    subprocess.run([sys.executable, str(root / 'tools/generate-roi-volume-fixture.py'),
                    str(dest)], check=True)

    regular = [pydicom.dcmread(path) for path in sorted((dest / 'regular').glob('*.dcm'))]
    assert [float(ds.ImagePositionPatient[2]) for ds in regular] == [0, 2, 4, 6, 8]
    assert all(float(ds.SpacingBetweenSlices) == 2 for ds in regular)
    areas = [square_area(ds.pixel_array) for ds in regular]
    assert areas == [1, 1, 1, 1, 1]
    assert abs(trapezoid(areas, [0, 2, 4, 6, 8]) - 0.8) < 1e-9

    uneven = [pydicom.dcmread(path) for path in sorted((dest / 'uneven').glob('*.dcm'))]
    zs = [float(ds.ImagePositionPatient[2]) for ds in uneven]
    assert zs == [0, 2, 8]
    assert abs(trapezoid([1, 1, 1], zs) - 0.8) < 1e-9

    gap = [pydicom.dcmread(path) for path in sorted((dest / 'gap').glob('*.dcm'))]
    gap_z = [float(ds.ImagePositionPatient[2]) for ds in gap]
    assert gap_z == [0, 2, 4, 6]
    occupied = [(square_area(ds.pixel_array), z) for ds, z in zip(gap, gap_z)
                if square_area(ds.pixel_array) > 0]
    assert occupied == [(1.0, 0.0), (1.0, 6.0)]
    assert abs(trapezoid([1, 1], [0, 6]) - 0.6) < 1e-9

    lie = [pydicom.dcmread(path) for path in sorted((dest / 'sbs-lie').glob('*.dcm'))]
    assert [float(ds.ImagePositionPatient[2]) for ds in lie] == [0, 2, 4, 6, 8]
    assert all(float(ds.SpacingBetweenSlices) == 99 for ds in lie)
    assert abs(trapezoid([1] * 5, [0, 2, 4, 6, 8]) - 0.8) < 1e-9
    index_volume = trapezoid([1] * 5, [i * 99 for i in range(5)])
    assert abs(index_volume - 0.8) > 1

    disconnected = [pydicom.dcmread(path) for path in sorted((dest / 'disconnected').glob('*.dcm'))]
    assert [float(ds.ImagePositionPatient[2]) for ds in disconnected] == [0, 5]
    assert [square_area(ds.pixel_array) for ds in disconnected] == [0.5, 0.5]
    assert abs(trapezoid([0.5, 0.5], [0, 5]) - 0.25) < 1e-9

print('PASS: fixture IPP/areas match regular 0.8, uneven 0.8, gap 0.6, disconnected 0.25; SBS 99 is a lie')
