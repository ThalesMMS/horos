#!/usr/bin/env python3
"""Atlas NIfTI→MR/SEG conversion keeps affine, LPS, labels and does not register (#377 C).

General NIfTI import (#151) and longitudinal registration (#378) stay elsewhere.
SEG persistence reuses DicomSEG; this does not reimplement the codec.
"""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
source = root / 'Horos/Sources/HorosAtlasConversion.swift'
seg = root / 'Horos/Sources/DicomSEG.swift'
if not source.is_file():
    raise SystemExit('FAIL: Horos/Sources/HorosAtlasConversion.swift is missing')
if not seg.is_file():
    raise SystemExit('FAIL: Horos/Sources/DicomSEG.swift is missing')
pbx = (root / 'Horos.xcodeproj/project.pbxproj').read_text()
if 'HorosAtlasConversion.swift' not in pbx:
    raise SystemExit('FAIL: HorosAtlasConversion.swift is not in the Xcode project')

main = r'''
import Foundation

func expect(_ ok: Bool, _ message: String) {
    if !ok { fputs("FAIL: \(message)\n", stderr); exit(1) }
}

func expectEqual<T: Equatable>(_ got: T, _ want: T, _ message: String) {
    if got != want { fputs("FAIL: \(message): got \(got) want \(want)\n", stderr); exit(1) }
}

func close(_ a: Double, _ b: Double, _ eps: Double = 1e-4) -> Bool {
    abs(a - b) <= eps
}

func close3(_ a: [Double], _ b: [Double], _ eps: Double = 1e-4) -> Bool {
    guard a.count >= 3, b.count >= 3 else { return false }
    return close(a[0], b[0], eps) && close(a[1], b[1], eps) && close(a[2], b[2], eps)
}

func nifti(
    nx: Int, ny: Int, nz: Int,
    sx: Float, sy: Float, sz: Float,
    origin: (Float, Float, Float),
    sform: Int16,
    values: [Int16],
    srowX: (Float, Float, Float, Float)? = nil,
    srowY: (Float, Float, Float, Float)? = nil,
    srowZ: (Float, Float, Float, Float)? = nil
) -> Data {
    var header = Data(count: 352)
    func putI32(_ offset: Int, _ value: Int32) {
        var le = value.littleEndian
        header.replaceSubrange(offset..<(offset + 4), with: Data(bytes: &le, count: 4))
    }
    func putI16(_ offset: Int, _ value: Int16) {
        var le = value.littleEndian
        header.replaceSubrange(offset..<(offset + 2), with: Data(bytes: &le, count: 2))
    }
    func putF(_ offset: Int, _ value: Float) {
        var le = value.bitPattern.littleEndian
        header.replaceSubrange(offset..<(offset + 4), with: Data(bytes: &le, count: 4))
    }
    putI32(0, 348)
    putI16(40, 3)
    putI16(42, Int16(nx))
    putI16(44, Int16(ny))
    putI16(46, Int16(nz))
    putI16(48, 1)
    putI16(50, 1)
    putI16(52, 1)
    putI16(54, 1)
    putI16(70, 4)
    putI16(72, 16)
    putF(76, 1)
    putF(80, sx)
    putF(84, sy)
    putF(88, sz)
    putF(108, 352)
    putF(112, 1)
    putF(116, 0)
    putI16(252, 1)
    putI16(254, sform)
    let x = srowX ?? (sx, 0, 0, origin.0)
    let y = srowY ?? (0, sy, 0, origin.1)
    let z = srowZ ?? (0, 0, sz, origin.2)
    putF(280, x.0); putF(284, x.1); putF(288, x.2); putF(292, x.3)
    putF(296, y.0); putF(300, y.1); putF(304, y.2); putF(308, y.3)
    putF(312, z.0); putF(316, z.1); putF(320, z.2); putF(324, z.3)
    header.replaceSubrange(344..<348, with: Data("n+1\0".utf8))
    var voxels = Data()
    for value in values {
        var le = value.littleEndian
        voxels.append(Data(bytes: &le, count: 2))
    }
    return header + voxels
}

func fill(_ nx: Int, _ ny: Int, _ nz: Int, _ at: [(Int, Int, Int, Int16)]) -> [Int16] {
    var values = [Int16](repeating: 0, count: nx * ny * nz)
    for (x, y, z, v) in at {
        values[x + nx * (y + ny * z)] = v
    }
    return values
}

let nx = 4, ny = 4, nz = 2
let imageValues = fill(nx, ny, nz, [
    (0, 0, 0, 100), (1, 1, 0, 110), (2, 2, 1, 120)
])
let labelValues = fill(nx, ny, nz, [
    (1, 1, 0, 1), (1, 2, 0, 1), (2, 1, 1, 2)
])
let image = try HorosAtlasNiftiVolume.parse(nifti(
    nx: nx, ny: ny, nz: nz, sx: 0.5, sy: 0.5, sz: 3.0,
    origin: (10, 20, 30), sform: 1, values: imageValues
))
let labels = try HorosAtlasNiftiVolume.parse(nifti(
    nx: nx, ny: ny, nz: nz, sx: 0.5, sy: 0.5, sz: 3.0,
    origin: (10, 20, 30), sform: 1, values: labelValues
))

let conversion = try HorosAtlasConversion.convert(
    image: image,
    labels: labels,
    labelNames: [1: "cortex", 2: "putamen"],
    sliceAxis: 2,
    patientStudyUID: "1.2.840.10008.patient.study",
    patientFrameOfReferenceUID: "1.2.840.10008.patient.for"
)

expect(!conversion.registeredToPatient, "atlas must not be presented as registered to the patient")
expect(conversion.provenance.contains("not-registered-to-patient"), "provenance names the non-registration")
expect(conversion.dicom.studyInstanceUID != "1.2.840.10008.patient.study", "atlas study UID is not the patient study")
expect(conversion.dicom.frameOfReferenceUID != "1.2.840.10008.patient.for", "atlas FoR is not the patient FoR")
expect(conversion.dicom.studyInstanceUID.hasPrefix("2.25."), "DICOM references are UIDs")
expectEqual(conversion.labels.map { $0.name }.sorted(), ["cortex", "putamen"], "label names")
expectEqual(conversion.labels.first { $0.name == "cortex" }?.value, 1, "cortex value")
expectEqual(conversion.labels.first { $0.name == "putamen" }?.value, 2, "putamen value")
expectEqual(conversion.labels.first { $0.name == "cortex" }?.occupiedVoxels, 2, "cortex voxels")
expectEqual(conversion.labels.first { $0.name == "putamen" }?.occupiedVoxels, 1, "putamen voxels")

expectEqual(conversion.geometry.columns, 4, "columns")
expectEqual(conversion.geometry.rows, 4, "rows")
expectEqual(conversion.geometry.frames, 2, "frames")
expect(close(conversion.geometry.spacingCol, 0.5), "column spacing from affine")
expect(close(conversion.geometry.spacingRow, 0.5), "row spacing from affine")
expect(close(conversion.geometry.sliceThickness, 3.0), "slice spacing from affine")
expect(close3(conversion.geometry.originLPS, [-10, -20, 30]), "RAS origin (10,20,30) becomes LPS")
expect(close3(Array(conversion.geometry.orientation.prefix(3)), [-1, 0, 0]), "RAS +X becomes LPS -X")
expect(close3(Array(conversion.geometry.orientation.suffix(3)), [0, -1, 0]), "RAS +Y becomes LPS -Y")
expect(conversion.geometry.frameOriginsLPS.count == 2, "one IPP per slice")
expect(close3(conversion.geometry.frameOriginsLPS[1], [-10, -20, 33]), "second slice follows affine Z in LPS")

let document = try conversion.segmentationDocument()
expectEqual(document.geometry.rows, 4, "SEG rows")
expectEqual(document.geometry.columns, 4, "SEG columns")
expectEqual(document.geometry.frames, 2, "SEG frames")
expect(close(document.geometry.spacingCol, 0.5), "SEG column spacing")
expect(close(document.geometry.spacingRow, 0.5), "SEG row spacing")
expect(close(document.geometry.sliceThickness, 3.0), "SEG slice thickness")
expect(document.identity.frameOfReferenceUID == conversion.dicom.frameOfReferenceUID, "SEG FoR matches atlas")
expect(document.identity.studyInstanceUID == conversion.dicom.studyInstanceUID, "SEG study matches atlas")
expect(document.segments.contains { $0.provenance.contains("not-registered-to-patient") }, "SEG provenance is not a registration claim")
let cortex = document.segments.first { $0.label == "cortex" }!
expect(cortex.frames[0][1 * 4 + 1] == 1, "cortex voxel (1,1,0)")
expect(cortex.frames[0][2 * 4 + 1] == 1, "cortex voxel (1,2,0) in row-major")
expect(cortex.frames[1].allSatisfy { $0 == 0 }, "cortex absent on slice 1")
let putamen = document.segments.first { $0.label == "putamen" }!
expect(putamen.frames[1][1 * 4 + 2] == 1, "putamen voxel (2,1,1)")

let encoded = try DicomSEGCodec.encode(document)
let decoded = DicomSEGCodec.decode(encoded)
expect(decoded.segments.contains { $0.label == "cortex" }, "SEG round-trip keeps labels")
expect(decoded.identity.frameOfReferenceUID == conversion.dicom.frameOfReferenceUID, "FoR survives encode")
expect(decoded.geometry.rows == 4 && decoded.geometry.columns == 4, "SEG geometry round-trip")

do {
    _ = try HorosAtlasNiftiVolume.parse(nifti(
        nx: nx, ny: ny, nz: nz, sx: 0.5, sy: 0.5, sz: 3.0,
        origin: (0, 0, 0), sform: 0, values: imageValues
    ))
    expect(false, "missing sform must fail")
} catch HorosAtlasConversionError.missingSform {
} catch {
    expect(false, "missing sform must be missingSform, got \(error)")
}

let otherShape = try HorosAtlasNiftiVolume.parse(nifti(
    nx: 4, ny: 4, nz: 3, sx: 0.5, sy: 0.5, sz: 3.0,
    origin: (10, 20, 30), sform: 1,
    values: [Int16](repeating: 0, count: 4 * 4 * 3)
))
do {
    _ = try HorosAtlasConversion.convert(image: image, labels: otherShape, labelNames: [1: "x"])
    expect(false, "shape mismatch must fail")
} catch HorosAtlasConversionError.labelShapeMismatch {
} catch {
    expect(false, "shape mismatch must be labelShapeMismatch, got \(error)")
}

let shifted = try HorosAtlasNiftiVolume.parse(nifti(
    nx: nx, ny: ny, nz: nz, sx: 0.5, sy: 0.5, sz: 3.0,
    origin: (11, 20, 30), sform: 1, values: labelValues
))
do {
    _ = try HorosAtlasConversion.convert(image: image, labels: shifted, labelNames: [1: "x"])
    expect(false, "affine mismatch must fail")
} catch HorosAtlasConversionError.affineMismatch {
} catch {
    expect(false, "affine mismatch must be affineMismatch, got \(error)")
}

let zero = nifti(
    nx: 2, ny: 2, nz: 2, sx: 0, sy: 1, sz: 1,
    origin: (0, 0, 0), sform: 1,
    values: [Int16](repeating: 0, count: 8)
)
do {
    let volume = try HorosAtlasNiftiVolume.parse(zero)
    _ = try HorosAtlasConversion.convert(image: volume, labels: volume, labelNames: [:])
    expect(false, "zero-length affine column must fail")
} catch HorosAtlasConversionError.zeroLengthDirection {
} catch {
    expect(false, "zero-length must be zeroLengthDirection, got \(error)")
}

let superiorRows = (
    x: (Float(0.5), Float(0), Float(0), Float(10)),
    y: (Float(0), Float(0), Float(0), Float(20)),
    z: (Float(0), Float(0.5), Float(3), Float(30))
)
let superiorRow = try HorosAtlasNiftiVolume.parse(nifti(
    nx: nx, ny: ny, nz: nz, sx: 0.5, sy: 0.5, sz: 3.0,
    origin: (10, 20, 30), sform: 1, values: labelValues,
    srowX: superiorRows.x, srowY: superiorRows.y, srowZ: superiorRows.z
))
let imageSuperior = try HorosAtlasNiftiVolume.parse(nifti(
    nx: nx, ny: ny, nz: nz, sx: 0.5, sy: 0.5, sz: 3.0,
    origin: (10, 20, 30), sform: 1, values: imageValues,
    srowX: superiorRows.x, srowY: superiorRows.y, srowZ: superiorRows.z
))
let reversed = try HorosAtlasConversion.convert(
    image: imageSuperior, labels: superiorRow, labelNames: [1: "cortex", 2: "putamen"]
)
expect(close3(Array(reversed.geometry.orientation.suffix(3)), [0, 0, -1]),
       "superior-pointing NIfTI row is flipped so DICOM row 0 is inferior")
let reversedDoc = try reversed.segmentationDocument()
let reversedCortex = reversedDoc.segments.first { $0.label == "cortex" }!
expect(reversedCortex.frames[0][(4 - 1 - 1) * 4 + 1] == 1, "cortex y=1 maps to flipped DICOM row")
expect(reversedCortex.frames[0][(4 - 1 - 2) * 4 + 1] == 1, "cortex y=2 maps to flipped DICOM row")

print("PASS: atlas NIfTI conversion keeps affine, LPS/RAS, labels and is not registered")
'''

with tempfile.TemporaryDirectory(prefix='horos-atlas-') as directory:
    path = Path(directory)
    (path / 'main.swift').write_text(main)
    compiled = subprocess.run(
        ['xcrun', 'swiftc', '-swift-version', '5',
         str(seg), str(source), str(path / 'main.swift'),
         '-o', str(path / 'test')],
        capture_output=True, text=True)
    if compiled.returncode != 0:
        print(compiled.stderr)
        raise SystemExit('FAIL: swiftc HorosAtlasConversion.swift')
    ran = subprocess.run([str(path / 'test')], capture_output=True, text=True)
    if ran.returncode != 0:
        print(ran.stdout)
        print(ran.stderr)
        raise SystemExit('FAIL: atlas conversion tests')
    print(ran.stdout.strip())
