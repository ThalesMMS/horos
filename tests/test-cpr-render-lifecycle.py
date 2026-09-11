#!/usr/bin/env python3
"""CPR render reentrancy, NaNs and open/close lifecycle (#204).

horosproject/horos#531 hangs on Xcode 10/11 SDKs from DrawRect recursion in the
CPR views. #470 hangs with and without a resample prompt. Shared volume
fixtures with #31/#221 name geometry; they are not this hang.
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

CPRRenderLifecycle.reset()
expect(CPRRenderLifecycle.phase == "idle", "a new session starts idle")

// Open without resample (isotropic fixture) and with resample (user accepted).
let native = CPRRenderLifecycle.beginOpening(resampled: false)
expect(native.accepted && native.phase == "opening-native",
       "native open is a distinct lifecycle: \(native.phase) \(native.diagnosis)")
expect(CPRRenderLifecycle.markOpen().phase == "open", "native open reaches open")

CPRRenderLifecycle.reset()
let resampled = CPRRenderLifecycle.beginOpening(resampled: true)
expect(resampled.accepted && resampled.phase == "opening-resampled",
       "resampled open is a distinct lifecycle: \(resampled.phase)")
expect(CPRRenderLifecycle.markOpen().phase == "open",
       "resampled open also reaches open: the hang is not the prompt")

let curve = CPRRenderLifecycle.markCurveReady()
expect(curve.accepted && curve.phase == "curve-ready",
       "a finished curve is still in a live window: \(curve.phase)")

// Nested drawRect of the same view is the #531 hang. Skip it; do not recurse.
let first = CPRRenderLifecycle.beginDraw(named: "mpr")
expect(first.accepted && first.phase == "drawing",
       "first draw is accepted: \(first.diagnosis)")
let nested = CPRRenderLifecycle.beginDraw(named: "mpr")
expect(!nested.accepted && nested.phase == "reentrant",
       "nested drawRect is named, not an infinite loop: \(nested.phase) \(nested.diagnosis)")
expect(nested.diagnosis.lowercased().contains("drawrect"),
       "reentrant diagnosis must name drawRect: \(nested.diagnosis)")
CPRRenderLifecycle.endDraw(named: "mpr")
let after = CPRRenderLifecycle.beginDraw(named: "mpr")
expect(after.accepted, "after endDraw the same view may draw again")
CPRRenderLifecycle.endDraw(named: "mpr")

// Sibling CPR views may draw together; that is not recursion of one view.
expect(CPRRenderLifecycle.beginDraw(named: "straightened").accepted,
       "straightened may draw while mpr is idle")
expect(CPRRenderLifecycle.beginDraw(named: "stretched").accepted,
       "stretched is a sibling, not a nested mpr draw")
CPRRenderLifecycle.endDraw(named: "straightened")
CPRRenderLifecycle.endDraw(named: "stretched")

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
let closing = CPRRenderLifecycle.beginClosing()
expect(closing.accepted && closing.phase == "closing", "close starts a named phase")
let duringClose = CPRRenderLifecycle.beginDraw(named: "mpr")
expect(!duringClose.accepted && duringClose.phase == "closing",
       "draw during close is skipped: \(duringClose.phase) \(duringClose.diagnosis)")
expect(CPRRenderLifecycle.markClosed().phase == "closed", "window reached closed")
expect(!CPRRenderLifecycle.beginDraw(named: "mpr").accepted,
       "a closed window does not re-enter drawRect")

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

print("PASS: resampled and native open; nested drawRect is named; NaN spacing is invalid; close skips draw")
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
