#!/usr/bin/env python3
"""Play/pause wrapping stays in range; inconsistent 4D geometry is named, not indexed."""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
main = r'''import Foundation

final class FakePix: NSObject {
    @objc var pwidth: Int
    @objc var pheight: Int
    init(_ width: Int, _ height: Int) {
        pwidth = width
        pheight = height
    }
}

func pixList(_ count: Int, width: Int, height: Int) -> NSMutableArray {
    NSMutableArray(array: (0..<count).map { _ in FakePix(width, height) })
}

func volume(_ slices: Int, width: Int, height: Int, extra: Int = 0) -> NSData {
    NSMutableData(length: slices * width * height * MemoryLayout<Float>.size + extra)!
}

func check(_ condition: @autoclosure () -> Bool, _ message: String) {
    precondition(condition(), message)
}

// Play wrapping never returns a negative index or one past the last time.
check(FourDSeriesGuard.wrappedIndex(0, count: 3) == 0, "first time")
check(FourDSeriesGuard.wrappedIndex(2, count: 3) == 2, "last time")
check(FourDSeriesGuard.wrappedIndex(3, count: 3) == 0, "wrap forward")
check(FourDSeriesGuard.wrappedIndex(-1, count: 3) == 2, "wrap backward")
check(FourDSeriesGuard.wrappedIndex(7, count: 3) == 1, "large positive")
check(FourDSeriesGuard.wrappedIndex(-4, count: 3) == 2, "large negative")
check(FourDSeriesGuard.wrappedIndex(0, count: 0) == 0, "empty series stays at 0")
check(FourDSeriesGuard.wrappedIndex(-1, count: 0) == 0, "empty series does not go negative")
check(FourDSeriesGuard.wrappedIndex(5, count: 0) == 0, "empty series ignores the request")
check(FourDSeriesGuard.wrappedIndex(0, count: -2) == 0, "negative count is not a valid range")

var index = 2
var visited = Set<Int>()
for _ in 0..<9 {
    index = FourDSeriesGuard.nextIndex(index, count: 3)
    check(index >= 0 && index < 3, "play left \(index)")
    visited.insert(index)
}
check(visited == [0, 1, 2], "nine play steps visit every time")
check(FourDSeriesGuard.nextIndex(0, count: 0) == 0, "play on an empty series stays at 0")
check(FourDSeriesGuard.alignedTimeIndex(requested: 5, count: 3) == 2, "SR files/pix/volume share the wrap")
check(FourDSeriesGuard.alignedTimeIndex(requested: -1, count: 0) == 0, "SR does not index -1")

check(FourDSeriesGuard.canStoreTime(at: 0, capacity: 500), "first slot")
check(FourDSeriesGuard.canStoreTime(at: 499, capacity: 500), "last slot")
check(!FourDSeriesGuard.canStoreTime(at: 500, capacity: 500), "past capacity")
check(!FourDSeriesGuard.canStoreTime(at: -1, capacity: 500), "negative slot")
let capacity = FourDSeriesGuard.capacityReason(at: 500, capacity: 500)!
check(capacity.contains("500"), capacity)

// Uniform synthetic 4D: three times, four 8x8 slices, matching buffers.
let slices = 4, width = 8, height = 8
let reference = FourDSeriesGuard.geometry(fromPixList: pixList(slices, width: width, height: height),
                                         volume: volume(slices, width: width, height: height))!
check(reference.width == width && reference.height == height && reference.sliceCount == slices,
      "uniform geometry")
check(reference.bufferLength == reference.expectedBufferLength, "buffer matches the voxels")
for time in 0..<3 {
    let candidate = FourDSeriesGuard.geometry(fromPixList: pixList(slices, width: width, height: height),
                                             volume: volume(slices, width: width, height: height))
    check(FourDSeriesGuard.reconstructionRefusal(comparing: candidate, to: reference, at: time) == nil,
          "time \(time) matches")
    check(FourDSeriesGuard.reasonForInconsistentSlices(pixList(slices, width: width, height: height),
                                                    atTime: time) == nil,
          "slices agree at \(time)")
}

// Missing frame: a later time has fewer slices than the first volume.
let shortTime = FourDSeriesGuard.geometry(fromPixList: pixList(3, width: width, height: height),
                                          volume: volume(3, width: width, height: height))
let missing = FourDSeriesGuard.reconstructionRefusal(comparing: shortTime, to: reference, at: 1)!
check(missing.contains("2") && missing.contains("3") && missing.contains("4"), missing)
check(missing.lowercased().contains("slice"), missing)

// Divergent in-plane size at another time.
let otherSize = FourDSeriesGuard.geometry(fromPixList: pixList(slices, width: 16, height: 8),
                                          volume: volume(slices, width: 16, height: 8))
let size = FourDSeriesGuard.reconstructionRefusal(comparing: otherSize, to: reference, at: 2)!
check(size.contains("3") && size.contains("16") && size.contains("8"), size)

// One slice inside a time disagrees with the others.
let mixed = pixList(slices, width: width, height: height)
mixed[1] = FakePix(16, 8)
let mixedSlices = FourDSeriesGuard.reasonForInconsistentSlices(mixed, atTime: 1)!
check(mixedSlices.contains("2"), mixedSlices)

// Buffer shorter than the voxels it has to back: the pointer would be read past its end.
let shortBuffer = FourDSeriesGuard.geometry(fromPixList: pixList(slices, width: width, height: height),
                                            volume: NSMutableData(length: 12))
let lifetime = FourDSeriesGuard.reconstructionRefusal(comparing: shortBuffer, to: reference, at: 1)!
check(lifetime.contains("12"), lifetime)
check(lifetime.contains("\(reference.expectedBufferLength)"), lifetime)

let empty = FourDSeriesGuard.reconstructionRefusal(comparing: nil, to: reference, at: 1)!
check(empty.contains("2"), empty)
check(empty.lowercased().contains("frame") || empty.lowercased().contains("no"), empty)

let emptyList = FourDSeriesGuard.reasonForInconsistentSlices(NSMutableArray(), atTime: 0)!
check(!emptyList.isEmpty, emptyList)

print("PASS: wrap stays in range; missing frame, size and short buffer are named")
'''

with tempfile.TemporaryDirectory(prefix='horos-four-d-') as tmp:
    p = Path(tmp)
    (p / 'main.swift').write_text(main)
    subprocess.run([
        'xcrun', 'swiftc',
        str(root / 'Horos/Sources/FourDSeriesGuard.swift'),
        str(p / 'main.swift'), '-o', str(p / 'test')
    ], check=True)
    subprocess.run([str(p / 'test')], check=True)

def objc_body(source, signature):
    at = 0
    while True:
        at = source.find(signature, at)
        if at < 0:
            return ''
        brace = source.find('{', at)
        semi = source.find(';', at)
        if brace >= 0 and (semi < 0 or brace < semi):
            break
        at += len(signature)
    depth, index = 0, brace
    while index < len(source):
        if source[index] == '{':
            depth += 1
        elif source[index] == '}':
            depth -= 1
            if depth == 0:
                return source[brace:index + 1]
        index += 1
    return ''


vr = (root / 'Horos/Sources/VRController.mm').read_bytes().decode('latin1')
viewer = (root / 'Horos/Sources/ViewerController.m').read_bytes().decode('latin1')
header = (root / 'Horos/Sources/VRController.h').read_bytes().decode('latin1')
mpr = (root / 'Horos/Sources/MPRController.m').read_bytes().decode('latin1')

assert 'HorosFourDSeriesGuard' in vr, 'VR play/reconstruct does not use the 4D index guard'
assert 'wrappedIndex:' in vr, 'VR setMovieFrame does not wrap the requested time'
assert 'reconstructionRefusalComparing' in viewer or 'fourDReconstructionRefusalReason' in viewer, (
    '3D reconstruction does not ask whether the times share geometry')
panel = viewer[viewer.index('initWithPix:pixList['):viewer.index('initWithPix:pixList[') + 80]
assert 'pixList[0]' in panel and 'curMovieIndex' not in panel, (
    'the floating MIP panel still pairs the current time\'s pix with volume 0')
assert 'pixList[ MAX4D]' in header, (
    'VR still keeps only 100 times while the 2D viewer can hold 500')
assert 'HorosFourDSeriesGuard' in mpr, 'MPR play does not wrap with the same helper'
assert 'fourDReconstructionRefusalReason' in viewer, 'reconstruction has no explicit refusal'

sr_action = objc_body(viewer, '-(IBAction) SRViewer:(id) sender')
assert 'refuseFourDReconstructionWithTitle:' in sr_action, (
    'Surface Rendering still opens a 4D volume without the geometry refusal')
assert 'Surface Rendering' in sr_action, 'SR refusal must keep the Surface Rendering title'

endo_action = objc_body(viewer, '-(IBAction) endoscopyViewer:(id) sender')
assert 'refuseFourDReconstructionWithTitle:' in endo_action, (
    'Endoscopy still opens a 4D volume without the geometry refusal')
assert 'Endoscopy' in endo_action, 'Endoscopy refusal must keep the Endoscopy title'

sr_open = objc_body(viewer, '- (SRController *)openSRViewer')
assert 'wrappedIndex:' in sr_open, 'openSRViewer does not wrap the requested 4D time'
assert 'alignedTimeIndex' in (root / 'Horos/Sources/FourDSeriesGuard.swift').read_text(encoding='utf-8')
assert 'fileList[0]' not in sr_open, 'openSRViewer still pairs the current pix with fileList[0]'
assert 'pixList[time]' in sr_open and 'fileList[time]' in sr_open and 'volumeData[time]' in sr_open, (
    'openSRViewer must use one wrapped time for pix, files and volume')
print('PASS: production play wrapping and reconstruction refusal stay wired')
