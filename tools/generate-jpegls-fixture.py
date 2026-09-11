#!/usr/bin/env python3
"""DICOM images in JPEG-LS, with pixels a reference can be compared against.

Transfer syntax 1.2.840.10008.1.2.4.80 is JPEG-LS lossless: the pixels that come
out are the pixels that went in, so "is the image right?" has an exact answer.
1.2.840.10008.1.2.4.81 is near-lossless, where the answer is "within the error
the file declares".

  mono-lossless      one component, 16 bit, lossless
  rgb-sample         three components, 8 bit, lossless, interleave sample
  rgb-line           the same, interleave line
  rgb-none           the same, interleave none: one scan per component
  mono-nearlossless  one component, 16 bit, allowed error 3
  uncompressed       the same mono picture, explicit VR little endian

The three RGB series carry the same picture encoded three ways, which is the
distinction that matters to a decoder: only "none" splits the components into
separate scans.

The picture is a wedge crossed with a step, different in each component, so a
plane written where a sample belongs, an off-by-one row, or a component swap is
visible rather than plausible. The uncompressed series is the reference: the two
show the same picture if the decoder is right.

Requires pyjpegls (`pip install pyjpegls`).
"""
import argparse
import json
from pathlib import Path

import numpy
from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.encaps import encapsulate
from pydicom.uid import (ExplicitVRLittleEndian, JPEGLSLossless, JPEGLSNearLossless,
                         SecondaryCaptureImageStorage, generate_uid)

import jpeg_ls

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('destination', type=Path, help='an empty directory for the files')
parser.add_argument('--rows', type=int, default=64)
parser.add_argument('--columns', type=int, default=61, help='odd, so a stride mistake shows')
arguments = parser.parse_args()

arguments.destination.mkdir(parents=True, exist_ok=True)
if any(arguments.destination.iterdir()):
    raise SystemExit('%s is not empty' % arguments.destination)

rows, columns = arguments.rows, arguments.columns
study = generate_uid()


def picture(components, high):
    """A wedge crossed with a step, different in each component."""
    x = numpy.arange(columns)
    y = numpy.arange(rows)[:, None]
    base = (x * 7 + y * 13) % (high + 1)
    base[rows // 3: 2 * rows // 3, columns // 4: 3 * columns // 4] = high
    if components == 1:
        return base.astype(numpy.uint16 if high > 255 else numpy.uint8)
    planes = [(base + offset) % (high + 1) for offset in (0, high // 3, 2 * high // 3)]
    return numpy.stack(planes, axis=-1).astype(numpy.uint16 if high > 255 else numpy.uint8)


def build(name, series_number, description, pixels, syntax, error=0, interleave=None):
    instance = generate_uid()
    dataset = Dataset()
    dataset.file_meta = FileMetaDataset()
    dataset.file_meta.MediaStorageSOPClassUID = SecondaryCaptureImageStorage
    dataset.file_meta.MediaStorageSOPInstanceUID = instance
    dataset.file_meta.TransferSyntaxUID = syntax
    dataset.file_meta.ImplementationClassUID = generate_uid()

    components = 1 if pixels.ndim == 2 else pixels.shape[2]
    bits = 16 if pixels.dtype == numpy.uint16 else 8

    dataset.SpecificCharacterSet = 'ISO_IR 100'
    dataset.SOPClassUID = SecondaryCaptureImageStorage
    dataset.SOPInstanceUID = instance
    dataset.StudyInstanceUID = study
    dataset.SeriesInstanceUID = generate_uid()
    dataset.PatientName = 'JPEGLS^FIXTURE'
    dataset.PatientID = 'JPEGLS-109'
    dataset.PatientBirthDate = '19700101'
    dataset.PatientSex = 'O'
    dataset.StudyDate = '20260101'
    dataset.StudyTime = '120000'
    dataset.ContentDate = '20260101'
    dataset.ContentTime = '120000'
    dataset.AccessionNumber = 'JLS109'
    dataset.StudyID = '109'
    dataset.SeriesNumber = series_number
    dataset.InstanceNumber = 1
    dataset.Modality = 'OT'
    dataset.StudyDescription = 'JPEG-LS'
    dataset.SeriesDescription = description
    dataset.ImageType = ['ORIGINAL', 'PRIMARY']
    dataset.PixelSpacing = [1.0, 1.0]

    dataset.Rows = rows
    dataset.Columns = columns
    dataset.SamplesPerPixel = components
    dataset.PhotometricInterpretation = 'RGB' if components == 3 else 'MONOCHROME2'
    if components == 3:
        dataset.PlanarConfiguration = 0
    dataset.BitsAllocated = bits
    dataset.BitsStored = bits
    dataset.HighBit = bits - 1
    dataset.PixelRepresentation = 0
    if components == 1:
        dataset.WindowCenter = float(int(pixels.max()) // 2)
        dataset.WindowWidth = float(int(pixels.max()) + 1)
        dataset.RescaleIntercept = 0.0
        dataset.RescaleSlope = 1.0

    if syntax == ExplicitVRLittleEndian:
        dataset.PixelData = pixels.tobytes()
    else:
        # Interleave "none" encodes one scan per component, so its source is
        # planes. Passing the interleaved array with mode 0 makes pyjpegls
        # describe a picture that is three wide with sixty-four components.
        if interleave == 0 and components == 3:
            source = numpy.ascontiguousarray(pixels.transpose(2, 0, 1)).tobytes()
        else:
            source = numpy.ascontiguousarray(pixels).tobytes()
        frame = jpeg_ls.encode_buffer(source, rows=rows, columns=columns,
                                      samples_per_pixel=components, bits_stored=bits,
                                      lossy_error=error, interleave_mode=interleave)
        dataset.PixelData = encapsulate([bytes(frame)])
        dataset['PixelData'].is_undefined_length = True

    path = arguments.destination / ('%s.dcm' % name)
    dataset.save_as(str(path), enforce_file_format=True)
    print('%-18s %-34s %d component(s), %d bit, error %d, interleave %s' %
          (name, description, components, bits, error,
           'default' if interleave is None else interleave))
    return pixels


mono = picture(1, 4000)
rgb = picture(3, 250)

build('uncompressed', 1, 'uncompressed reference', mono, ExplicitVRLittleEndian)
build('mono-lossless', 2, 'JPEG-LS lossless, 16 bit', mono, JPEGLSLossless)
build('rgb-sample', 3, 'JPEG-LS lossless RGB, interleave sample', rgb,
      JPEGLSLossless, interleave=2)
build('rgb-line', 4, 'JPEG-LS lossless RGB, interleave line', rgb,
      JPEGLSLossless, interleave=1)
build('rgb-none', 5, 'JPEG-LS lossless RGB, interleave none', rgb,
      JPEGLSLossless, interleave=0)
build('mono-nearlossless', 6, 'JPEG-LS near-lossless, error 3', mono,
      JPEGLSNearLossless, error=3)

reference = arguments.destination / 'reference.json'
reference.write_text(json.dumps({
    'rows': rows, 'columns': columns,
    'mono': mono.tolist(),
    'rgb': rgb.tolist(),
    'nearLosslessError': 3,
}))
print()
print('study %s' % study)
print('reference pixels in %s' % reference.name)
