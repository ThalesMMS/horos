import AppKit

/// VTK display space is the view's backing pixels. AppKit frames stay in points.
@objc(HorosVTKRetinaGeometry)
public final class VTKRetinaGeometry: NSObject {
    private static let shear: CGFloat = 0.25

    @objc(displaySizeOfView:)
    public static func displaySize(of view: NSView) -> NSSize {
        let rect = view.convertToBacking(view.bounds)
        return NSSize(width: abs(rect.size.width), height: abs(rect.size.height))
    }

    @objc(displayScaleOfView:)
    public static func displayScale(of view: NSView) -> CGFloat {
        let width = view.bounds.size.width
        let displayWidth = displaySize(of: view).width
        guard width.isFinite, width > 0, displayWidth.isFinite, displayWidth > 0 else { return 1 }
        return displayWidth / width
    }

    @objc(displayPointFromWindowPoint:inView:)
    public static func displayPoint(fromWindowPoint windowPoint: NSPoint, in view: NSView) -> NSPoint {
        VRInteractionGeometry.backingPoint(windowPoint, in: view)
    }

    @objc(resizeHandleDisplayThresholdForPointThreshold:scale:)
    public static func resizeHandleDisplayThreshold(pointThreshold: CGFloat, scale: CGFloat) -> CGFloat {
        scaledThreshold(pointThreshold, scale: scale)
    }

    @objc(scissorsDragThresholdForPointThreshold:scale:)
    public static func scissorsDragThreshold(pointThreshold: CGFloat, scale: CGFloat) -> CGFloat {
        scaledThreshold(pointThreshold, scale: scale)
    }

    @objc(cropHandleDisplayToleranceForPointTolerance:scale:)
    public static func cropHandleDisplayTolerance(pointTolerance: CGFloat, scale: CGFloat) -> CGFloat {
        scaledThreshold(pointTolerance, scale: scale)
    }

    @objc(isViewportResizeHandleAtX:y:threshold:)
    public static func isViewportResizeHandle(x: CGFloat, y: CGFloat, threshold: CGFloat) -> Bool {
        guard [x, y, threshold].allSatisfy({ $0.isFinite }), threshold > 0 else { return false }
        return x >= 0 && y >= 0 && x < threshold && y < threshold
    }

    @objc(scissorsOverlayForDisplay:)
    public static func scissorsOverlay(forDisplay display: NSPoint) -> NSPoint {
        display
    }

    @objc(windowCenterOffsetForDisplay:displaySize:)
    public static func windowCenterOffset(forDisplay display: NSPoint, displaySize: NSSize) -> NSPoint {
        guard [display.x, display.y, displaySize.width, displaySize.height].allSatisfy({ $0.isFinite }),
              displaySize.width > 0, displaySize.height > 0 else { return .zero }
        return NSPoint(x: -(display.x - displaySize.width / 2),
                       y: -(display.y - displaySize.height / 2))
    }

    @objc(quadrantOfDisplayX:y:width:height:)
    public static func quadrant(ofDisplayX x: CGFloat, y: CGFloat, width: CGFloat, height: CGFloat) -> Int {
        guard [x, y, width, height].allSatisfy({ $0.isFinite }), width > 0, height > 0,
              x >= 0, y >= 0, x <= width, y <= height else { return -1 }
        let east = x >= width / 2
        let north = y >= height / 2
        return (north ? 2 : 0) + (east ? 1 : 0)
    }

    @objc(projectedCropHandlesMinX:minY:minZ:maxX:maxY:maxZ:displayWidth:displayHeight:)
    public static func projectedCropHandles(minX: Double, minY: Double, minZ: Double,
                                            maxX: Double, maxY: Double, maxZ: Double,
                                            displayWidth: CGFloat, displayHeight: CGFloat) -> [NSNumber] {
        guard let box = box(minX: minX, minY: minY, minZ: minZ, maxX: maxX, maxY: maxY, maxZ: maxZ),
              displayWidth.isFinite, displayHeight.isFinite, displayWidth > 0, displayHeight > 0 else { return [] }
        return worldHandles(in: box).flatMap { world in
            let point = project(world, box: box, displayWidth: displayWidth, displayHeight: displayHeight)
            return [NSNumber(value: Double(point.x)), NSNumber(value: Double(point.y))]
        }
    }

    @objc(cropHandleIndexAtX:y:handles:tolerance:)
    public static func cropHandleIndex(atX x: CGFloat, y: CGFloat, handles: [NSNumber], tolerance: CGFloat) -> Int {
        guard [x, y, tolerance].allSatisfy({ $0.isFinite }), tolerance > 0, handles.count == 14,
              handles.allSatisfy({ $0.doubleValue.isFinite }) else { return -1 }
        var best = -1
        var bestDistance = Double.infinity
        for handle in 0..<7 {
            let dx = x - CGFloat(handles[handle * 2].doubleValue)
            let dy = y - CGFloat(handles[handle * 2 + 1].doubleValue)
            let distance = hypot(dx, dy)
            if distance <= tolerance, Double(distance) < bestDistance {
                bestDistance = Double(distance)
                best = handle
            }
        }
        return best
    }

    @objc(movedVolumeBoundsMovingHandle:displayFromX:fromY:toX:toY:minX:minY:minZ:maxX:maxY:maxZ:displayWidth:displayHeight:)
    public static func movedVolumeBounds(movingHandle handle: Int,
                                         displayFromX fromX: CGFloat, fromY: CGFloat,
                                         toX: CGFloat, toY: CGFloat,
                                         minX: Double, minY: Double, minZ: Double,
                                         maxX: Double, maxY: Double, maxZ: Double,
                                         displayWidth: CGFloat, displayHeight: CGFloat) -> [NSNumber] {
        guard let box = box(minX: minX, minY: minY, minZ: minZ, maxX: maxX, maxY: maxY, maxZ: maxZ),
              (0...6).contains(handle),
              [fromX, fromY, toX, toY, displayWidth, displayHeight].allSatisfy({ $0.isFinite }),
              displayWidth > 0, displayHeight > 0 else { return [] }
        let worldDX = worldSpan(box.maxX - box.minX, displayDelta: toX - fromX, displayLength: displayWidth)
        let worldDY = worldSpan(box.maxY - box.minY, displayDelta: toY - fromY, displayLength: displayHeight)
        var next = box
        switch handle {
        case 0: next.minX += worldDX
        case 1: next.maxX += worldDX
        case 2: next.minY += worldDY
        case 3: next.maxY += worldDY
        case 4: next.minZ += worldDX
        case 5: next.maxZ += worldDX
        default:
            next.minX += worldDX; next.maxX += worldDX
            next.minY += worldDY; next.maxY += worldDY
        }
        guard next.minX < next.maxX, next.minY < next.maxY, next.minZ < next.maxZ else { return numbers(box) }
        return numbers(next)
    }

    @objc(placedBoxFollowingMinX:minY:minZ:maxX:maxY:maxZ:)
    public static func placedBox(followingMinX minX: Double, minY: Double, minZ: Double,
                                 maxX: Double, maxY: Double, maxZ: Double) -> [NSNumber] {
        guard let box = box(minX: minX, minY: minY, minZ: minZ, maxX: maxX, maxY: maxY, maxZ: maxZ) else { return [] }
        return numbers(box)
    }

    @objc(cropBoxEnabledAfterToggle:)
    public static func cropBoxEnabled(afterToggle currentlyEnabled: Bool) -> Bool {
        !currentlyEnabled
    }

    private struct Box {
        var minX, minY, minZ, maxX, maxY, maxZ: Double
    }

    private static func scaledThreshold(_ points: CGFloat, scale: CGFloat) -> CGFloat {
        guard points.isFinite, scale.isFinite, points > 0, scale > 0 else { return 0 }
        return points * scale
    }

    private static func box(minX: Double, minY: Double, minZ: Double,
                            maxX: Double, maxY: Double, maxZ: Double) -> Box? {
        let values = [minX, minY, minZ, maxX, maxY, maxZ]
        guard values.allSatisfy({ $0.isFinite }), minX < maxX, minY < maxY, minZ < maxZ else { return nil }
        return Box(minX: minX, minY: minY, minZ: minZ, maxX: maxX, maxY: maxY, maxZ: maxZ)
    }

    private static func numbers(_ box: Box) -> [NSNumber] {
        [box.minX, box.minY, box.minZ, box.maxX, box.maxY, box.maxZ].map(NSNumber.init(value:))
    }

    private static func worldHandles(in box: Box) -> [(Double, Double, Double)] {
        let midX = (box.minX + box.maxX) / 2
        let midY = (box.minY + box.maxY) / 2
        let midZ = (box.minZ + box.maxZ) / 2
        return [
            (box.minX, midY, midZ),
            (box.maxX, midY, midZ),
            (midX, box.minY, midZ),
            (midX, box.maxY, midZ),
            (midX, midY, box.minZ),
            (midX, midY, box.maxZ),
            (midX, midY, midZ),
        ]
    }

    private static func project(_ world: (Double, Double, Double), box: Box,
                                displayWidth: CGFloat, displayHeight: CGFloat) -> NSPoint {
        let nx = CGFloat((world.0 - box.minX) / (box.maxX - box.minX))
        let ny = CGFloat((world.1 - box.minY) / (box.maxY - box.minY))
        let nz = CGFloat((world.2 - box.minZ) / (box.maxZ - box.minZ))
        return NSPoint(x: (nx + shear * nz) / (1 + shear) * displayWidth,
                       y: (ny + shear * nz) / (1 + shear) * displayHeight)
    }

    private static func worldSpan(_ span: Double, displayDelta: CGFloat, displayLength: CGFloat) -> Double {
        Double(displayDelta / displayLength * (1 + shear)) * span
    }
}
