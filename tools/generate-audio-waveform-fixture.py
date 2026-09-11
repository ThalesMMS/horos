#!/usr/bin/env python3
"""Audio attached to a study, as DICOM says to attach it.

The question in #72 is which container to use before writing an importer. DICOM
already has one for sound: Basic Voice Audio Waveform Storage
(1.2.840.10008.5.1.4.1.1.9.4.1), a Waveform IOD whose samples are ordinary
linear PCM in Waveform Data (5400,1010). It belongs to a study and a series like
any other instance, so it inherits the patient and study identifiers, the query
model and the transfer of everything else - which an audio file carried beside
the study does not.

This writes one such instance: one channel, 8000 Hz, 16 bit signed, a tone that
is easy to recognise again, and the same StudyInstanceUID as a study the reader
already has, so it arrives inside that study rather than beside it.

    python3 tools/generate-audio-waveform-fixture.py <empty dir> [--study UID] [--seconds 2]
"""
import argparse
import math
import struct
from pathlib import Path

from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.sequence import Sequence
from pydicom.uid import ExplicitVRLittleEndian, generate_uid

BASIC_VOICE_AUDIO = '1.2.840.10008.5.1.4.1.1.9.4.1'

parser = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument('destination', type=Path, help='an empty directory for the file')
parser.add_argument('--study', help='attach to this StudyInstanceUID instead of a new study')
parser.add_argument('--patient-name', default='AUDIO^WAVEFORM')
parser.add_argument('--patient-id', default='AUDIO-72')
# The reader keeps two studies apart when the patient identity differs, even with
# one Study Instance UID - name, identifier and date of birth all take part - and
# says which of them differs. Audio meant to join a study has to carry the same.
parser.add_argument('--birth-date', default='19700101')
parser.add_argument('--sex', default='O')
parser.add_argument('--seconds', type=float, default=2.0)
parser.add_argument('--frequency', type=float, default=440.0, help='the tone, in Hz')
parser.add_argument('--rate', type=int, default=8000, help='sampling frequency')
arguments = parser.parse_args()

arguments.destination.mkdir(parents=True, exist_ok=True)
if any(arguments.destination.iterdir()):
    raise SystemExit('%s is not empty' % arguments.destination)

count = int(arguments.seconds * arguments.rate)
# A quarter-scale tone: loud enough to see, far from clipping.
samples = [int(8000 * math.sin(2 * math.pi * arguments.frequency * n / arguments.rate))
           for n in range(count)]
data = struct.pack('<%dh' % count, *samples)

instance = generate_uid()
dataset = Dataset()
dataset.file_meta = FileMetaDataset()
dataset.file_meta.MediaStorageSOPClassUID = BASIC_VOICE_AUDIO
dataset.file_meta.MediaStorageSOPInstanceUID = instance
dataset.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
dataset.file_meta.ImplementationClassUID = generate_uid()

dataset.SpecificCharacterSet = 'ISO_IR 100'
dataset.SOPClassUID = BASIC_VOICE_AUDIO
dataset.SOPInstanceUID = instance
dataset.StudyInstanceUID = arguments.study or generate_uid()
dataset.SeriesInstanceUID = generate_uid()
dataset.PatientName = arguments.patient_name
dataset.PatientID = arguments.patient_id
dataset.PatientBirthDate = arguments.birth_date
dataset.PatientSex = arguments.sex
dataset.StudyDate = '20260101'
dataset.StudyTime = '120000'
dataset.ContentDate = '20260101'
dataset.ContentTime = '120000'
dataset.AcquisitionDateTime = '20260101120000'
dataset.AccessionNumber = 'AUDIO72'
dataset.StudyID = '72'
dataset.SeriesNumber = 972
dataset.InstanceNumber = 1
dataset.Modality = 'AU'                     # PS 3.3 C.7.3.1.1.1
dataset.StudyDescription = 'audio attached to a study'
dataset.SeriesDescription = 'dictation, %g Hz tone' % arguments.frequency

channel = Dataset()
source = Dataset()
source.CodeValue = '5000'                   # PS 3.16, Audio Channel Source
source.CodingSchemeDesignator = 'MDC'
source.CodeMeaning = 'Audio'
channel.ChannelSourceSequence = Sequence([source])
channel.ChannelSensitivity = '1.0'
channel.ChannelSensitivityCorrectionFactor = '1.0'
channel.ChannelBaseline = '0.0'
channel.ChannelTimeSkew = '0.0'
channel.WaveformBitsStored = 16
units = Dataset()
units.CodeValue = 'V'
units.CodingSchemeDesignator = 'UCUM'
units.CodeMeaning = 'volt'
channel.ChannelSensitivityUnitsSequence = Sequence([units])

waveform = Dataset()
waveform.MultiplexGroupTimeOffset = '0.0'
waveform.TriggerTimeOffset = '0.0'
waveform.WaveformOriginality = 'ORIGINAL'
waveform.NumberOfWaveformChannels = 1
waveform.NumberOfWaveformSamples = count
waveform.SamplingFrequency = str(float(arguments.rate))
waveform.MultiplexGroupLabel = 'AUDIO'
waveform.ChannelDefinitionSequence = Sequence([channel])
waveform.WaveformBitsAllocated = 16
waveform.WaveformSampleInterpretation = 'SS'   # signed 16-bit linear
waveform.WaveformData = data

dataset.WaveformSequence = Sequence([waveform])

path = arguments.destination / 'voice-audio.dcm'
dataset.save_as(str(path), enforce_file_format=True)
print('%-18s %s' % ('SOP class', BASIC_VOICE_AUDIO))
print('%-18s %s' % ('study', dataset.StudyInstanceUID))
print('%-18s %d samples, %g Hz, %g s, 16 bit signed, one channel'
      % ('waveform', count, arguments.rate, arguments.seconds))
print('%-18s %s / %s / %s' % ('patient', dataset.PatientName, dataset.PatientID, dataset.PatientBirthDate))
print('%-18s %s' % ('file', path))
