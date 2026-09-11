#!/usr/bin/env python3
"""Surface Rendering and Endoscopy refuse the same inconsistent 4D geometry as VR."""
from pathlib import Path
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
failures = []


def check(condition, message):
    if not condition:
        failures.append(message)


def body(source, signature):
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


# Compile the production helper: the SR/Endoscopy paths share the #220 phantom.
code = r'''
import Foundation

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

func volume(_ slices: Int, width: Int, height: Int) -> NSData {
    NSMutableData(length: slices * width * height * MemoryLayout<Float>.size)!
}

func check(_ condition: @autoclosure () -> Bool, _ message: String) {
    precondition(condition(), message)
}

let slices = 4, width = 8, height = 8
let reference = FourDSeriesGuard.geometry(
    fromPixList: pixList(slices, width: width, height: height),
    volume: volume(slices, width: width, height: height))!

check(FourDSeriesGuard.reconstructionRefusal(
    comparing: FourDSeriesGuard.geometry(
        fromPixList: pixList(slices, width: width, height: height),
        volume: volume(slices, width: width, height: height)),
    to: reference, at: 0) == nil, "uniform time 0")

let missing = FourDSeriesGuard.reconstructionRefusal(
    comparing: FourDSeriesGuard.geometry(
        fromPixList: pixList(3, width: width, height: height),
        volume: volume(3, width: width, height: height)),
    to: reference, at: 1)!
check(missing.contains("2") && missing.lowercased().contains("slice"), missing)

let size = FourDSeriesGuard.reconstructionRefusal(
    comparing: FourDSeriesGuard.geometry(
        fromPixList: pixList(slices, width: 16, height: 8),
        volume: volume(slices, width: 16, height: 8)),
    to: reference, at: 2)!
check(size.contains("16"), size)

let shortBuffer = FourDSeriesGuard.reconstructionRefusal(
    comparing: FourDSeriesGuard.geometry(
        fromPixList: pixList(slices, width: width, height: height),
        volume: NSMutableData(length: 12)),
    to: reference, at: 1)!
check(shortBuffer.contains("12"), shortBuffer)

check(FourDSeriesGuard.wrappedIndex(-1, count: 3) == 2, "open uses the same wrap")
check(FourDSeriesGuard.alignedTimeIndex(requested: 5, count: 3) == 2, "pix/files/volume share the wrap")
check(FourDSeriesGuard.wrappedIndex(3, count: 3) == 0, "open does not pass the last time")
check(FourDSeriesGuard.wrappedIndex(7, count: 0) == 0, "empty series opens time 0")

print("PASS: SR/Endoscopy share the 4D refusal phantom")
'''
with tempfile.TemporaryDirectory(prefix='horos-four-d-sr-') as tmp:
    p = Path(tmp)
    (p / 'main.swift').write_text(code)
    subprocess.run([
        'xcrun', 'swiftc',
        str(root / 'Horos/Sources/FourDSeriesGuard.swift'),
        str(p / 'main.swift'), '-o', str(p / 'test')
    ], check=True)
    subprocess.run([str(p / 'test')], check=True)

viewer = (root / 'Horos/Sources/ViewerController.m').read_bytes().decode('latin1')
sr = body(viewer, '-(IBAction) SRViewer:(id) sender')
endo = body(viewer, '-(IBAction) endoscopyViewer:(id) sender')
open_sr = body(viewer, '- (SRController *)openSRViewer')

check('refuseFourDReconstructionWithTitle' in sr,
      'SRViewer must refuse inconsistent 4D geometry before opening VTK')
check('Surface Rendering' in sr,
      'SRViewer must name Surface Rendering in the refusal title')
check('refuseFourDReconstructionWithTitle' in endo,
      'endoscopyViewer must refuse inconsistent 4D geometry before opening VTK')
check('Endoscopy' in endo,
      'endoscopyViewer must name Endoscopy in the refusal title')

check('wrappedIndex' in open_sr or 'alignedTimeIndexRequested' in open_sr,
      'openSRViewer must wrap the time into 0 ..< maxMovieIndex')
check('pixList[curMovieIndex]' not in open_sr,
      'openSRViewer must not index pixList with an unwrapped curMovieIndex')
# Same local time index for pix, files and volume.
check('fileList[0]' not in open_sr,
      'openSRViewer must not pair the current volume with fileList[0]')
check('pixList[' in open_sr and 'fileList[' in open_sr and 'volumeData[' in open_sr,
      'openSRViewer must pass pixList, fileList and volumeData')

if failures:
    for item in failures:
        print('FAIL:', item, file=sys.stderr)
    sys.exit(1)
print('PASS: SR and Endoscopy refuse 4D geometry and open one aligned time')
