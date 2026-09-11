#!/usr/bin/env python3
"""Synthetic CT/MR series for the #304 scroll/IOAccel baseline.

Nothing here comes from a person. Destination must be empty. Default geometry
is 64×64, 0.5 mm axial slices. The catalog writes 100, 500 and 1250 images
for CT and MR plus a synchronized pair that shares a frame of reference.

    python3 tools/generate-scroll-baseline-fixture.py --plan
    python3 tools/generate-scroll-baseline-fixture.py <empty dir> --modality CT --slices 100
    python3 tools/generate-scroll-baseline-fixture.py <empty dir> --catalog
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from scroll_baseline import AXIAL, catalog_plan, uid  # noqa: E402


def refuse_nonempty(destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    if any(destination.iterdir()):
        raise SystemExit(f'{destination} is not empty')


def pixels(size: int, index: int):
    import numpy
    columns = numpy.arange(size, dtype=numpy.uint16)
    rows = numpy.arange(size, dtype=numpy.uint16)[:, None]
    return ((columns + rows + index * 3) % 4096).astype(numpy.uint16)


def write_series(destination: Path, *, name: str, modality: str, slices: int,
                 spacing: float, size: int, study_uid: str | None = None,
                 series_uid: str | None = None,
                 frame_of_reference: str | None = None) -> None:
    from pydicom.dataset import Dataset, FileMetaDataset
    from pydicom.uid import CTImageStorage, MRImageStorage, ExplicitVRLittleEndian

    refuse_nonempty(destination)
    sop_class = CTImageStorage if modality == 'CT' else MRImageStorage
    study_uid = study_uid or uid(f'study-{name}')
    series_uid = series_uid or uid(f'series-{name}')
    frame = frame_of_reference or uid(f'for-{name}')
    if frame and not frame.startswith('2.25.'):
        frame = uid(f'for-{frame}')
    intercept = -1024.0 if modality == 'CT' else 0.0
    center, width = (40.0, 400.0) if modality == 'CT' else (300.0, 600.0)
    for index in range(slices):
        sop = uid(f'sop-{name}-{index + 1}')
        dataset = Dataset()
        dataset.file_meta = FileMetaDataset()
        dataset.file_meta.MediaStorageSOPClassUID = sop_class
        dataset.file_meta.MediaStorageSOPInstanceUID = sop
        dataset.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
        dataset.SOPClassUID = sop_class
        dataset.SOPInstanceUID = sop
        dataset.StudyInstanceUID = study_uid
        dataset.SeriesInstanceUID = series_uid
        dataset.FrameOfReferenceUID = frame
        dataset.PatientName = f'QA^ScrollBaseline {modality}'
        dataset.PatientID = f'LOCAL-SCROLL-{modality}'
        dataset.PatientBirthDate = '19700101'
        dataset.PatientSex = 'O'
        dataset.StudyDate = dataset.SeriesDate = dataset.ContentDate = '20260911'
        dataset.StudyTime = dataset.SeriesTime = dataset.ContentTime = '120000'
        dataset.StudyID = 'S304'
        dataset.AccessionNumber = 'SCROLL304'
        dataset.StudyDescription = 'synthetic scroll baseline'
        dataset.SeriesDescription = name
        dataset.SeriesNumber = 1
        dataset.InstanceNumber = index + 1
        dataset.Modality = modality
        dataset.ImageType = ['ORIGINAL', 'PRIMARY', 'AXIAL']
        dataset.ImagePositionPatient = [0.0, 0.0, index * spacing]
        dataset.ImageOrientationPatient = list(AXIAL)
        dataset.SliceLocation = float(index * spacing)
        dataset.PixelSpacing = [1.0, 1.0]
        dataset.SliceThickness = spacing
        dataset.SpacingBetweenSlices = spacing
        dataset.Rows = dataset.Columns = size
        dataset.SamplesPerPixel = 1
        dataset.PhotometricInterpretation = 'MONOCHROME2'
        dataset.BitsAllocated = dataset.BitsStored = 16
        dataset.HighBit = 15
        dataset.PixelRepresentation = 0
        dataset.RescaleIntercept = intercept
        dataset.RescaleSlope = 1.0
        dataset.WindowCenter = center
        dataset.WindowWidth = width
        dataset.PixelData = pixels(size, index).tobytes()
        dataset.save_as(str(destination / f'{index + 1:04d}.dcm'),
                        write_like_original=False)


def write_catalog(destination: Path) -> None:
    refuse_nonempty(destination)
    for spec in catalog_plan()['series']:
        write_series(destination / spec['name'],
                     name=spec['name'],
                     modality=spec['modality'],
                     slices=spec['slices'],
                     spacing=spec['spacing_mm'],
                     size=spec['size'],
                     study_uid=spec['study_uid'],
                     series_uid=spec['series_uid'],
                     frame_of_reference=spec['frame_of_reference'])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('destination', type=Path, nargs='?')
    parser.add_argument('--plan', action='store_true')
    parser.add_argument('--catalog', action='store_true')
    parser.add_argument('--modality', choices=('CT', 'MR'), default='CT')
    parser.add_argument('--slices', type=int, default=100)
    parser.add_argument('--spacing', type=float, default=0.5)
    parser.add_argument('--size', type=int, default=64)
    parser.add_argument('--name', default='')
    parser.add_argument('--frame-of-reference', default='')
    arguments = parser.parse_args()
    if arguments.plan:
        json.dump(catalog_plan(), sys.stdout, indent=2)
        sys.stdout.write('\n')
        return
    if arguments.destination is None:
        parser.error('destination is required unless --plan is set')
    if arguments.catalog:
        write_catalog(arguments.destination)
        return
    if arguments.slices < 1:
        parser.error('slices must be at least 1')
    name = arguments.name or f'{arguments.modality.lower()}-{arguments.slices}'
    write_series(arguments.destination, name=name, modality=arguments.modality,
                 slices=arguments.slices, spacing=arguments.spacing,
                 size=arguments.size,
                 frame_of_reference=arguments.frame_of_reference or None)


if __name__ == '__main__':
    main()
