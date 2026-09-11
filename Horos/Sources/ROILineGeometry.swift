import Foundation
import AppKit
import simd

/// Perpendicular, parallel and midpoint of a line ROI in physical millimetres.
/// Pixel-space 90° is not physical 90° when spacing is anisotropic.
@objc(HorosROILineConstruction)
public final class ROILineConstruction: NSObject {
    @objc public let midpoint: NSPoint
    @objc public let parallelA: NSPoint
    @objc public let parallelB: NSPoint
    @objc public let perpendicularA: NSPoint
    @objc public let perpendicularB: NSPoint

    @objc public init(midpoint: NSPoint, parallelA: NSPoint, parallelB: NSPoint,
                      perpendicularA: NSPoint, perpendicularB: NSPoint) {
        self.midpoint = midpoint
        self.parallelA = parallelA
        self.parallelB = parallelB
        self.perpendicularA = perpendicularA
        self.perpendicularB = perpendicularB
    }
}

@objc(HorosROILineGeometry)
public final class ROILineGeometry: NSObject {
    /// Zero or non-finite spacing is treated as 1 mm/pixel, matching ROI length/angle.
    @objc(constructionFromLineA:b:spacingX:spacingY:)
    public static func construction(from a: NSPoint, b: NSPoint,
                                    spacingX: CGFloat, spacingY: CGFloat) -> ROILineConstruction? {
        guard [a.x, a.y, b.x, b.y, spacingX, spacingY].allSatisfy({ $0.isFinite }) else { return nil }
        let sx = resolvedSpacing(spacingX)
        let sy = resolvedSpacing(spacingY)
        let aPhys = physicalPoint(from: a, spacingX: sx, spacingY: sy)
        let bPhys = physicalPoint(from: b, spacingX: sx, spacingY: sy)
        let direction = SIMD2(Double(bPhys.x - aPhys.x), Double(bPhys.y - aPhys.y))
        let length = simd_length(direction)
        guard length > 0, length.isFinite else { return nil }
        let midPhys = NSPoint(x: (aPhys.x + bPhys.x) / 2, y: (aPhys.y + bPhys.y) / 2)
        let perp = SIMD2(-direction.y, direction.x)
        let offset = perp * (length / simd_length(perp))
        guard offset.x.isFinite, offset.y.isFinite else { return nil }
        let half = offset / 2
        return ROILineConstruction(
            midpoint: pixelPoint(from: midPhys, spacingX: sx, spacingY: sy),
            parallelA: pixelPoint(from: NSPoint(x: aPhys.x + CGFloat(offset.x),
                                                y: aPhys.y + CGFloat(offset.y)),
                                  spacingX: sx, spacingY: sy),
            parallelB: pixelPoint(from: NSPoint(x: bPhys.x + CGFloat(offset.x),
                                                y: bPhys.y + CGFloat(offset.y)),
                                  spacingX: sx, spacingY: sy),
            perpendicularA: pixelPoint(from: NSPoint(x: midPhys.x - CGFloat(half.x),
                                                     y: midPhys.y - CGFloat(half.y)),
                                       spacingX: sx, spacingY: sy),
            perpendicularB: pixelPoint(from: NSPoint(x: midPhys.x + CGFloat(half.x),
                                                     y: midPhys.y + CGFloat(half.y)),
                                       spacingX: sx, spacingY: sy)
        )
    }

    @objc(physicalPointFromPixel:spacingX:spacingY:)
    public static func physicalPoint(from pixel: NSPoint, spacingX: CGFloat, spacingY: CGFloat) -> NSPoint {
        NSPoint(x: pixel.x * resolvedSpacing(spacingX), y: pixel.y * resolvedSpacing(spacingY))
    }

    @objc(pixelPointFromPhysical:spacingX:spacingY:)
    public static func pixelPoint(from physical: NSPoint, spacingX: CGFloat, spacingY: CGFloat) -> NSPoint {
        NSPoint(x: physical.x / resolvedSpacing(spacingX), y: physical.y / resolvedSpacing(spacingY))
    }

    /// Physical-space angle in degrees. The existing tAngle tool uses the same spacing rule.
    @objc(physicalAngleDegreesAt:armA:armB:spacingX:spacingY:)
    public static func physicalAngleDegrees(at vertex: NSPoint, armA: NSPoint, armB: NSPoint,
                                            spacingX: CGFloat, spacingY: CGFloat) -> Double {
        let sx = resolvedSpacing(spacingX)
        let sy = resolvedSpacing(spacingY)
        let origin = physicalPoint(from: vertex, spacingX: sx, spacingY: sy)
        let a = physicalPoint(from: armA, spacingX: sx, spacingY: sy)
        let b = physicalPoint(from: armB, spacingX: sx, spacingY: sy)
        return VRMeasurementGeometry.angleDegrees(
            atX: Double(origin.x), y: Double(origin.y), z: 0,
            armAX: Double(a.x), armAY: Double(a.y), armAZ: 0,
            armBX: Double(b.x), armBY: Double(b.y), armBZ: 0)
    }

    @objc(physicalDotProductFrom:to:otherFrom:otherTo:spacingX:spacingY:)
    public static func physicalDotProduct(from a0: NSPoint, to a1: NSPoint,
                                          otherFrom b0: NSPoint, otherTo b1: NSPoint,
                                          spacingX: CGFloat, spacingY: CGFloat) -> Double {
        let sx = resolvedSpacing(spacingX)
        let sy = resolvedSpacing(spacingY)
        let a = SIMD2(Double((a1.x - a0.x) * sx), Double((a1.y - a0.y) * sy))
        let b = SIMD2(Double((b1.x - b0.x) * sx), Double((b1.y - b0.y) * sy))
        return simd_dot(a, b)
    }

    private static func resolvedSpacing(_ value: CGFloat) -> CGFloat {
        value.isFinite && value != 0 ? value : 1
    }
}
