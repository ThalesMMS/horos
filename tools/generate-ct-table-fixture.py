#!/usr/bin/env python3
"""Generate a synthetic CT series that has a patient and a table under it.

A255 (#373, from #255) asks for a *"corte de mesa sintética no modo suportado"*:
a table that can actually be cropped away, so that removing it is something that
can be measured rather than looked at. Real CT examples are not usable for that
here -- they are not synthetic, and the criterion's evidence has to be.

The geometry is fixed and documented so a validation can name the pixels it
measured without carrying the images:

    512 x 512, 1 mm pixels, 8 axial slices, HU via RescaleIntercept = -1024

    background (air)     -1000 HU   everywhere else
    patient ellipse        +40 HU   centre (256, 216), radii 150 x 110
      bone ring           +700 HU   the outer 8 mm of that ellipse
    table bar             +200 HU   rows 400..431, columns 96..415

The table is well clear of the patient ellipse (which ends at row 326), so a
region drawn around the patient excludes it, and setting the pixels outside that
region to air is exactly the operation the criterion describes.
"""
import argparse
import uuid
from pathlib import Path

import numpy
from pydicom.dataset import FileDataset, FileMetaDataset
from pydicom.uid import CTImageStorage, ExplicitVRLittleEndian

AIR, SOFT, BONE, TABLE = -1000, 40, 700, 200
WIDTH = HEIGHT = 512
CENTRE = (256, 216)          # column, row
RADII = (150, 110)           # column, row
BONE_THICKNESS = 8
TABLE_ROWS = (400, 432)      # half-open
TABLE_COLUMNS = (96, 416)    # half-open
SLICES = 8


def uid(value):
    return '2.25.' + str(uuid.uuid5(uuid.NAMESPACE_URL, 'urn:horos:ct-table:' + value).int)


def slicePixels():
    rows, columns = numpy.ogrid[:HEIGHT, :WIDTH]
    normalised = (((columns - CENTRE[0]) / RADII[0]) ** 2
                  + ((rows - CENTRE[1]) / RADII[1]) ** 2)
    inner = (((columns - CENTRE[0]) / (RADII[0] - BONE_THICKNESS)) ** 2
             + ((rows - CENTRE[1]) / (RADII[1] - BONE_THICKNESS)) ** 2)

    image = numpy.full((HEIGHT, WIDTH), AIR, dtype=numpy.int16)
    image[normalised <= 1] = BONE
    image[inner <= 1] = SOFT
    image[TABLE_ROWS[0]:TABLE_ROWS[1], TABLE_COLUMNS[0]:TABLE_COLUMNS[1]] = TABLE
    return image


def generate(output):
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        raise ValueError('Use an empty output directory')

    pixels = slicePixels()
    for index in range(SLICES):
        meta = FileMetaDataset()
        meta.MediaStorageSOPClassUID = CTImageStorage
        meta.MediaStorageSOPInstanceUID = uid('image-%d' % index)
        meta.TransferSyntaxUID = ExplicitVRLittleEndian

        ds = FileDataset(str(output / ('%02d.dcm' % index)), {}, file_meta=meta,
                         preamble=b'\0' * 128)
        ds.SOPClassUID = CTImageStorage
        ds.SOPInstanceUID = meta.MediaStorageSOPInstanceUID
        ds.StudyInstanceUID = uid('study')
        ds.SeriesInstanceUID = uid('series')
        ds.FrameOfReferenceUID = uid('frame')

        ds.PatientName = 'QA^CT Table'
        ds.PatientID = 'LOCAL-CT-TABLE'
        ds.StudyID = 'CTTABLE'
        ds.StudyDescription = 'Table Removal Acceptance'
        ds.SeriesDescription = 'CT Table Phantom'
        ds.StudyDate = ds.SeriesDate = ds.ContentDate = '20260912'
        ds.StudyTime = ds.SeriesTime = ds.ContentTime = '120000'

        ds.Modality = 'CT'
        ds.SeriesNumber = 1
        ds.InstanceNumber = index + 1
        ds.ImageType = ['ORIGINAL', 'PRIMARY', 'AXIAL']

        ds.Rows, ds.Columns = HEIGHT, WIDTH
        ds.PixelSpacing = [1, 1]
        ds.SliceThickness = 2
        ds.SpacingBetweenSlices = 2
        ds.ImageOrientationPatient = [1, 0, 0, 0, 1, 0]
        ds.ImagePositionPatient = [-256, -216, index * 2]
        ds.SliceLocation = index * 2

        ds.SamplesPerPixel = 1
        ds.PhotometricInterpretation = 'MONOCHROME2'
        ds.PixelRepresentation = 0
        ds.BitsAllocated = ds.BitsStored = 16
        ds.HighBit = 15
        ds.RescaleIntercept = -1024
        ds.RescaleSlope = 1
        ds.RescaleType = 'HU'
        ds.WindowCenter = 40
        ds.WindowWidth = 400
        # Stored values are unsigned; HU = stored + intercept.
        ds.PixelData = (pixels - int(ds.RescaleIntercept)).astype(numpy.uint16).tobytes()
        ds.save_as(ds.filename, enforce_file_format=True)

    print('Generated %d axial CT images, %dx%d.' % (SLICES, WIDTH, HEIGHT))
    print('  patient ellipse  centre (%d, %d) radii %d x %d, soft %+d HU, bone rim %+d HU'
          % (CENTRE[0], CENTRE[1], RADII[0], RADII[1], SOFT, BONE))
    print('  table bar        rows %d..%d, columns %d..%d, %+d HU'
          % (TABLE_ROWS[0], TABLE_ROWS[1] - 1, TABLE_COLUMNS[0], TABLE_COLUMNS[1] - 1, TABLE))
    print('  background       %+d HU' % AIR)
    print('The patient ends at row %d, so a region around it excludes the table.'
          % (CENTRE[1] + RADII[1]))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('output', type=Path)
    generate(parser.parse_args().output)
