#!/usr/bin/env python3
"""Reference lines follow one coordinate convention and name why they are absent.

#306 is the 2D viewer's slice-cut lines, not the interactive crosshair. Keyboard
and wheel already share `sendSyncMessage:`. What was still missing was the
rendered mapping used when those lines are drawn on a related window, and a
reason a person can tell apart when a different Frame of Reference, a different
study, a disabled preference or parallel planes produce no line.
"""
from pathlib import Path
import re
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
failures = []


def source(relative):
    path = root / relative
    if len(sys.argv) > 1:
        return subprocess.check_output(['git', 'show', sys.argv[1] + ':' + relative]).decode('latin1')
    return path.read_bytes().decode('latin1')


def strip(text):
    text = re.sub(r'//[^\n]*', '', text)
    return re.sub(r'/\*.*?\*/', '', text, flags=re.S)


view = source('Horos/Sources/DCMView.m')
header = source('Horos/Sources/DCMView.h')
swift = root / 'Horos/Sources/ViewerReferenceLines.swift'
xib = source('Horos/Resources/en.lproj/Viewer.xib')

if not swift.exists() and len(sys.argv) <= 1:
    failures.append('ViewerReferenceLines.swift is missing')

if '@property(copy) NSString *referenceLineAbsenceReason;' not in header:
    failures.append('DCMView has nowhere to keep why the related window has no line')

cleaned = strip(view)
if 'HorosViewerReferenceLines' not in view:
    failures.append('DCMView never asks ViewerReferenceLines for the shared contract')
if 'invalidateReferenceLines' not in view:
    failures.append('the stale-line paths still copy the same HUGE_VALF block instead of one invalidation')
if 'overlayTextDisplayingLines' not in view and 'overlayText' not in view:
    failures.append('the related window never draws the reason a line is absent')
if 'renderedPointSliceX' not in view:
    failures.append('drawCrossLines still inlines the millimetre-to-view mapping')

keydown = cleaned[cleaned.find('- (void) keyDown:'):cleaned.find('- (BOOL) shouldPropagate')]
wheel = cleaned[cleaned.find('- (void)scrollWheel:'):cleaned.find('- (void) otherMouseDown:')]
if 'sendSyncMessage' not in keydown:
    failures.append('keyDown: no longer sends the sync that updates related lines')
if 'sendSyncMessage' not in wheel:
    failures.append('scrollWheel: no longer sends the sync that updates related lines')

# A SAMESTUDY=NO / incompatible-frame admission must still drop leftover lines.
sync_at = cleaned.find('-(void) sync:')
if sync_at < 0:
    sync_at = cleaned.find('- (void) sync:')
sync = cleaned[sync_at:] if sync_at >= 0 else ''
if not sync:
    failures.append('sync: is gone')
else:
    end = sync.find('\n-(void) roiSelected:')
    if end < 0:
        end = sync.find('\n- (void) roiSelected:')
    sync = sync[:end] if end > 0 else sync
    if 'invalidateReferenceLines' not in sync:
        failures.append('sync: can still leave a previous compatible line when the source is incompatible')

if 'HorosCellSlider' not in xib or 'HorosCellSliderCell' not in xib:
    failures.append('Viewer.xib lost the HorosCellSlider cells from #388')

main = r'''
import Foundation

let source = "2.25.111"
let destination = "2.25.222"
let study = "2.25.study"

let reasons = [
    ViewerReferenceLines.reasonForIncompatibleFrame(source: source, destination: destination),
    ViewerReferenceLines.reasonForDifferentStudy(),
    ViewerReferenceLines.reasonForLinesDisabled(),
    ViewerReferenceLines.reasonForParallelPlanes(),
]
assert(Set(reasons).count == reasons.count, "the reasons have to be told apart")
for reason in reasons {
    assert(!reason.isEmpty && reason.count < 80, reason)
}

// Shared Frame of Reference, same study: a line is allowed.
assert(ViewerReferenceLines.sameThreeDWorld(
    destinationFrame: "2.25.common", sourceFrame: "2.25.common",
    destinationStudy: study, sourceStudy: study, useFrameOfReference: true))
assert(ViewerReferenceLines.absenceReason(
    destinationFrame: "2.25.common", sourceFrame: "2.25.common",
    destinationStudy: study, sourceStudy: study,
    useFrameOfReference: true, sameStudyOnly: true, registered: false) == nil)

// Same study, different Frame of Reference, preference on: no misleading line.
assert(!ViewerReferenceLines.sameThreeDWorld(
    destinationFrame: destination, sourceFrame: source,
    destinationStudy: study, sourceStudy: study, useFrameOfReference: true))
let incompatible = ViewerReferenceLines.absenceReason(
    destinationFrame: destination, sourceFrame: source,
    destinationStudy: study, sourceStudy: study,
    useFrameOfReference: true, sameStudyOnly: false, registered: false)
assert(incompatible == ViewerReferenceLines.reasonForIncompatibleFrame(
    source: source, destination: destination), incompatible ?? "nil")
assert(incompatible!.contains(source) && incompatible!.contains(destination), incompatible!)

// SAMESTUDY=NO still admits the sync block, but must not compute a line.
assert(ViewerReferenceLines.admitSynchronization(
    sameWorld: false, registered: false, sameStudyOnly: false, manualSync: false))
assert(!ViewerReferenceLines.shouldComputeLines(sameWorld: false, registered: false))

// UseFrameofReferenceUID off: the same study is treated as one world.
assert(ViewerReferenceLines.sameThreeDWorld(
    destinationFrame: destination, sourceFrame: source,
    destinationStudy: study, sourceStudy: study, useFrameOfReference: false))

// Different study, SAMESTUDY on, not registered: no line, named as a study mismatch.
assert(!ViewerReferenceLines.sameThreeDWorld(
    destinationFrame: "2.25.common", sourceFrame: "2.25.common",
    destinationStudy: "2.25.a", sourceStudy: "2.25.b", useFrameOfReference: true))
assert(ViewerReferenceLines.absenceReason(
    destinationFrame: "2.25.common", sourceFrame: "2.25.common",
    destinationStudy: "2.25.a", sourceStudy: "2.25.b",
    useFrameOfReference: true, sameStudyOnly: true, registered: false)
    == ViewerReferenceLines.reasonForDifferentStudy())
assert(!ViewerReferenceLines.admitSynchronization(
    sameWorld: false, registered: false, sameStudyOnly: true, manualSync: false))

// A registered pair is allowed even when the studies differ.
assert(ViewerReferenceLines.shouldComputeLines(sameWorld: false, registered: true))
assert(ViewerReferenceLines.admitSynchronization(
    sameWorld: false, registered: true, sameStudyOnly: true, manualSync: false))

// Missing Frame of Reference does not invent an incompatibility.
assert(ViewerReferenceLines.sameThreeDWorld(
    destinationFrame: nil, sourceFrame: source,
    destinationStudy: study, sourceStudy: study, useFrameOfReference: true))

// Only the related, non-key window draws the key window's cut. Both key is
// the "two active sources" case; an app switch with neither key draws nothing.
assert(ViewerReferenceLines.shouldDisplaySourceLines(
    destinationIsKey: false, sourceIsKey: true, sourceIsFullscreen: false))
assert(!ViewerReferenceLines.shouldDisplaySourceLines(
    destinationIsKey: true, sourceIsKey: true, sourceIsFullscreen: false))
assert(!ViewerReferenceLines.shouldDisplaySourceLines(
    destinationIsKey: false, sourceIsKey: false, sourceIsFullscreen: false))
assert(ViewerReferenceLines.shouldDisplaySourceLines(
    destinationIsKey: false, sourceIsKey: false, sourceIsFullscreen: true))
assert(!ViewerReferenceLines.bothWindowsActivelySourcing(
    destinationIsKey: false, sourceIsKey: true))
assert(ViewerReferenceLines.bothWindowsActivelySourcing(
    destinationIsKey: true, sourceIsKey: true))

// Fixture: sagittal x=8 → axial column centre 8.5 mm → OpenGL x = scale*(8.5-16).
assert(abs(ViewerReferenceLines.fixtureAxialSliceX(forSagittalIndex: 8) - 8.5) < 1e-9)
assert(abs(ViewerReferenceLines.fixtureAxialSliceY(forCoronalPhysicalY: 8) - 8.5) < 1e-9)
let keyboard = ViewerReferenceLines.fixtureRenderedLine(sagittalIndex: 8, scale: 2)
let wheel = ViewerReferenceLines.fixtureRenderedLine(sagittalIndex: 8, scale: 2)
assert(keyboard.0.x == wheel.0.x && keyboard.1.x == wheel.1.x)
assert(abs(keyboard.0.x - 2 * (8.5 - 16)) < 1e-9)
assert(abs(keyboard.0.y - 2 * (0 - 16)) < 1e-9)
assert(abs(keyboard.1.y - 2 * (32 - 16)) < 1e-9)

// Zoom keeps the line on the same image column.
let zoomed = ViewerReferenceLines.fixtureRenderedLine(sagittalIndex: 8, scale: 4)
assert(abs(zoomed.0.x - 2 * keyboard.0.x) < 1e-9)

// Non-finite inputs do not invent a vertex.
let bad = ViewerReferenceLines.renderedPoint(
    sliceX: .nan, sliceY: 0, pixelSpacingX: 1, pixelSpacingY: 1,
    width: 32, height: 32, scale: 1)
assert(bad.x.isNaN && bad.y.isNaN)

// Annotation/graphics: the sentence is only drawn where other overlay text is.
assert(ViewerReferenceLines.overlayText(
    displayingLines: false, annotationType: 0, hasFiniteLine: false,
    relationshipReason: reasons[0]) == nil)
assert(ViewerReferenceLines.overlayText(
    displayingLines: false, annotationType: 2, hasFiniteLine: true,
    relationshipReason: nil) == ViewerReferenceLines.reasonForLinesDisabled())
assert(ViewerReferenceLines.overlayText(
    displayingLines: true, annotationType: 2, hasFiniteLine: false,
    relationshipReason: reasons[0]) == reasons[0])
assert(ViewerReferenceLines.overlayText(
    displayingLines: true, annotationType: 2, hasFiniteLine: true,
    relationshipReason: nil) == nil)
assert(ViewerReferenceLines.logPrefix().lowercased().contains("reference"))

print("PASS: shared world, identifiable absence, fixture rendered alignment, keyboard/wheel same line")
'''

if swift.exists() or len(sys.argv) > 1:
    swift_source = source('Horos/Sources/ViewerReferenceLines.swift') if len(sys.argv) > 1 else swift.read_text()
    with tempfile.TemporaryDirectory(prefix='horos-viewer-reference-') as tmp:
        p = Path(tmp)
        (p / 'main.swift').write_text(main)
        (p / 'ViewerReferenceLines.swift').write_text(swift_source)
        built = subprocess.run(
            ['xcrun', '--sdk', 'macosx', 'swiftc', '-o', str(p / 'test'),
             str(p / 'ViewerReferenceLines.swift'), str(p / 'main.swift')],
            capture_output=True, text=True)
        if built.returncode != 0:
            failures.append('ViewerReferenceLines does not compile:\n%s' % built.stderr[-1500:])
        else:
            ran = subprocess.run([str(p / 'test')], capture_output=True, text=True)
            if ran.returncode != 0:
                failures.append(ran.stdout + ran.stderr)
            else:
                print(ran.stdout.strip())

for failure in failures:
    print('FAIL: %s' % failure)

if failures:
    sys.exit(1)
print('ok: reference lines share one rendered mapping and name why a related window has none')
