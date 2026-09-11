#!/usr/bin/env python3
"""Click, scissors and crop stay aligned in VTK display pixels at 1x and 2x.

#29 is the Retina mismatch: NSEvent points versus the VTK backing framebuffer.
A click and the tool overlay must occupy the same display pixel; every crop
handle must be hittable; a scissors stroke must reach every quadrant. Mixing
AppKit frame points with backing mouse coordinates is the failure this guards.
"""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
code = r'''
import AppKit

final class BackingView: NSView {
    var scale: CGFloat = 1
    override func convertToBacking(_ point: NSPoint) -> NSPoint {
        NSPoint(x: point.x * scale, y: point.y * scale)
    }
    override func convertToBacking(_ size: NSSize) -> NSSize {
        NSSize(width: size.width * scale, height: size.height * scale)
    }
    override func convertToBacking(_ rect: NSRect) -> NSRect {
        NSRect(origin: convertToBacking(rect.origin), size: convertToBacking(rect.size))
    }
}

let window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 800, height: 600),
                      styleMask: .borderless, backing: .buffered, defer: false)
let container = NSView(frame: NSRect(x: 80, y: 30, width: 600, height: 500))
window.contentView!.addSubview(container)
let view = BackingView(frame: NSRect(x: 20, y: 15, width: 400, height: 300))
container.addSubview(view)

let volume = (minX: 10.0, minY: 20.0, minZ: 30.0, maxX: 50.0, maxY: 80.0, maxZ: 90.0)
let pointClicks = [
    NSPoint(x: 40, y: 50),
    NSPoint(x: 360, y: 50),
    NSPoint(x: 40, y: 250),
    NSPoint(x: 360, y: 250),
]

for scale in [CGFloat(1), CGFloat(2)] {
    view.scale = scale
    let displaySize = VTKRetinaGeometry.displaySize(of: view)
    precondition(abs(displaySize.width - 400 * scale) < 1e-8)
    precondition(abs(displaySize.height - 300 * scale) < 1e-8)
    precondition(abs(VTKRetinaGeometry.displayScale(of: view) - scale) < 1e-8)

    let resizeThreshold = VTKRetinaGeometry.resizeHandleDisplayThreshold(pointThreshold: 20, scale: scale)
    precondition(abs(resizeThreshold - 20 * scale) < 1e-8)
    precondition(VTKRetinaGeometry.isViewportResizeHandle(x: 19 * scale, y: 3 * scale, threshold: resizeThreshold))
    precondition(!VTKRetinaGeometry.isViewportResizeHandle(x: 21 * scale, y: 3 * scale, threshold: resizeThreshold))

    let dragThreshold = VTKRetinaGeometry.scissorsDragThreshold(pointThreshold: 5, scale: scale)
    precondition(abs(dragThreshold - 5 * scale) < 1e-8)

    for viewPoint in pointClicks {
        let windowPoint = NSPoint(x: 80 + 20 + viewPoint.x, y: 30 + 15 + viewPoint.y)
        let display = VTKRetinaGeometry.displayPoint(fromWindowPoint: windowPoint, in: view)
        let expected = NSPoint(x: viewPoint.x * scale, y: viewPoint.y * scale)
        precondition(abs(display.x - expected.x) < 1e-8 && abs(display.y - expected.y) < 1e-8)

        let overlay = VTKRetinaGeometry.scissorsOverlay(forDisplay: display)
        precondition(abs(overlay.x - display.x) < 1e-8 && abs(overlay.y - display.y) < 1e-8)

        let quadrant = VTKRetinaGeometry.quadrant(ofDisplayX: display.x, y: display.y,
                                                  width: displaySize.width, height: displaySize.height)
        precondition(quadrant >= 0 && quadrant <= 3)

        if display.x > view.bounds.width || display.y > view.bounds.height {
            let mismatched = VTKRetinaGeometry.quadrant(ofDisplayX: display.x, y: display.y,
                                                        width: view.bounds.width, height: view.bounds.height)
            precondition(mismatched != quadrant,
                         "Frame points used as VTK display size must miss a Retina click past the point midline")
        }

        let offset = VTKRetinaGeometry.windowCenterOffset(forDisplay: display, displaySize: displaySize)
        let recovered = NSPoint(x: displaySize.width / 2 - offset.x,
                                y: displaySize.height / 2 - offset.y)
        precondition(abs(recovered.x - display.x) < 1e-8 && abs(recovered.y - display.y) < 1e-8)
        if scale > 1 {
            let legacy = VTKRetinaGeometry.windowCenterOffset(forDisplay: display, displaySize: view.bounds.size)
            precondition(abs(legacy.x - offset.x) > 1 || abs(legacy.y - offset.y) > 1,
                         "Window-center math in frame points cannot match a Retina display click")
        }
    }

    let seen = NSMutableSet()
    for viewPoint in pointClicks {
        let windowPoint = NSPoint(x: 80 + 20 + viewPoint.x, y: 30 + 15 + viewPoint.y)
        let display = VTKRetinaGeometry.displayPoint(fromWindowPoint: windowPoint, in: view)
        seen.add(VTKRetinaGeometry.quadrant(ofDisplayX: display.x, y: display.y,
                                            width: displaySize.width, height: displaySize.height))
    }
    precondition(seen.count == 4, "Scissors must reach every quadrant at scale \(scale)")

    let handles = VTKRetinaGeometry.projectedCropHandles(
        minX: volume.minX, minY: volume.minY, minZ: volume.minZ,
        maxX: volume.maxX, maxY: volume.maxY, maxZ: volume.maxZ,
        displayWidth: displaySize.width, displayHeight: displaySize.height)
    precondition(handles.count == 14)

    let tolerance = VTKRetinaGeometry.cropHandleDisplayTolerance(pointTolerance: 8, scale: scale)
    precondition(abs(tolerance - 8 * scale) < 1e-8)
    for handle in 0..<7 {
        let hx = handles[handle * 2].doubleValue
        let hy = handles[handle * 2 + 1].doubleValue
        let hit = VTKRetinaGeometry.cropHandleIndex(atX: hx, y: hy, handles: handles, tolerance: tolerance)
        precondition(hit == handle, "Handle \(handle) must be selectable at \(scale)x")
        let dragged = VTKRetinaGeometry.cropHandleIndex(atX: hx + 6 * scale, y: hy,
                                                        handles: handles, tolerance: tolerance)
        precondition(dragged == handle, "Handle \(handle) must stay selectable while dragging at \(scale)x")
        if scale > 1 {
            let pointSpaceMiss = VTKRetinaGeometry.cropHandleIndex(
                atX: hx / scale, y: hy / scale, handles: handles, tolerance: 8)
            precondition(pointSpaceMiss < 0,
                         "A 1x click on a 2x handle display position must miss")
        }
    }

    let moved = VTKRetinaGeometry.movedVolumeBounds(
        movingHandle: 1, displayFromX: handles[2].doubleValue, fromY: handles[3].doubleValue,
        toX: handles[2].doubleValue + 20 * scale, toY: handles[3].doubleValue,
        minX: volume.minX, minY: volume.minY, minZ: volume.minZ,
        maxX: volume.maxX, maxY: volume.maxY, maxZ: volume.maxZ,
        displayWidth: displaySize.width, displayHeight: displaySize.height)
    precondition(moved.count == 6)
    precondition(abs(moved[0].doubleValue - volume.minX) < 1e-8)
    precondition(moved[3].doubleValue > volume.maxX)

    let followed = VTKRetinaGeometry.placedBox(
        followingMinX: volume.minX + 5, minY: volume.minY, minZ: volume.minZ,
        maxX: volume.maxX + 5, maxY: volume.maxY, maxZ: volume.maxZ)
    precondition(abs(followed[0].doubleValue - (volume.minX + 5)) < 1e-8)
    precondition(abs(followed[3].doubleValue - (volume.maxX + 5)) < 1e-8)
}

precondition(VTKRetinaGeometry.cropBoxEnabled(afterToggle: false))
precondition(!VTKRetinaGeometry.cropBoxEnabled(afterToggle: true))
print("PASS: VTK display pixels coincide at 1x/2x; scissors reach four quadrants; seven crop handles select and drag; box follows volume; enabled state toggles")
'''

with tempfile.TemporaryDirectory(prefix='horos-vtk-retina-') as d:
    p = Path(d)
    (p / 'main.swift').write_text(code)
    subprocess.run([
        'xcrun', 'swiftc',
        str(root / 'Horos/Sources/VRInteractionGeometry.swift'),
        str(root / 'Horos/Sources/VTKRetinaGeometry.swift'),
        str(p / 'main.swift'),
        '-o', str(p / 'test'),
    ], check=True)
    subprocess.run([str(p / 'test')], check=True)
