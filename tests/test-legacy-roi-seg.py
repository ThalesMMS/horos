#!/usr/bin/env python3
"""Legacy Horos/OsiriX ROI archives become an editable derived SEG (#377 B).

Brush and closed-polygon ROIs that already carry SOP/patient geometry become a
binary DICOM SEG that reuses the #376 model. Typedstream archives have no SOP
fields, so they are refused rather than matched by patient name. Lengths and
text are not regions. The original ROI name/type/colour stay recoverable so the
conversion can be reversed. Re-converting the same source keeps the tracking
UID. Atlas conversion and Metal surfaces stay on their own types.
"""
from pathlib import Path
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
source = root / 'Horos/Sources/HorosLegacyROISeg.swift'
seg = root / 'Horos/Sources/DicomSEG.swift'
interchange = root / 'Horos/Sources/ROIInterchange.swift'
archive = root / 'Horos/Sources/ROIArchiveFormat.swift'
pbx = (root / 'Horos.xcodeproj/project.pbxproj').read_text(encoding='utf-8')
database = (root / 'Horos/Sources/DicomDatabase.mm').read_bytes().decode('latin1')
failures = []

if not source.is_file():
    print('FAIL: Horos/Sources/HorosLegacyROISeg.swift is missing')
    sys.exit(1)
if 'HorosLegacyROISeg.swift' not in pbx:
    failures.append('HorosLegacyROISeg.swift is not in the Xcode project')
if 'HorosLegacyROISeg.swift in Sources' not in pbx:
    failures.append('HorosLegacyROISeg.swift is not in a Sources build phase')
if 'HorosLegacyROISeg' in database:
    failures.append('legacy ROI→SEG must not be wired as the incoming-folder indexer')
if (root / 'Scripts/test_plugin_cleanup.py').exists() or (root / 'tests/test_plugin_cleanup.py').exists():
    failures.append('ystarrev test_plugin_cleanup.py was copied; plugin removal is out of scope')

archive_src = archive.read_text(encoding='utf-8') if archive.is_file() else ''
for field in ('sopInstanceUID', 'seriesInstanceUID', 'frameOfReferenceUID', 'frame'):
    if field not in archive_src:
        failures.append('ROIArchiveFormat no longer names the identity %s a typedstream lacks' % field)

driver = r'''
import Foundation
import AppKit

func expect(_ ok: Bool, _ message: String) {
    if !ok { fputs("FAIL: \(message)\n", stderr); exit(1) }
}

func point(_ x: Double, _ y: Double) -> NSValue {
    NSValue(point: NSPoint(x: x, y: y))
}

func brushSeries(includeSOP: Bool) -> ROIInterchangeSeries {
    let series = ROIInterchangeSeries()
    series.studyInstanceUID = "1.2.840.10008.1.2.377.study"
    series.seriesInstanceUID = "1.2.840.10008.1.2.377.series"
    series.frameOfReferenceUID = "1.2.840.10008.1.2.377.for"
    let image = ROIInterchangeImage()
    image.index = 0
    image.sopInstanceUID = includeSOP ? "1.2.840.10008.1.2.377.sop" : nil
    image.rows = 8
    image.columns = 8
    image.pixelSpacingX = 1
    image.pixelSpacingY = 1
    image.sliceThickness = 2
    image.imagePosition = [0, 0, 0]
    image.imageOrientation = [1, 0, 0, 0, 1, 0]
    let roi = ROIInterchangeROI()
    roi.name = "kidney brush"
    roi.typeCode = ROIInterchangeType.brush.rawValue
    roi.red = 0.2; roi.green = 0.8; roi.blue = 0.1
    roi.brushWidth = 3
    roi.brushHeight = 3
    roi.brushOriginX = 2
    roi.brushOriginY = 2
    roi.brushMask = Data([1, 1, 0, 1, 1, 0, 0, 0, 0])
    image.rois = [roi]
    series.images = [image]
    return series
}

func polygonSeries() -> ROIInterchangeSeries {
    let series = brushSeries(includeSOP: true)
    let roi = ROIInterchangeROI()
    roi.name = "closed square"
    roi.typeCode = ROIInterchangeType.closedPolygon.rawValue
    roi.red = 1; roi.green = 0; roi.blue = 0
    roi.points = [point(1, 1), point(4, 1), point(4, 4), point(1, 4)]
    series.images[0].rois = [roi]
    return series
}

func lengthSeries() -> ROIInterchangeSeries {
    let series = brushSeries(includeSOP: true)
    let roi = ROIInterchangeROI()
    roi.name = "ruler"
    roi.typeCode = ROIInterchangeType.length.rawValue
    roi.points = [point(0, 0), point(3, 0)]
    series.images[0].rois = [roi]
    return series
}

expect(HorosLegacyROISeg.usesSharedSEGModel, "B reuses #376, it does not invent a second ROI store")
expect(HorosLegacyROISeg.mayGuessIdentityFromPatientName == false, "no patient-name matcher")
expect(ROIArchiveFormat.absentROIArchiveIdentityFields.contains("sopInstanceUID"),
       "typedstream still lacks SOP identity")

switch HorosLegacyROISeg.convert(brushSeries(includeSOP: false)) {
case .success:
    expect(false, "a payload without SOP must not become a SEG")
case .failure(let refusal):
    expect(refusal == .missingIdentity, "missing SOP is missingIdentity, not a guessed match: \(refusal)")
}

expect(HorosLegacyROISeg.convertTypedstreamArchive(Data([0x04, 0x0b]) + Data("streamtyped".utf8)) == .missingIdentity,
       "typedstream archives cannot be associated by SOP they do not store")

switch HorosLegacyROISeg.convert(lengthSeries()) {
case .success:
    expect(false, "a length is not a region")
case .failure(let refusal):
    expect(refusal == .unsupportedType, "length/text stay measurements: \(refusal)")
}

let first = try { () -> DicomSEGDocument in
    switch HorosLegacyROISeg.convert(brushSeries(includeSOP: true)) {
    case .success(let document): return document
    case .failure(let refusal):
        expect(false, "identified brush must convert: \(refusal)")
        exit(1)
    }
}()
expect(first.kind == .binary, "brush becomes binary SEG")
expect(first.previewKind == "segmentation", "derived SEG is not a scalar preview")
expect(first.identity.sourceSOPInstanceUIDs == ["1.2.840.10008.1.2.377.sop"], "source SOP preserved")
expect(first.identity.frameOfReferenceUID == "1.2.840.10008.1.2.377.for", "FoR preserved")
expect(first.identity.studyInstanceUID == "1.2.840.10008.1.2.377.study", "study preserved")
expect(first.geometry.rows == 8 && first.geometry.columns == 8, "mask is in image space")
expect(first.segments.count == 1, "one brush, one segment")
let kidney = first.segments[0]
expect(kidney.label == "kidney brush", "name")
expect(abs(kidney.color.g - 0.8) < 1e-9, "colour")
expect(kidney.kind == .binary, "binary")
expect(kidney.algorithm == "MANUAL", "manual provenance")
expect(kidney.occupiedVoxels == 4, "four painted brush pixels, not the empty 3x3")
expect(kidney.frames[0][2 * 8 + 2] == 1, "mask origin lands on the image")
expect(kidney.frames[0][2 * 8 + 4] == 0, "unpainted brush column stays empty")
expect(kidney.provenance.contains("derived-from-legacy-roi"), "derived, not a second native SEG")
expect(kidney.provenance.contains("brush"), "type survives in provenance")
let restored = HorosLegacyROISeg.originalROI(from: kidney)!
expect(restored.name == "kidney brush", "reversible name")
expect(restored.typeCode == ROIInterchangeType.brush.rawValue, "reversible type")
expect(abs(restored.green - 0.8) < 1e-9, "reversible colour")
expect(restored.brushWidth == 3 && restored.brushHeight == 3, "reversible brush size")
expect(restored.brushMask == Data([1, 1, 0, 1, 1, 0, 0, 0, 0]), "mask round-trips")

let encoded = try DicomSEGCodec.encode(first)
let decoded = DicomSEGCodec.decode(encoded)
expect(decoded.segments[0].label == "kidney brush", "SEG bytes keep the label")
expect(decoded.segments[0].frames[0][2 * 8 + 2] == 1, "SEG bytes keep the mask")
expect(decoded.identity.sourceSOPInstanceUIDs == ["1.2.840.10008.1.2.377.sop"], "source SOP in DICOM")

let second = try { () -> DicomSEGDocument in
    switch HorosLegacyROISeg.convert(brushSeries(includeSOP: true)) {
    case .success(let document): return document
    case .failure(let refusal):
        expect(false, "second convert failed: \(refusal)")
        exit(1)
    }
}()
expect(second.segments[0].trackingUID == kidney.trackingUID, "reimport is idempotent")
expect(second.identity.sopInstanceUID != first.identity.sopInstanceUID, "each derived file still gets its own SOP")

let polygon = try { () -> DicomSEGDocument in
    switch HorosLegacyROISeg.convert(polygonSeries()) {
    case .success(let document): return document
    case .failure(let refusal):
        expect(false, "closed polygon must fill: \(refusal)")
        exit(1)
    }
}()
let square = polygon.segments[0]
expect(square.occupiedVoxels >= 9, "filled 3x3 interior of the square, got \(square.occupiedVoxels)")
expect(square.frames[0][2 * 8 + 2] == 1, "interior pixel is inside")
expect(square.frames[0][0] == 0, "outside stays empty")
let restoredPoly = HorosLegacyROISeg.originalROI(from: square)!
expect(restoredPoly.typeCode == ROIInterchangeType.closedPolygon.rawValue, "polygon type reversible")
expect(restoredPoly.points.count == 4, "vertices reversible")

print("PASS: legacy brush/polygon ROIs become derived SEG without guessing identity")
'''

with tempfile.TemporaryDirectory(prefix='horos-legacy-roi-seg-') as tmp:
    path = Path(tmp)
    (path / 'main.swift').write_text(driver)
    built = subprocess.run(
        ['xcrun', '--sdk', 'macosx', 'swiftc',
         '-o', str(path / 'test'),
         str(source), str(seg), str(interchange), str(archive),
         str(path / 'main.swift')],
        capture_output=True, text=True)
    if built.returncode != 0:
        failures.append('HorosLegacyROISeg.swift did not compile:\n%s' % built.stderr[-2000:])
    else:
        ran = subprocess.run([str(path / 'test')], capture_output=True, text=True, timeout=60)
        print(ran.stdout.strip())
        if ran.returncode != 0:
            failures.append('the conversion contract failed: %s' % (ran.stderr or ran.stdout)[-1500:])

for failure in failures:
    print('FAIL: %s' % failure)
if failures:
    sys.exit(1)
print('ok: identified brush and closed-polygon ROIs become derived SEG; archives without SOP are refused')
