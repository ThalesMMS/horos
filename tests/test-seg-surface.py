#!/usr/bin/env python3
"""SEG masks become voxel-face meshes without forcing spherical topology (#377 A)."""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
source = root / 'Horos/Sources/HorosSEGSurface.swift'
seg = root / 'Horos/Sources/DicomSEG.swift'
algo = root / 'Horos/Sources/ROISurfaceAlgorithm.swift'
failures = []
if not source.is_file():
    raise SystemExit('FAIL: Horos/Sources/HorosSEGSurface.swift is missing')

driver = r'''
import Foundation
import simd

func expect(_ ok: Bool, _ message: String) {
    if !ok { fputs("FAIL: \(message)\n", stderr); exit(1) }
}

func close(_ a: Double, _ b: Double, _ e: Double = 1e-9) {
    expect(a.isFinite && b.isFinite && abs(a - b) < e, "\(a) != \(b)")
}

func geometry(rows: Int, columns: Int, frames: Int, spacing: Double = 1) -> DicomSEGGeometry {
    DicomSEGGeometry(
        rows: rows, columns: columns, frames: frames,
        spacingRow: spacing, spacingCol: spacing, sliceThickness: spacing,
        origin: [0, 0, 0],
        orientation: [1, 0, 0, 0, 1, 0],
        frameOfReferenceUID: "1.2.840.10008.1.2.1.377.1",
        frameOrigins: (0..<frames).map { [0.0, 0.0, Double($0) * spacing] }
    )
}

func segment(number: UInt16, label: String, geometry: DicomSEGGeometry,
             voxels: [(Int, Int, Int)], color: (Double, Double, Double) = (1, 0, 0),
             visible: Bool = true) -> DicomSEGSegment {
    var frames = (0..<geometry.frames).map { _ in
        Data(repeating: 0, count: geometry.rows * geometry.columns)
    }
    for (column, row, frame) in voxels {
        var plane = frames[frame]
        plane[row * geometry.columns + column] = 1
        frames[frame] = plane
    }
    return DicomSEGSegment(
        number: number, label: label, trackingUID: DicomSEGCodec.makeUID(),
        color: color, visible: visible, kind: .binary, algorithm: "MANUAL",
        provenance: "synthetic-surface", referencedSOPInstanceUIDs: ["1.2.840.10008.5.1.4.1.1.2.377.1"],
        frames: frames, maximumFractionalValue: 255)
}

expect(HorosSEGSurface.usesSharedSEGModel, "A reuses #376")
expect(!HorosSEGSurface.buildsParallelROIStore, "A must not invent another ROI store")
expect(!HorosSEGSurface.nativeViewerOverlayImplemented,
       "native MPR/3D/scout overlay remains a gap")
expect(!HorosSEGSurface.simplificationForcesSphericalTopology,
       "refinement must not force spherical topology")

let cubeGeom = geometry(rows: 2, columns: 2, frames: 2)
let cubeVoxels = [(0, 0, 0), (1, 0, 0), (0, 1, 0), (1, 1, 0),
                   (0, 0, 1), (1, 0, 1), (0, 1, 1), (1, 1, 1)]
let cubeSeg = segment(number: 1, label: "cube", geometry: cubeGeom, voxels: cubeVoxels)
let cubeMesh = HorosSEGSurface.extract(segment: cubeSeg, geometry: cubeGeom)
expect(ROISurfaceAlgorithm.isClosed(cubeMesh), "a filled 2x2x2 cube is closed")
expect(HorosSEGSurface.isSpherical(cubeMesh), "one cube is a topological sphere")
let cubeMask = HorosSEGSurface.maskVolumeCm3(segment: cubeSeg, geometry: cubeGeom)
close(cubeMask, 0.008)
let cubeMeshCm3 = ROISurfaceAlgorithm.volumeCm3(cubeMesh)!
close(cubeMeshCm3, cubeMask)
expect(HorosSEGSurface.volumeIsCoherent(meshCm3: cubeMeshCm3, maskCm3: cubeMask),
       "mask and mesh represent the same 8 mm³ region")

let splitGeom = geometry(rows: 2, columns: 6, frames: 2)
var splitVoxels: [(Int, Int, Int)] = []
for z in 0..<2 {
    for y in 0..<2 {
        for x in 0..<2 { splitVoxels.append((x, y, z)) }
        for x in 4..<6 { splitVoxels.append((x, y, z)) }
    }
}
let splitSeg = segment(number: 2, label: "two-cubes", geometry: splitGeom, voxels: splitVoxels)
let splitMesh = HorosSEGSurface.extract(segment: splitSeg, geometry: splitGeom)
let splitInspect = HorosSEGSurface.inspect(splitMesh)
expect(splitInspect.closed, "two cubes remain a closed surface")
expect(splitInspect.componentCount == 2, "disconnected components stay two, got \(splitInspect.componentCount)")
expect(!HorosSEGSurface.isSpherical(splitMesh), "two cubes are not one sphere")
expect(HorosSEGSurface.eulerCharacteristic(splitMesh) == 4,
       "two spheres have χ=4, got \(HorosSEGSurface.eulerCharacteristic(splitMesh))")
let splitMask = HorosSEGSurface.maskVolumeCm3(segment: splitSeg, geometry: splitGeom)
close(splitMask, 0.016)
expect(HorosSEGSurface.volumeIsCoherent(meshCm3: ROISurfaceAlgorithm.volumeCm3(splitMesh)!,
                                        maskCm3: splitMask),
       "disconnected mask and mesh volumes stay coherent")

let cavityGeom = geometry(rows: 3, columns: 3, frames: 3)
var cavityVoxels: [(Int, Int, Int)] = []
for z in 0..<3 {
    for y in 0..<3 {
        for x in 0..<3 {
            if x == 1 && y == 1 && z == 1 { continue }
            cavityVoxels.append((x, y, z))
        }
    }
}
let cavitySeg = segment(number: 3, label: "cavity", geometry: cavityGeom, voxels: cavityVoxels)
let cavityMesh = HorosSEGSurface.extract(segment: cavitySeg, geometry: cavityGeom)
let cavityInspect = HorosSEGSurface.inspect(cavityMesh)
expect(cavityInspect.closed, "a cube with a cavity is still closed")
expect(cavityInspect.componentCount == 2, "outer shell and cavity stay two components, got \(cavityInspect.componentCount)")
expect(!HorosSEGSurface.isSpherical(cavityMesh), "a cavity is not a single sphere")
let cavityMask = HorosSEGSurface.maskVolumeCm3(segment: cavitySeg, geometry: cavityGeom)
close(cavityMask, 0.026)
expect(HorosSEGSurface.volumeIsCoherent(meshCm3: ROISurfaceAlgorithm.volumeCm3(cavityMesh)!,
                                        maskCm3: cavityMask),
       "cavity mask and mesh volumes stay coherent")

let tubeGeom = geometry(rows: 3, columns: 3, frames: 4)
var tubeVoxels: [(Int, Int, Int)] = []
for z in 0..<4 {
    for y in 0..<3 {
        for x in 0..<3 {
            if x == 1 && y == 1 { continue }
            tubeVoxels.append((x, y, z))
        }
    }
}
let tubeSeg = segment(number: 4, label: "tube", geometry: tubeGeom, voxels: tubeVoxels)
let tubeMesh = HorosSEGSurface.extract(segment: tubeSeg, geometry: tubeGeom)
expect(ROISurfaceAlgorithm.isClosed(tubeMesh), "a voxel tube with a hole is a closed pipe")
expect(HorosSEGSurface.inspect(tubeMesh).componentCount == 1, "a tube is one component")
expect(!HorosSEGSurface.isSpherical(tubeMesh),
       "a tube is not a sphere (χ=\(HorosSEGSurface.eulerCharacteristic(tubeMesh)))")
let refinedTube = HorosSEGSurface.refine(tubeMesh, keeping: [SIMD3(1, 1, 2)])
expect(ROISurfaceAlgorithm.isClosed(refinedTube), "refinement must keep the pipe closed")
expect(!HorosSEGSurface.isSpherical(refinedTube), "refinement must not force spherical topology")

let identity = DicomSEGIdentity(
    sopInstanceUID: DicomSEGCodec.makeUID(),
    seriesInstanceUID: DicomSEGCodec.makeUID(),
    studyInstanceUID: DicomSEGCodec.makeUID(),
    frameOfReferenceUID: cubeGeom.frameOfReferenceUID,
    sourceSOPInstanceUIDs: ["1.2.840.10008.5.1.4.1.1.2.377.1"]
)
let kidney = segment(number: 1, label: "kidney", geometry: cubeGeom, voxels: cubeVoxels, color: (1, 0, 0))
let cortexVoxels = [(0, 0, 0), (1, 0, 0)]
let cortex = segment(number: 2, label: "cortex", geometry: cubeGeom, voxels: cortexVoxels, color: (0, 1, 0))
let store = DicomSEGStore(document: DicomSEGDocument(
    identity: identity, geometry: cubeGeom, kind: .binary,
    segments: [kidney, cortex], diagnoses: [], sourceBytes: nil))
let surfaces = HorosSEGSurfaceSet(store: store)
expect(surfaces.overlays.count == 2, "one surface per segment")
expect(surfaces.overlay(segment: 1)?.name == "kidney", "name comes from the store")
expect(HorosSEGSurfaceView.allCases.allSatisfy { surfaces.overlay(segment: 1)!.appears(in: $0) },
       "planar/MPR/volume/scout share visibility")
surfaces.setOpacity(0.4, trackingUID: store.document.segments[0].trackingUID)
let pin = cubeMesh.vertices[0]
surfaces.pinLandmark(pin, trackingUID: store.document.segments[0].trackingUID)
expect(store.setLabel("kidney-L", segment: 1), "rename uses the shared command")
expect(store.setColor((0, 0, 1), segment: 1), "recolour uses the shared command")
expect(store.setVisibility(false, segment: 2), "visibility uses the shared command")
let copy = store.duplicate(segment: 1)
expect(copy != nil, "duplicate uses the shared command")
surfaces.reload(from: store)
expect(surfaces.overlay(segment: 1)?.name == "kidney-L", "rename syncs the surface")
expect(surfaces.overlay(segment: 1)?.color.b == 1, "colour syncs the surface")
expect(surfaces.overlay(segment: 1)?.opacity == 0.4, "opacity is presentation, not a second store")
expect(surfaces.overlay(segment: 1)?.pinnedLandmarks.count == 1, "pinned landmarks survive reload")
expect(surfaces.overlay(segment: 2)?.visible == false, "hidden segment is hidden in every view")
expect(surfaces.overlay(segment: 2)?.appears(in: .scout) == false, "scout follows visibility")
expect(surfaces.overlays.contains(where: { $0.segmentNumber == copy }), "duplicate grows the surface set")
expect(store.remove(segment: 2), "delete uses the shared command")
surfaces.reload(from: store)
expect(surfaces.overlay(segment: 2) == nil, "deleted segment disappears from every view")
expect(store.undo(), "undo restore")
surfaces.reload(from: store)
expect(surfaces.overlay(segment: 2) != nil, "undo brings the surface back")

print("PASS: SEG masks keep tubes, cavities and disconnected components without a parallel ROI store")
'''

with tempfile.TemporaryDirectory(prefix='horos-seg-surface-') as tmp:
    path = Path(tmp)
    (path / 'main.swift').write_text(driver)
    built = subprocess.run(
        ['xcrun', '--sdk', 'macosx', 'swiftc',
         '-o', str(path / 'test'),
         str(source), str(seg), str(algo),
         str(path / 'main.swift')],
        capture_output=True, text=True)
    if built.returncode != 0:
        failures.append('HorosSEGSurface.swift did not compile:\n%s' % built.stderr[-2500:])
    else:
        ran = subprocess.run([str(path / 'test')], capture_output=True, text=True, timeout=60)
        print(ran.stdout.strip())
        if ran.returncode != 0:
            failures.append('the surface contract failed: %s' % (ran.stderr or ran.stdout)[-2000:])

for failure in failures:
    print('FAIL: %s' % failure)
if failures:
    raise SystemExit(1)
print('ok: SEG voxel-face meshes preserve topology and stay coherent with the mask')
