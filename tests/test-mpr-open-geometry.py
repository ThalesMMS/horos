#!/usr/bin/env python3
"""3D MPR opening names invalid geometry instead of crashing (#217, #206).

A large CTA with ROIs and migrated mouse-overlay prefs must still open.
A coherent oblique IOP opens; a mixed orientation is named and refused.
Zero/NaN interval or spacing is named. Overlay conversion is refused while
the hidden VR controller is still presenting a modal during init.
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

func opening(slices: Int, spacingX: Double, spacingY: Double, interval: Double,
             minInterval: Double, maxInterval: Double,
             width: Int, height: Int, mismatched: Int, rois: Int) -> MPROpenDecision {
    MPROpenGeometry.opening(withSliceCount: slices, spacingX: spacingX, spacingY: spacingY,
                            sliceInterval: interval, minInterval: minInterval,
                            maxInterval: maxInterval, width: width, height: height,
                            mismatchedSlices: mismatched, roiCount: rois)
}

// Large chest CTA (TAVI-style): hundreds of slices, ROIs present, regular interval.
let cta = opening(slices: 420, spacingX: 0.5, spacingY: 0.5, interval: 0.5,
                  minInterval: 0.5, maxInterval: 0.5, width: 512, height: 512,
                  mismatched: 0, rois: 12)
expect(cta.accepted && cta.phase == "open",
       "CTA with ROIs must open: \(cta.phase) \(cta.diagnosis)")

let noRoi = opening(slices: 420, spacingX: 0.5, spacingY: 0.5, interval: 0.5,
                    minInterval: 0.5, maxInterval: 0.5, width: 512, height: 512,
                    mismatched: 0, rois: 0)
expect(noRoi.accepted, "the same CTA without ROIs must also open")

// Migrated prefs only affect overlay drawing, not the volume gate.
expect(cta.accepted, "MPRDisplayMousePosition is not a geometry refusal")

let zeroInterval = opening(slices: 420, spacingX: 0.5, spacingY: 0.5, interval: 0,
                            minInterval: 0, maxInterval: 0, width: 512, height: 512,
                            mismatched: 0, rois: 0)
expect(!zeroInterval.accepted && zeroInterval.phase == "calibrate",
       "zero slice interval must ask for calibration: \(zeroInterval.diagnosis)")
expect(zeroInterval.diagnosis.lowercased().contains("interval"),
       "zero interval diagnosis must name the voxel/slice interval: \(zeroInterval.diagnosis)")

let nanInterval = opening(slices: 420, spacingX: 0.5, spacingY: 0.5, interval: .nan,
                           minInterval: 0, maxInterval: 0, width: 512, height: 512,
                           mismatched: 0, rois: 0)
expect(!nanInterval.accepted && nanInterval.phase == "refused",
       "non-finite interval is invalid geometry: \(nanInterval.diagnosis)")

let zeroSpacing = opening(slices: 420, spacingX: 0, spacingY: 0.5, interval: 0.5,
                          minInterval: 0.5, maxInterval: 0.5, width: 512, height: 512,
                          mismatched: 0, rois: 0)
expect(!zeroSpacing.accepted && zeroSpacing.phase == "calibrate",
       "zero pixel spacing must ask for calibration")

let fewSlices = opening(slices: 4, spacingX: 0.5, spacingY: 0.5, interval: 0.5,
                        minInterval: 0.5, maxInterval: 0.5, width: 512, height: 512,
                        mismatched: 0, rois: 0)
expect(!fewSlices.accepted && fewSlices.phase == "refused",
       "four slices are not volumic: \(fewSlices.diagnosis)")
expect(fewSlices.diagnosis.lowercased().contains("volumic"),
       "non-volumic diagnosis must stay explicit: \(fewSlices.diagnosis)")

let mixedSize = opening(slices: 420, spacingX: 0.5, spacingY: 0.5, interval: 0.5,
                         minInterval: 0.5, maxInterval: 0.5, width: 512, height: 512,
                         mismatched: 8, rois: 0)
expect(!mixedSize.accepted && mixedSize.phase == "refused",
       "mixed matrices are invalid geometry: \(mixedSize.diagnosis)")

// Varying interval is a warning, not a crash and not a hard refuse.
let irregular = opening(slices: 420, spacingX: 0.5, spacingY: 0.5, interval: 0.6,
                         minInterval: 0.4, maxInterval: 0.9, width: 512, height: 512,
                         mismatched: 0, rois: 3)
expect(irregular.accepted && irregular.phase == "open",
       "irregular interval still opens after naming the variation: \(irregular.diagnosis)")
expect(irregular.diagnosis.lowercased().contains("interval"),
       "irregular diagnosis must mention interval: \(irregular.diagnosis)")

// #206: a shared IOP is volumic even when it is not axial. Compare 9-component
// orientations the way isDataVolumicIn4D does (reference = slice 1).
let axial = [1.0, 0, 0, 0, 1.0, 0, 0, 0, 1.0]
let oblique30: [Double] = {
    let c = Darwin.cos(30.0 * Double.pi / 180.0)
    let s = Darwin.sin(30.0 * Double.pi / 180.0)
    return [1.0, 0, 0, 0, c, s, 0, -s, c]
}()
let oblique15: [Double] = {
    let c = Darwin.cos(15.0 * Double.pi / 180.0)
    let s = Darwin.sin(15.0 * Double.pi / 180.0)
    return [1.0, 0, 0, 0, c, s, 0, -s, c]
}()
func stack(_ orientation: [Double], count: Int = 16) -> [[Double]] {
    Array(repeating: orientation, count: count)
}

expect(MPROpenGeometry.mismatchedOrientations(among: stack(axial)) == 0,
       "uniform axial slices share one orientation")
expect(MPROpenGeometry.mismatchedOrientations(among: stack(oblique30)) == 0,
       "a coherent oblique stack is one orientation, not a mix")
var mixed = stack(oblique30)
mixed[8] = oblique15
expect(MPROpenGeometry.mismatchedOrientations(among: mixed) == 1,
       "one rotated slice is a single orientation mismatch")

func openingIOP(orientations: [[Double]], interval: Double = 2.0,
                minInterval: Double = 2.0, maxInterval: Double = 2.0) -> MPROpenDecision {
    MPROpenGeometry.opening(withSliceCount: orientations.count, spacingX: 0.5, spacingY: 0.5,
                            sliceInterval: interval, minInterval: minInterval, maxInterval: maxInterval,
                            width: 64, height: 64, mismatchedSlices: 0, roiCount: 0,
                            mismatchedOrientations: MPROpenGeometry.mismatchedOrientations(among: orientations))
}

let uniform = openingIOP(orientations: stack(axial))
expect(uniform.accepted && uniform.phase == "open" && uniform.diagnosis == "ready",
       "uniform axial must open: \(uniform.phase) \(uniform.diagnosis)")

let coherentOblique = openingIOP(orientations: stack(oblique30))
expect(coherentOblique.accepted && coherentOblique.phase == "open",
       "coherent 30° IOP must open: \(coherentOblique.phase) \(coherentOblique.diagnosis)")

let irregularOblique = openingIOP(orientations: stack(oblique30), interval: 2.0,
                                  minInterval: 2.0, maxInterval: 6.0)
expect(irregularOblique.accepted && irregularOblique.phase == "open",
       "irregular spacing on a shared IOP still opens: \(irregularOblique.diagnosis)")
expect(irregularOblique.diagnosis.lowercased().contains("interval"),
       "irregular oblique diagnosis must name the interval")

let incompatible = openingIOP(orientations: mixed)
expect(!incompatible.accepted && incompatible.phase == "refused",
       "mixed IOP must be refused with a diagnosis: \(incompatible.phase) \(incompatible.diagnosis)")
expect(incompatible.diagnosis.lowercased().contains("orientation"),
       "mixed IOP diagnosis must name orientation: \(incompatible.diagnosis)")
expect(incompatible.diagnosis.lowercased().contains("crash") == false,
       "the refusal is a diagnosis, not a crash label")

// Overlay: historical crash is convertDICOMCoords while hidden VR init is modal.
expect(!MPROpenGeometry.canConvertSliceCoords(destinationPix: true, companionA: true,
                                            companionB: true, spacingX: 0.5, spacingY: 0.5,
                                            vrAttached: false, displayMousePosition: true),
       "mouse overlay must wait until the hidden VR view is attached")
expect(!MPROpenGeometry.canConvertSliceCoords(destinationPix: true, companionA: false,
                                            companionB: true, spacingX: 0.5, spacingY: 0.5,
                                            vrAttached: true, displayMousePosition: true),
       "missing companion pix must not convert DICOM coords")
expect(!MPROpenGeometry.canConvertSliceCoords(destinationPix: true, companionA: true,
                                            companionB: true, spacingX: 0, spacingY: 0.5,
                                            vrAttached: true, displayMousePosition: true),
       "zero spacing must not convert DICOM coords")
expect(MPROpenGeometry.canConvertSliceCoords(destinationPix: true, companionA: true,
                                           companionB: true, spacingX: 0.5, spacingY: 0.5,
                                           vrAttached: true, displayMousePosition: true),
       "ready views with migrated mouse-position pref may convert")
expect(!MPROpenGeometry.canConvertSliceCoords(destinationPix: true, companionA: true,
                                            companionB: true, spacingX: 0.5, spacingY: 0.5,
                                            vrAttached: true, displayMousePosition: false),
       "overlay conversion is off when the pref is off")

expect(!MPROpenGeometry.shouldPresentHighDynamicPrompt(duringHiddenInit: true),
       "hidden MPR VR init must not run a modal that re-enters drawing")
expect(MPROpenGeometry.shouldPresentHighDynamicPrompt(duringHiddenInit: false),
       "interactive VR still presents the high-dynamic prompt")

print("PASS: CTA opens with ROIs; coherent oblique IOP opens; mixed IOP is named; overlay waits for VR attach")
'''
with tempfile.TemporaryDirectory(prefix='horos-mpr-open-geometry-') as d:
    p = Path(d)
    (p / 'main.swift').write_text(code)
    subprocess.run([
        'xcrun', 'swiftc',
        str(root / 'Horos/Sources/MPROpenGeometry.swift'),
        str(p / 'main.swift'), '-o', str(p / 'test')
    ], check=True)
    subprocess.run([str(p / 'test')], check=True)
