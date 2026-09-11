#!/usr/bin/env python3
"""4D MPR ROI mean/min/max follow the selected time on an oblique plane."""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
code = r'''
import Foundation

func close(_ a: Double, _ b: Double, _ e: Double = 1e-6) {
    precondition(a.isFinite && b.isFinite && abs(a - b) < e, "\(a) != \(b)")
}

func volume(time: Int, width: Int, height: Int, depth: Int) -> [Float] {
    var voxels = [Float](repeating: 0, count: width * height * depth)
    for z in 0..<depth {
        let value = Float(100 * time + z)
        for y in 0..<height {
            for x in 0..<width {
                voxels[x + width * (y + height * z)] = value
            }
        }
    }
    return voxels
}

func reconstruct(time: Int) -> [Float] {
    var plane = [Float](repeating: 0, count: 8 * 8)
    let voxels = volume(time: time, width: 8, height: 8, depth: 8)
    voxels.withUnsafeBufferPointer { source in
        plane.withUnsafeMutableBufferPointer { dest in
            ROITemporalStatistics.reconstructNearest(
                volume: source.baseAddress!, width: 8, height: 8, depth: 8,
                planeWidth: 8, planeHeight: 8,
                originX: 0, originY: 0, originZ: 0,
                rowX: 1, rowY: 0, rowZ: 1,
                colX: 0, colY: 1, colZ: 0,
                into: dest.baseAddress!)
        }
    }
    return plane
}

func stats(time: Int, plane: [Float], identity: String) -> ROIIntensityStats {
    plane.withUnsafeBufferPointer { buffer in
        ROITemporalStatistics.sampleRectangle(
            minX: 2, minY: 1, maxX: 5, maxY: 2,
            in: buffer.baseAddress!, width: 8, height: 8,
            timeIndex: time, geometryIdentity: identity)!
    }
}

let fingerprint = ROITemporalStatistics.geometryFingerprint(
    minX: 2, minY: 1, maxX: 5, maxY: 2,
    originX: 0, originY: 0, originZ: 0,
    rowX: 1, rowY: 0, rowZ: 1,
    colX: 0, colY: 1, colZ: 0)
precondition(fingerprint.contains("2,1,5,2"))

// Analytical: pixel (i,j) samples voxel (i, j, i) → value 100*t + i.
// ROI i=2...5, j=1...2 → eight samples, mean 100*t+3.5, min 100*t+2, max 100*t+5.
let cache = ROITemporalValueCache()
var identity = "QA-4D-oblique"
for time in [0, 1, 2, 0, 2, 1, 0] {
    let plane = reconstruct(time: time)
    // Pixel (2,0) must be the oblique z=i sample, not axial z=0.
    close(Double(plane[2]), Double(100 * time + 2))
    let measured = stats(time: time, plane: plane, identity: fingerprint)
    close(measured.mean, Double(100 * time) + 3.5)
    close(measured.minimum, Double(100 * time + 2))
    close(measured.maximum, Double(100 * time + 5))
    precondition(measured.sampleCount == 8)
    precondition(measured.timeIndex == time)
    precondition(measured.geometryIdentity == fingerprint)
    cache.store(measured)
    precondition(cache.storedValues(matchingTimeIndex: time, geometryIdentity: fingerprint) === measured)
    let other = time == 0 ? 1 : 0
    precondition(cache.storedValues(matchingTimeIndex: other, geometryIdentity: fingerprint) == nil)
    precondition(!ROITemporalStatistics.cachedValuesRemainValid(
        previousTimeIndex: other, currentTimeIndex: time, geometryUnchanged: true))
    precondition(ROITemporalStatistics.cachedValuesRemainValid(
        previousTimeIndex: time, currentTimeIndex: time, geometryUnchanged: true))
}

precondition(ROITemporalStatistics.mustRefreshCachedValuesAfterReconstructedBufferChange())

let binding = ROITemporalBinding(identity: identity, geometryFingerprint: fingerprint, timeIndex: 0)
let switched = binding.switchingTime(to: 1)
precondition(switched.identity == identity)
precondition(switched.geometryFingerprint == fingerprint)
precondition(switched.timeIndex == 1)

let silent = switched.applyingGeometry("moved-plane", atTime: 2, explicitPropagation: false)
precondition(silent == nil)
let explicit = switched.applyingGeometry("moved-plane", atTime: 2, explicitPropagation: true)!
precondition(explicit.identity == identity)
precondition(explicit.geometryFingerprint == "moved-plane")
precondition(explicit.timeIndex == 2)

let restored = ROITemporalBinding.restored(from: switched.propertyList)!
precondition(restored.identity == identity)
precondition(restored.geometryFingerprint == fingerprint)
precondition(restored.timeIndex == 1)

let empty: [Float] = [Float.nan, Float.nan]
empty.withUnsafeBufferPointer { buffer in
    precondition(ROITemporalStatistics.sampleRectangle(
        minX: 0, minY: 0, maxX: 1, maxY: 0,
        in: buffer.baseAddress!, width: 2, height: 1,
        timeIndex: 0, geometryIdentity: fingerprint) == nil)
}

print("PASS: 4D oblique ROI mean/min/max follow the selected time; cache, geometry and identity hold")
'''
with tempfile.TemporaryDirectory(prefix='horos-mpr-4d-roi-') as d:
    p = Path(d)
    (p / 'main.swift').write_text(code)
    subprocess.run([
        'xcrun', 'swiftc',
        str(root / 'Horos/Sources/ROITemporalStatistics.swift'),
        str(p / 'main.swift'), '-o', str(p / 'test')
    ], check=True)
    subprocess.run([str(p / 'test')], check=True)
