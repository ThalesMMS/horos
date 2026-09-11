#!/usr/bin/env python3
"""Scissor / fillROI writes stay inside the volume, and undo has a size.

The 2016 MRA crash was a write just past a 512×512×204 float allocation while
applyScissor waited on fillROI. The sanitizer is the check those callers share:
a stack or clip that is not a plane of that orientation is refused, a clip on
the edge is brought inside, and every voxel of an accepted plan has an index
inside width × height × slices. Undo is the same voxels stored as 16-bit
samples; a multiply that does not fit is zero, not a wrapped allocation.

A text check cannot run fillROI, so the arithmetic is compiled here and the
callers are only checked for asking the sanitizer before they write.
"""
from pathlib import Path
import re
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
failures = []

fill = (root / 'Horos/Sources/DCMPix.m').read_bytes().decode('latin1')
controller = (root / 'Horos/Sources/VRController.mm').read_bytes().decode('latin1')

fill_roi = fill[fill.find('- (void) fillROI:(ROI*) roi newVal :(float) newVal minValue :(float) minValue maxValue :(float) maxValue outside :(BOOL) outside orientationStack :(long) orientationStack stackNo :(long) stackNo restore :(BOOL) restore addition:(BOOL) addition spline:(BOOL) spline clipMin:'):]
if 'HorosVRScissorBounds planWithWidth:' not in fill_roi[:2500]:
    failures.append('fillROI writes before asking the sanitizer')
if 'textureInsideColumns:' not in fill_roi:
    failures.append('a brush that hangs off the slice still forms a pointer first')
if 'ptsInt && no > 0' not in fill_roi and 'ptsInt != nil && no > 0' not in fill_roi:
    failures.append('an empty polygon still reads ptsInt[0] for the outside fill')

draw = fill[fill.find('static inline void DrawRuns('):fill.find('void ras_FillPolygon(')]
if 'orientation == 0' not in draw or 'h' not in draw:
    failures.append('DrawRuns still clamps a sagittal run to the image width')
if re.search(r'if\(\s*start >= w\)\s*start = w', draw) and 'runLimit' not in draw:
    failures.append('DrawRuns clamps every orientation to width, including sagittal rows')

apply_at = controller.find('- (void) applyScissor')
apply = controller[apply_at:controller.find('- (void) prepareUndo', apply_at)]
if 'HorosVRScissorBounds planWithWidth:' not in apply:
    failures.append('applyScissor still picks a pixList index before the sanitizer')
if 'plan.accepted' not in apply and 'accepted]' not in apply:
    failures.append('applyScissor does not refuse a geometry it cannot use')

undo_at = controller.find('- (void) prepareUndo')
undo = controller[undo_at:controller.find('- (IBAction) undo:', undo_at)]
if 'undoByteCountForWidth:' not in undo:
    failures.append('prepareUndo still multiplies the undo size without a checked count')

for failure in failures:
    print('FAIL: %s' % failure)
reported = len(failures)

main = r'''import Foundation

func plan(_ width: Int, _ height: Int, _ slices: Int, orientation: Int, stack: Int,
          restore: Bool = false,
          minX: Double = 0, minY: Double = 0, maxX: Double = 0, maxY: Double = 0) -> VRScissorPlan {
    VRScissorBounds.plan(width: width, height: height, sliceCount: slices,
                         orientation: orientation, stackNo: stack, restore: restore,
                         clipMinX: minX, clipMinY: minY, clipMaxX: maxX, clipMaxY: maxY)
}

func mustAccept(_ p: VRScissorPlan, _ what: String) {
    precondition(p.accepted, "\(what): \(p.reason)")
}

func mustRefuse(_ p: VRScissorPlan, _ what: String) {
    precondition(!p.accepted, "\(what) was accepted")
    precondition(!p.reason.isEmpty, "\(what) has no reason")
    precondition(p.undoBytes == 0)
}

// The reported MRA volume: 512×512×204 floats is 204 MiB.
let mra = plan(512, 512, 204, orientation: 2, stack: 0)
mustAccept(mra, "MRA axial first slice")
precondition(mra.pixIndex == 0)
precondition(mra.planeWidth == 512 && mra.planeHeight == 512)
precondition(mra.undoBytes == 512 * 512 * 204 * 2)

mustAccept(plan(512, 512, 204, orientation: 2, stack: 203), "MRA axial last slice")
mustRefuse(plan(512, 512, 204, orientation: 2, stack: 204), "MRA axial past the last slice")
mustAccept(plan(512, 512, 204, orientation: 0, stack: 511), "MRA sagittal last column")
mustRefuse(plan(512, 512, 204, orientation: 0, stack: 512), "MRA sagittal past the last column")
mustAccept(plan(512, 512, 204, orientation: 1, stack: 511), "MRA coronal last row")
mustRefuse(plan(512, 512, 204, orientation: 1, stack: 512), "MRA coronal past the last row")
mustRefuse(plan(512, 512, 204, orientation: 3, stack: 0), "unknown orientation")
mustRefuse(plan(512, 512, 204, orientation: -1, stack: 0), "negative orientation")
mustRefuse(plan(0, 512, 204, orientation: 2, stack: 0), "empty width")
mustRefuse(plan(512, 512, 0, orientation: 2, stack: 0), "empty stack")

// A zero clip is the historical "whole plane" request, not an empty rectangle.
let whole = plan(64, 48, 16, orientation: 2, stack: 3)
mustAccept(whole, "zero clip")
precondition(whole.clipMinX == 0 && whole.clipMinY == 0)
precondition(whole.clipMaxX == 64 && whole.clipMaxY == 48)

// A clip that hangs off the edge is brought inside; one that misses is refused.
let edge = plan(64, 48, 16, orientation: 2, stack: 0,
                minX: 60, minY: -4, maxX: 80, maxY: 10)
mustAccept(edge, "clip hanging off the axial plane")
precondition(edge.clipMinX == 60 && edge.clipMaxX == 64)
precondition(edge.clipMinY == 0 && edge.clipMaxY == 10)
mustRefuse(plan(64, 48, 16, orientation: 2, stack: 0,
                minX: 80, minY: 0, maxX: 90, maxY: 10), "clip entirely past the plane")
mustRefuse(plan(64, 48, 16, orientation: 2, stack: 0,
                minX: .nan, minY: 0, maxX: 8, maxY: 8), "non-finite clip")

// Sagittal plane is (row × slice), not (column × row). A rectangular volume
// is the case that used to walk width rows of a shorter slice.
let sagittal = plan(512, 256, 100, orientation: 0, stack: 10)
mustAccept(sagittal, "rectangular sagittal")
precondition(sagittal.pixIndex == 0)
precondition(sagittal.planeWidth == 256 && sagittal.planeHeight == 100)
precondition(sagittal.undoBytes == 512 * 256 * 100 * 2)

let coronal = plan(512, 256, 100, orientation: 1, stack: 200)
mustAccept(coronal, "rectangular coronal")
precondition(coronal.pixIndex == 0)
precondition(coronal.planeWidth == 512 && coronal.planeHeight == 100)

mustRefuse(plan(64, 48, 16, orientation: 2, stack: -1, restore: true),
           "restore with a negative stack")
mustAccept(plan(64, 48, 16, orientation: 2, stack: 4, restore: true,
                minX: 0, minY: 0, maxX: 8, maxY: 8), "restore of a slice that exists")

// Every accepted boundary sample has an index; one step past does not.
func index(_ w: Int, _ h: Int, _ s: Int, _ ori: Int, _ stack: Int, _ x: Int, _ y: Int) -> Int? {
    VRScissorBounds.voxelIndex(width: w, height: h, sliceCount: s,
                               orientation: ori, stackNo: stack,
                               planeX: x, planeY: y)?.intValue
}

let lastAxial = index(512, 512, 204, 2, 203, 511, 511)
precondition(lastAxial == 512 * 512 * 204 - 1, "last axial voxel is \(String(describing: lastAxial))")
precondition(index(512, 512, 204, 2, 203, 512, 511) == nil)
precondition(index(512, 512, 204, 2, 204, 0, 0) == nil)

let lastSagittal = index(512, 256, 100, 0, 511, 255, 99)
precondition(lastSagittal == 512 * 256 * 99 + 255 * 512 + 511, "\(String(describing: lastSagittal))")
precondition(index(512, 256, 100, 0, 511, 256, 99) == nil)
precondition(index(512, 256, 100, 0, 512, 0, 0) == nil)

let lastCoronal = index(512, 256, 100, 1, 255, 511, 99)
precondition(lastCoronal == 512 * 256 * 99 + 255 * 512 + 511)
precondition(index(512, 256, 100, 1, 255, 512, 99) == nil)

// An accepted plan's clip rectangle is entirely indexable.
for ori in [0, 1, 2] {
    let p = plan(512, 256, 100, orientation: ori, stack: ori == 1 ? 255 : 10)
    mustAccept(p, "index walk ori \(ori)")
    let x0 = Int(p.clipMinX), x1 = Int(p.clipMaxX) - 1
    let y0 = Int(p.clipMinY), y1 = Int(p.clipMaxY) - 1
    for (x, y) in [(x0, y0), (x1, y0), (x0, y1), (x1, y1)] {
        precondition(index(512, 256, 100, ori, p.stackNo, x, y) != nil,
                     "ori \(ori) corner (\(x),\(y)) is outside")
    }
}

// A brush that starts off the slice is brought inside; one that misses is empty.
func texture(_ ox: Int, _ oy: Int, _ w: Int, _ h: Int) -> [Int] {
    VRScissorBounds.textureInside(columns: 64, rows: 48, originX: ox, originY: oy,
                                  width: w, height: h).map { $0.intValue }
}
precondition(texture(10, 10, 8, 6) == [10, 10, 8, 6])
precondition(texture(-4, -4, 10, 10) == [0, 0, 6, 6])
precondition(texture(60, 40, 16, 16) == [60, 40, 4, 8])
precondition(texture(80, 0, 4, 4) == [64, 0, 0, 4] || texture(80, 0, 4, 4)[2] == 0)

let overflow = VRScissorBounds.undoByteCount(width: Int.max, height: Int.max, sliceCount: Int.max)
precondition(overflow == 0, "overflowing undo size was \(overflow)")
precondition(VRScissorBounds.undoByteCount(width: 0, height: 8, sliceCount: 8) == 0)

print("PASS: scissor plans stay inside the volume, and undo has a size")
'''

with tempfile.TemporaryDirectory(prefix='horos-scissor-') as tmp:
    p = Path(tmp)
    (p / 'main.swift').write_text(main)
    build = subprocess.run(['swiftc', str(root / 'Horos/Sources/VRScissorBounds.swift'),
                            str(p / 'main.swift'), '-o', str(p / 'test')],
                           capture_output=True, text=True)
    if build.returncode:
        print(build.stderr.strip()[-2000:])
        sys.exit('the scissor bounds did not compile')
    checks = subprocess.run([str(p / 'test')], capture_output=True, text=True)
    print((checks.stdout + checks.stderr).strip())
    if checks.returncode:
        failures.append('the scissor bounds do not keep writes inside the volume')

for failure in failures[reported:]:
    print('FAIL: %s' % failure)
if failures:
    sys.exit(1)
print('ok: scissor cuts at the edge stay inside the volume, and undo has a size')
