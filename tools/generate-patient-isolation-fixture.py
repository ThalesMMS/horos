#!/usr/bin/env python3
"""Generate marked synthetic MR stacks in two interleaved import batches."""
import argparse
import hashlib
import json
from pathlib import Path
import runpy

import numpy as np
from pydicom.uid import MRImageStorage, generate_uid


def generate(output, patients):
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        raise ValueError('Use an empty output directory')
    base = runpy.run_path(str(Path(__file__).with_name('generate-jpeg-series-fixture.py')))
    records = []
    for patient in range(1, patients + 1):
        study, frame = generate_uid(), generate_uid()
        for series in (1, 2):
            series_uid = generate_uid()
            for instance in range(1, 9):
                # Identical basenames across patients/series exercise path identity.
                batch = 'first' if instance % 2 else 'second'
                path = output / batch / f'patient-{patient:02}' / f'series-{series}' / f'{instance:02}.dcm'
                path.parent.mkdir(parents=True, exist_ok=True)
                ds = base['dataset'](path, 'patient-isolation', False)
                ds.SOPClassUID = ds.file_meta.MediaStorageSOPClassUID = MRImageStorage
                ds.SOPInstanceUID = ds.file_meta.MediaStorageSOPInstanceUID = generate_uid()
                ds.StudyInstanceUID, ds.SeriesInstanceUID = study, series_uid
                ds.FrameOfReferenceUID = frame
                ds.PatientName = f'QA^Isolation{patient:02}'
                ds.PatientID = f'LOCAL-ISOLATION-{patient:02}'
                ds.StudyDescription = 'Synthetic Patient Isolation'
                ds.StudyID = f'ISOLATE{patient:02}'
                ds.SeriesDescription = f'Isolation stack {series}'
                ds.SeriesNumber, ds.InstanceNumber = series, instance
                ds.Modality = 'MR'
                ds.ImageType = ['ORIGINAL', 'PRIMARY', 'OTHER']
                del ds.ConversionType
                ds.Rows = ds.Columns = 128
                ds.BitsAllocated = ds.BitsStored = 16
                ds.HighBit = 15
                ds.ImageOrientationPatient = [1, 0, 0, 0, 1, 0]
                ds.ImagePositionPatient = [0, 0, instance * 2]
                ds.PixelSpacing = [1, 1]
                ds.SliceThickness = ds.SpacingBetweenSlices = 2
                ds.RescaleIntercept, ds.RescaleSlope = 0, 1
                ds.WindowCenter, ds.WindowWidth = 2048, 4096
                # Exact numeric identity plus visible binary patient and slice bars.
                pixels = np.full((128, 128), patient * 64 + series * 16 + instance, dtype='<u2')
                for bit in range(6):
                    pixels[24:48, 16 + bit * 16:28 + bit * 16] = 3800 if patient & (1 << bit) else 200
                pixels[56:72, 16:16 + series * 40] = 3500
                pixels[88:104, 16:16 + instance * 12] = 3000
                ds.PixelData = pixels.tobytes()
                ds.save_as(path, enforce_file_format=True)
                records.append(dict(path=str(path.relative_to(output)), patient=str(ds.PatientID),
                                    study=study, series=series_uid, sop=str(ds.SOPInstanceUID),
                                    instance=instance, marker=int(pixels[0, 0]),
                                    pixels_sha256=hashlib.sha256(ds.PixelData).hexdigest(),
                                    file_sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    (output / 'manifest.json').write_text(json.dumps(records, indent=2) + '\n')
    print(f'Generated {len(records)} MR instances for {patients} synthetic patients')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--patients', type=int, default=40)
    args = parser.parse_args()
    if not 1 <= args.patients <= 40:
        parser.error('--patients must be between 1 and 40')
    generate(args.output, args.patients)
