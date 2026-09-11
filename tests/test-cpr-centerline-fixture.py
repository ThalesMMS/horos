#!/usr/bin/env python3
"""Generator fixtures import as the same views as the interactive session."""
from pathlib import Path
import subprocess
import tempfile
root = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='horos-cpr-centerline-fixture-') as d:
    dest = Path(d) / 'fixture'
    subprocess.run([
        'python3', str(root / 'tools/generate-cpr-centerline-fixture.py'), str(dest)
    ], check=True)
    interactive = (dest / 'interactive-equivalent.txt').read_text()
    artery = (dest / 'volume-geometry.txt').read_text()
    pixel = (dest / 'pixel-labeled.txt').read_text()
    code = r'''
import Foundation

func expect(_ ok: Bool, _ message: String) {
    precondition(ok, message)
}

let interactive = CPRCenterlineImport.importPatientSpaceText(CommandLine.arguments[1])
expect(interactive.accepted && interactive.nodeCount == 3,
       "interactive fixture: \(interactive.diagnosis)")
let session = CurvedMPRPathSession()
expect(session.addPatientNodeX(0, y: 0, z: 0).accepted, "origin")
expect(session.addPatientNodeX(10, y: 0, z: 0).accepted, "second")
expect(session.addPatientNodeX(10, y: 8, z: 4).accepted, "third")
expect(session.complete().phase == "complete", "interactive complete")
let packed: [NSNumber] = [0, 0, 0, 10, 0, 0, 10, 8, 4].map { NSNumber(value: $0) }
expect(interactive.viewIdentity == CPRCenterlineImport.viewIdentity(from: packed),
       "generator interactive fixture must match the drawn path")

let artery = CPRCenterlineImport.importPatientSpaceText(CommandLine.arguments[2])
expect(artery.accepted && artery.nodeCount == 6, "volume fixture: \(artery.diagnosis)")
expect(artery.space == "patient", "volume fixture stays in patient space")

let pixel = CPRCenterlineImport.importPatientSpaceText(CommandLine.arguments[3])
expect(!pixel.accepted, "pixel-labeled fixture must be refused")

print("PASS: generated fixtures import as patient-space CPR views")
'''
    build = Path(d)
    (build / 'main.swift').write_text(code)
    subprocess.run([
        'xcrun', 'swiftc',
        str(root / 'Horos/Sources/CurvedMPRPath.swift'),
        str(root / 'Horos/Sources/CPRCenterlineImport.swift'),
        str(build / 'main.swift'), '-o', str(build / 'test')
    ], check=True)
    subprocess.run([str(build / 'test'), interactive, artery, pixel], check=True)
