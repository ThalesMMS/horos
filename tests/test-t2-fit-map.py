#!/usr/bin/env python3
"""Fit a synthetic multi-echo T2 phantom with the native arm64 T2 Fit Map."""
from pathlib import Path
import math
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
source = root / 'Horos/Sources/T2FitMap.swift'
if not source.is_file():
    raise SystemExit('FAIL: Horos/Sources/T2FitMap.swift is missing')

code = r'''
import Foundation

func close(_ a: Double, _ b: Double, _ e: Double = 0.05) {
    precondition(a.isFinite && b.isFinite && abs(a - b) < e, "\(a) != \(b)")
}

precondition(T2FitMap.version == "1.0")
precondition(T2FitMap.abi == "arm64-native")
precondition(T2FitMap.menuTitle == "T2 Fit Map")
precondition(T2FitMap.legacyVersion == "1.3")
precondition(T2FitMap.legacyPrincipalClass == "MappingT2FitFilter")
precondition(T2FitMap.sourceRevision == "6b4036242ca4f821679bcd83942a4b842d7ffb2c")

let tes = [10.0, 20.0, 40.0, 80.0]
func signal(t2: Double, te: Double, s0: Double = 1000) -> Double {
    s0 * exp(-te / t2)
}

let pixel = T2FitMap.fitPixel(echoes: tes.map {
    T2FitMap.Echo(teMilliseconds: $0, signal: signal(t2: 80, te: $0))
})!
close(pixel.t2Milliseconds, 80)
close(pixel.protonDensity, 1000, 1)

let few = T2FitMap.fitSeries(
    signals: [[100, 50]],
    echoTimesMilliseconds: [10],
    width: 1, height: 1)
precondition(few.code == T2FitMap.ErrorCode.tooFewEchoes.rawValue)
precondition(few.reason.contains("echo"))

let missing = T2FitMap.fitSeries(
    signals: [[100, 50], [80, 40]],
    echoTimesMilliseconds: [10, 0],
    width: 1, height: 1)
precondition(missing.code == T2FitMap.ErrorCode.missingEchoTimes.rawValue)
precondition(missing.reason.contains("TE") || missing.reason.contains("echo time"))

let rising = T2FitMap.fitPixel(echoes: [
    T2FitMap.Echo(teMilliseconds: 10, signal: 10),
    T2FitMap.Echo(teMilliseconds: 40, signal: 40),
    T2FitMap.Echo(teMilliseconds: 80, signal: 80)
])!
precondition(rising.t2Milliseconds == 0)

let width = 8, height = 8
let truths: [Double] = [40, 80, 120, 200]
var frames: [[Float]] = tes.map { _ in [Float](repeating: 0, count: width * height) }
for y in 0..<height {
    for x in 0..<width {
        let t2 = truths[(y < 4 ? 0 : 2) + (x < 4 ? 0 : 1)]
        for (echo, te) in tes.enumerated() {
            frames[echo][y * width + x] = Float(signal(t2: t2, te: te))
        }
    }
}
let map = T2FitMap.fitSeries(
    signals: frames, echoTimesMilliseconds: tes, width: width, height: height)
precondition(map.code == 0, map.reason)
precondition(map.t2Milliseconds.count == width * height)
for y in 0..<height {
    for x in 0..<width {
        let expected = truths[(y < 4 ? 0 : 2) + (x < 4 ? 0 : 1)]
        close(Double(map.t2Milliseconds[y * width + x]), expected, 0.2)
    }
}
precondition(map.validCount == width * height)

let groups = T2FitMap.groupEchoSequences(origins: [
    (0, 0, 0), (0, 0, 5), (0, 0, 10),
    (0, 0, 0), (0, 0, 5), (0, 0, 10)
])
precondition(groups == [[0, 3], [1, 4], [2, 5]])

let filter = T2FitMapFilter()
precondition(filter.prepareFilter(nil) == 0)
precondition(filter.filterImage("T2 Fit Map") == T2FitMap.ErrorCode.emptySeries.rawValue)
precondition(filter.lastReason.contains("viewer") || filter.lastReason.contains("phantom"))

filter.prepare(signals: frames, echoTimesMilliseconds: tes, width: width, height: height)
precondition(filter.filterImage("T2 Fit Map") == 0)
precondition(filter.lastMap.count == width * height)
close(Double(filter.lastMap[0]), 40, 0.2)
close(Double(filter.lastMap[7]), 80, 0.2)

print("PASS: native T2 Fit Map 1.0 recovers phantom compartments and diagnoses missing series")
'''

with tempfile.TemporaryDirectory(prefix='horos-t2-fit-map-') as directory:
    path = Path(directory)
    (path / 'main.swift').write_text(code)
    subprocess.run([
        'xcrun', 'swiftc', str(source), str(path / 'main.swift'),
        '-o', str(path / 'test')
    ], check=True)
    subprocess.run([str(path / 'test')], check=True)
