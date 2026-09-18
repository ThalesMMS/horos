#!/usr/bin/env python3
"""CPR render reentrancy, NaNs and open/close lifecycle (#204).

horosproject/horos#531 hangs on Xcode 10/11 SDKs from DrawRect recursion in the
CPR views. #470 hangs with and without a resample prompt. Shared volume
fixtures with #31/#221 name geometry; they are not this hang.

The phase and the draw depth are per window. They were static once, and two
Curved MPR windows then shared them: closing either left "closed" behind and
every view of the window still on screen had its draw refused, so its panels
went blank. That case is the last one below.
"""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
code = r'''
import Foundation

func expect(_ ok: Bool, _ message: String) {
    precondition(ok, message)
}

let lifecycle = CPRRenderLifecycle()
lifecycle.reset()
expect(lifecycle.phase == "idle", "a new session starts idle")

// Open without resample (isotropic fixture) and with resample (user accepted).
let native = lifecycle.beginOpening(resampled: false)
expect(native.accepted && native.phase == "opening-native",
       "native open is a distinct lifecycle: \(native.phase) \(native.diagnosis)")
expect(lifecycle.markOpen().phase == "open", "native open reaches open")

lifecycle.reset()
let resampled = lifecycle.beginOpening(resampled: true)
expect(resampled.accepted && resampled.phase == "opening-resampled",
       "resampled open is a distinct lifecycle: \(resampled.phase)")
expect(lifecycle.markOpen().phase == "open",
       "resampled open also reaches open: the hang is not the prompt")

let curve = lifecycle.markCurveReady()
expect(curve.accepted && curve.phase == "curve-ready",
       "a finished curve is still in a live window: \(curve.phase)")

// Nested drawRect of the same view is the #531 hang. Skip it; do not recurse.
let first = lifecycle.beginDraw(named: "mpr")
expect(first.accepted && first.phase == "drawing",
       "first draw is accepted: \(first.diagnosis)")
let nested = lifecycle.beginDraw(named: "mpr")
expect(!nested.accepted && nested.phase == "reentrant",
       "nested drawRect is named, not an infinite loop: \(nested.phase) \(nested.diagnosis)")
expect(nested.diagnosis.lowercased().contains("drawrect"),
       "reentrant diagnosis must name drawRect: \(nested.diagnosis)")
lifecycle.endDraw(named: "mpr")
let after = lifecycle.beginDraw(named: "mpr")
expect(after.accepted, "after endDraw the same view may draw again")
lifecycle.endDraw(named: "mpr")

// Sibling CPR views may draw together; that is not recursion of one view.
expect(lifecycle.beginDraw(named: "straightened").accepted,
       "straightened may draw while mpr is idle")
expect(lifecycle.beginDraw(named: "stretched").accepted,
       "stretched is a sibling, not a nested mpr draw")
lifecycle.endDraw(named: "straightened")
lifecycle.endDraw(named: "stretched")

// Synchronous [view display] during drawRect is the hang on newer AppKit.
expect(!CPRRenderLifecycle.shouldDisplaySynchronously(whileDrawing: true),
       "do not call display from inside drawRect")
expect(CPRRenderLifecycle.shouldDisplaySynchronously(whileDrawing: false),
       "outside drawRect, a deferred setNeedsDisplay is enough")

// Shared fixture spacing: 1 mm isotropic is drawable; NaN/zero are named.
expect(CPRRenderLifecycle.diagnoseSpacingX(1, spacingY: 1) == "ready",
       "isotropic 1 mm from the shared fixture is drawable")
expect(CPRRenderLifecycle.diagnoseSpacingX(0.5, spacingY: 2) == "ready",
       "anisotropic regular fixture is still drawable geometry")
let nan = CPRRenderLifecycle.diagnoseSpacingX(.nan, spacingY: 1)
expect(nan == "not a number", "NaN spacing is named, got \(nan)")
let zero = CPRRenderLifecycle.diagnoseSpacingX(0, spacingY: 1)
expect(zero == "invalid spacing", "zero spacing is named: \(zero)")
let huge = CPRRenderLifecycle.diagnoseSpacingX(1500, spacingY: 1)
expect(huge == "out of range", "out-of-range spacing is named: \(huge)")
expect(CPRRenderLifecycle.diagnoseSpacingX(.infinity, spacingY: 1) == "not a number",
       "non-finite spacing is not rewritten")

// Close must refuse further drawing so teardown cannot re-enter drawRect.
let closing = lifecycle.beginClosing()
expect(closing.accepted && closing.phase == "closing", "close starts a named phase")
let duringClose = lifecycle.beginDraw(named: "mpr")
expect(!duringClose.accepted && duringClose.phase == "closing",
       "draw during close is skipped: \(duringClose.phase) \(duringClose.diagnosis)")
expect(lifecycle.markClosed().phase == "closed", "window reached closed")
expect(!lifecycle.beginDraw(named: "mpr").accepted,
       "a closed window does not re-enter drawRect")

// Two Curved MPR windows. Closing one must not blank the other: the phase and
// the draw depth belong to the window, not to the process.
let windowA = CPRRenderLifecycle()
let windowB = CPRRenderLifecycle()
for window in [windowA, windowB] {
    window.reset()
    _ = window.beginOpening(resampled: false)
    _ = window.markOpen()
}
_ = windowB.beginClosing()
_ = windowB.markClosed()
expect(windowB.phase == "closed", "the window that closed is closed")
expect(windowA.phase == "open", "the window still on screen stays open: \(windowA.phase)")
for name in ["mpr-1", "straightened", "transverse-0"] {
    let draw = windowA.beginDraw(named: name)
    expect(draw.accepted,
           "\(name) of the open window still paints after the other closed: \(draw.diagnosis)")
    windowA.endDraw(named: name)
}

// A draw in flight in one window is not recursion in the other.
expect(windowA.beginDraw(named: "straightened").accepted, "window A draws")
let windowC = CPRRenderLifecycle()
_ = windowC.markOpen()
expect(windowC.beginDraw(named: "straightened").accepted,
       "the same view name in another window is not a nested draw")
windowC.endDraw(named: "straightened")
windowA.endDraw(named: "straightened")

// Hang stack: nested -[CPRMPRDCMView drawRect:] is drawrect-recursion, not VTK.
let stack = """
Thread 0:: Dispatch queue: com.apple.main-thread
0   Horos   -[CPRMPRDCMView drawRect:]
1   Horos   -[DCMView drawRect:]
2   AppKit  -[NSView displayIfNeeded]
3   Horos   -[CPRMPRDCMView setNeedsDisplay:]
4   Horos   -[CPRMPRDCMView drawRect:]
5   Horos   -[CPRController showWindow:]
"""
expect(CPRRenderLifecycle.classifyHangStack(stack) == "drawrect-recursion",
       "nested drawRect is the hang, got \(CPRRenderLifecycle.classifyHangStack(stack))")
expect(CPRRenderLifecycle.classifyHangStack("vtkFixedPointRayCastImage::GetZBufferValue") == "unclassified",
       "Z-buffer is #213, not this hang")

print("PASS: resampled and native open; nested drawRect is named; NaN spacing is invalid; close skips draw in its own window only")
'''
with tempfile.TemporaryDirectory(prefix='horos-cpr-render-lifecycle-') as d:
    p = Path(d)
    (p / 'main.swift').write_text(code)
    subprocess.run([
        'xcrun', 'swiftc',
        str(root / 'Horos/Sources/CPRRenderLifecycle.swift'),
        str(p / 'main.swift'), '-o', str(p / 'test')
    ], check=True)
    subprocess.run([str(p / 'test')], check=True)
