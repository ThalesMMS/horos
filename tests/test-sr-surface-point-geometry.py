#!/usr/bin/env python3
"""Click, surface pick and exported DICOM coincide on a landmark phantom at 1x/2x.

vtkWorldPointPicker without a z-buffer lands on the camera focal plane. Surface
Rendering's iso actors are PickableOff, so that fallback is what throw3DPointOnSurface
used. A landmark on a surface offset from the focal plane must not export the
focal-plane voxel. The same window click at backing scale 1 and 2 must yield the
same world point and the same DICOM voxel.
"""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
code = r'''
import AppKit
import Foundation
import simd

final class BackingView: NSView {
    var scale: CGFloat = 1
    override func convertToBacking(_ point: NSPoint) -> NSPoint {
        NSPoint(x: point.x * scale, y: point.y * scale)
    }
}

func near(_ a: SIMD3<Double>, _ b: SIMD3<Double>, _ eps: Double = 1e-8) -> Bool {
    simd_length(a - b) < eps
}

let identity: [NSNumber] = [
    1, 0, 0, 0,
    0, 1, 0, 0,
    0, 0, 1, 0,
    0, 0, 0, 1,
]
let rotatedZ: [NSNumber] = [
    0, -1, 0, 0,
    1,  0, 0, 0,
    0,  0, 1, 0,
    0,  0, 0, 1,
]

let world = SRSurfacePointGeometry.voxel(
    fromWorldX: 14, y: 26, z: 38,
    rowMajorMatrix: identity,
    actorPositionX: 10, actorPositionY: 20, actorPositionZ: 30,
    spacingX: 2, spacingY: 3, spacingZ: 4)!
precondition(abs(world.x - 2) < 1e-8 && abs(world.y - 2) < 1e-8 && abs(world.z - 2) < 1e-8,
             "FAIL: identity convert3Dto2Dpoint formula drifted")

let rotated = SRSurfacePointGeometry.voxel(
    fromWorldX: 0, y: 2, z: 0,
    rowMajorMatrix: rotatedZ,
    actorPositionX: 10, actorPositionY: 0, actorPositionZ: 0,
    spacingX: 1, spacingY: 1, spacingZ: 1)!
precondition(abs(rotated.x + 8) < 1e-8 && abs(rotated.y) < 1e-8 && abs(rotated.z) < 1e-8,
             "FAIL: actor-matrix conversion no longer matches convert3Dto2Dpoint")

let matrixOnly = SRSurfacePointGeometry.voxel(
    fromWorldX: 4, y: 6, z: 8,
    rowMajorMatrix: identity,
    actorPositionX: 0, actorPositionY: 0, actorPositionZ: 0,
    spacingX: 0, spacingY: 0, spacingZ: 0)!
precondition(abs(matrixOnly.x - 4) < 1e-8 && abs(matrixOnly.y - 6) < 1e-8 && abs(matrixOnly.z - 8) < 1e-8,
             "FAIL: missing iso actor must still invert the orientation matrix")

let landmark = SIMD3<Double>(40, 22, 8)
let cameraPosition = SIMD3<Double>(32, 32, 80)
let focal = SIMD3<Double>(32, 32, 16)
let viewUp = SIMD3<Double>(0, 1, 0)
let parallelScale = 32.0
let viewport1 = SIMD2<Double>(400, 300)
let viewport2 = SIMD2<Double>(800, 600)

let display1 = SRSurfacePointGeometry.displayPoint(
    forWorld: landmark,
    viewportWidth: viewport1.x, viewportHeight: viewport1.y,
    cameraPositionX: cameraPosition.x, cameraPositionY: cameraPosition.y, cameraPositionZ: cameraPosition.z,
    focalX: focal.x, focalY: focal.y, focalZ: focal.z,
    viewUpX: viewUp.x, viewUpY: viewUp.y, viewUpZ: viewUp.z,
    parallelScale: parallelScale, viewAngle: 30, parallel: true)!
let display2 = NSPoint(x: display1.x * 2, y: display1.y * 2)

let window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 800, height: 600),
                       styleMask: .borderless, backing: .buffered, defer: false)
let view = BackingView(frame: NSRect(x: 20, y: 15, width: 400, height: 300))
window.contentView!.addSubview(view)
let windowClick = NSPoint(x: 20 + display1.x, y: 15 + display1.y)
view.scale = 1
let backing1 = SRSurfacePointGeometry.displayPoint(windowClick, in: view)
view.scale = 2
let backing2 = SRSurfacePointGeometry.displayPoint(windowClick, in: view)
precondition(abs(backing1.x - display1.x) < 1e-8 && abs(backing1.y - display1.y) < 1e-8)
precondition(abs(backing2.x - display2.x) < 1e-8 && abs(backing2.y - display2.y) < 1e-8)

func pick(display: NSPoint, viewport: SIMD2<Double>) -> (focal: SIMD3<Double>, surface: SIMD3<Double>, voxel: SRSurfacePoint) {
    let focalWorld = SRSurfacePointGeometry.focalPlaneWorld(
        fromDisplayX: display.x, y: display.y,
        viewportWidth: viewport.x, viewportHeight: viewport.y,
        cameraPositionX: cameraPosition.x, cameraPositionY: cameraPosition.y, cameraPositionZ: cameraPosition.z,
        focalX: focal.x, focalY: focal.y, focalZ: focal.z,
        viewUpX: viewUp.x, viewUpY: viewUp.y, viewUpZ: viewUp.z,
        parallelScale: parallelScale, viewAngle: 30, parallel: true)!
    let surfaceWorld = SRSurfacePointGeometry.surfaceWorld(
        fromDisplayX: display.x, y: display.y,
        viewportWidth: viewport.x, viewportHeight: viewport.y,
        cameraPositionX: cameraPosition.x, cameraPositionY: cameraPosition.y, cameraPositionZ: cameraPosition.z,
        focalX: focal.x, focalY: focal.y, focalZ: focal.z,
        viewUpX: viewUp.x, viewUpY: viewUp.y, viewUpZ: viewUp.z,
        parallelScale: parallelScale, viewAngle: 30, parallel: true,
        planePointX: landmark.x, planePointY: landmark.y, planePointZ: landmark.z,
        planeNormalX: 0, planeNormalY: 0, planeNormalZ: 1)!
    let voxel = SRSurfacePointGeometry.voxel(
        fromWorldX: surfaceWorld.x, y: surfaceWorld.y, z: surfaceWorld.z,
        rowMajorMatrix: identity,
        actorPositionX: 0, actorPositionY: 0, actorPositionZ: 0,
        spacingX: 1, spacingY: 1, spacingZ: 1)!
    return (focalWorld, surfaceWorld, voxel)
}

let at1 = pick(display: backing1, viewport: viewport1)
let at2 = pick(display: backing2, viewport: viewport2)
precondition(near(SIMD3(at1.surface.x, at1.surface.y, at1.surface.z), landmark),
             "FAIL: 1x surface pick missed the landmark")
precondition(near(SIMD3(at2.surface.x, at2.surface.y, at2.surface.z), landmark),
             "FAIL: 2x surface pick missed the landmark")
precondition(near(SIMD3(at1.voxel.x, at1.voxel.y, at1.voxel.z), landmark),
             "FAIL: exported DICOM voxel does not match the landmark")
precondition(near(SIMD3(at2.voxel.x, at2.voxel.y, at2.voxel.z), landmark),
             "FAIL: 2x exported DICOM voxel drifted from the landmark")
precondition(!near(at1.focal, landmark, 0.5),
             "FAIL: fixture collapsed; focal-plane pick must not already sit on the surface")
let focalVoxel = SRSurfacePointGeometry.voxel(
    fromWorldX: at1.focal.x, y: at1.focal.y, z: at1.focal.z,
    rowMajorMatrix: identity,
    actorPositionX: 0, actorPositionY: 0, actorPositionZ: 0,
    spacingX: 1, spacingY: 1, spacingZ: 1)!
precondition(abs(focalVoxel.z - 16) < 1e-6,
             "FAIL: WorldPointPicker fallback is no longer the focal-plane slice")
precondition(abs(focalVoxel.z - landmark.z) > 1,
             "FAIL: exporting the focal-plane pick would report the landmark")

print("PASS: click, surface pick and exported DICOM coincide at 1x/2x; focal-plane picker does not")
'''
with tempfile.TemporaryDirectory(prefix='horos-sr-surface-point-') as d:
    p = Path(d)
    (p / 'main.swift').write_text(code)
    subprocess.run(
        ['xcrun', 'swiftc',
         str(root / 'Horos/Sources/VRInteractionGeometry.swift'),
         str(root / 'Horos/Sources/SRSurfacePointGeometry.swift'),
         str(p / 'main.swift'), '-o', str(p / 'test')],
        check=True)
    subprocess.run([str(p / 'test')], check=True)
