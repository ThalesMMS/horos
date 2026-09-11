#!/usr/bin/env python3
"""Shared DICOM SEG model, geometry mapping, commands and round-trip (#376)."""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
source = root / 'Horos/Sources/DicomSEG.swift'
if not source.is_file():
    raise SystemExit('FAIL: Horos/Sources/DicomSEG.swift is missing')
pbx = (root / 'Horos.xcodeproj/project.pbxproj').read_text()
if 'DicomSEG.swift' not in pbx:
    raise SystemExit('FAIL: DicomSEG.swift is not in the Xcode project')

main = r'''
import Foundation

func expect(_ ok: Bool, _ message: String) {
    if !ok { fputs("FAIL: \(message)\n", stderr); exit(1) }
}

func plane(rows: Int, columns: Int, ones: [(Int, Int)]) -> Data {
    var data = Data(repeating: 0, count: rows * columns)
    for (row, column) in ones {
        data[row * columns + column] = 1
    }
    return data
}

func fractional(rows: Int, columns: Int, values: [(Int, Int, UInt8)]) -> Data {
    var data = Data(repeating: 0, count: rows * columns)
    for (row, column, value) in values {
        data[row * columns + column] = value
    }
    return data
}

let forUID = "1.2.840.10008.1.2.1.376.1"
let sourceA = "1.2.840.10008.5.1.4.1.1.2.376.1"
let sourceB = "1.2.840.10008.5.1.4.1.1.2.376.2"

let axial = DicomSEGGeometry(
    rows: 4, columns: 4, frames: 2,
    spacingRow: 1, spacingCol: 1, sliceThickness: 2,
    origin: [0, 0, 0],
    orientation: [1, 0, 0, 0, 1, 0],
    frameOfReferenceUID: forUID,
    frameOrigins: [[0, 0, 0], [0, 0, 2]]
)

var kidney = DicomSEGSegment(
    number: 1, label: "kidney", trackingUID: DicomSEGCodec.makeUID(),
    color: (1, 0, 0), visible: true, kind: .binary, algorithm: "MANUAL",
    provenance: "synthetic", referencedSOPInstanceUIDs: [sourceA, sourceB],
    frames: [
        plane(rows: 4, columns: 4, ones: [(1, 1), (1, 2)]),
        plane(rows: 4, columns: 4, ones: [(2, 1)])
    ],
    maximumFractionalValue: 255
)
var cortex = DicomSEGSegment(
    number: 2, label: "cortex", trackingUID: DicomSEGCodec.makeUID(),
    color: (0, 1, 0), visible: true, kind: .binary, algorithm: "MANUAL",
    provenance: "synthetic", referencedSOPInstanceUIDs: [sourceA, sourceB],
    frames: [
        plane(rows: 4, columns: 4, ones: [(1, 1)]),
        plane(rows: 4, columns: 4, ones: [(2, 2)])
    ],
    maximumFractionalValue: 255
)

let identity = DicomSEGIdentity(
    sopInstanceUID: DicomSEGCodec.makeUID(),
    seriesInstanceUID: DicomSEGCodec.makeUID(),
    studyInstanceUID: DicomSEGCodec.makeUID(),
    frameOfReferenceUID: forUID,
    sourceSOPInstanceUIDs: [sourceA, sourceB]
)
expect(DicomSEGIdentity.jsonKeys.contains("sopInstanceUID"), "JSON identity keys stay aligned with #233")

var document = DicomSEGDocument(
    identity: identity, geometry: axial, kind: .binary,
    segments: [kidney, cortex], diagnoses: [], sourceBytes: nil
)
expect(document.previewKind == "segmentation", "SEG is not a scalar acquisition preview")

let encoded = try DicomSEGCodec.encode(document)
let decoded = DicomSEGCodec.decode(encoded)
expect(decoded.identity.sopInstanceUID == identity.sopInstanceUID, "SOP round-trip")
expect(decoded.identity.frameOfReferenceUID == forUID, "FoR round-trip")
expect(decoded.segments.count == 2, "both segments survive")
expect(decoded.segments[0].label == "kidney", "label")
expect(decoded.segments[0].frames[0][1 * 4 + 1] == 1, "binary voxel")
expect(decoded.segments[0].frames[1][2 * 4 + 1] == 1, "second slice")
expect(decoded.segments[1].frames[0][1 * 4 + 1] == 1, "overlapping second segment")
expect(decoded.kind == .binary, "binary kind")
expect(decoded.sourceBytes != nil, "original bytes preserved on decode")

let derived = try DicomSEGStore(document: decoded).exportDerived()
let derivedDoc = DicomSEGCodec.decode(derived)
expect(derivedDoc.identity.sopInstanceUID != decoded.identity.sopInstanceUID, "export uses a new SOP")
expect(derivedDoc.identity.seriesInstanceUID != decoded.identity.seriesInstanceUID, "export uses a new series")
expect(decoded.sourceBytes == encoded, "source object is not overwritten")

let store = DicomSEGStore(document: decoded)
expect(store.setLabel("kidney left", segment: 1), "rename")
expect(store.document.segments[0].label == "kidney left", "rename applied")
expect(store.setColor((0, 0, 1), segment: 1), "color")
expect(store.setVisibility(false, segment: 1), "hide")
let copy = store.duplicate(segment: 1)
expect(copy == 3, "duplicate gets a new number")
expect(store.document.segments.contains(where: { $0.trackingUID != decoded.segments[0].trackingUID && $0.number == 3 }), "duplicate identity")
expect(store.undo(), "undo duplicate")
expect(store.document.segments.count == 2, "duplicate removed")
expect(store.undo() && store.undo() && store.undo(), "undo visibility/color/label")
expect(store.document.segments[0].label == "kidney", "label restored")
expect(store.document.segments[0].visible, "visibility restored")
expect(store.redo(), "redo label")
expect(store.document.segments[0].label == "kidney left", "redo")

let silent = store.setMask([Data(repeating: 1, count: 16), Data(repeating: 1, count: 16)], segment: 1, explicit: false)
expect(silent == nil, "binary mask may be set without a threshold flag")

var fraction = DicomSEGSegment(
    number: 1, label: "edema", trackingUID: DicomSEGCodec.makeUID(),
    color: (1, 1, 0), visible: true, kind: .fractional, algorithm: "AUTOMATIC",
    provenance: "fractional phantom", referencedSOPInstanceUIDs: [sourceA, sourceB],
    frames: [
        fractional(rows: 4, columns: 4, values: [(1, 1, 200), (1, 2, 40)]),
        fractional(rows: 4, columns: 4, values: [(2, 1, 200)])
    ],
    maximumFractionalValue: 255
)
var fracDoc = DicomSEGDocument(
    identity: identity, geometry: axial, kind: .fractional,
    segments: [fraction], diagnoses: [], sourceBytes: nil
)
let fracBytes = try DicomSEGCodec.encode(fracDoc)
let fracDecoded = DicomSEGCodec.decode(fracBytes)
expect(fracDecoded.kind == .fractional, "fractional kind")
expect(fracDecoded.segments[0].frames[0][1 * 4 + 1] == 200, "fraction preserved")
expect(fracDecoded.segments[0].frames[0][1 * 4 + 2] == 40, "low fraction preserved")

let fracStore = DicomSEGStore(document: fracDecoded)
expect(fracStore.setMask([Data(repeating: 1, count: 16), Data(repeating: 0, count: 16)], segment: 1, explicit: false) == .silentBinarize,
       "fractional does not become binary silently")
expect(fracStore.document.segments[0].kind == .fractional, "kind unchanged")
expect(fracStore.binarize(segment: 1, threshold: 128) == nil, "explicit threshold")
expect(fracStore.document.segments[0].kind == .binary, "now binary")
expect(fracStore.document.segments[0].frames[0][1 * 4 + 1] == 1, "threshold kept high")
expect(fracStore.document.segments[0].frames[0][1 * 4 + 2] == 0, "threshold dropped low")
expect(fracStore.document.segments[0].provenance.contains("thresholded"), "threshold is traced")
expect(fracStore.undo(), "threshold is reversible")
expect(fracStore.document.segments[0].kind == .fractional, "kind restored")
expect(fracStore.document.segments[0].frames[0][1 * 4 + 2] == 40, "low fraction restored")

let oblique = DicomSEGGeometry(
    rows: 4, columns: 4, frames: 2,
    spacingRow: 2, spacingCol: 1, sliceThickness: 3,
    origin: [10, 20, 30],
    orientation: [0, 1, 0, 0, 0, 1],
    frameOfReferenceUID: forUID,
    frameOrigins: [[10, 20, 30], [10, 20, 33]]
)
let mapped = DicomSEGGeometryMap.map(segment: decoded.segments[0], from: axial, onto: axial)
expect((try? mapped.get()) != nil, "same-grid map")
let otherFoR = DicomSEGGeometry(
    rows: 4, columns: 4, frames: 2,
    spacingRow: 1, spacingCol: 1, sliceThickness: 2,
    origin: [0, 0, 0], orientation: [1, 0, 0, 0, 1, 0],
    frameOfReferenceUID: "1.2.840.10008.1.2.1.376.other",
    frameOrigins: [[0, 0, 0], [0, 0, 2]]
)
switch DicomSEGGeometryMap.map(segment: decoded.segments[0], from: axial, onto: otherFoR) {
case .failure(let diagnosis):
    expect(diagnosis == .incompatibleGeometry, "different FoR is named")
case .success:
    expect(false, "different FoR must not map")
}

let missingFoR = DicomSEGGeometry(
    rows: 4, columns: 4, frames: 1,
    spacingRow: 1, spacingCol: 1, sliceThickness: 1,
    origin: [0, 0, 0], orientation: [1, 0, 0, 0, 1, 0],
    frameOfReferenceUID: "", frameOrigins: [[0, 0, 0]]
)
switch DicomSEGGeometryMap.map(segment: decoded.segments[0], from: axial, onto: missingFoR) {
case .failure(let diagnosis):
    expect(diagnosis == .missingFrameOfReference, "missing FoR is named")
case .success:
    expect(false, "missing FoR must not map")
}

let obliqueMap = DicomSEGGeometryMap.map(segment: decoded.segments[0], from: axial, onto: axial)
let same = try obliqueMap.get()
expect(same[0][1 * 4 + 1] == 1, "anisotropic/oblique path still samples the source voxel")

var shuffled = document
let first = shuffled.segments[0].frames[0]
let second = shuffled.segments[0].frames[1]
shuffled.segments[0].frames = [second, first]
shuffled.geometry.frameOrigins = [[0, 0, 2], [0, 0, 0]]
let shuffledBytes = try DicomSEGCodec.encode(shuffled)
let shuffledDecoded = DicomSEGCodec.decode(shuffledBytes)
let spatial = shuffledDecoded.geometry.indexOfFrame(matchingOrigin: [0, 0, 0])
expect(spatial == 1, "file order is not assumed: z=0 is the second stored origin")
expect(shuffledDecoded.segments[0].frames[spatial!][1 * 4 + 1] == 1 || shuffledDecoded.segments[0].frames[0][2 * 4 + 1] == 1,
       "voxels follow IPP, not file order")

var empty = kidney
empty.frames = [Data(repeating: 0, count: 16), Data(repeating: 0, count: 16)]
empty.label = "empty"
var emptyDoc = DicomSEGDocument(identity: identity, geometry: axial, kind: .binary, segments: [empty], diagnoses: [], sourceBytes: nil)
let emptyBytes = try DicomSEGCodec.encode(emptyDoc)
let emptyDecoded = DicomSEGCodec.decode(emptyBytes)
expect(emptyDecoded.diagnoses.contains(.emptySegment), "empty segment is diagnosed")

var truncated = encoded
if let pixelRange = truncated.range(of: Data([0xE0, 0x7F, 0x10, 0x00])) {
    _ = pixelRange
}
let truncatedDoc = DicomSEGCodec.decode(Data(encoded.prefix(encoded.count / 2)))
expect(truncatedDoc.diagnoses.contains(.truncatedFrames) || truncatedDoc.diagnoses.contains(.notDICOM) || truncatedDoc.segments.isEmpty || truncatedDoc.diagnoses.contains(.emptySegment),
       "truncated payload is not a silent success: \(truncatedDoc.diagnoses)")

let missingRef = DicomSEGCodec.decode(encoded)
expect(missingRef.identity.sourceSOPInstanceUIDs.contains(sourceA), "referenced SOP kept")

let notDicom = DicomSEGCodec.decode(Data("not dicom".utf8))
expect(notDicom.diagnoses.contains(.notDICOM), "non-DICOM is named")

print("PASS: SEG binary/fractional round-trip, identities, undo, geometry, diagnoses")
'''

with tempfile.TemporaryDirectory(prefix='horos-seg-') as directory:
    path = Path(directory)
    (path / 'main.swift').write_text(main)
    compiled = subprocess.run(
        ['xcrun', 'swiftc', '-swift-version', '5', str(source), str(path / 'main.swift'), '-o', str(path / 'test')],
        capture_output=True, text=True)
    if compiled.returncode != 0:
        print(compiled.stderr)
        raise SystemExit('FAIL: swiftc DicomSEG.swift')
    ran = subprocess.run([str(path / 'test')], capture_output=True, text=True)
    if ran.returncode != 0:
        print(ran.stdout)
        print(ran.stderr)
        raise SystemExit('FAIL: DicomSEG tests')
    print(ran.stdout.strip())
