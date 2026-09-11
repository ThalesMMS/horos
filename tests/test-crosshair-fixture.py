#!/usr/bin/env python3
"""Validate the DICOM geometry shared by the A295 native crosshair cases."""
from pathlib import Path
import subprocess
import sys
import tempfile

try:
    import numpy as np
    import pydicom
except ImportError:
    print('Requires Python with pydicom and numpy (use the local fixture venv)', file=sys.stderr)
    raise SystemExit(2)

root = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='horos-crosshair-fixture-') as temporary:
    records = {}
    for label, flags, count in [('orthogonal', [], 64), ('parallel', ['--parallel-pair'], 48),
                                 ('oblique', ['--oblique'], 16)]:
        folder = Path(temporary) / label
        subprocess.run([sys.executable, str(root/'tools/generate-cross-reference-fixture.py'),
                        str(folder), *flags], check=True, capture_output=True)
        files = list(folder.glob('*.dcm'))
        assert len(files) == count
        for path in files:
            ds = pydicom.dcmread(path)
            records.setdefault(int(ds.SeriesNumber), []).append(ds)
    assert set(records) == set(range(1, 9))
    all_images = [ds for group in records.values() for ds in group]
    assert len({ds.SOPInstanceUID for ds in all_images}) == 128
    assert len({ds.StudyInstanceUID for ds in all_images}) == 1
    common = records[1][0].FrameOfReferenceUID
    assert all(records[n][0].FrameOfReferenceUID == common for n in [2, 3, 5, 6, 8])
    assert records[4][0].FrameOfReferenceUID != common
    assert records[7][0].FrameOfReferenceUID != common

    point = np.array([8., 8., 8.])
    for number, group in records.items():
        group.sort(key=lambda ds: int(ds.InstanceNumber))
        assert [int(ds.InstanceNumber) for ds in group] == list(range(1, 17))
        nearest = []
        for ds in group:
            iop = np.array(ds.ImageOrientationPatient, dtype=float)
            column_step, row_step = iop[:3], iop[3:]
            normal = np.cross(column_step, row_step)
            basis = np.column_stack([column_step, row_step, normal])
            assert np.allclose(basis.T@basis, np.eye(3), atol=1e-8, rtol=0)
            assert abs(np.linalg.det(basis)-1) < 1e-8
            origin = np.array(ds.ImagePositionPatient, dtype=float)
            local = basis.T@(point-origin)
            assert 0 <= local[0] <= 31 and 0 <= local[1] <= 31
            nearest.append(abs(local[2]))
            yy, xx = np.mgrid[:32, :32]
            patient = origin + xx[..., None]*column_step + yy[..., None]*row_step
            expected = patient@np.array([1, 2, 3]) + (256 if number == 8 else 0)
            pixels = np.frombuffer(ds.PixelData, dtype='<u2').reshape(32, 32)
            assert np.max(np.abs(pixels-expected)) <= (0.500001 if number == 8 else 1e-8)
            if number == 8:
                assert float(ds.WindowCenter)-float(ds.WindowWidth)/2 < pixels.mean() < float(ds.WindowCenter)+float(ds.WindowWidth)/2
                assert abs(normal[0]) > 0.5 and abs(normal[2]) > 0.5
        assert np.argmin(nearest) == 8 and min(nearest) < 1e-8
        if number == 8:
            ds = group[8]
            iop = np.array(ds.ImageOrientationPatient, dtype=float)
            centre = np.array(ds.ImagePositionPatient, dtype=float) + 15.5*(iop[:3]+iop[3:])
            assert np.allclose(centre, point, atol=1e-8, rtol=0)

print('PASS: 128 MR images, unique identities, frame controls, orthogonal/oblique bases, shared landmark and patient-space intensity field')
