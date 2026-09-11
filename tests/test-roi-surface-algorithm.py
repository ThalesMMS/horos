#!/usr/bin/env python3
"""Power Crust is named unavailable; a known cube is a closed, coherent surface."""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
code = r'''
import Foundation
import simd

func close(_ a: Double, _ b: Double, _ e: Double = 1e-6) {
    precondition(a.isFinite && b.isFinite && abs(a - b) < e, "\(a) != \(b)")
}

func expect(_ ok: Bool, _ message: String) {
    precondition(ok, message)
}

expect(ROISurfaceAlgorithm.isAvailable(forPreference: 0), "0 is Iso Contour")
expect(ROISurfaceAlgorithm.name(forPreference: 0) == "iso-contour", "0 is named iso-contour")
expect(ROISurfaceAlgorithm.unavailabilityReason(forPreference: 0) == nil,
       "available Iso has no unavailability reason")
let iso = ROISurfaceAlgorithm.resolvePreference(0)
expect(iso.available && iso.name == "iso-contour" && iso.preference == 0,
       "resolve(0) is Iso Contour")

expect(ROISurfaceAlgorithm.isAvailable(forPreference: 1), "1 is Delaunay")
expect(ROISurfaceAlgorithm.name(forPreference: 1) == "delaunay", "1 is named delaunay")
let delaunay = ROISurfaceAlgorithm.resolvePreference(1)
expect(delaunay.available && delaunay.preference == 1, "resolve(1) is Delaunay")

expect(!ROISurfaceAlgorithm.isAvailable(forPreference: 2),
       "Power Crust is not a supported algorithm")
expect(ROISurfaceAlgorithm.name(forPreference: 2) == "power-crust",
       "2 is named Power Crust, not Iso")
let power = ROISurfaceAlgorithm.resolvePreference(2)
expect(!power.available && power.name != "iso-contour",
       "Power Crust must not fall through to Iso Contour")
let powerText = (ROISurfaceAlgorithm.unavailabilityReason(forPreference: 2) ?? "").lowercased()
expect(powerText.contains("power crust") || powerText.contains("unavailable"),
       "Power Crust diagnosis must be explicit: \(powerText)")

for unknown in [-1, 3, 99] {
    let decision = ROISurfaceAlgorithm.resolvePreference(unknown)
    expect(!decision.available, "\(unknown) must be refused")
    expect(decision.name != "iso-contour",
           "\(unknown) must not silently become Iso Contour")
    expect(ROISurfaceAlgorithm.unavailabilityReason(forPreference: unknown) != nil,
           "\(unknown) needs an explicit diagnosis")
}

expect(!ROISurfaceAlgorithm.shouldRewritePreference(afterFailure: 1),
       "Delaunay failure must not rewrite UseDelaunayFor3DRoi to Iso")
expect(!ROISurfaceAlgorithm.shouldReplaceUnavailableAlgorithmWithIsoContour(),
       "an unavailable algorithm must not be replaced with Iso Contour")

let closedCube = ROISurfaceAlgorithm.cube(origin: .zero, sideMm: 10)
expect(ROISurfaceAlgorithm.isClosed(closedCube), "a 10 mm cube is a closed surface")
close(ROISurfaceAlgorithm.volumeCm3(closedCube)!, 1)

func axial(_ z: Double) -> ROIVolumeSlice {
    ROIVolumeSlice(areaCm2: 1, originX: 0, originY: 0, originZ: z,
                   normalX: 0, normalY: 0, normalZ: 1, componentCount: 1,
                   maskPixelCount: 0, pixelAreaMm2: 0, spacingBetweenSlicesMm: 5)
}
let trap = ROIVolumeGeometry.volume(
    from: [axial(0), axial(5), axial(10)],
    seriesOrigins: [0.0, 5.0, 10.0].map { ROIPatientPoint(x: 0, y: 0, z: $0) },
    interpolateMissing: false, meshPointCount: 0)!
close(trap.volumeCm3, 1)
expect(ROISurfaceAlgorithm.volumeIsCoherent(
        meshCm3: ROISurfaceAlgorithm.volumeCm3(closedCube)!,
        trapezoidCm3: trap.volumeCm3, tolerance: 1e-6),
       "mesh volume must match the trapezoid in cm³")

let opened = ROISurfaceAlgorithm.droppingLastFaces(closedCube, count: 2)
expect(!ROISurfaceAlgorithm.isClosed(opened), "a cube without one face is not closed")
expect(ROISurfaceAlgorithm.volumeCm3(opened) == nil,
       "an open surface has no closed-mesh volume")

let two = ROISurfaceAlgorithm.disjointCubes(sideMm: 10, gapMm: 10)
expect(ROISurfaceAlgorithm.isClosed(two),
       "two disconnected cubes remain a closed topology")
close(ROISurfaceAlgorithm.volumeCm3(two)!, 2)

print("PASS: Power Crust refused; 10 mm cube closed and 1 cm³; open face rejected; two cubes stay closed")
'''
with tempfile.TemporaryDirectory(prefix='horos-roi-surface-') as d:
    p = Path(d)
    (p / 'main.swift').write_text(code)
    subprocess.run([
        'xcrun', 'swiftc',
        str(root / 'Horos/Sources/ROIIntersliceGeometry.swift'),
        str(root / 'Horos/Sources/ROIVolumeGeometry.swift'),
        str(root / 'Horos/Sources/ROISurfaceAlgorithm.swift'),
        str(p / 'main.swift'), '-o', str(p / 'test')
    ], check=True)
    subprocess.run([str(p / 'test')], check=True)
