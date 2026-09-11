#!/usr/bin/env python3
"""Import a patient-space xyz centerline and match the interactive CPR path."""
from pathlib import Path
import subprocess
import tempfile
root = Path(__file__).resolve().parents[1]
code = r'''
import Foundation

func expect(_ ok: Bool, _ message: String) {
    precondition(ok, message)
}

func identity(from points: [(Double, Double, Double)]) -> String {
    let session = CurvedMPRPathSession()
    var packed: [NSNumber] = []
    for point in points {
        let decision = session.addPatientNodeX(point.0, y: point.1, z: point.2)
        expect(decision.accepted, "interactive node refused: \(decision.diagnosis)")
        packed.append(contentsOf: [NSNumber(value: point.0), NSNumber(value: point.1),
                                   NSNumber(value: point.2)])
    }
    expect(session.complete().phase == "complete", "interactive path must complete")
    return CPRCenterlineImport.viewIdentity(from: packed)
}

let interactivePoints = [(0.0, 0.0, 0.0), (10.0, 0.0, 0.0), (10.0, 8.0, 4.0)]
let interactiveID = identity(from: interactivePoints)

let text = """
# space=patient
# units=mm
0 0 0
10 0 0
10 8 4
"""
let imported = CPRCenterlineImport.importPatientSpaceText(text)
expect(imported.accepted && imported.phase == "complete",
       "patient-space file must complete: \(imported.diagnosis)")
expect(imported.space == "patient" && imported.nodeCount == 3,
       "imported nodes stay in patient space")
expect(imported.viewIdentity == interactiveID,
       "imported views must match the interactive centerline\n\(imported.viewIdentity)\n---\n\(interactiveID)")

let defaultSpace = CPRCenterlineImport.importPatientSpaceText("0 0 0\n10 0 0\n10 8 4\n")
expect(defaultSpace.accepted && defaultSpace.viewIdentity == interactiveID,
       "omitted space header defaults to patient millimetres")

let csv = CPRCenterlineImport.importPatientSpaceText("x,y,z\n0,0,0\n10,0,0\n10,8,4\n")
expect(csv.accepted && csv.viewIdentity == interactiveID, "csv patient nodes import")

let commas = CPRCenterlineImport.importPatientSpaceText("0, 0, 0; 10, 0, 0; 10, 8, 4\n")
expect(commas.accepted && commas.viewIdentity == interactiveID,
       "semicolon groups are patient nodes")

let oneLine = CPRCenterlineImport.importPatientSpaceText("0 0 0 10 0 0 10 8 4\n")
expect(oneLine.accepted && oneLine.viewIdentity == interactiveID,
       "one-line xyz triplets import")

let extra = CPRCenterlineImport.importPatientSpaceText("0 0 0 1.2\n10 0 0 1.1\n10 8 4 0.9\n")
expect(extra.accepted && extra.viewIdentity == interactiveID,
       "a radius column is ignored")

let lps = CPRCenterlineImport.importPatientSpaceText("# space=lps\n0 0 0\n10 0 0\n10 8 4\n")
expect(lps.accepted && lps.space == "patient" && lps.viewIdentity == interactiveID,
       "LPS is the DICOM patient frame")

let pixel = CPRCenterlineImport.importPatientSpaceText("# space=pixel\n0 0 0\n10 0 0\n10 8 4\n")
expect(!pixel.accepted && pixel.nodeCount == 0,
       "pixel space is refused: \(pixel.diagnosis)")
expect(pixel.diagnosis == "coordinates are not patient space",
       "pixel refusal keeps its diagnosis: \(pixel.diagnosis)")

let voxels = CPRCenterlineImport.importPatientSpaceText("# units=px\n0 0 0\n10 0 0\n10 8 4\n")
expect(!voxels.accepted && voxels.diagnosis == "coordinates are not patient millimetres",
       "pixel units are refused")

let short = CPRCenterlineImport.importPatientSpaceText("0 0 0\n10 0 0\n")
expect(!short.accepted && short.diagnosis == "need at least 3 nodes",
       "two nodes cannot produce CPR views")

let nan = CPRCenterlineImport.importPatientSpaceText("0 0 0\n10 nan 0\n10 8 4\n")
expect(!nan.accepted && nan.nodeCount == 0, "NaN refuses the whole file")

let coincident = CPRCenterlineImport.importPatientSpaceText("0 0 0\n10 0 0\n10 0 0\n10 8 4\n")
expect(coincident.accepted && coincident.nodeCount == 3 && coincident.viewIdentity == interactiveID,
       "a coincident node is skipped like the interactive path")

let empty = CPRCenterlineImport.importPatientSpaceText("# space=patient\n")
expect(!empty.accepted, "an empty file is refused")

let malformed = CPRCenterlineImport.importPatientSpaceText("0 0\n10 0 0\n10 8 4\n")
expect(!malformed.accepted && malformed.diagnosis == "malformed centerline line",
       "a short line is refused")

let roundTrip = CPRCenterlineImport.importPatientSpaceText(
    CPRCenterlineImport.patientSpaceText(from: imported.packedNodes))
expect(roundTrip.accepted && roundTrip.viewIdentity == interactiveID,
       "exported patient-space text reimports to the same views")

let artery = [
    (4.0, 16.0, 0.0), (8.0, 16.0, 6.0), (12.0, 16.0, 12.0),
    (18.0, 14.0, 18.0), (24.0, 12.0, 24.0), (28.0, 12.0, 30.0),
]
let arteryID = identity(from: artery)
let arteryText = """
# space=patient
4 16 0
8 16 6
12 16 12
18 14 18
24 12 24
28 12 30
"""
let arteryImport = CPRCenterlineImport.importPatientSpaceText(arteryText)
expect(arteryImport.accepted && arteryImport.nodeCount == 6,
       "volume-geometry centerline imports")
expect(arteryImport.viewIdentity == arteryID,
       "longer imported path matches the interactive session")
expect(arteryImport.viewIdentity.contains("transverse=0.5"),
       "imported views keep the CPR transverse default")
expect(arteryImport.viewIdentity.contains("spacing=2.0") || arteryImport.viewIdentity.contains("spacing=2"),
       "imported views keep the 2 mm transverse spacing")

print("PASS: patient-space xyz imports the same CPR views as the interactive centerline")
'''
with tempfile.TemporaryDirectory(prefix='horos-cpr-centerline-import-') as d:
    p = Path(d)
    (p / 'main.swift').write_text(code)
    subprocess.run([
        'xcrun', 'swiftc',
        str(root / 'Horos/Sources/CurvedMPRPath.swift'),
        str(root / 'Horos/Sources/CPRCenterlineImport.swift'),
        str(p / 'main.swift'), '-o', str(p / 'test')
    ], check=True)
    subprocess.run([str(p / 'test')], check=True)
