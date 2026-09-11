import AppKit
import simd

/// Coordinates for projected length overlays in a parallel VTK viewport.
@objc(HorosVRMeasurementGeometry)
public final class VRMeasurementGeometry: NSObject {
    /// Return the nearest editable handle, or -1 for a new measurement.
    /// All inputs use the same coordinate space; callers scale the hit radius.
    @objc(editableEndpointAt:first:second:tolerance:)
    public static func editableEndpoint(at point: NSPoint, first: NSPoint, second: NSPoint, tolerance: CGFloat) -> Int {
        guard [point.x, point.y, first.x, first.y, second.x, second.y, tolerance].allSatisfy({ $0.isFinite }),
              tolerance > 0 else { return -1 }
        let firstDistance = hypot(point.x - first.x, point.y - first.y)
        let secondDistance = hypot(point.x - second.x, point.y - second.y)
        guard min(firstDistance, secondDistance) <= tolerance else { return -1 }
        return firstDistance <= secondDistance ? 0 : 1
    }

    /// VTK's parallel camera preserves its vertical world extent on resize.
    /// Both sizes and the point must use backing pixels, not AppKit frame points.
    @objc(resizedPoint:fromSize:toSize:cameraZoom:)
    public static func resizedPoint(_ point: NSPoint, from oldSize: NSSize, to newSize: NSSize, cameraZoom: CGFloat = 1) -> NSPoint {
        guard [point.x, point.y, oldSize.width, oldSize.height,
               newSize.width, newSize.height, cameraZoom].allSatisfy({ $0.isFinite }),
              oldSize.width > 0, oldSize.height > 0,
              newSize.width > 0, newSize.height > 0, cameraZoom > 0 else { return point }
        let ratio = newSize.height / oldSize.height * cameraZoom
        let result = NSPoint(x: (point.x - oldSize.width / 2) * ratio + newSize.width / 2,
                             y: (point.y - oldSize.height / 2) * ratio + newSize.height / 2)
        return result.x.isFinite && result.y.isFinite ? result : point
    }

    /// Patient-space angle in degrees at the vertex. Camera pose is irrelevant.
    /// Degenerate or non-finite arms return NaN.
    @objc(angleDegreesAtX:y:z:armAX:armAY:armAZ:armBX:armBY:armBZ:)
    public static func angleDegrees(atX vx: Double, y vy: Double, z vz: Double,
                                    armAX ax: Double, armAY ay: Double, armAZ az: Double,
                                    armBX bx: Double, armBY by: Double, armBZ bz: Double) -> Double {
        let values = [vx, vy, vz, ax, ay, az, bx, by, bz]
        guard values.allSatisfy({ $0.isFinite }) else { return .nan }
        let vertex = SIMD3(vx, vy, vz)
        let armA = SIMD3(ax, ay, az) - vertex
        let armB = SIMD3(bx, by, bz) - vertex
        let lengthA = simd_length(armA)
        let lengthB = simd_length(armB)
        guard lengthA > 0, lengthB > 0 else { return .nan }
        let cosine = min(1, max(-1, simd_dot(armA, armB) / (lengthA * lengthB)))
        return acos(cosine) * 180 / .pi
    }
}
