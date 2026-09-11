import Foundation
import simd

/// One 2D ROI point plus the DICOM slice that owns it.
@objc(HorosROISlicePoint)
public final class ROISlicePoint: NSObject {
    @objc public let pixelX: Double
    @objc public let pixelY: Double
    @objc public let originX: Double
    @objc public let originY: Double
    @objc public let originZ: Double
    @objc public let rowX: Double
    @objc public let rowY: Double
    @objc public let rowZ: Double
    @objc public let colX: Double
    @objc public let colY: Double
    @objc public let colZ: Double
    @objc public let normalX: Double
    @objc public let normalY: Double
    @objc public let normalZ: Double
    @objc public let spacingX: Double
    @objc public let spacingY: Double
    @objc public let pixelCenter: Bool

    @objc public init(pixelX: Double, pixelY: Double,
                      originX: Double, originY: Double, originZ: Double,
                      rowX: Double, rowY: Double, rowZ: Double,
                      colX: Double, colY: Double, colZ: Double,
                      normalX: Double, normalY: Double, normalZ: Double,
                      spacingX: Double, spacingY: Double,
                      pixelCenter: Bool) {
        self.pixelX = pixelX
        self.pixelY = pixelY
        self.originX = originX
        self.originY = originY
        self.originZ = originZ
        self.rowX = rowX
        self.rowY = rowY
        self.rowZ = rowZ
        self.colX = colX
        self.colY = colY
        self.colZ = colZ
        self.normalX = normalX
        self.normalY = normalY
        self.normalZ = normalZ
        self.spacingX = spacingX
        self.spacingY = spacingY
        self.pixelCenter = pixelCenter
    }

    var values: [Double] {
        [pixelX, pixelY, originX, originY, originZ,
         rowX, rowY, rowZ, colX, colY, colZ,
         normalX, normalY, normalZ, spacingX, spacingY]
    }
}

@objc(HorosROIPatientPoint)
public final class ROIPatientPoint: NSObject {
    @objc public let x: Double
    @objc public let y: Double
    @objc public let z: Double

    @objc public init(x: Double, y: Double, z: Double) {
        self.x = x
        self.y = y
        self.z = z
    }

    var vector: SIMD3<Double> { SIMD3(x, y, z) }
}

/// Pixel coordinates of a patient point on a slice, plus the through-plane millimetre offset.
@objc(HorosROIPlaneProjection)
public final class ROIPlaneProjection: NSObject {
    @objc public let pixelX: Double
    @objc public let pixelY: Double
    @objc public let throughPlane: Double

    @objc public init(pixelX: Double, pixelY: Double, throughPlane: Double) {
        self.pixelX = pixelX
        self.pixelY = pixelY
        self.throughPlane = throughPlane
    }
}

/// Distances between two slice points in patient millimetres.
/// `projectedDistance` is the in-plane length on the first slice; `distance3D` keeps the through-plane offset.
@objc(HorosROIIntersliceMeasure)
public final class ROIIntersliceMeasure: NSObject {
    @objc public let firstX: Double
    @objc public let firstY: Double
    @objc public let firstZ: Double
    @objc public let secondX: Double
    @objc public let secondY: Double
    @objc public let secondZ: Double
    @objc public let distance3D: Double
    @objc public let projectedDistance: Double
    @objc public let throughPlaneOffset: Double
    @objc public let unit: String
    @objc public let orientation: String
    @objc public let slicesParallel: Bool
    @objc public let summary: String

    @objc public init(firstX: Double, firstY: Double, firstZ: Double,
                      secondX: Double, secondY: Double, secondZ: Double,
                      distance3D: Double, projectedDistance: Double,
                      throughPlaneOffset: Double, unit: String,
                      orientation: String, slicesParallel: Bool, summary: String) {
        self.firstX = firstX
        self.firstY = firstY
        self.firstZ = firstZ
        self.secondX = secondX
        self.secondY = secondY
        self.secondZ = secondZ
        self.distance3D = distance3D
        self.projectedDistance = projectedDistance
        self.throughPlaneOffset = throughPlaneOffset
        self.unit = unit
        self.orientation = orientation
        self.slicesParallel = slicesParallel
        self.summary = summary
    }
}

@objc(HorosROIIntersliceGeometry)
public final class ROIIntersliceGeometry: NSObject {
    /// Same conversion as `DCMPix convertPixDoubleX:pixY:toDICOMCoords:pixelCenter:`.
    /// Zero or non-finite spacing is 1 mm/pixel, matching `ROILineGeometry`.
    /// Inverse of `patientPoint(from:)` on the slice plane. `throughPlane` is millimetres along the slice normal.
    @objc(projectionOf:onto:)
    public static func projection(of patient: ROIPatientPoint, onto slice: ROISlicePoint) -> ROIPlaneProjection? {
        guard patient.vector.allFinite, slice.values.allSatisfy(\.isFinite) else { return nil }
        let origin = SIMD3(slice.originX, slice.originY, slice.originZ)
        let row = SIMD3(slice.rowX, slice.rowY, slice.rowZ)
        let col = SIMD3(slice.colX, slice.colY, slice.colZ)
        guard simd_length(row) > 0, simd_length(col) > 0 else { return nil }
        let delta = patient.vector - origin
        let sx = resolvedSpacing(slice.spacingX)
        let sy = resolvedSpacing(slice.spacingY)
        var x = simd_dot(delta, row) / sx
        var y = simd_dot(delta, col) / sy
        if slice.pixelCenter {
            x += 0.5
            y += 0.5
        }
        let through = simd_dot(delta, normalizedOrAxial(planeNormal(for: slice)))
        guard x.isFinite, y.isFinite, through.isFinite else { return nil }
        return ROIPlaneProjection(pixelX: x, pixelY: y, throughPlane: through)
    }

    @objc(patientPointFrom:)
    public static func patientPoint(from point: ROISlicePoint) -> ROIPatientPoint {
        var x = point.pixelX
        var y = point.pixelY
        if point.pixelCenter {
            x -= 0.5
            y -= 0.5
        }
        let sx = resolvedSpacing(point.spacingX)
        let sy = resolvedSpacing(point.spacingY)
        if point.normalX != 0 || point.normalY != 0 || point.normalZ != 0 {
            return ROIPatientPoint(
                x: point.originX + y * point.colX * sy + x * point.rowX * sx,
                y: point.originY + y * point.colY * sy + x * point.rowY * sx,
                z: point.originZ + y * point.colZ * sy + x * point.rowZ * sx)
        }
        return ROIPatientPoint(x: point.originX + x * sx,
                               y: point.originY + y * sy,
                               z: point.originZ)
    }

    @objc(measureFrom:to:)
    public static func measure(from first: ROISlicePoint, to second: ROISlicePoint) -> ROIIntersliceMeasure? {
        guard first.values.allSatisfy(\.isFinite), second.values.allSatisfy(\.isFinite) else { return nil }
        let a = patientPoint(from: first).vector
        let b = patientPoint(from: second).vector
        let normal = planeNormal(for: first)
        return measure(from: a, to: b, planeNormal: normal, otherNormal: planeNormal(for: second))
    }

    @objc(measureFromX:y:z:toX:y:z:planeNormalX:planeNormalY:planeNormalZ:)
    public static func measure(fromX: Double, y firstY: Double, z firstZ: Double,
                               toX: Double, y secondY: Double, z secondZ: Double,
                               planeNormalX: Double, planeNormalY: Double, planeNormalZ: Double) -> ROIIntersliceMeasure? {
        measure(from: SIMD3(fromX, firstY, firstZ),
                to: SIMD3(toX, secondY, secondZ),
                planeNormal: SIMD3(planeNormalX, planeNormalY, planeNormalZ),
                otherNormal: SIMD3(planeNormalX, planeNormalY, planeNormalZ))
    }

    private static func measure(from a: SIMD3<Double>, to b: SIMD3<Double>,
                                planeNormal: SIMD3<Double>,
                                otherNormal: SIMD3<Double>) -> ROIIntersliceMeasure? {
        let values = [a.x, a.y, a.z, b.x, b.y, b.z, planeNormal.x, planeNormal.y, planeNormal.z]
        guard values.allSatisfy(\.isFinite) else { return nil }
        let delta = b - a
        let distance3D = simd_length(delta)
        guard distance3D > 0, distance3D.isFinite else { return nil }
        let normal = normalizedOrAxial(planeNormal)
        let through = simd_dot(delta, normal)
        let projected = delta - normal * through
        let projectedDistance = simd_length(projected)
        guard projectedDistance.isFinite, through.isFinite else { return nil }
        let orientation = orientationName(normal)
        let parallel = otherNormal.allFinite && abs(abs(simd_dot(normal, normalizedOrAxial(otherNormal))) - 1) < 1e-6
        let summary = String(format: "%.2f mm proj / %.2f mm 3D (%@)",
                             projectedDistance, distance3D, orientation)
        return ROIIntersliceMeasure(
            firstX: a.x, firstY: a.y, firstZ: a.z,
            secondX: b.x, secondY: b.y, secondZ: b.z,
            distance3D: distance3D, projectedDistance: projectedDistance,
            throughPlaneOffset: through, unit: "mm",
            orientation: orientation, slicesParallel: parallel, summary: summary)
    }

    private static func planeNormal(for point: ROISlicePoint) -> SIMD3<Double> {
        let stored = SIMD3(point.normalX, point.normalY, point.normalZ)
        if simd_length(stored) > 0 { return stored }
        let crossed = simd_cross(SIMD3(point.rowX, point.rowY, point.rowZ),
                                 SIMD3(point.colX, point.colY, point.colZ))
        if simd_length(crossed) > 0 { return crossed }
        return SIMD3(0, 0, 1)
    }

    private static func normalizedOrAxial(_ vector: SIMD3<Double>) -> SIMD3<Double> {
        let length = simd_length(vector)
        return length > 0 && length.isFinite ? vector / length : SIMD3(0, 0, 1)
    }

    /// Same axis rule as `ViewerController` orientationVector: the largest |normal| component.
    private static func orientationName(_ normal: SIMD3<Double>) -> String {
        let ax = abs(normal.x), ay = abs(normal.y), az = abs(normal.z)
        if ax >= ay && ax >= az { return ax >= 0.9 ? "sagittal" : "oblique" }
        if ay >= ax && ay >= az { return ay >= 0.9 ? "coronal" : "oblique" }
        return az >= 0.9 ? "axial" : "oblique"
    }

    private static func resolvedSpacing(_ value: Double) -> Double {
        value.isFinite && value != 0 ? value : 1
    }
}

private extension SIMD3 where Scalar == Double {
    var allFinite: Bool { x.isFinite && y.isFinite && z.isFinite }
}
