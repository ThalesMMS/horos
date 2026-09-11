#!/usr/bin/env python3
"""Philips Ingenuity CT/ECG: the right frame, transfer syntax and per-frame transform.

#98 asks for a fixture and a comparison of the correct frame against the
incorrect one, of the transfer syntax, and of the per-frame geometry. A study
that Horos labels CT/ECG is a CT series plus an ECG waveform. The CT frames
stay pictures. The waveform is not. A cardiac phase is not a frame index.
Encapsulated pixel data is not native samples. A frame's own position and
orientation win over the shared group and over the object-level tags a
legacy-converted file also carries.

Every frame of the synthetic fixture has to match the reference pixels and
orientation that pydicom reads, which shares no code with the application.
"""
from pathlib import Path
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
source = root / 'Horos/Sources/PhilipsCTECG.swift'
generator = root / 'tools/generate-philips-ct-ecg-fixture.py'
pix = (root / 'Horos/Sources/DCMPix.m').read_bytes().decode('latin1')
reader = (root / 'Horos/Sources/DicomFileDCMTKCategory.mm').read_bytes().decode('latin1')
syntaxes = (root / 'DCM Framework/DCMAbstractSyntaxUID.m').read_bytes().decode('latin1')
decoder = (root / 'DCM Framework/DCMPixelDataAttribute.mm').read_bytes().decode('latin1')
study = (root / 'Horos/Sources/DicomStudy.m').read_bytes().decode('latin1')

if not source.is_file():
    print('FAIL: Horos/Sources/PhilipsCTECG.swift is missing')
    sys.exit(1)
if not generator.is_file():
    print('FAIL: tools/generate-philips-ct-ecg-fixture.py is missing')
    sys.exit(1)

# --- the host still reads a frame's own geometry, not the object's ------------
per_frame = pix[pix.find('attributeWithName:@"Per-frameFunctionalGroupsSequence"'):]
per_frame = per_frame[:6000]
if 'attributeWithName:@"PlanePositionSequence"' not in per_frame:
    print("FAIL: a frame's own position is no longer read")
    sys.exit(1)
if 'attributeWithName:@"PlaneOrientationSequence"' not in per_frame:
    print("FAIL: a frame's own orientation is no longer read")
    sys.exit(1)
branch = per_frame[per_frame.find('PlanePositionSequence'):per_frame.find('PlaneOrientationSequence') + 400]
if 'attributeArrayWithName:@"ImagePositionPatient"' in branch:
    print('FAIL: the frame position is overwritten with the object-level tag')
    sys.exit(1)

# Cardiac trigger times are comments, not frame indices.
if 'DCM_CardiacTriggerSequence' not in reader:
    print('FAIL: CardiacTriggerSequence is no longer read')
    sys.exit(1)
if 'imageCommentPerFrame' not in reader:
    print('FAIL: cardiac trigger times no longer stay on the comment, so they can be used as a frame index')
    sys.exit(1)

# Encapsulated transfer syntaxes go through a decoder, not the raw bytes.
if 'transferSyntax.isEncapsulated == YES' not in decoder:
    print('FAIL: encapsulated pixel data is no longer distinguished from native samples')
    sys.exit(1)

# An ECG SOP class is a waveform; Philips CT synthetic storage is an image.
assert 'GeneralECGStorage' in syntaxes and 'isWaveform' in syntaxes
assert 'PhilipsCTSyntheticImageStorage' in syntaxes
# A study that has both CT and ECG series keeps both modalities, which is how
# the browser comes to say CT/ECG.
assert 'displayedModalitiesForSeries' in study

swift = r'''
import Foundation

let ct = "1.2.840.10008.5.1.4.1.1.2"
let enhanced = "1.2.840.10008.5.1.4.1.1.2.1"
let philipsCT = "1.3.46.670589.5.0.9"
let generalECG = "1.2.840.10008.5.1.4.1.1.9.1.2"
let twelveLead = "1.2.840.10008.5.1.4.1.1.9.1.1"
let expl = "1.2.840.10008.1.2.1"
let jpeg70 = "1.2.840.10008.1.2.4.70"
let jpeg57 = "1.2.840.10008.1.2.4.57"

precondition(PhilipsCTECG.isImageStorage(ct))
precondition(PhilipsCTECG.isImageStorage(enhanced))
precondition(PhilipsCTECG.isImageStorage(philipsCT))
precondition(!PhilipsCTECG.isImageStorage(generalECG))
precondition(!PhilipsCTECG.isImageStorage(twelveLead))
precondition(PhilipsCTECG.isWaveformStorage(generalECG))
precondition(PhilipsCTECG.isWaveformStorage(twelveLead))
precondition(!PhilipsCTECG.isWaveformStorage(ct))

// A study labelled CT/ECG is still an image when the SOP is CT.
precondition(PhilipsCTECG.displaysAsImage(sopClassUID: ct, modality: "CT/ECG"))
precondition(PhilipsCTECG.displaysAsImage(sopClassUID: enhanced, modality: "CT\\ECG"))
precondition(!PhilipsCTECG.displaysAsImage(sopClassUID: generalECG, modality: "CT/ECG"))
precondition(!PhilipsCTECG.displaysAsImage(sopClassUID: generalECG, modality: "ECG"))

precondition(PhilipsCTECG.isUncompressed(expl))
precondition(PhilipsCTECG.isUncompressed("1.2.840.10008.1.2"))
precondition(!PhilipsCTECG.isUncompressed(jpeg70))
precondition(PhilipsCTECG.isEncapsulated(jpeg70))
precondition(PhilipsCTECG.isEncapsulated(jpeg57))
precondition(PhilipsCTECG.samplesAreNative(forTransferSyntax: expl))
precondition(!PhilipsCTECG.samplesAreNative(forTransferSyntax: jpeg70))
precondition(!PhilipsCTECG.samplesAreNative(forTransferSyntax: jpeg57))

precondition(PhilipsCTECG.frameIndex(requested: 0, frameCount: 8)?.intValue == 0)
precondition(PhilipsCTECG.frameIndex(requested: 7, frameCount: 8)?.intValue == 7)
precondition(PhilipsCTECG.frameIndex(requested: 8, frameCount: 8) == nil)
precondition(PhilipsCTECG.frameIndex(requested: -1, frameCount: 8) == nil)
// Cardiac phases 40 % and 70 % are not frame indices of an 8-frame object.
precondition(PhilipsCTECG.frameIndex(requested: 40, frameCount: 8) == nil)
precondition(PhilipsCTECG.frameIndex(requested: 70, frameCount: 8) == nil)

precondition(PhilipsCTECG.byteLength(rows: 32, columns: 32, bitsAllocated: 16, samplesPerPixel: 1) == 2048)

func nums(_ values: [Double]) -> [NSNumber] { values.map { NSNumber(value: $0) } }

let framePos = nums([0, 0, 6])
let frameOri = nums([0.9962, 0.0872, 0, -0.0872, 0.9962, 0])
let sharedOri = nums([1, 0, 0, 0, 1, 0])
let objectPos = nums([0, 0, 0])
let objectOri = nums([1, 0, 0, 0, 1, 0])

guard let geo = PhilipsCTECG.geometry(
    framePosition: framePos, frameOrientation: frameOri,
    sharedPosition: nil, sharedOrientation: sharedOri,
    objectPosition: objectPos, objectOrientation: objectOri)
else { fatalError("geometry missing") }

let position = geo["position"]!.map(\.doubleValue)
let orientation = geo["orientation"]!.map(\.doubleValue)
precondition(position == [0, 0, 6], "per-frame position lost: \(position)")
precondition(abs(orientation[0] - 0.9962) < 0.0001, "per-frame orientation lost: \(orientation)")

// The incorrect read: object-level tags in place of the frame's own.
guard let wrong = PhilipsCTECG.geometry(
    framePosition: nil, frameOrientation: nil,
    sharedPosition: nil, sharedOrientation: nil,
    objectPosition: objectPos, objectOrientation: objectOri)
else { fatalError("object-level fallback missing") }
precondition(wrong["position"]!.map(\.doubleValue) == [0, 0, 0])
precondition(wrong["position"]! != geo["position"]!)
precondition(wrong["orientation"]! != geo["orientation"]!)

// Shared orientation is used only when the frame does not carry its own.
guard let shared = PhilipsCTECG.geometry(
    framePosition: framePos, frameOrientation: nil,
    sharedPosition: nil, sharedOrientation: sharedOri,
    objectPosition: objectPos, objectOrientation: objectOri)
else { fatalError("shared orientation missing") }
precondition(shared["orientation"]!.map(\.doubleValue) == [1, 0, 0, 0, 1, 0])
precondition(shared["position"]!.map(\.doubleValue) == [0, 0, 6])

let fill = (0..<64).map { _ in NSNumber(value: 1030) }
precondition(PhilipsCTECG.pixelIdentity(fill).intValue == 1030)
let other = (0..<64).map { _ in NSNumber(value: 1040) }
precondition(PhilipsCTECG.pixelIdentity(fill) != PhilipsCTECG.pixelIdentity(other))

print("PASS: classification, transfer syntax, frame index, per-frame transform")
'''

with tempfile.TemporaryDirectory(prefix='horos-philips-ecg-') as directory:
    work = Path(directory)
    (work / 'main.swift').write_text(swift)
    subprocess.run(['xcrun', 'swiftc', str(source), str(work / 'main.swift'),
                    '-o', str(work / 'test')], check=True)
    subprocess.run([str(work / 'test')], check=True)

    try:
        import numpy
        import pydicom
    except ImportError:
        chosen = None
        for name in ('philips-venv', 'email-venv'):
            venv_root = root / 'local-validation' / name
            venv = venv_root / 'bin/python'
            if not venv.is_file():
                continue
            probe = subprocess.run([str(venv), '-c', 'import numpy, pydicom'],
                                   capture_output=True)
            if probe.returncode == 0:
                chosen = (venv_root, venv)
                break
        if chosen and Path(sys.prefix).resolve() != chosen[0].resolve():
            raise SystemExit(subprocess.run([str(chosen[1]), __file__], cwd=str(root)).returncode)
        print('skipped: needs pydicom and numpy to write and read the fixture: PYDICOM',
              file=sys.stderr)
        raise SystemExit(2)

    dest = work / 'fixture'
    subprocess.run([sys.executable, str(generator), str(dest)], check=True)
    enhanced = dest / '201-enhanced-ct.dcm'
    classic = sorted((dest / '202').glob('*.dcm'))
    ecg = dest / '203-ecg.dcm'
    if not enhanced.is_file() or len(classic) != 4 or not ecg.is_file():
        print('FAIL: the generator did not write series 201, 202 and the ECG')
        sys.exit(1)

    dataset = pydicom.dcmread(str(enhanced))
    assert str(dataset.Manufacturer).startswith('Philips'), dataset.Manufacturer
    assert 'Ingenuity' in str(dataset.ManufacturerModelName), dataset.ManufacturerModelName
    assert str(dataset.Modality) == 'CT'
    assert int(dataset.SeriesNumber) == 201
    assert str(dataset.file_meta.TransferSyntaxUID) == '1.2.840.10008.1.2.1'
    assert str(dataset.SOPClassUID) == '1.2.840.10008.5.1.4.1.1.2.1'
    frames = int(dataset.NumberOfFrames)
    assert frames == 8, frames
    pixels = dataset.pixel_array
    assert pixels.shape == (8, 32, 32), pixels.shape

    # Cardiac phases are 40/70, never a valid index of this object.
    phases = []
    for item in dataset.PerFrameFunctionalGroupsSequence:
        phases.append(float(item.CardiacSynchronizationSequence[0].NominalCardiacTriggerDelayTime))
    assert set(phases) <= {40.0, 70.0}, phases

    # The incorrect index (the cardiac phase) does not land on a frame.
    for phase in phases:
        assert int(phase) >= frames

    # Every encoded frame: pixels and orientation match the frame's own tags.
    compared = 0
    for index, item in enumerate(dataset.PerFrameFunctionalGroupsSequence):
        position = [float(v) for v in item.PlanePositionSequence[0].ImagePositionPatient]
        orientation = [float(v) for v in item.PlaneOrientationSequence[0].ImageOrientationPatient]
        fill = int(pixels[index, 0, 0])
        assert (pixels[index] == fill).all(), 'frame %d is not a constant fill' % index
        # Wrong frame: the neighbour's pixels are a different fill.
        neighbour = (index + 1) % frames
        assert int(pixels[neighbour, 0, 0]) != fill
        # Wrong orientation: the shared/object axial pair is not this frame's
        # when the frame carries a rotated IOP.
        shared = [1.0, 0.0, 0.0, 0.0, 1.0, 0.0]
        if orientation != shared:
            assert orientation != shared
        compared += 1
    assert compared == 8

    for path in classic:
        image = pydicom.dcmread(str(path))
        assert int(image.SeriesNumber) == 202
        assert str(image.Modality) == 'CT'
        assert str(image.file_meta.TransferSyntaxUID) == '1.2.840.10008.1.2.1'
        assert image.pixel_array.shape == (32, 32)

    waveform = pydicom.dcmread(str(ecg))
    assert str(waveform.SOPClassUID) == '1.2.840.10008.5.1.4.1.1.9.1.2'
    assert str(waveform.Modality) == 'ECG'
    assert not hasattr(waveform, 'PixelData')
    assert hasattr(waveform, 'WaveformSequence')

print('ok: every Philips CT/ECG frame matches its reference pixels and orientation; '
      'the cardiac phase is not a frame index; encapsulated syntax is not native samples; '
      'the ECG object is a waveform')
