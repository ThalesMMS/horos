#!/usr/bin/env python3
"""NIfTI atlas conversion keeps affine, spacing, LPS/RAS and labels, and
never claims the atlas is registered to a patient (#377 C).

General NIfTI import (#151) stays a different path: this helper produces DICOM
MR and SEG from an atlas image plus a label map. It does not go through
DicomDatabase's incoming-folder indexer.
"""
from pathlib import Path
import struct
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
failures = []


def check(condition, message):
    if not condition:
        failures.append(message)


source = root / 'Horos/Sources/NiftiAtlasConversion.swift'
pbx = (root / 'Horos.xcodeproj/project.pbxproj').read_text(encoding='utf-8')
database = (root / 'Horos/Sources/DicomDatabase.mm').read_bytes().decode('latin1')
defaults = (root / 'Horos/Sources/DefaultsOsiriX.m').read_bytes().decode('latin1')
volume_view = (root / 'Horos/Sources/ROIVolumeView.mm').read_bytes().decode('latin1')

check(source.is_file(), 'NiftiAtlasConversion.swift is missing')
check('NiftiAtlasConversion.swift' in pbx,
      'NiftiAtlasConversion.swift is not in the app target')
check('isNIfTIFile:srcPath' in database,
      'general NIfTI import (#151) must stay on DicomDatabase; atlas conversion is not a substitute')
check('NiftiAtlasConversion' not in database,
      'atlas conversion must not be wired as the incoming-folder NIfTI indexer')

# A247: Delaunay is optional and iso-contour (0) is the default. Since
# d5f326ad8 an unavailable algorithm is refused with a diagnosis instead of
# being silently rewritten to iso-contour: Power Crust is a tag in
# ROIVolume.xib whose VTK path is not built, and quietly reconstructing with a
# different algorithm would hand back a surface the user did not ask for.
check('setObject:@"0" forKey:@"UseDelaunayFor3DRoi"' in defaults,
      'UseDelaunayFor3DRoi must default to iso-contour, not Delaunay')
check('[HorosROISurfaceAlgorithm resolvePreference:' in volume_view,
      'ROIVolumeView no longer asks the surface-algorithm helper before VTK')
check('choice.available' in volume_view and 'choice.diagnosis' in volume_view,
      'an unavailable algorithm must be refused with its diagnosis, not reconstructed')
check('setInteger:0 forKey:@"UseDelaunayFor3DRoi"' not in volume_view,
      'an unavailable algorithm must not be silently rewritten to iso-contour')
check('ROIVolumeGeometry.swift' in pbx,
      'closed-surface volume still needs the host trapezoid helper (A247)')

for failure in failures:
    print('FAIL: %s' % failure)
reported = len(failures)


def write_nifti(path, nx, ny, nz, spacing, affine, values, sform_code=1):
    header = bytearray(348)
    struct.pack_into('<i', header, 0, 348)
    struct.pack_into('<8h', header, 40, 3, nx, ny, nz, 1, 1, 1, 1)
    struct.pack_into('<h', header, 70, 4)
    struct.pack_into('<h', header, 72, 16)
    struct.pack_into('<8f', header, 76, 1.0, spacing[0], spacing[1], spacing[2], 0, 0, 0, 0)
    struct.pack_into('<f', header, 108, 352.0)
    struct.pack_into('<f', header, 112, 1.0)
    struct.pack_into('<f', header, 116, 0.0)
    struct.pack_into('<h', header, 252, 1)
    struct.pack_into('<h', header, 254, sform_code)
    struct.pack_into('<4f', header, 280, *affine[0])
    struct.pack_into('<4f', header, 296, *affine[1])
    struct.pack_into('<4f', header, 312, *affine[2])
    header[344:348] = b'n+1\x00'
    payload = struct.pack('<' + 'h' * len(values), *values)
    path.write_bytes(bytes(header) + b'\0' * 4 + payload)


def index_of(x, y, z, nx, ny):
    return x + nx * (y + ny * z)


def parse_dicom(blob):
    check(blob[128:132] == b'DICM', 'DICOM preamble is missing')
    pos = 132
    tags = {}
    while pos + 8 <= len(blob):
        group, element = struct.unpack_from('<HH', blob, pos)
        vr = blob[pos + 4:pos + 6].decode('ascii', errors='replace')
        if vr in {'OB', 'OW', 'OF', 'SQ', 'UT', 'UN', 'UC', 'UR', 'OD', 'OL', 'OV'}:
            length = struct.unpack_from('<I', blob, pos + 8)[0]
            start = pos + 12
        else:
            length = struct.unpack_from('<H', blob, pos + 6)[0]
            start = pos + 8
        value = blob[start:start + length]
        tags[(group, element)] = (vr, value)
        pos = start + length
        if (group, element) == (0x7fe0, 0x0010):
            break
    return tags


def decode_ds(value):
    return [float(part) for part in value.decode('ascii').rstrip(' \0').split('\\') if part]


def decode_ui(value):
    return value.decode('ascii').rstrip('\0')


def decode_cs(value):
    return value.decode('ascii').rstrip(' \0')


def decode_us(value):
    count = len(value) // 2
    return struct.unpack('<' + 'H' * count, value)


code = r'''
import Foundation

func close(_ a: Double, _ b: Double, _ e: Double = 1e-5) {
    precondition(a.isFinite && b.isFinite && abs(a - b) < e, "\(a) != \(b)")
}

let folder = URL(fileURLWithPath: CommandLine.arguments[1])
let imageURL = folder.appendingPathComponent("atlas.nii")
let labelsURL = folder.appendingPathComponent("labels.nii")
let missingSform = folder.appendingPathComponent("nosform.nii")
let shifted = folder.appendingPathComponent("shifted.nii")

do {
    _ = try NiftiAtlasConversion.convert(
        imageURL: missingSform, segmentationURL: labelsURL,
        labels: [1: "left"], atlasIdentity: "phantom")
    fatalError("missing sform must be refused")
} catch AtlasConversionError.missingSform {
} catch {
    fatalError("missing sform must name missingSform, not \(error)")
}

do {
    _ = try NiftiAtlasConversion.convert(
        imageURL: imageURL, segmentationURL: shifted,
        labels: [1: "left"], atlasIdentity: "phantom")
    fatalError("shifted affine must be refused")
} catch AtlasConversionError.affineMismatch {
} catch {
    fatalError("affine mismatch must name affineMismatch, not \(error)")
}

let converted = try NiftiAtlasConversion.convert(
    imageURL: imageURL,
    segmentationURL: labelsURL,
    labels: [1: "left", 2: "right"],
    atlasIdentity: "phantom-atlas-v1",
    patientStudyUID: "1.2.840.10008.1.2.999")

precondition(converted.registeredToPatient == false, "an atlas must not claim patient registration")
precondition(converted.referencedStudyUID == "1.2.840.10008.1.2.999",
             "bibliographic DICOM references must be preserved: \(converted.referencedStudyUID ?? "nil")")
precondition(converted.frameOfReferenceUID != converted.referencedStudyUID,
             "the atlas Frame of Reference must stay atlas-native")
precondition(converted.derivationDescription.lowercased().contains("atlas"),
             converted.derivationDescription)
precondition(converted.derivationDescription.lowercased().contains("not registered"),
             converted.derivationDescription)
precondition(!converted.derivationDescription.lowercased().contains("registered to the patient"),
             converted.derivationDescription)

let geometry = converted.geometry
precondition(geometry.rows == 4 && geometry.columns == 4, "\(geometry.rows)x\(geometry.columns)")
close(geometry.rowSpacingMm, 0.5)
close(geometry.columnSpacingMm, 0.5)
close(geometry.sliceSpacingMm, 3.0)
precondition(geometry.sliceCount == 3, "\(geometry.sliceCount)")

let iop = geometry.imageOrientationPatient
close(iop[0], -1); close(iop[1], 0); close(iop[2], 0)
close(iop[3], 0); close(iop[4], -1); close(iop[5], 0)

let first = converted.mrInstances[0]
close(first.imagePositionPatient[0], -10)
close(first.imagePositionPatient[1], -20)
close(first.imagePositionPatient[2], 30)

precondition(converted.segments.map { $0.label } == ["left", "right"])
precondition(converted.segments.map { $0.labelValue } == [1, 2])
precondition(converted.segments[0].segmentNumber == 1)
precondition(converted.segments[1].segmentNumber == 2)

let leftMask = converted.segments[0].frames.flatMap { [UInt8]($0) }
precondition(leftMask.filter { $0 == 1 }.count == 8, "left 2x2x2 block is 8 voxels, got \(leftMask.filter { $0 == 1 }.count)")
precondition(converted.segments[1].frames.flatMap { [UInt8]($0) }.filter { $0 == 1 }.count == 1,
             "right label is a single voxel")

let mr = converted.mrDICOM(instanceNumber: 1)
let seg = converted.segmentationDICOM(segmentNumber: 1)
FileManager.default.createFile(atPath: folder.appendingPathComponent("mr.dcm").path, contents: mr)
FileManager.default.createFile(atPath: folder.appendingPathComponent("seg.dcm").path, contents: seg)

print("PASS: geometry, labels and registration flag")
'''

nx = ny = 4
nz = 3
spacing = (0.5, 0.5, 3.0)
affine = (
    (0.5, 0.0, 0.0, 10.0),
    (0.0, 0.5, 0.0, 20.0),
    (0.0, 0.0, 3.0, 30.0),
)
image_values = [100] * (nx * ny * nz)
label_values = [0] * (nx * ny * nz)
for z in range(2):
    for y in range(2):
        for x in range(2):
            label_values[index_of(x, y, z, nx, ny)] = 1
label_values[index_of(2, 2, 1, nx, ny)] = 2
shifted_affine = (
    (0.5, 0.0, 0.0, 11.0),
    (0.0, 0.5, 0.0, 20.0),
    (0.0, 0.0, 3.0, 30.0),
)

with tempfile.TemporaryDirectory(prefix='horos-atlas-') as tmp:
    folder = Path(tmp)
    write_nifti(folder / 'atlas.nii', nx, ny, nz, spacing, affine, image_values)
    write_nifti(folder / 'labels.nii', nx, ny, nz, spacing, affine, label_values)
    write_nifti(folder / 'nosform.nii', nx, ny, nz, spacing, affine, image_values, sform_code=0)
    write_nifti(folder / 'shifted.nii', nx, ny, nz, spacing, shifted_affine, label_values)

    (folder / 'main.swift').write_text(code)
    build = subprocess.run(
        ['xcrun', 'swiftc', '-parse-as-library', str(source), str(folder / 'main.swift'),
         '-o', str(folder / 'test')],
        capture_output=True, text=True)
    # @main is not used; compile as a script instead if parse-as-library fails.
    if build.returncode:
        build = subprocess.run(
            ['xcrun', 'swiftc', str(source), str(folder / 'main.swift'), '-o', str(folder / 'test')],
            capture_output=True, text=True)
    if build.returncode:
        print(build.stderr.strip()[-2500:])
        failures.append('NiftiAtlasConversion.swift did not compile')
    else:
        run = subprocess.run([str(folder / 'test'), str(folder)], capture_output=True, text=True)
        print((run.stdout + run.stderr).strip())
        if run.returncode:
            failures.append('atlas conversion helper failed')
        else:
            mr_tags = parse_dicom((folder / 'mr.dcm').read_bytes())
            seg_tags = parse_dicom((folder / 'seg.dcm').read_bytes())
            check(decode_ui(mr_tags[(0x0008, 0x0016)][1]) == '1.2.840.10008.5.1.4.1.1.4',
                  'MR SOP Class is wrong')
            pixel_spacing = decode_ds(mr_tags[(0x0028, 0x0030)][1])
            check(abs(pixel_spacing[0] - 0.5) < 1e-5 and abs(pixel_spacing[1] - 0.5) < 1e-5,
                  'MR PixelSpacing is %s' % pixel_spacing)
            iop = decode_ds(mr_tags[(0x0020, 0x0037)][1])
            check(len(iop) == 6 and abs(iop[0] + 1) < 1e-5 and abs(iop[4] + 1) < 1e-5,
                  'MR ImageOrientationPatient is %s' % iop)
            ipp = decode_ds(mr_tags[(0x0020, 0x0032)][1])
            check(abs(ipp[0] + 10) < 1e-5 and abs(ipp[1] + 20) < 1e-5 and abs(ipp[2] - 30) < 1e-5,
                  'MR ImagePositionPatient is %s' % ipp)
            check(decode_cs(mr_tags[(0x0008, 0x0008)][1]).startswith('DERIVED'),
                  'MR ImageType must be derived')
            check(decode_ui(seg_tags[(0x0008, 0x0016)][1]) == '1.2.840.10008.5.1.4.1.1.66.4',
                  'SEG SOP Class is wrong')
            check((0x0070, 0x0080) not in seg_tags,
                  'SEG must not carry a spatial-registration graphic layer')
            check(b'registered to the patient' not in seg_tags.get((0x0008, 0x2111), ('', b''))[1].lower(),
                  'SEG DerivationDescription claims patient registration')
            check(decode_ui(mr_tags[(0x0020, 0x0052)][1]) == decode_ui(seg_tags[(0x0020, 0x0052)][1]),
                  'MR and SEG Frame of Reference must match')
            check(decode_ui(mr_tags[(0x0020, 0x0052)][1]) != '1.2.840.10008.1.2.999',
                  'atlas Frame of Reference copied the patient study UID')

for failure in failures[reported:]:
    print('FAIL: %s' % failure)
if failures:
    sys.exit(1)
print('ok: atlas conversion keeps LPS geometry and labels and refuses patient registration')
