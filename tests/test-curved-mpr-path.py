#!/usr/bin/env python3
"""Draw and complete a Curved MPR path in patient millimetres, including origin."""
from pathlib import Path
import subprocess
import tempfile
root = Path(__file__).resolve().parents[1]
code = r'''
import Foundation

func expect(_ ok: Bool, _ message: String) {
    precondition(ok, message)
}

let session = CurvedMPRPathSession()
expect(session.nodeCount == 0, "empty session starts idle")
expect(session.complete().phase == "rejected", "complete before nodes is rejected")
expect(session.nodeCount == 0, "rejected complete preserves an empty path")

// The volume-geometry fixture places the first slice at patient (0,0,0).
// Origin is a valid node; refusing it made Debug builds abort while drawing.
let origin = session.addPatientNodeX(0, y: 0, z: 0)
expect(origin.accepted && origin.phase == "drawing" && origin.nodeCount == 1,
       "origin in patient space is a drawable node: \(origin.diagnosis)")

let second = session.addPatientNodeX(10, y: 0, z: 0)
expect(second.accepted && second.nodeCount == 2, "second node accepted")
expect(session.complete().phase == "rejected", "two nodes cannot conclude the curve")
expect(session.nodeCount == 2, "short curve is preserved with a diagnosis")

let coincident = session.addPatientNodeX(10, y: 0, z: 0)
expect(!coincident.accepted && session.nodeCount == 2, "coincident node is refused")

let nan = session.addPatientNodeX(.nan, y: 0, z: 4)
expect(!nan.accepted && session.nodeCount == 2, "non-finite node is refused and kept out")

let third = session.addPatientNodeX(10, y: 8, z: 4)
expect(third.accepted && third.nodeCount == 3, "third node makes the curve completable")
let done = session.complete()
expect(done.accepted && done.phase == "complete" && done.nodeCount == 3,
       "three patient nodes conclude the curve: \(done.diagnosis)")

// Close and reopen: a new session can draw again without leftover nodes.
let reopened = CurvedMPRPathSession()
expect(reopened.nodeCount == 0, "reopened path is empty")
expect(reopened.addPatientNodeX(1, y: 2, z: 3).accepted, "reopened session accepts a first node")
expect(reopened.addPatientNodeX(4, y: 2, z: 3).accepted, "reopened session accepts a second node")
expect(reopened.addPatientNodeX(4, y: 6, z: 7).accepted, "reopened session accepts a third node")
expect(reopened.complete().phase == "complete", "reopened session concludes")

print("PASS: origin is drawable; three nodes complete; short/NaN input is preserved")
'''
with tempfile.TemporaryDirectory(prefix='horos-curved-mpr-path-') as d:
    p = Path(d)
    (p / 'main.swift').write_text(code)
    subprocess.run([
        'xcrun', 'swiftc',
        str(root / 'Horos/Sources/CurvedMPRPath.swift'),
        str(p / 'main.swift'), '-o', str(p / 'test')
    ], check=True)
    subprocess.run([str(p / 'test')], check=True)
