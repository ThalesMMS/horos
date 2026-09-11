#!/usr/bin/env python3
"""Flythrough WL/WW interpolation stays inside keyframe limits and is applied.

Issue #222: black pixels only in frames between keyframes that change window,
distinct from framebuffer crop. The path stored interpolated WL/WW as long
and VR setCamera skipped the transfer when ww <= 1.
"""
import re
import subprocess
import tempfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
failures = []


def check(condition, message):
    if not condition:
        failures.append(message)


flythru = (root / 'Horos/Sources/FlyThru.m').read_bytes().decode('latin1')
vrview = (root / 'Horos/Sources/VRView.mm').read_bytes().decode('latin1')
adapter = (root / 'Horos/Sources/VRFlyThruAdapter.m').read_bytes().decode('latin1')
controller = (root / 'Horos/Sources/FlyThruController.mm').read_bytes().decode('latin1')
policy = (root / 'Horos/Sources/SeriesReplaceLoadPolicy.swift').read_text()
viewer = (root / 'Horos/Sources/ViewerController.m').read_bytes().decode('latin1')


def method_body(source, signature):
    at = source.find(signature)
    if at < 0:
        return ''
    opening = source.index('{', at)
    depth, index = 0, opening
    while index < len(source):
        if source[index] == '{':
            depth += 1
        elif source[index] == '}':
            depth -= 1
            if depth == 0:
                return source[opening:index + 1]
        index += 1
    return ''


def comments_stripped(text):
    text = re.sub(r'//[^\n]*', '', text)
    return re.sub(r'/\*.*?\*/', '', text, flags=re.S)


compute = method_body(flythru, '-(void) computePath')
set_camera = method_body(vrview, '- (void) setCamera: (Camera*) cam')
image_for_frame = method_body(controller, '-(NSImage*) imageForFrame:(NSNumber*) cur maxFrame:(NSNumber*) max')
two_arg = method_body(
    viewer,
    '- (BOOL) isDataVolumicIn4D: (BOOL) check4D checkEverythingLoaded:(BOOL) c;')

# --- path cameras keep float windows inside the keyframe envelope ----------
check(compute, 'FlyThru computePath is gone')
check('#import "Horos-Swift.h"' in flythru, 'FlyThru.m must see HorosFlyThruWindow')
check('HorosFlyThruWindow' in compute, 'computePath must clamp through HorosFlyThruWindow')
check('(long)[iwl x]' not in comments_stripped(compute),
      'computePath must not truncate interpolated level to long')
check('(long)[iww x]' not in comments_stripped(compute),
      'computePath must not truncate interpolated width to long')
check('clampedLevel:' in compute and 'clampedWidth:' in compute,
      'computePath must clamp level and width to the keyframe envelope')
check('(long)[index4D x]' in compute,
      '4D movie index may still be stored as long; do not change that contract')

# --- setCamera applies the transfer before VTK camera / capture -------------
check(set_camera, 'VRView setCamera: is gone')
check('HorosFlyThruWindow' in set_camera, 'setCamera must resolve the window through HorosFlyThruWindow')
check('[cam ww] > 1' not in comments_stripped(set_camera),
      'setCamera must not skip a width of 1 after interpolation')
wl_at = comments_stripped(set_camera).find('resolveLevel:')
pos_at = comments_stripped(set_camera).find('SetPosition')
check(wl_at >= 0 and pos_at > wl_at,
      'transfer must be applied before the VTK camera is moved')
check('setWLWW' in comments_stripped(set_camera),
      'setCamera must still call setWLWW so the color/opacity table matches the frame')

# --- export captures after setCamera, not a second windowing path ----------
check('setCurrentViewToCamera' in adapter, 'VR adapter must apply the path camera')
check('nsimageQuicktime' in adapter, 'VR adapter still captures through nsimageQuicktime')
check('setCurrentViewToCamera' in image_for_frame and 'getCurrentCameraImage' in image_for_frame,
      'exported frames must be the render after setCamera of that path index')

# --- #425 overload and series-replace policy stay as origin/main left them
check('@objc(HorosSeriesReplaceLoadPolicy)' in policy,
      'HorosSeriesReplaceLoadPolicy must stay')
check('isDataVolumicIn4D: check4D checkEverythingLoaded: c tryToCorrect:' in comments_stripped(two_arg),
      'the two-argument volumic probe must still forward both flags')

main = r'''import Foundation

func catmullRom(_ p0: Double, _ p1: Double, _ p2: Double, _ p3: Double, _ t: Double) -> Double {
    let t2 = t * t
    let t3 = t2 * t
    return 0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2
        + (-p0 + 3 * p1 - 3 * p2 + p3) * t3)
}

// vtkCardinalSpline (tension 0) overshoots on a 4-step path that narrows
// then widens: WW 1500 / 400 / 40 / 1500. The 400→40 segment goes negative.
var rawMin = Double.infinity
var clampedMin = Double.infinity
var sawNegative = false
let keyWWs = [1500.0, 400.0, 40.0, 1500.0]
for i in 0..<32 {
    let t = Double(i) / 31.0
    let raw = catmullRom(keyWWs[0], keyWWs[1], keyWWs[2], keyWWs[3], t)
    rawMin = min(rawMin, raw)
    if raw < 0 { sawNegative = true }
    let clamped = FlyThruWindow.clampedWidth(raw, rangeMin: 40, rangeMax: 1500)
    clampedMin = min(clampedMin, clamped)
    assert(clamped >= 40 && clamped <= 1500, "\(clamped)")
    assert(clamped >= FlyThruWindow.minimumWidth)
}
assert(rawMin < 0, "the spline fixture must go negative, got \(rawMin)")
assert(sawNegative)
assert(clampedMin >= 40)

// Extreme WL overshoot would walk the transfer off the data.
let overshotLevel = FlyThruWindow.clampedLevel(800, rangeMin: 40, rangeMax: 300)
assert(overshotLevel == 300)
assert(FlyThruWindow.clampedLevel(40.5, rangeMin: 40, rangeMax: 300) == 40.5)

// Float windows survive: the long cast turned 1.7 into 1, then setCamera skipped.
assert(FlyThruWindow.clampedWidth(1.7, rangeMin: 1.7, rangeMax: 400) == 1.7)
assert(FlyThruWindow.clampedLevel(-1024.25, rangeMin: -2000, rangeMax: 400) == -1024.25)

var level = 0.0, width = 0.0
assert(FlyThruWindow.resolve(level: &level, width: &width) == false, "0,0 is the unset sentinel")

level = 40; width = 1
assert(FlyThruWindow.resolve(level: &level, width: &width))
assert(level == 40 && width == 1, "a width of 1 must be applied, not skipped")

level = 40; width = 0.5
assert(FlyThruWindow.resolve(level: &level, width: &width))
assert(width == 0.5)

level = 166; width = -50
assert(FlyThruWindow.resolve(level: &level, width: &width))
assert(width == FlyThruWindow.minimumWidth && level == 166)

level = 40; width = Double.nan
assert(FlyThruWindow.resolve(level: &level, width: &width))
assert(width == FlyThruWindow.minimumWidth)

// Linear midpoint between two keyframes covers the data both of them
// show; the overshot 800/40 window that the spline used to store does not.
let data = 40.0
assert(FlyThruWindow.transferCovers(data, level: 40, width: 400))
assert(FlyThruWindow.transferCovers(data, level: 300, width: 1500))
assert(FlyThruWindow.transferCovers(data, level: 170, width: 950))
assert(!FlyThruWindow.transferCovers(data, level: 800, width: 40),
       "overshot WL/WW must be the black-voxel case")
assert(!FlyThruWindow.transferCovers(data, level: 166, width: 0))
assert(!FlyThruWindow.transferCovers(data, level: 166, width: -50))
let clampedWL = FlyThruWindow.clampedLevel(800, rangeMin: 40, rangeMax: 300)
let clampedWW = FlyThruWindow.clampedWidth(2, rangeMin: 400, rangeMax: 1500)
assert(clampedWL == 300 && clampedWW == 400)
assert(FlyThruWindow.transferCovers(clampedWL, level: clampedWL, width: clampedWW))

print("PASS: spline overshoot is clamped, floats survive, WW=1 is applied, transfer covers the keyframe data")
'''

with tempfile.TemporaryDirectory(prefix='horos-flythru-window-') as tmp:
    p = Path(tmp)
    (p / 'main.swift').write_text(main)
    subprocess.run(['swiftc', str(root / 'Horos/Sources/FlyThruWindow.swift'),
                    str(p / 'main.swift'), '-o', str(p / 'test')], check=True)
    subprocess.run([str(p / 'test')], check=True)

if failures:
    raise SystemExit('FAIL:\n' + '\n'.join(failures))
print('PASS: flythrough WL/WW interpolation, limits and transfer-before-capture')
