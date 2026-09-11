#!/usr/bin/env python3
"""The preview knows which window it is showing and why (#608).

Compiles `Horos/Sources/PreviewWindowing.swift` against a driver that builds
phantom frames whose expected window this file computes independently, in
Python, before the comparison — CT with and without a stored window, MR over a
dominant zero background, NM and PT counts, a colour frame, an invalid stored
window, a frame of extreme outliers and one too small to guess from.

It then walks the state machine the browser uses: a manual adjustment survives
scrolling inside a series and a second publication of the same frame, and is
dropped by a new Series Instance UID or by the same file at a new revision
(#603). A width of zero is a request for automatic selection, never an image
one unit wide, and a colour frame never receives a scalar window.
"""
from pathlib import Path
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
source = root / 'Horos/Sources/PreviewWindowing.swift'
project = (root / 'Horos.xcodeproj/project.pbxproj').read_text()
failures = []
if project.count('PreviewWindowing.swift in Sources') < 1:
    failures.append('PreviewWindowing.swift is not in the Horos target')

# ---------------------------------------------------------------- expectations
# An independent restatement of what the acceptance asks for, used to compute
# the expected window of every phantom before the Swift code is run.

SAMPLE_BUDGET = 5000
MINIMUM_SAMPLES = 32


def tolerance(value):
    return max(abs(value) * 0.00001, 0.0001)


def background_of(corners):
    best, best_count = None, 1
    for candidate in corners:
        limit = tolerance(candidate)
        count = sum(1 for value in corners if abs(value - candidate) <= limit)
        if count > best_count:
            best, best_count = candidate, count
    return best


def expected_window(values, width, height, modality):
    """Sampled, background-rejecting automatic window; None when unusable."""
    count = width * height
    corners = [values[i] for i in (0, width - 1, (height - 1) * width, count - 1)]
    background = background_of(corners)
    step = max(1, count // SAMPLE_BUDGET)
    kept = []
    for index in range(0, count, step):
        value = values[index]
        if background is not None and abs(value - background) <= tolerance(background):
            continue
        if modality == 'MR' and abs(value) <= 1.2e-7:
            continue
        kept.append(value)
    if len(kept) < MINIMUM_SAMPLES:
        return None
    kept.sort()
    low_p, high_p = (0.01, 0.99) if modality in ('US', 'XA', 'RF') else (0.005, 0.995)

    def index_for(p):
        if len(kept) <= 1:
            return 0
        # round-half-away-from-zero, as Float.rounded() does
        raw = (len(kept) - 1) * p
        return min(max(int(raw + 0.5), 0), len(kept) - 1)

    low_index, high_index = index_for(low_p), max(index_for(high_p), index_for(low_p))
    low, high = kept[low_index], kept[high_index]
    if modality in ('PT', 'NM') and low >= 0:
        low = 0.0
    window = max(high - low, 1.0)
    return (low + window / 2.0, window)


# ------------------------------------------------------------------- phantoms
# Each phantom is described once, here and in the Swift driver, by the same
# recipe. 100x50 is 5000 samples, so no stride is involved and the numbers are
# exact; the striding phantom is separate and deliberately larger.

def ct_air_background():
    """4000 pixels of air at -1000 HU, then the values 0..999 exactly once."""
    values = [-1000.0] * 5000
    for i in range(1000):
        values[4000 + i] = float(i)
    return values


def mr_zero_background():
    """A zero background the corners do not agree on, plus a tissue band."""
    values = [0.0] * 5000
    for corner, value in zip((0, 99, 4900, 4999), (1.0, 2.0, 3.0, 4.0)):
        values[corner] = value
    for i in range(1000):
        values[3000 + i] = 100.0 + i
    return values


def pt_counts():
    """Counts over an empty background: the low end belongs at zero."""
    values = [0.0] * 5000
    for i in range(2000):
        values[2500 + i] = 3.0 + i * 0.01
    return values


def outliers():
    """A tissue band with four pixels far outside it, under the 0.5% clip."""
    values = [-1000.0] * 5000
    for i in range(1000):
        values[2000 + i] = 20.0 + i * 0.1
    for i in range(4):
        values[1000 + i] = 30000.0
    return values


def striding():
    """40000 pixels: eight times the sample budget, so the stride is 8."""
    values = [-1000.0] * 40000
    for i in range(8000):
        values[32000 + i] = float(i % 1000)
    return values


phantoms = {
    'ct': (ct_air_background(), 100, 50, 'CT'),
    'mr': (mr_zero_background(), 100, 50, 'MR'),
    'pt': (pt_counts(), 100, 50, 'PT'),
    'outliers': (outliers(), 100, 50, 'CT'),
    'striding': (striding(), 200, 200, 'CT'),
}
expected = {name: expected_window(*args) for name, args in phantoms.items()}
for name, window in expected.items():
    if window is None:
        failures.append('phantom %s produced no expected window; the test is wrong' % name)

# The tolerance is fixed before the comparison: these are exactly representable
# small integers and tenths, so a single-precision round trip is the only error.
TOLERANCE = 0.01

DRIVER = r'''
import Foundation

func expect(_ ok: Bool, _ reason: String) { if !ok { print("FAIL: " + reason); exit(1) } }
func close(_ a: Float, _ b: Double, _ tolerance: Double, _ what: String) {
    expect(abs(Double(a) - b) <= tolerance, "\(what): got \(a), expected \(b) +/- \(tolerance)")
}

// ---- the phantoms, built by the same recipe the test states in Python ------
func ctAirBackground() -> [Float] {
    var values = [Float](repeating: -1000, count: 5000)
    for i in 0..<1000 { values[4000 + i] = Float(i) }
    return values
}
func mrZeroBackground() -> [Float] {
    var values = [Float](repeating: 0, count: 5000)
    for (corner, value) in zip([0, 99, 4900, 4999], [Float(1), 2, 3, 4]) { values[corner] = value }
    for i in 0..<1000 { values[3000 + i] = 100 + Float(i) }
    return values
}
func ptCounts() -> [Float] {
    var values = [Float](repeating: 0, count: 5000)
    for i in 0..<2000 { values[2500 + i] = 3 + Float(i) * 0.01 }
    return values
}
func outlierFrame() -> [Float] {
    var values = [Float](repeating: -1000, count: 5000)
    for i in 0..<1000 { values[2000 + i] = 20 + Float(i) * 0.1 }
    for i in 0..<4 { values[1000 + i] = 30000 }
    return values
}
func stridingFrame() -> [Float] {
    var values = [Float](repeating: -1000, count: 40000)
    for i in 0..<8000 { values[32000 + i] = Float(i % 1000) }
    return values
}

func window(_ values: [Float], _ width: Int, _ height: Int, _ modality: String) -> PreviewWindow? {
    values.withUnsafeBufferPointer {
        PreviewAutomaticWindow.window(values: $0.baseAddress, width: width, height: height, modality: modality)
    }
}

// 1. Every phantom lands on the window this test computed for it beforehand.
__EXPECTATIONS__

// 2. The extremes do not set the width: eight pixels at 30000 are clipped away.
let outlierWindow = window(outlierFrame(), 100, 50, "CT")!
expect(outlierWindow.width < 200, "4 outliers at 30000 widened the window to \(outlierWindow.width)")
expect(outlierWindow.level > 20 && outlierWindow.level < 130, "the level left the tissue band: \(outlierWindow.level)")
expect(outlierWindow.source == .automatic, "a computed window says so")

// 3. The dominant background is excluded rather than allowed to set the low end.
let ctWindow = window(ctAirBackground(), 100, 50, "CT")!
expect(ctWindow.level - ctWindow.width / 2 > -100, "air at -1000 was not rejected: low end \(ctWindow.level - ctWindow.width / 2)")

// 4. MR rejects zeros even when the corners disagree about the background.
let mrWindow = window(mrZeroBackground(), 100, 50, "MR")!
expect(mrWindow.level - mrWindow.width / 2 > 0, "MR kept the zero background: \(mrWindow.level - mrWindow.width / 2)")
expect(window(mrZeroBackground(), 100, 50, "CT")!.level < mrWindow.level,
       "the zero rejection is specific to MR")

// 5. Counts start at zero: PT and NM keep their low end.
let ptWindow = window(ptCounts(), 100, 50, "PT")!
close(ptWindow.level - ptWindow.width / 2, 0, 0.001, "the PT low end is zero")
let nmValues = ptCounts()
let nmWindow = window(nmValues, 100, 50, "NM")!
close(nmWindow.level - nmWindow.width / 2, 0, 0.001, "the NM low end is zero")

// 6. Too few usable samples is an honest nil, not a guess.
var tiny = [Float](repeating: -1000, count: 32)
for i in 0..<8 { tiny[8 + i] = Float(i) }
expect(window(tiny, 8, 4, "CT") == nil, "a frame with 8 usable samples produced a window anyway")
expect(PreviewAutomaticWindow.window(values: nil, width: 100, height: 50, modality: "CT") == nil, "a null buffer produced a window")
expect(window([Float](repeating: 3, count: 100), 0, 0, "CT") == nil, "a frame with no size produced a window")

// 7. A frame that is all one value has no window to compute.
expect(window([Float](repeating: 7, count: 5000), 100, 50, "CT") == nil, "a uniform frame produced a window")

// 8. Reading the frame does not write to it: the measured pixels are untouched.
var quantitative = ptCounts()
let before = quantitative
_ = window(quantitative, 100, 50, "PT")
expect(quantitative == before, "computing the automatic window changed the pixels")

// ---- the ladder -----------------------------------------------------------
let dicom = PreviewWindow(level: 40, width: 400, source: .dicom)
let automatic = PreviewWindow(level: 500, width: 900, source: .automatic)
let stored = PreviewWindow(level: 0, width: 4096, source: .storedRange)

// 9. A modality that is not MR keeps a valid stored window.
expect(PreviewWindowPolicy.defaultWindow(modality: "CT", dicom: dicom, automatic: automatic,
                                         frameRange: nil, storedRange: stored, isColor: false) == dicom,
       "CT did not keep its DICOM window")
// 10. MR prefers the computed one, as the origin does.
expect(PreviewWindowPolicy.defaultWindow(modality: "mr", dicom: dicom, automatic: automatic,
                                         frameRange: nil, storedRange: stored, isColor: false) == automatic,
       "MR did not take the computed window")
// 11. MR with nothing to compute from still keeps a valid DICOM window.
expect(PreviewWindowPolicy.defaultWindow(modality: "MR", dicom: dicom, automatic: nil,
                                         frameRange: nil, storedRange: stored, isColor: false) == dicom,
       "MR with no samples lost its DICOM window")
// 12. An invalid stored window is skipped, in every shape it arrives in.
for invalid in [PreviewWindow(level: 40, width: 0, source: .dicom),
                PreviewWindow(level: 40, width: -350, source: .dicom),
                PreviewWindow(level: .nan, width: 400, source: .dicom),
                PreviewWindow(level: 40, width: .infinity, source: .dicom)] {
    expect(invalid.isValid == false, "\(invalid) was accepted as a window")
    expect(PreviewWindowPolicy.defaultWindow(modality: "CT", dicom: invalid, automatic: automatic,
                                             frameRange: nil, storedRange: stored, isColor: false) == automatic,
           "an invalid DICOM window was used instead of the computed one")
}
// 12b. With nothing to sample, the frame's own range comes before the stored
//      bit range: a uniform frame shown at full 16-bit scale is flat grey.
let frameRange = PreviewWindow(level: 11, width: 20, source: .frameRange)
expect(PreviewWindowPolicy.defaultWindow(modality: "CT", dicom: nil, automatic: nil,
                                         frameRange: frameRange, storedRange: stored, isColor: false) == frameRange,
       "the frame's own range was skipped for the stored bit range")
expect(PreviewWindowPolicy.defaultWindow(modality: "MR", dicom: dicom, automatic: nil,
                                         frameRange: frameRange, storedRange: stored, isColor: false) == dicom,
       "MR with a valid DICOM window took the frame range instead")
expect(PreviewWindowPolicy.defaultWindow(modality: "CT", dicom: nil, automatic: automatic,
                                         frameRange: frameRange, storedRange: stored, isColor: false) == automatic,
       "the frame range beat the computed window")
expect(PreviewWindowPolicy.defaultWindow(modality: "US", dicom: nil, automatic: nil,
                                         frameRange: frameRange, storedRange: stored, isColor: true).source == .color,
       "a colour frame took the frame range")

// 13. The stored range is the last resort, and there is always an answer.
expect(PreviewWindowPolicy.defaultWindow(modality: "CT", dicom: nil, automatic: nil,
                                         frameRange: nil, storedRange: stored, isColor: false) == stored,
       "the stored range is not the last resort")
expect(PreviewWindowPolicy.defaultWindow(modality: "CT", dicom: nil, automatic: nil,
                                         frameRange: nil, storedRange: nil, isColor: false).isValid,
       "a frame with no window at all got an invalid one")
// 14. A colour frame is never given a scalar window.
let colour = PreviewWindowPolicy.defaultWindow(modality: "US", dicom: dicom, automatic: automatic,
                                               frameRange: nil, storedRange: stored, isColor: true)
expect(colour.source == .color, "a colour frame was given a \(colour.source.name) window")
close(colour.width, 255, 0.001, "a colour frame keeps its full presentation range")
// 15. Sampling is skipped when the ladder can never reach it.
expect(PreviewWindowPolicy.needsAutomaticWindow(modality: "CT", dicom: dicom, isColor: false) == false,
       "CT with a valid window still sampled the pixels")
expect(PreviewWindowPolicy.needsAutomaticWindow(modality: "MR", dicom: dicom, isColor: false),
       "MR did not sample the pixels")
expect(PreviewWindowPolicy.needsAutomaticWindow(modality: "CT", dicom: nil, isColor: false),
       "CT without a window did not sample the pixels")
expect(PreviewWindowPolicy.needsAutomaticWindow(modality: "US", dicom: nil, isColor: true) == false,
       "a colour frame sampled the pixels")

// ---- the state machine ----------------------------------------------------
let policy = PreviewWindowPolicy()
// 16. The first frame of a selection computes its defaults.
expect(policy.beginFrame(seriesKey: "1.2.3", path: "/a/1.dcm", revisionKey: "r1"),
       "the first frame did not ask for defaults")
_ = policy.window(modality: "CT", dicom: dicom, automatic: automatic, frameRange: nil, storedRange: stored, isColor: false)
// 17. A person adjusts the window.
expect(policy.recordRequested(level: 300, width: 1500), "a valid adjustment was refused")
expect(policy.manualWindow?.width == 1500, "the adjustment was not recorded")
// 17b. A redraw re-asserting the window already on screen is not an adjustment.
let reassert = PreviewWindowPolicy()
_ = reassert.beginFrame(seriesKey: "1.2.3", path: "/a/1.dcm", revisionKey: "r1")
let settledWindow = reassert.window(modality: "CT", dicom: dicom, automatic: automatic,
                                    frameRange: nil, storedRange: stored, isColor: false)
expect(reassert.recordRequested(level: settledWindow.level, width: settledWindow.width) == false,
       "re-asserting the window on screen was recorded as a manual adjustment")
expect(reassert.manualWindow == nil, "a redraw left a manual window behind")
expect(reassert.appliedWindow?.source == .dicom, "a redraw changed the source of the window")

// 18. Scrolling to the next file of the same series keeps it.
expect(policy.beginFrame(seriesKey: "1.2.3", path: "/a/2.dcm", revisionKey: "r2") == false,
       "scrolling inside a series asked for new defaults")
expect(policy.window(modality: "CT", dicom: dicom, automatic: automatic,
                     frameRange: nil, storedRange: stored, isColor: false).width == 1500,
       "the adjustment did not survive a scroll")
// 19. The same frame published a second time keeps it too.
expect(policy.beginFrame(seriesKey: "1.2.3", path: "/a/2.dcm", revisionKey: "r2") == false,
       "a second publication of the same frame reset the window")
expect(policy.manualWindow?.width == 1500, "a late publication erased the adjustment")
// 20. The same file at a new revision does not.
expect(policy.beginFrame(seriesKey: "1.2.3", path: "/a/2.dcm", revisionKey: "r3"),
       "the same path at a new revision kept the old defaults")
expect(policy.manualWindow == nil, "a new revision kept the manual window")
// 20b. A file replaced while the rest of the series was scrolled through is
//      still noticed when the scroll comes back to it.
let round = PreviewWindowPolicy()
_ = round.beginFrame(seriesKey: "5.5.5", path: "/s/1.dcm", revisionKey: "a1")
_ = round.window(modality: "CT", dicom: dicom, automatic: automatic, frameRange: nil,
                 storedRange: stored, isColor: false)
expect(round.recordRequested(level: 77, width: 777), "an adjustment was refused")
for index in 2...6 {
    expect(round.beginFrame(seriesKey: "5.5.5", path: "/s/\(index).dcm", revisionKey: "b\(index)") == false,
           "scrolling to /s/\(index).dcm asked for new defaults")
}
expect(round.beginFrame(seriesKey: "5.5.5", path: "/s/1.dcm", revisionKey: "a1") == false,
       "returning to an unchanged file asked for new defaults")
expect(round.manualWindow?.width == 777, "returning to an unchanged file dropped the adjustment")
for index in 2...6 {
    _ = round.beginFrame(seriesKey: "5.5.5", path: "/s/\(index).dcm", revisionKey: "b\(index)")
}
expect(round.beginFrame(seriesKey: "5.5.5", path: "/s/1.dcm", revisionKey: "a2"),
       "a file replaced while the series was scrolled through kept its old defaults")
expect(round.manualWindow == nil, "the replaced file kept the adjustment made for its previous contents")

// 21. A new series resets, whatever the path says.
_ = policy.window(modality: "CT", dicom: dicom, automatic: automatic, frameRange: nil, storedRange: stored, isColor: false)
expect(policy.recordRequested(level: 10, width: 20), "an adjustment was refused")
expect(policy.beginFrame(seriesKey: "9.9.9", path: "/a/2.dcm", revisionKey: "r3"),
       "a new Series Instance UID did not reset the defaults")
expect(policy.manualWindow == nil, "a new series kept the manual window")
// 22. A loose file with no series identifier resets by path.
let loose = PreviewWindowPolicy()
expect(loose.beginFrame(seriesKey: "", path: "/a/1.dcm", revisionKey: "r1"), "the first loose frame")
_ = loose.window(modality: "CT", dicom: dicom, automatic: nil, frameRange: nil, storedRange: stored, isColor: false)
expect(loose.recordRequested(level: 5, width: 50), "an adjustment was refused")
expect(loose.beginFrame(seriesKey: "", path: "/b/1.dcm", revisionKey: "r9"),
       "a different loose file did not reset")
// 23. A width of zero is a request for automatic selection, not an adjustment.
let zero = PreviewWindowPolicy()
_ = zero.beginFrame(seriesKey: "1.2.3", path: "/a/1.dcm", revisionKey: "r1")
_ = zero.window(modality: "CT", dicom: dicom, automatic: automatic, frameRange: nil, storedRange: stored, isColor: false)
expect(zero.recordRequested(level: 40, width: 0) == false, "a zero width was recorded as an adjustment")
expect(zero.manualWindow == nil, "a zero width left a manual window behind")
expect(zero.recordRequested(level: 40, width: .nan) == false, "a NaN width was recorded")
expect(zero.recordRequested(level: .infinity, width: 400) == false, "an infinite level was recorded")
// The next frame therefore computes defaults again rather than applying width 1.
expect(zero.beginFrame(seriesKey: "1.2.3", path: "/a/2.dcm", revisionKey: "r2"),
       "after a zero-width request the defaults were not recomputed")
// 24. A colour frame ignores a manual scalar window.
let colourPolicy = PreviewWindowPolicy()
_ = colourPolicy.beginFrame(seriesKey: "7.7.7", path: "/a/us.dcm", revisionKey: "r1")
_ = colourPolicy.window(modality: "US", dicom: nil, automatic: nil, frameRange: nil, storedRange: stored, isColor: true)
expect(colourPolicy.recordRequested(level: 300, width: 1500), "an adjustment was refused")
expect(colourPolicy.window(modality: "US", dicom: nil, automatic: nil,
                           frameRange: nil, storedRange: stored, isColor: true).source == .color,
       "a colour frame received a scalar window")
// 25. The generation only moves when the defaults are dropped.
let generations = PreviewWindowPolicy()
_ = generations.beginFrame(seriesKey: "1.2.3", path: "/a/1.dcm", revisionKey: "r1")
_ = generations.window(modality: "CT", dicom: dicom, automatic: nil, frameRange: nil, storedRange: stored, isColor: false)
let settled = generations.generation
_ = generations.beginFrame(seriesKey: "1.2.3", path: "/a/2.dcm", revisionKey: "r2")
expect(generations.generation == settled, "a scroll bumped the generation")
_ = generations.beginFrame(seriesKey: "4.5.6", path: "/a/3.dcm", revisionKey: "r3")
expect(generations.generation > settled, "a new series did not bump the generation")

// ---- redraw coalescing ----------------------------------------------------
// 26. A burst of requests costs one redraw, and the last one is what runs.
let coalescer = PreviewRedrawCoalescer(interval: 0.02)
var drawn: [Int] = []
for position in 0..<40 { coalescer.request { drawn.append(position) } }
expect(drawn.isEmpty, "a redraw ran before the interval elapsed")
expect(coalescer.coalescedCount == 39, "39 requests should have been folded, not \(coalescer.coalescedCount)")
let deadline = Date().addingTimeInterval(2)
while drawn.isEmpty && Date() < deadline { RunLoop.current.run(mode: .default, before: Date().addingTimeInterval(0.01)) }
expect(drawn == [39], "the burst drew \(drawn); only the newest position should be drawn")
expect(coalescer.redrawCount == 1, "a 40-notch burst cost \(coalescer.redrawCount) redraws")
// 27. Ending the gesture does not wait for the interval.
coalescer.resetCounters()
var flushed: [Int] = []
for position in 100..<105 { coalescer.request { flushed.append(position) } }
coalescer.flush()
expect(flushed == [104], "flush drew \(flushed)")
expect(coalescer.hasPendingRedraw == false, "flush left a redraw pending")
coalescer.request { flushed.append(-1) }
coalescer.cancel()
expect(coalescer.hasPendingRedraw == false, "cancel left a redraw pending")

print("ok: preview window sources separated; \(__PHANTOM_COUNT__) phantoms matched their precomputed windows")
'''

if not failures:
    lines = []
    for name, (values, width, height, modality) in phantoms.items():
        level, window_width = expected[name]
        builder = {'ct': 'ctAirBackground()', 'mr': 'mrZeroBackground()', 'pt': 'ptCounts()',
                   'outliers': 'outlierFrame()', 'striding': 'stridingFrame()'}[name]
        lines.append(
            'do {\n'
            '    let result = window(%s, %d, %d, "%s")\n'
            '    expect(result != nil, "phantom %s produced no window")\n'
            '    close(result!.level, %r, %r, "phantom %s level")\n'
            '    close(result!.width, %r, %r, "phantom %s width")\n'
            '    expect(result!.source == .automatic, "phantom %s window is not marked automatic")\n'
            '}' % (builder, width, height, modality, name,
                   float(level), TOLERANCE, name, float(window_width), TOLERANCE, name, name))
    driver = DRIVER.replace('__EXPECTATIONS__', '\n'.join(lines))
    driver = driver.replace('__PHANTOM_COUNT__', str(len(phantoms)))

    with tempfile.TemporaryDirectory() as tmp:
        main = Path(tmp) / 'main.swift'
        main.write_text(driver)
        binary = Path(tmp) / 'driver'
        build = subprocess.run(['xcrun', 'swiftc', '-O', str(source), str(main), '-o', str(binary)],
                               capture_output=True, text=True)
        if build.returncode != 0:
            failures.append('driver did not compile:\n' + build.stderr[-4000:])
        else:
            run = subprocess.run([str(binary)], capture_output=True, text=True)
            if run.returncode != 0:
                failures.append((run.stdout + run.stderr).strip() or 'driver failed without output')
            else:
                print(run.stdout.strip())
                for name in phantoms:
                    level, width = expected[name]
                    print('   %-9s expected WL %.4g WW %.4g (+/- %g)' % (name, level, width, TOLERANCE))

if failures:
    for failure in failures:
        print('FAIL:', failure)
    raise SystemExit(1)
