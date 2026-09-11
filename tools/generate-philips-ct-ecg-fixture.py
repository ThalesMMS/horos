#!/usr/bin/env python3
"""A synthetic Philips Ingenuity CT/ECG study: series 201, 202 and a waveform.

The original report is a Philips Ingenuity CT series 201-202 in a study that
Horos labels CT/ECG. There is no real Ingenuity archive in this checkout. This
writes the structure the acceptance asks to compare: frames whose encoding
order is not their geometry, a transfer syntax that can be read as native
samples, per-frame position and orientation (one frame rotated so a shared
read is wrong), cardiac phases that are not frame indices, classic single-
frame slices in series 202, and a General ECG waveform that is not a picture.

Each CT frame is a constant fill that says which slice it is. The wrong frame
and the wrong transform are then a different number.

    python3 tools/generate-philips-ct-ecg-fixture.py <empty dir>
"""
import argparse
import math
import struct
from pathlib import Path

import numpy
from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.sequence import Sequence
from pydicom.uid import ExplicitVRLittleEndian, generate_uid

ENHANCED_CT = '1.2.840.10008.5.1.4.1.1.2.1'
CT_IMAGE = '1.2.840.10008.5.1.4.1.1.2'
GENERAL_ECG = '1.2.840.10008.5.1.4.1.1.9.1.2'
AXIAL = [1.0, 0.0, 0.0, 0.0, 1.0, 0.0]
# About 5 degrees in the axial plane, so using the shared IOP is wrong.
ROTATED = [0.9962, 0.0872, 0.0, -0.0872, 0.9962, 0.0]


def file_meta(sop_class, instance):
    meta = FileMetaDataset()
    meta.MediaStorageSOPClassUID = sop_class
    meta.MediaStorageSOPInstanceUID = instance
    meta.TransferSyntaxUID = ExplicitVRLittleEndian
    meta.ImplementationClassUID = generate_uid()
    return meta


def identity(dataset, study, series, instance, name, patient_id):
    dataset.SpecificCharacterSet = 'ISO_IR 100'
    dataset.SOPClassUID = dataset.file_meta.MediaStorageSOPClassUID
    dataset.SOPInstanceUID = instance
    dataset.StudyInstanceUID = study
    dataset.SeriesInstanceUID = series
    dataset.PatientName = name
    dataset.PatientID = patient_id
    dataset.PatientBirthDate = '19700101'
    dataset.PatientSex = 'O'
    dataset.StudyDate = '20260101'
    dataset.StudyTime = '120000'
    dataset.ContentDate = '20260101'
    dataset.ContentTime = '120000'
    dataset.AccessionNumber = 'PHILIPS98'
    dataset.StudyID = '98'
    dataset.Manufacturer = 'Philips'
    dataset.ManufacturerModelName = 'Ingenuity CT'
    dataset.is_little_endian = True
    dataset.is_implicit_VR = False


def pixel_header(dataset, rows, columns):
    dataset.Rows = rows
    dataset.Columns = columns
    dataset.SamplesPerPixel = 1
    dataset.PhotometricInterpretation = 'MONOCHROME2'
    dataset.BitsAllocated = 16
    dataset.BitsStored = 16
    dataset.HighBit = 15
    dataset.PixelRepresentation = 0
    dataset.PixelSpacing = [0.7, 0.7]
    dataset.SliceThickness = 2.0
    dataset.RescaleIntercept = -1024.0
    dataset.RescaleSlope = 1.0
    dataset.RescaleType = 'HU'
    dataset.WindowCenter = 40.0
    dataset.WindowWidth = 400.0


parser = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument('destination', type=Path, help='an empty directory for the files')
parser.add_argument('--frames', type=int, default=8)
parser.add_argument('--rows', type=int, default=32)
parser.add_argument('--columns', type=int, default=32)
arguments = parser.parse_args()

arguments.destination.mkdir(parents=True, exist_ok=True)
if any(arguments.destination.iterdir()):
    raise SystemExit('%s is not empty' % arguments.destination)

count = arguments.frames
geometry = list(range(count))
written = geometry[1::2] + geometry[0::2]
study = generate_uid()
series_201 = generate_uid()
series_202 = generate_uid()
series_ecg = generate_uid()
instance_201 = generate_uid()

enhanced = Dataset()
enhanced.file_meta = file_meta(ENHANCED_CT, instance_201)
identity(enhanced, study, series_201, instance_201, 'PHILIPS^INGENUITY', 'PHILIPS-98')
enhanced.Modality = 'CT'
enhanced.SeriesNumber = 201
enhanced.InstanceNumber = 1
enhanced.ImageType = ['ORIGINAL', 'PRIMARY', 'VOLUME', 'NONE']
enhanced.SeriesDescription = 'Cardiac gated CT series 201'
enhanced.StudyDescription = 'Philips Ingenuity CT/ECG'
enhanced.ScanOptions = 'ECG'
enhanced.CardiacSynchronizationTechnique = 'PROSPECTIVE'
enhanced.NumberOfFrames = count
pixel_header(enhanced, arguments.rows, arguments.columns)
# Object-level tags of a legacy-converted file: the first encoded frame only.
first_slice = written[0]
enhanced.ImagePositionPatient = [0.0, 0.0, float(first_slice * 2)]
enhanced.ImageOrientationPatient = list(AXIAL)

shared = Dataset()
measures = Dataset()
measures.PixelSpacing = [0.7, 0.7]
measures.SliceThickness = 2.0
measures.SpacingBetweenSlices = 2.0
shared.PixelMeasuresSequence = [measures]
plane = Dataset()
plane.ImageOrientationPatient = list(AXIAL)
shared.PlaneOrientationSequence = [plane]
transformation = Dataset()
transformation.RescaleIntercept = -1024.0
transformation.RescaleSlope = 1.0
transformation.RescaleType = 'HU'
shared.PixelValueTransformationSequence = [transformation]
enhanced.SharedFunctionalGroupsSequence = [shared]

per_frame = []
frames = []
print('series 201 Enhanced CT, Explicit VR LE, %d frames written %s' % (count, written))
print('frame  file  slice    z   fill  phase  orientation')
for position, slice_index in enumerate(written):
    item = Dataset()
    content = Dataset()
    content.StackID = '1'
    content.InStackPositionNumber = slice_index + 1
    content.DimensionIndexValues = [1, slice_index + 1]
    content.FrameAcquisitionNumber = position + 1
    item.FrameContentSequence = [content]

    plane_position = Dataset()
    plane_position.ImagePositionPatient = [0.0, 0.0, float(slice_index * 2)]
    item.PlanePositionSequence = [plane_position]

    # Slice 3 is rotated so a shared/object axial read is the incorrect transform.
    orientation = ROTATED if slice_index == 3 else AXIAL
    plane_orientation = Dataset()
    plane_orientation.ImageOrientationPatient = list(orientation)
    item.PlaneOrientationSequence = [plane_orientation]

    # (0018,9118) Cardiac Synchronization Sequence. The host's DCMTK alias is
    # CardiacTriggerSequence; pydicom's keyword is the standard name. The delay
    # is (0020,9153) Nominal Cardiac Trigger Delay Time, 40 ms or 70 ms, never
    # a valid frame index of this object.
    trigger = Dataset()
    trigger.NominalCardiacTriggerDelayTime = 40.0 if slice_index % 2 == 0 else 70.0
    item.CardiacSynchronizationSequence = [trigger]

    per_frame.append(item)
    fill = 1000 + 10 * slice_index
    frames.append(numpy.full((arguments.rows, arguments.columns), fill, dtype=numpy.uint16))
    print('  %2d    %2d     %2d  %5.1f  %4d   %4.0f  %s'
          % (position, position, slice_index, slice_index * 2.0, fill,
             trigger.NominalCardiacTriggerDelayTime, 'rotated' if slice_index == 3 else 'axial'))

enhanced.PerFrameFunctionalGroupsSequence = per_frame
enhanced.PixelData = numpy.stack(frames).tobytes()
path_201 = arguments.destination / '201-enhanced-ct.dcm'
enhanced.save_as(str(path_201), enforce_file_format=True)
print(path_201)

classic_dir = arguments.destination / '202'
classic_dir.mkdir()
print('series 202 classic CT, Explicit VR LE, 4 instances')
for slice_index in range(4):
    instance = generate_uid()
    image = Dataset()
    image.file_meta = file_meta(CT_IMAGE, instance)
    identity(image, study, series_202, instance, 'PHILIPS^INGENUITY', 'PHILIPS-98')
    image.Modality = 'CT'
    image.SeriesNumber = 202
    image.InstanceNumber = slice_index + 1
    image.ImageType = ['ORIGINAL', 'PRIMARY', 'AXIAL']
    image.SeriesDescription = 'Cardiac gated CT series 202'
    image.StudyDescription = 'Philips Ingenuity CT/ECG'
    image.ScanOptions = 'ECG'
    pixel_header(image, arguments.rows, arguments.columns)
    image.ImagePositionPatient = [0.0, 0.0, 100.0 + slice_index * 2.0]
    image.ImageOrientationPatient = list(AXIAL)
    image.SliceLocation = 100.0 + slice_index * 2.0
    fill = 2000 + 10 * slice_index
    image.PixelData = numpy.full((arguments.rows, arguments.columns), fill,
                                 dtype=numpy.uint16).tobytes()
    path = classic_dir / ('IM-%04d.dcm' % (slice_index + 1))
    image.save_as(str(path), enforce_file_format=True)
    print('  %s  slice %d  z=%5.1f  fill=%d' % (path.name, slice_index,
                                                100.0 + slice_index * 2.0, fill))

samples = [int(4000 * math.sin(2 * math.pi * 60 * n / 500.0)) for n in range(250)]
# Two channels interleaved: lead I and a half-scale copy.
interleaved = []
for sample in samples:
    interleaved.extend([sample, sample // 2])
ecg_data = struct.pack('<%dh' % len(interleaved), *interleaved)

instance_ecg = generate_uid()
ecg = Dataset()
ecg.file_meta = file_meta(GENERAL_ECG, instance_ecg)
identity(ecg, study, series_ecg, instance_ecg, 'PHILIPS^INGENUITY', 'PHILIPS-98')
ecg.Modality = 'ECG'
ecg.SeriesNumber = 203
ecg.InstanceNumber = 1
ecg.SeriesDescription = 'General ECG waveform'
ecg.StudyDescription = 'Philips Ingenuity CT/ECG'

channel_i = Dataset()
source_i = Dataset()
source_i.CodeValue = '5.6.3-9-1'
source_i.CodingSchemeDesignator = 'SCPECG'
source_i.CodeMeaning = 'Lead I'
channel_i.ChannelSourceSequence = Sequence([source_i])
channel_i.WaveformBitsStored = 16
channel_ii = Dataset()
source_ii = Dataset()
source_ii.CodeValue = '5.6.3-9-2'
source_ii.CodingSchemeDesignator = 'SCPECG'
source_ii.CodeMeaning = 'Lead II'
channel_ii.ChannelSourceSequence = Sequence([source_ii])
channel_ii.WaveformBitsStored = 16

waveform = Dataset()
waveform.WaveformOriginality = 'ORIGINAL'
waveform.NumberOfWaveformChannels = 2
waveform.NumberOfWaveformSamples = len(samples)
waveform.SamplingFrequency = '500.0'
waveform.MultiplexGroupLabel = 'ECG'
waveform.ChannelDefinitionSequence = Sequence([channel_i, channel_ii])
waveform.WaveformBitsAllocated = 16
waveform.WaveformSampleInterpretation = 'SS'
waveform.WaveformData = ecg_data
ecg.WaveformSequence = Sequence([waveform])

path_ecg = arguments.destination / '203-ecg.dcm'
ecg.save_as(str(path_ecg), enforce_file_format=True)
print(path_ecg)
print('study %s' % study)
print('CT/ECG: series 201+202 are images, series 203 is a waveform')
