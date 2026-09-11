#!/usr/bin/env python3
"""Audio attached to a study: the container, and what reads it back.

#72 asks which container to use before writing an importer. DICOM has one for
sound - Basic Voice Audio Waveform Storage, 1.2.840.10008.5.1.4.1.1.9.4.1 - and
the application already lists a waveform series and keeps it. This checks that
the class is among the ones it knows as waveforms, and that the generator writes
an instance a second reader gets the samples back from.
"""
from pathlib import Path
import math, struct, subprocess, sys, tempfile

root = Path(__file__).resolve().parents[1]
BASIC_VOICE = '1.2.840.10008.5.1.4.1.1.9.4.1'
syntaxes = (root / 'DCM Framework/DCMAbstractSyntaxUID.m').read_bytes().decode('latin1')
assert f'BasicVoiceStorage = @"{BASIC_VOICE}"' in syntaxes, 'the audio class is no longer declared'
assert 'BasicVoiceStorage, nil]' in syntaxes, 'the audio class left the waveform syntaxes'
study = (root / 'Horos/Sources/DicomStudy.m').read_bytes().decode('latin1')
assert 'isWaveform:uid' in study, 'a waveform series is no longer listed in the browser'

try:
    import pydicom
except ImportError:
    print('skipped: needs pydicom to write and read the waveform: PYDICOM')
    sys.exit(2)

with tempfile.TemporaryDirectory(prefix='horos-audio-waveform-') as tmp:
    out = Path(tmp) / 'fixture'
    subprocess.run([sys.executable, str(root / 'tools/generate-audio-waveform-fixture.py'), str(out),
                    '--seconds', '0.25', '--frequency', '440', '--rate', '8000'],
                   check=True, capture_output=True)
    written = out / 'voice-audio.dcm'
    assert written.exists(), 'the generator wrote no file'

    dataset = pydicom.dcmread(str(written))
    assert str(dataset.SOPClassUID) == BASIC_VOICE, dataset.SOPClassUID
    assert str(dataset.Modality) == 'AU', dataset.Modality
    waveform = dataset.WaveformSequence[0]
    count = int(waveform.NumberOfWaveformSamples)
    assert count == 2000, count
    assert int(waveform.WaveformBitsAllocated) == 16
    assert str(waveform.WaveformSampleInterpretation) == 'SS'
    assert float(waveform.SamplingFrequency) == 8000.0
    # The channel says what it is and in what units, or another reader cannot use it.
    channel = waveform.ChannelDefinitionSequence[0]
    assert str(channel.ChannelSourceSequence[0].CodeMeaning) == 'Audio'
    assert str(channel.ChannelSensitivityUnitsSequence[0].CodeValue) == 'V'

    samples = struct.unpack('<%dh' % count, bytes(waveform.WaveformData))
    expected = [int(8000 * math.sin(2 * math.pi * 440 * n / 8000)) for n in range(count)]
    assert list(samples) == expected, 'the samples read back are not the ones written'

    # And the identity it has to carry to join a study rather than make a new one.
    for attribute in ('StudyInstanceUID', 'SeriesInstanceUID', 'PatientID',
                      'PatientName', 'PatientBirthDate'):
        assert str(getattr(dataset, attribute)), f'{attribute} is empty'

print('PASS: Basic Voice Audio Waveform is a known waveform class, and the instance reads back '
      'with its 2000 samples, rate, bit depth, channel source and units intact')
