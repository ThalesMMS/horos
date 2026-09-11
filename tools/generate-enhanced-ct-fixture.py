#!/usr/bin/env python3
"""An Enhanced CT or MR whose frames are stored out of geometric order.

The point of the file is that encoding order and physical order disagree. Frame
0 in the file is not the bottom of the stack, the positions are in
`PerFrameFunctionalGroupsSequence` > `PlanePositionSequence` > (0020,0032), and
the orientation is where a real Enhanced CT puts it - once, in
`SharedFunctionalGroupsSequence` > `PlaneOrientationSequence` - because it is the
same for every frame.

Each frame is filled with a constant value that says which slice it is: frame at
z = 2*k is filled with 100*k. Whatever order the frames end up in, the pixels say
where each one belongs.
"""
import argparse
from pathlib import Path

import numpy
from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.uid import ExplicitVRLittleEndian, generate_uid

ENHANCED_CT = '1.2.840.10008.5.1.4.1.1.2.1'
ENHANCED_MR = '1.2.840.10008.5.1.4.1.1.4.1'

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('destination', type=Path, help='an empty directory for the file')
parser.add_argument('--frames', type=int, default=12)
parser.add_argument('--spacing', type=float, default=2.0, help='mm between slices')
parser.add_argument('--rows', type=int, default=32)
parser.add_argument('--columns', type=int, default=32)
parser.add_argument('--order', default='shuffled', choices=('shuffled', 'sorted', 'reversed'),
                    help='the order the frames are written in, which is not their geometry')
parser.add_argument('--orientation', default='shared', choices=('shared', 'per-frame'),
                    help='where ImageOrientationPatient lives')
parser.add_argument('--modality', default='CT', choices=('CT', 'MR'),
                    help='Enhanced CT or Enhanced MR')
parser.add_argument('--plane', default='axial', choices=('axial', 'sagittal', 'coronal'),
                    help='the plane the frames are acquired in, which decides both the '
                         'orientation and the axis the positions move along')
parser.add_argument('--legacy-position', action='store_true',
                    help='also write an object-level ImagePositionPatient, the way a legacy '
                         'converted enhanced object does')
parser.add_argument('--stack-numbers', default='geometric',
                    choices=('geometric', 'file', 'none', 'repeated'),
                    help='what InStackPositionNumber says: the frame\'s place in the stack, '
                         'its place in the file, nothing at all, or two stacks each numbered '
                         'from one')
arguments = parser.parse_args()

arguments.destination.mkdir(parents=True, exist_ok=True)
if any(arguments.destination.iterdir()):
    raise SystemExit('%s is not empty' % arguments.destination)

count = arguments.frames
geometry = list(range(count))
if arguments.order == 'reversed':
    written = list(reversed(geometry))
elif arguments.order == 'sorted':
    written = list(geometry)
else:
    # A fixed interleave, so the file is the same every time it is generated.
    written = geometry[1::2] + geometry[0::2]

study = generate_uid()
series = generate_uid()
instance = generate_uid()

dataset = Dataset()
dataset.file_meta = FileMetaDataset()
sop_class = ENHANCED_MR if arguments.modality == 'MR' else ENHANCED_CT
dataset.file_meta.MediaStorageSOPClassUID = sop_class
dataset.file_meta.MediaStorageSOPInstanceUID = instance
dataset.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
dataset.file_meta.ImplementationClassUID = generate_uid()
dataset.is_little_endian = True
dataset.is_implicit_VR = False

dataset.SpecificCharacterSet = 'ISO_IR 100'
dataset.SOPClassUID = sop_class
dataset.SOPInstanceUID = instance
dataset.StudyInstanceUID = study
dataset.SeriesInstanceUID = series
dataset.PatientName = 'ENHANCED^%s' % arguments.modality
dataset.PatientID = 'ENH%s-85' % arguments.modality
dataset.PatientBirthDate = '19700101'
dataset.PatientSex = 'O'
dataset.StudyDate = '20260101'
dataset.StudyTime = '120000'
dataset.ContentDate = '20260101'
dataset.ContentTime = '120000'
dataset.AccessionNumber = 'ENHCT85'
dataset.StudyID = '85'
dataset.SeriesNumber = 1
dataset.InstanceNumber = 1
dataset.Modality = arguments.modality
dataset.StudyDescription = 'Enhanced %s stored out of order' % arguments.modality
dataset.SeriesDescription = 'frames written %s' % arguments.order
dataset.ImageType = ['ORIGINAL', 'PRIMARY', 'VOLUME', 'NONE']

dataset.Rows = arguments.rows
dataset.Columns = arguments.columns
dataset.NumberOfFrames = count
dataset.SamplesPerPixel = 1
dataset.PhotometricInterpretation = 'MONOCHROME2'
dataset.BitsAllocated = 16
dataset.BitsStored = 16
dataset.HighBit = 15
dataset.PixelRepresentation = 0

# Row and column direction cosines, and the axis the slices advance along - the
# one the normal of those two points down.
PLANES = {'axial':    ([1.0, 0.0, 0.0, 0.0, 1.0, 0.0], 2),
          'sagittal': ([0.0, 1.0, 0.0, 0.0, 0.0, -1.0], 0),
          'coronal':  ([1.0, 0.0, 0.0, 0.0, 0.0, -1.0], 1)}
orientation, moving = PLANES[arguments.plane]

dataset.DimensionOrganizationSequence = [Dataset()]
dataset.DimensionOrganizationSequence[0].DimensionOrganizationUID = generate_uid()

shared = Dataset()
measures = Dataset()
measures.PixelSpacing = [0.7, 0.7]
measures.SliceThickness = arguments.spacing
measures.SpacingBetweenSlices = arguments.spacing
shared.PixelMeasuresSequence = [measures]
transformation = Dataset()
transformation.RescaleIntercept = -1024.0
transformation.RescaleSlope = 1.0
transformation.RescaleType = 'HU'
shared.PixelValueTransformationSequence = [transformation]
window = Dataset()
window.WindowCenter = 40.0
window.WindowWidth = 400.0
shared.FrameVOILUTSequence = [window]
if arguments.orientation == 'shared':
    plane = Dataset()
    plane.ImageOrientationPatient = list(orientation)
    shared.PlaneOrientationSequence = [plane]
dataset.SharedFunctionalGroupsSequence = [shared]

frames = []
per_frame = []
for position, slice_index in enumerate(written):
    item = Dataset()

    if arguments.stack_numbers != 'none':
        content = Dataset()
        if arguments.stack_numbers == 'repeated':
            # Two stacks, each numbered from one, so the numbers repeat.
            content.StackID = '1' if slice_index < count // 2 else '2'
            content.InStackPositionNumber = (slice_index % (count // 2)) + 1
        elif arguments.stack_numbers == 'file':
            content.StackID = '1'
            content.InStackPositionNumber = position + 1
        else:
            content.StackID = '1'
            content.InStackPositionNumber = slice_index + 1
        content.DimensionIndexValues = [int(content.StackID), content.InStackPositionNumber]
        content.FrameAcquisitionNumber = position + 1
        item.FrameContentSequence = [content]

    plane_position = Dataset()
    position = [0.0, 0.0, 0.0]
    position[moving] = slice_index * arguments.spacing
    plane_position.ImagePositionPatient = list(position)
    item.PlanePositionSequence = [plane_position]

    if arguments.orientation == 'per-frame':
        plane = Dataset()
        plane.ImageOrientationPatient = list(orientation)
        item.PlaneOrientationSequence = [plane]

    per_frame.append(item)
    frames.append(numpy.full((arguments.rows, arguments.columns), 100 * slice_index,
                             dtype=numpy.uint16))

if arguments.legacy_position:
    # One position for the whole object, which is only the first frame's. A frame
    # that takes this instead of its own lands where the first one is.
    first = [0.0, 0.0, 0.0]
    first[moving] = written[0] * arguments.spacing
    dataset.ImagePositionPatient = list(first)
    dataset.ImageOrientationPatient = list(orientation)

dataset.PerFrameFunctionalGroupsSequence = per_frame
dataset.PixelData = numpy.stack(frames).tobytes()

path = arguments.destination / 'enhanced-ct.dcm'
dataset.save_as(str(path), enforce_file_format=True)

print('%s' % path)
print('study %s' % study)
print('series %s' % series)
print('instance %s' % instance)
print('%d frames, %.1f mm apart, %s, orientation %s, written %s, stack numbers %s'
      % (count, arguments.spacing, arguments.plane, arguments.orientation, arguments.order,
         arguments.stack_numbers))
print('orientation %s, slices advance along %s'
      % (orientation, 'xyz'[moving]))
print('written order (frame index -> slice, z, fill, in-stack position):')
for position, slice_index in enumerate(written):
    item = per_frame[position]
    stack = (item.FrameContentSequence[0].InStackPositionNumber
             if 'FrameContentSequence' in item else None)
    print('  frame %2d -> slice %2d  z=%6.1f  fill=%-5d  in-stack %s'
          % (position, slice_index, slice_index * arguments.spacing, 100 * slice_index,
             stack if stack is not None else '(none)'))
