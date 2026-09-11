#!/usr/bin/env python3
"""rois_series / JSON format diagnosis: incompatible or empty is never a silent success."""
from pathlib import Path
import json
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
fixture = root / 'tests/fixtures/roi-association/axial-length.json'
code = r'''
import Foundation
import AppKit

func close(_ a: Double, _ b: Double, _ e: Double = 1e-9) {
    precondition(abs(a - b) < e, "\(a) != \(b)")
}

precondition(ROIArchiveFormat.persistedROIArchiveFields.contains("name"))
precondition(ROIArchiveFormat.persistedROIArchiveFields.contains("color"))
precondition(ROIArchiveFormat.persistedROIArchiveFields.contains("type"))
precondition(ROIArchiveFormat.persistedROIArchiveFields.contains("points"))
precondition(ROIArchiveFormat.absentROIArchiveIdentityFields.contains("sopInstanceUID"))
precondition(ROIArchiveFormat.absentROIArchiveIdentityFields.contains("seriesInstanceUID"))
precondition(ROIArchiveFormat.absentROIArchiveIdentityFields.contains("frame"))
precondition(ROIArchiveFormat.absentROIArchiveIdentityFields.contains("imageOrientationPatient"))

precondition(ROIArchiveFormat.classify(Data()) == .empty)
precondition(ROIArchiveFormat.classify(Data([0, 1, 2, 3])) == .unknown)
precondition(ROIArchiveFormat.classify(Data("bplist00".utf8)) == .keyedArchive)
precondition(ROIArchiveFormat.classify(Data("{}\n".utf8)) == .jsonInterchange)
var typed = Data([0x04, 0x0b])
typed.append(contentsOf: Data("streamtyped".utf8))
precondition(ROIArchiveFormat.classify(typed) == .typedstream)

let emptyJSON = ROIArchiveFormat.inspectJSON(Data("{}\n".utf8))
precondition(!emptyJSON.canImport)
precondition(emptyJSON.payload == .incompatible)
precondition(emptyJSON.reason.lowercased().contains("format") || emptyJSON.reason.lowercased().contains("missing"))

let garbage = ROIArchiveFormat.inspectJSON(Data("{not json".utf8))
precondition(!garbage.canImport)
precondition(garbage.payload == .incompatible)

let keyed = ROIArchiveInspection()
// Keyed archives are refused at classify time; unarchive is not attempted as success.
precondition(ROIArchiveFormat.classify(Data("bplist00".utf8)) == .keyedArchive)

let nothing = ROIArchiveFormat.inspectUnarchived(nil)
precondition(!nothing.canImport)
precondition(nothing.payload == .empty)
precondition(nothing.reason.lowercased().contains("no") || nothing.reason.lowercased().contains("nothing"))

let emptyList = ROIArchiveFormat.inspectUnarchived(NSArray())
precondition(!emptyList.canImport)
precondition(emptyList.payload == .empty)
precondition(emptyList.reason.contains("no ROI"))

let emptySeries = ROIArchiveFormat.inspectUnarchived([[]])
precondition(!emptySeries.canImport)
precondition(emptySeries.reason.contains("no ROI"))

let emptyNested = ROIArchiveFormat.inspectUnarchived([[[]]])
precondition(!emptyNested.canImport)
precondition(emptyNested.reason.contains("no ROI"))

let wrongRoot = ROIArchiveFormat.inspectUnarchived("rois_series")
precondition(!wrongRoot.canImport)
precondition(wrongRoot.payload == .incompatible)

let strings = ROIArchiveFormat.inspectUnarchived(["a", "b"])
precondition(!strings.canImport)
precondition(strings.payload == .incompatible)

let roiLike = NSObject()
let roiFile = ROIArchiveFormat.inspectUnarchived([roiLike])
precondition(roiFile.canImport)
precondition(roiFile.payload == .roiList)
precondition(roiFile.roiCount == 1)

let series = ROIArchiveFormat.inspectUnarchived([[[roiLike, NSObject()], [roiLike]]])
precondition(series.canImport)
precondition(series.payload == .roisSeries)
precondition(series.movieCount == 1)
precondition(series.sliceCount == 2)
precondition(series.roiCount == 3)

let seriesStrings = ROIArchiveFormat.inspectUnarchived([[["nope"]]])
precondition(!seriesStrings.canImport)
precondition(seriesStrings.payload == .incompatible)

let jsonURL = URL(fileURLWithPath: CommandLine.arguments[1])
let jsonData = try Data(contentsOf: jsonURL)
let jsonInspect = ROIArchiveFormat.inspectJSON(jsonData)
precondition(jsonInspect.canImport)
precondition(jsonInspect.payload == .jsonInterchange)
precondition(jsonInspect.roiCount == 1)

let decoded = try ROIInterchange.decode(jsonData)
let encoded = try ROIInterchange.encode(decoded, generator: "test")
let again = try ROIInterchange.decode(encoded)
precondition(again.images.count == 1)
let roi = again.images[0].rois[0]
precondition(roi.name == "QA Length")
precondition(roi.typeCode == ROIInterchangeType.length.rawValue)
close(roi.red, 0)
close(roi.green, 1)
close(roi.blue, 0)
precondition(roi.points.count == 2)
close(Double(roi.points[0].pointValue.x), 10)
close(Double(roi.points[0].pointValue.y), 20)
close(Double(roi.points[1].pointValue.x), 40)
close(Double(roi.points[1].pointValue.y), 20)
precondition(roi.patientPoints.count == 2)
close(roi.patientPoints[0][0], 10)
close(roi.patientPoints[0][1], 20)
close(roi.patientPoints[0][2], 0)

print("PASS: archive metadata audit, empty/incompatible diagnosis, JSON round-trip of geometry/color/name/type")
'''
fixture.parent.mkdir(parents=True, exist_ok=True)
document = {
    'format': 'org.horosproject.roi-interchange',
    'version': 1,
    'coordinateSystems': {
        'pixel': 'image pixels: x right, y down, origin at the top-left corner of pixel (0,0), one unit per pixel',
        'patient': 'DICOM patient coordinates (LPS), millimetres',
    },
    'series': {
        'studyInstanceUID': '1.2.826.0.1.3680043.8.498.231',
        'seriesInstanceUID': '1.2.826.0.1.3680043.8.498.231.1',
        'frameOfReferenceUID': '1.2.826.0.1.3680043.8.498.231.for',
        'modality': 'CT',
        'seriesDescription': 'Synthetic axial QA',
    },
    'images': [{
        'index': 0,
        'temporalIndex': 0,
        'sopInstanceUID': '1.2.826.0.1.3680043.8.498.231.sop.a',
        'frame': 0,
        'rows': 256,
        'columns': 256,
        'pixelSpacing': [1.0, 1.0],
        'imagePositionPatient': [0.0, 0.0, 0.0],
        'imageOrientationPatient': [1.0, 0.0, 0.0, 0.0, 1.0, 0.0],
        'rois': [{
            'name': 'QA Length',
            'type': 'length',
            'typeCode': 5,
            'points': [[10.0, 20.0], [40.0, 20.0]],
            'pointsPatient': [[10.0, 20.0, 0.0], [40.0, 20.0, 0.0]],
            'color': [0.0, 1.0, 0.0],
            'thickness': 2.0,
            'opacity': 1.0,
        }],
    }],
}
if not fixture.exists():
    fixture.write_text(json.dumps(document, indent=2, sort_keys=True) + '\n')
with tempfile.TemporaryDirectory(prefix='horos-roi-archive-') as d:
    p = Path(d)
    (p / 'main.swift').write_text(code)
    subprocess.run([
        'xcrun', 'swiftc',
        str(root / 'Horos/Sources/ROIIntersliceGeometry.swift'),
        str(root / 'Horos/Sources/ROIInterchange.swift'),
        str(root / 'Horos/Sources/ROIArchiveFormat.swift'),
        str(root / 'Horos/Sources/ROIAssociation.swift'),
        str(p / 'main.swift'), '-o', str(p / 'test')
    ], check=True)
    subprocess.run([str(p / 'test'), str(fixture)], check=True)
