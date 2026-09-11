#!/usr/bin/env python3
"""Retrieve-and-view state, reload coalescing and selection preservation (#604).

Compiles `Horos/Sources/RetrieveViewing.swift` with a driver: a double-click
begins a pending item once; the viewer opening records the time to first
image; every batch counts a reload; the transfer's end settles the phase from
the peer's counters and the confirmed inventory (complete, unverified,
interrupted, cancelled); the overlay text says which; reloads are coalesced
at half a second and never deferred beyond two; the import nudge fires once
per burst and only while something is live; and the operator's image is found
again by SOP instance and frame after an out-of-order reload.
"""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
source = root / 'Horos/Sources/RetrieveViewing.swift'
failures = []
if 'RetrieveViewing.swift in Sources' not in (root / 'Horos.xcodeproj/project.pbxproj').read_text():
    failures.append('RetrieveViewing.swift is not in the Horos target')

DRIVER = r'''
import Foundation
func expect(_ ok: Bool, _ reason: String) { if !ok { print("FAIL: " + reason); exit(1) } }
let viewing = RetrieveViewing.shared
let study = "1.2.3", series = "1.2.3.4"

// 1. Pending once.
expect(viewing.begin(studyUID: study, seriesUID: series, at: 100), "the first double-click begins the item")
expect(!viewing.begin(studyUID: study, seriesUID: series, at: 101), "a second double-click on a running item is idempotent")
expect(viewing.isPending(studyUID: study, seriesUID: series), "the item is pending before the viewer opens")
expect(viewing.concernsPending(studyUIDs: ["9.9", study]), "a batch carrying the study concerns the pending item")
expect(!viewing.concernsPending(studyUIDs: ["9.9"]), "a batch of other studies does not")
expect(viewing.state(studyUID: study, seriesUID: series)?.phase == .waiting, "waiting before anything landed")
expect(viewing.state(studyUID: study, seriesUID: series)!.overlayText.contains("waiting"), "the waiting overlay says so")

// 2. Viewer opened on partial content: receiving, first-image time recorded.
viewing.viewerOpened(studyUID: study, seriesUID: series, localCount: 2, at: 103.5)
expect(!viewing.isPending(studyUID: study, seriesUID: series), "an opened item is no longer pending")
expect(abs(viewing.secondsToFirstImage(studyUID: study, seriesUID: series) - 3.5) < 1e-9, "time to first image is measured from the double-click")
viewing.expectedCount(studyUID: study, seriesUID: series, expected: 10)
let receiving = viewing.state(studyUID: study, seriesUID: series)!
expect(receiving.phase == .receiving && receiving.isPartial, "receiving while the transfer runs")
expect(receiving.overlayText == "Receiving: 2 of 10 instances available, transfer in progress", "receiving overlay: \(receiving.overlayText)")
viewing.localCountChanged(studyUID: study, seriesUID: series, localCount: 6)
expect(viewing.reloads(studyUID: study, seriesUID: series) == 1, "each applied batch counts one reload")

// 3. Complete: every expected instance imported and the inventory confirmed.
viewing.transferEnded(studyUID: study, seriesUID: series, cancelled: false, received: 10, expected: 10, failed: 0,
                      inventoryConfirmed: true, localCount: 6, at: 110)
expect(viewing.state(studyUID: study, seriesUID: series)?.phase == .interrupted, "ended with 6 of 10 local is interrupted, not complete")
viewing.localCountChanged(studyUID: study, seriesUID: series, localCount: 10)
let complete = viewing.state(studyUID: study, seriesUID: series)!
expect(complete.phase == .complete && !complete.isPartial, "10 of 10 confirmed is complete")
expect(complete.overlayText.isEmpty, "a complete series draws no overlay")
expect(viewing.begin(studyUID: study, seriesUID: series, at: 120), "a finished item can be requested again")

// 4. Unverified: counters agree, no confirmed inventory.
viewing.viewerOpened(studyUID: study, seriesUID: series, localCount: 10, at: 121)
viewing.transferEnded(studyUID: study, seriesUID: series, cancelled: false, received: 10, expected: 10, failed: 0,
                      inventoryConfirmed: false, localCount: 10, at: 125)
let unverified = viewing.state(studyUID: study, seriesUID: series)!
expect(unverified.phase == .unverified, "without a confirmed inventory the end is unverified")
expect(unverified.overlayText.contains("not verified"), "the overlay says completeness is not verified")

// 5. Interrupted by failures, and by cancellation.
let other = "5.6"
expect(viewing.begin(studyUID: other, seriesUID: "", at: 200), "a study-level item")
viewing.viewerOpened(studyUID: other, seriesUID: "5.6.1", localCount: 3, at: 202)
expect(viewing.state(studyUID: other, seriesUID: "5.6.1")?.phase == .receiving, "a study item answers for any of its series")
viewing.transferEnded(studyUID: other, seriesUID: "", cancelled: false, received: 8, expected: 10, failed: 2,
                      inventoryConfirmed: true, localCount: 8, at: 210)
let failed = viewing.state(studyUID: other, seriesUID: "")!
expect(failed.phase == .interrupted && failed.overlayText.contains("2 failed"), "failures interrupt and are named: \(failed.overlayText)")
expect(viewing.begin(studyUID: other, seriesUID: "", at: 220), "restart after an interruption")
viewing.transferEnded(studyUID: other, seriesUID: "", cancelled: true, received: 1, expected: 10, failed: 0,
                      inventoryConfirmed: true, localCount: 1, at: 221)
expect(viewing.state(studyUID: other, seriesUID: "")?.phase == .interrupted, "cancellation is an interruption")
expect(!viewing.isPending(studyUID: other, seriesUID: ""), "a cancelled item is not pending")
viewing.forget(studyUID: other, seriesUID: "")
expect(viewing.state(studyUID: other, seriesUID: "") == nil, "forgetting removes the state")

// 6. Import nudge: once per burst, only while live.
expect(viewing.begin(studyUID: "7.7", seriesUID: "", at: 300), "live item for nudges")
expect(viewing.importNudgeWanted(studyUID: "7.7", at: 300.1), "the first store nudges the importer")
expect(!viewing.importNudgeWanted(studyUID: "7.7", at: 300.3), "a store 200 ms later does not")
expect(viewing.importNudgeWanted(studyUID: "7.7", at: 300.7), "half a second later it does again")
expect(!viewing.importNudgeWanted(studyUID: "8.8", at: 301.5), "a store for a study nobody is viewing does not")
viewing.transferEnded(studyUID: "7.7", seriesUID: "", cancelled: false, received: 1, expected: 1, failed: 0,
                      inventoryConfirmed: true, localCount: 1, at: 302)
expect(!viewing.importNudgeWanted(studyUID: "7.7", at: 303), "after the transfer ended no nudge is wanted")

// 7. Coalescing.
let coalescer = RefreshCoalescer(delay: 0.5, maxDeferral: 2)
expect(coalescer.request(at: 10.0) == 0, "the first request may run immediately")
coalescer.applied(at: 10.0)
let wait = coalescer.request(at: 10.2)
expect(abs(wait - 0.3) < 1e-9, "a request 200 ms after a reload waits the rest of the half second: \(wait)")
expect(coalescer.request(at: 10.4) > 0, "a request inside the window still waits")
expect(coalescer.waitBeforeApplying(at: 10.5) == 0, "at half a second it may run")
coalescer.applied(at: 10.5)
var t = 10.6
var deferred = 0.0
// A steady stream every 100 ms: the reload must happen by two seconds.
while t < 13 { deferred = coalescer.request(at: t); if deferred == 0 { break }; t += 0.1 }
expect(t - 10.5 <= 2.0 + 1e-9, "a steady stream is not deferred past two seconds: ran at +\(t - 10.5)")
expect(coalescer.appliedReloads == 2, "two reloads applied so far")

// 8. Selection preservation after an out-of-order reload.
let sops = ["c", "a", "b", "b"]; let frames: [NSNumber] = [0, 0, 0, 1]
expect(RetrieveViewing.index(ofSOPInstanceUID: "b", frame: 1, inSOPInstanceUIDs: sops, frames: frames, fallback: 0) == 3, "frame 1 of b is found")
expect(RetrieveViewing.index(ofSOPInstanceUID: "b", frame: 7, inSOPInstanceUIDs: sops, frames: frames, fallback: 0) == 2, "a missing frame falls back to the instance")
expect(RetrieveViewing.index(ofSOPInstanceUID: "zz", frame: 0, inSOPInstanceUIDs: sops, frames: frames, fallback: 9) == 3, "an absent instance clamps the fallback")
expect(RetrieveViewing.index(ofSOPInstanceUID: "", frame: 0, inSOPInstanceUIDs: [], frames: [], fallback: 2) == 0, "an empty list yields 0")
print("ok: retrieve-and-view state, coalescing and selection preservation")
'''

if not failures:
    with tempfile.TemporaryDirectory() as tmp:
        driver = Path(tmp) / 'main.swift'
        driver.write_text(DRIVER)
        binary = Path(tmp) / 'driver'
        build = subprocess.run(['xcrun', 'swiftc', str(source), str(driver), '-o', str(binary)], capture_output=True, text=True)
        if build.returncode != 0:
            failures.append('driver did not compile:\n' + build.stderr[-3000:])
        else:
            run = subprocess.run([str(binary)], capture_output=True, text=True)
            if run.returncode != 0:
                failures.append((run.stdout + run.stderr).strip() or 'driver failed without output')
            else:
                print(run.stdout.strip())

if failures:
    for failure in failures:
        print('FAIL:', failure)
    raise SystemExit(1)
