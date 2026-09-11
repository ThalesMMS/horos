#!/usr/bin/env python3
"""A DICOM whose pixel data is a video stream.

Transfer syntax 1.2.840.10008.1.2.4.102 - MPEG-4 AVC/H.264 High Profile / Level
4.1 - carries the whole video as one encapsulated fragment, not one fragment per
frame. The instance is a Video Photographic Image Storage object with
NumberOfFrames, a frame rate in Cine Rate and the usual colour attributes for
YBR_PARTIAL_420, which is what the standard requires for this syntax.

The picture is a moving wedge with a frame counter burned in, so a decoder that
returns the wrong frame is visible rather than plausible.

The frames are not square, so a viewer that reads Rows where it means Columns
shows a picture that is visibly wrong rather than one that happens to fit.

    python3 tools/generate-mpeg4-fixture.py <empty dir> [--frames 30]
        [--size 320x240] [--rate 15] [--b-frames 0]
        [--codec h264|hevc] [--truncate-stream N] [--declared-size WxH]

The last three write objects a viewer is meant to refuse rather than draw: a
codec outside the ones it decodes, a stream cut short, and a header whose frame
size disagrees with the stream. Each should produce a named reason on an empty
frame, not a picture of the compressed bytes.

Needs ffmpeg for the encoding; everything else is pydicom.
"""
import argparse
import shutil
import subprocess
from pathlib import Path

from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.encaps import encapsulate
from pydicom.uid import UID, generate_uid

MPEG4_HIGH_41 = '1.2.840.10008.1.2.4.102'
HEVC_MAIN_51 = '1.2.840.10008.1.2.4.107'
HEVC_MAIN10_51 = '1.2.840.10008.1.2.4.108'
VIDEO_PHOTOGRAPHIC = '1.2.840.10008.5.1.4.1.1.77.1.4.1'

parser = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument('destination', type=Path)
parser.add_argument('--frames', type=int, default=30)
parser.add_argument('--size', default='320x240', help='columns x rows')
parser.add_argument('--rate', type=int, default=15, help='frames per second')
parser.add_argument('--b-frames', type=int, default=0, dest='b_frames',
                    help='consecutive B pictures; above zero the coded order is '
                         'not the shown order')
parser.add_argument('--keyframe-interval', type=int, default=0, dest='keyint',
                    help='defaults to 5 without B pictures and 10 with them')
parser.add_argument('--codec', choices=('h264', 'hevc', 'hevc10'), default='h264',
                    help='hevc writes transfer syntax %s and hevc10 writes %s; no viewer '
                         'here decodes either. hevc10 encodes 10-bit, so the declared '
                         'syntax and the stream agree.' % (HEVC_MAIN_51, HEVC_MAIN10_51))
parser.add_argument('--truncate-stream', type=int, default=0, dest='truncate',
                    help='keep only this many bytes of the encoded stream')
parser.add_argument('--declared-size', default='', dest='declared',
                    help='write these Columns x Rows instead of the real ones')
arguments = parser.parse_args()

columns, _, rows = arguments.size.partition('x')
if not rows:
    rows = columns
columns, rows = int(columns), int(rows)
if columns % 2 or rows % 2:
    raise SystemExit('H.264 needs even dimensions, not %dx%d' % (columns, rows))
keyint = arguments.keyint or (10 if arguments.b_frames else 5)

declared_columns, declared_rows = columns, rows
if arguments.declared:
    a, _, b = arguments.declared.partition('x')
    declared_columns, declared_rows = int(a), int(b or a)

if shutil.which('ffmpeg') is None:
    raise SystemExit('ffmpeg is needed to encode the stream')
arguments.destination.mkdir(parents=True, exist_ok=True)
if any(arguments.destination.iterdir()):
    raise SystemExit('%s is not empty' % arguments.destination)

video = arguments.destination / 'stream.h264'
# A wedge that moves, with the frame number drawn on it: testsrc2 numbers its
# frames, so a decoder that hands back the wrong one is visible.
if arguments.codec == 'h264':
    encoding = ['-c:v', 'libx264', '-profile:v', 'high', '-level', '4.1',
                '-x264-params', 'keyint=%d:min-keyint=%d:scenecut=0%s'
                % (keyint, keyint, ':b-pyramid=normal' if arguments.b_frames else '')]
    container = 'h264'
    transfer_syntax = MPEG4_HIGH_41
    method = 'ISO_14496_10'
else:
    ten_bit = arguments.codec == 'hevc10'
    encoding = ['-c:v', 'libx265', '-profile:v', 'main10' if ten_bit else 'main',
                '-pix_fmt', 'yuv420p10le' if ten_bit else 'yuv420p', '-tag:v', 'hvc1',
                '-x265-params', 'log-level=error:keyint=%d:min-keyint=%d:scenecut=0'
                % (keyint, keyint)]
    container = 'hevc'
    transfer_syntax = HEVC_MAIN10_51 if ten_bit else HEVC_MAIN_51
    method = 'ISO_23008_2'

subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi',
                '-i', f'testsrc2=size={columns}x{rows}:rate={arguments.rate}',
                '-frames:v', str(arguments.frames),
                '-pix_fmt', 'yuv420p', '-g', str(keyint), '-bf', str(arguments.b_frames)]
               + encoding + ['-f', container, str(video)], check=True)
stream = video.read_bytes()
if arguments.truncate:
    stream = stream[:arguments.truncate]

instance = generate_uid()
dataset = Dataset()
dataset.file_meta = FileMetaDataset()
dataset.file_meta.MediaStorageSOPClassUID = VIDEO_PHOTOGRAPHIC
dataset.file_meta.MediaStorageSOPInstanceUID = instance
dataset.file_meta.TransferSyntaxUID = UID(transfer_syntax)
dataset.file_meta.ImplementationClassUID = generate_uid()

dataset.SpecificCharacterSet = 'ISO_IR 100'
dataset.SOPClassUID = VIDEO_PHOTOGRAPHIC
dataset.SOPInstanceUID = instance
dataset.StudyInstanceUID = generate_uid()
dataset.SeriesInstanceUID = generate_uid()
dataset.PatientName = 'MPEG4^FIXTURE'
dataset.PatientID = 'MPEG4-95'
dataset.PatientBirthDate = '19700101'
dataset.PatientSex = 'O'
dataset.StudyDate = '20260101'
dataset.StudyTime = '120000'
dataset.ContentDate = '20260101'
dataset.ContentTime = '120000'
dataset.AccessionNumber = 'MPEG495'
dataset.StudyID = '95'
dataset.SeriesNumber = 95
dataset.InstanceNumber = 1
dataset.Modality = 'XC'                      # external-camera photography
dataset.StudyDescription = 'MPEG-4 AVC encapsulated video'
dataset.SeriesDescription = ('%s, %d frames, %d B pictures%s%s'
                            % ('H.264 high profile level 4.1' if arguments.codec == 'h264'
                               else 'H.265 main 10 profile level 5.1'
                               if arguments.codec == 'hevc10'
                               else 'H.265 main profile level 5.1',
                               arguments.frames, arguments.b_frames,
                               ', truncated to %d bytes' % arguments.truncate if arguments.truncate else '',
                               ', declared %dx%d' % (declared_columns, declared_rows)
                               if (declared_columns, declared_rows) != (columns, rows) else ''))

dataset.Rows = declared_rows
dataset.Columns = declared_columns
dataset.SamplesPerPixel = 3
dataset.PhotometricInterpretation = 'YBR_PARTIAL_420'
dataset.PlanarConfiguration = 0
# PS3.5 A.4.7: a Main 10 stream is stored with Bits Allocated 16, so the
# attributes and the stream say the same thing about depth.
dataset.BitsAllocated = 16 if arguments.codec == 'hevc10' else 8
dataset.BitsStored = 10 if arguments.codec == 'hevc10' else 8
dataset.HighBit = dataset.BitsStored - 1
dataset.PixelRepresentation = 0
dataset.NumberOfFrames = arguments.frames
dataset.FrameIncrementPointer = 0x00181063   # Frame Time
dataset.FrameTime = '%.6g' % (1000.0 / arguments.rate)   # DS is 16 characters
dataset.CineRate = arguments.rate
dataset.LossyImageCompression = '01'
dataset.LossyImageCompressionMethod = method
# One fragment for the whole stream, which is what .102 requires.
dataset.PixelData = encapsulate([stream], has_bot=False)
dataset['PixelData'].is_undefined_length = True

path = arguments.destination / ('%s.dcm' % {'h264': 'mpeg4-avc', 'hevc': 'hevc',
                                            'hevc10': 'hevc-main10'}[arguments.codec])
dataset.save_as(str(path), enforce_file_format=True)
video.unlink()
print('%-20s %s' % ('transfer syntax', transfer_syntax))
print('%-20s %s' % ('SOP class', VIDEO_PHOTOGRAPHIC))
print('%-20s %d frames, %dx%d, %d fps, %d B pictures, %d bytes of %s'
      % ('stream', arguments.frames, columns, rows, arguments.rate,
         arguments.b_frames, len(stream), container.upper()))
if (declared_columns, declared_rows) != (columns, rows):
    print('%-20s %dx%d' % ('declared size', declared_columns, declared_rows))
print('%-20s %s' % ('study', dataset.StudyInstanceUID))
print('%-20s %s' % ('file', path))
