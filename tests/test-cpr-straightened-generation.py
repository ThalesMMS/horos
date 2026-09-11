#!/usr/bin/env python3
"""Valid centerlines generate; short, degenerate and looping curves stay recoverable."""
from pathlib import Path
import subprocess
import tempfile
root = Path(__file__).resolve().parents[1]
code = r'''
import Foundation

func packed(_ points: [(Double, Double, Double)]) -> [NSNumber] {
    points.flatMap { [NSNumber(value: $0.0), NSNumber(value: $0.1), NSNumber(value: $0.2)] }
}

func expect(_ ok: Bool, _ message: String) {
    precondition(ok, message)
}

let session = CPRStraightenedSession()
expect(session.nodeCount == 0, "empty session starts idle")
let tooFew = session.evaluate(pixelsWide: 100)
expect(tooFew.phase == "rejected" && tooFew.diagnosis == "need at least 3 nodes",
       "two missing nodes are named: \(tooFew.diagnosis)")
expect(tooFew.nodeCount == 0 && tooFew.markingsPreserved, "rejected complete keeps an empty path")

session.replacePackedNodes(packed([(0, 0, 0), (10, 0, 0)]))
let two = session.evaluate(pixelsWide: 100)
expect(!two.accepted && session.nodeCount == 2, "short node list is preserved")

// Phantom: duplicated / near-zero segments after the red points.
session.replacePackedNodes(packed([(0, 0, 0), (10, 0, 0), (10, 0, 0)]))
let degenerate = session.evaluate(pixelsWide: 100)
expect(!degenerate.accepted && degenerate.diagnosis == "degenerate spacing",
       "duplicated nodes are recoverable: \(degenerate.diagnosis)")
expect(degenerate.nodeCount == 3 && degenerate.markingsPreserved,
       "degenerate diagnosis does not drop the markings")

session.replacePackedNodes(packed([(0, 0, 0), (0.2, 0, 0), (0.4, 0.1, 0)]))
let short = session.evaluate(pixelsWide: 100)
expect(!short.accepted && short.diagnosis == "curve too short",
       "a sub-millimetre curve is refused: \(short.diagnosis)")
expect(short.nodeCount == 3, "short curve keeps its three nodes")

// Closed / self-crossing loop: first and last segments meet.
session.replacePackedNodes(packed([
    (0, 0, 0), (20, 0, 0), (20, 20, 0), (0.1, 0.1, 0)
]))
let loop = session.evaluate(pixelsWide: 200)
expect(!loop.accepted && loop.diagnosis == "self-intersecting loop",
       "a loop is named instead of entering the sample walk: \(loop.diagnosis)")
expect(loop.nodeCount == 4 && loop.originalVolumePreserved, "loop refusal keeps original volume")

// Valid phantom centerline.
let validNodes: [(Double, Double, Double)] = [(0, 0, 0), (20, 0, 0), (20, 15, 4)]
session.replacePackedNodes(packed(validNodes))
let ready = session.evaluate(pixelsWide: 100)
expect(ready.accepted && ready.phase == "ready", "valid curve is ready: \(ready.diagnosis)")
expect(abs(ready.lengthMillimetres - 35.524175) < 0.01, "length is the polyline in millimetres")
expect(abs(ready.sampleSpacing - ready.lengthMillimetres / 100) < 1e-9,
       "sample spacing is length / pixelsWide")

// Extreme curvature is still a valid straightened request (U-turn with clearance).
session.replacePackedNodes(packed([
    (0, 0, 0), (30, 0, 0), (32, 8, 0), (32, 40, 0)
]))
let extreme = session.beginGeneration(pixelsWide: 120)
expect(extreme.accepted && extreme.phase == "generating",
       "extreme curvature still generates: \(extreme.diagnosis)")
expect(session.nodeCount == 4, "generation start keeps the red points")

let cancelled = session.cancel()
expect(cancelled.accepted && cancelled.phase == "cancelled",
       "long generation can cancel: \(cancelled.diagnosis)")
expect(cancelled.nodeCount == 4 && cancelled.markingsPreserved,
       "cancel keeps the centerline markings")
expect(cancelled.originalVolumePreserved, "cancel keeps the original volume")
expect(session.nodeCount == 4, "session nodes survive cancel")

let idleCancel = session.cancel()
expect(!idleCancel.accepted && idleCancel.nodeCount == 4,
       "a second cancel is a no-op that still keeps markings")

session.replacePackedNodes(packed(validNodes))
let started = session.beginGeneration(pixelsWide: 80)
expect(started.phase == "generating", "valid curve enters generating")
let done = session.completeGeneration()
expect(done.accepted && done.phase == "complete" && done.nodeCount == 3,
       "valid curves complete straightened: \(done.diagnosis)")
expect(done.originalVolumePreserved && done.markingsPreserved,
       "completion does not drop original volume or markings")

let rejectedBegin = CPRStraightenedSession()
rejectedBegin.replacePackedNodes(packed([(0, 0, 0), (1, 0, 0)]))
let skipped = rejectedBegin.beginGeneration(pixelsWide: 64)
expect(!skipped.accepted && skipped.phase == "rejected",
       "begin on a short curve is a recoverable error")

print("PASS: valid straightened; short/degenerate/loop named; cancel keeps markings")
'''
with tempfile.TemporaryDirectory(prefix='horos-cpr-straightened-') as d:
    p = Path(d)
    (p / 'main.swift').write_text(code)
    subprocess.run([
        'xcrun', 'swiftc',
        str(root / 'Horos/Sources/CPRStraightenedGeneration.swift'),
        str(p / 'main.swift'), '-o', str(p / 'test')
    ], check=True)
    subprocess.run([str(p / 'test')], check=True)
