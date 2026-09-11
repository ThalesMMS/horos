import Foundation
import simd

/// One occupied ROI plane. `areaCm2` is the same unit as `-[ROI roiArea]`.
/// `spacingBetweenSlicesMm` is accepted so callers can pass the DICOM tag; the
/// volume method never reads it. Through-plane position is ImagePositionPatient
/// dotted with the unit normal.
@objc(HorosROIVolumeSlice)
public final class ROIVolumeSlice: NSObject {
    @objc public let areaCm2: Double
    @objc public let originX: Double
    @objc public let originY: Double
    @objc public let originZ: Double
    @objc public let normalX: Double
    @objc public let normalY: Double
    @objc public let normalZ: Double
    @objc public let componentCount: Int
    @objc public let maskPixelCount: Int
    @objc public let pixelAreaMm2: Double
    @objc public let spacingBetweenSlicesMm: Double

    @objc public init(areaCm2: Double,
                      originX: Double, originY: Double, originZ: Double,
                      normalX: Double, normalY: Double, normalZ: Double,
                      componentCount: Int,
                      maskPixelCount: Int,
                      pixelAreaMm2: Double,
                      spacingBetweenSlicesMm: Double) {
        self.areaCm2 = areaCm2
        self.originX = originX
        self.originY = originY
        self.originZ = originZ
        self.normalX = normalX
        self.normalY = normalY
        self.normalZ = normalZ
        self.componentCount = componentCount
        self.maskPixelCount = maskPixelCount
        self.pixelAreaMm2 = pixelAreaMm2
        self.spacingBetweenSlicesMm = spacingBetweenSlicesMm
    }

    var values: [Double] {
        [areaCm2, originX, originY, originZ, normalX, normalY, normalZ,
         pixelAreaMm2, spacingBetweenSlicesMm]
    }

    var origin: SIMD3<Double> { SIMD3(originX, originY, originZ) }
    var normal: SIMD3<Double> { SIMD3(normalX, normalY, normalZ) }
}

/// Trapezoidal volume from occupied ROI planes in patient millimetres.
@objc(HorosROIVolumeResult)
public final class ROIVolumeResult: NSObject {
    @objc public let volumeCm3: Double
    @objc public let method: String
    @objc public let unit: String
    @objc public let occupiedPlaneCount: Int
    @objc public let componentCount: Int
    @objc public let gapCount: Int
    @objc public let interpolated: Bool
    @objc public let maskConsistent: Bool
    @objc public let meshPointCount: Int
    @objc public let usedImagePositionPatient: Bool
    @objc public let usedSpacingBetweenSlices: Bool
    @objc public let summary: String

    @objc public init(volumeCm3: Double, method: String, unit: String,
                      occupiedPlaneCount: Int, componentCount: Int,
                      gapCount: Int, interpolated: Bool,
                      maskConsistent: Bool, meshPointCount: Int,
                      usedImagePositionPatient: Bool,
                      usedSpacingBetweenSlices: Bool,
                      summary: String) {
        self.volumeCm3 = volumeCm3
        self.method = method
        self.unit = unit
        self.occupiedPlaneCount = occupiedPlaneCount
        self.componentCount = componentCount
        self.gapCount = gapCount
        self.interpolated = interpolated
        self.maskConsistent = maskConsistent
        self.meshPointCount = meshPointCount
        self.usedImagePositionPatient = usedImagePositionPatient
        self.usedSpacingBetweenSlices = usedSpacingBetweenSlices
        self.summary = summary
    }
}

/// Documented ROI volume: host trapezoid (`Δs/10 × (Aᵢ + Aᵢ₊₁)/2`) with `Δs`
/// taken from ImagePositionPatient along the slice normal. Same unit conversion
/// as `ViewerController computeVolume` (mm → cm, area already in cm²).
///
/// Missing series slices are not filled unless `interpolateMissing` is true
/// (the host's explicit `generateMissingROIs` path). Disconnected components
/// on one plane have their areas summed; contours are never unioned. Mesh
/// point counts are display-only and do not enter the formula.
@objc(HorosROIVolumeGeometry)
public final class ROIVolumeGeometry: NSObject {
    private static let planeToleranceMm = 1e-4

    @objc(volumeFromSlices:seriesOrigins:interpolateMissing:meshPointCount:)
    public static func volume(from slices: [ROIVolumeSlice],
                              seriesOrigins: [ROIPatientPoint]?,
                              interpolateMissing: Bool,
                              meshPointCount: Int) -> ROIVolumeResult? {
        guard !slices.isEmpty,
              slices.allSatisfy({ $0.values.allSatisfy(\.isFinite) && $0.areaCm2 > 0 && $0.componentCount > 0 })
        else { return nil }

        let normal = normalizedOrAxial(slices[0].normal)
        var planes: [Plane] = []
        for slice in slices {
            let s = simd_dot(slice.origin, normal)
            guard s.isFinite else { return nil }
            if let index = planes.firstIndex(where: { abs($0.s - s) <= planeToleranceMm }) {
                planes[index].area += slice.areaCm2
                planes[index].components += slice.componentCount
                planes[index].maskPixels += slice.maskPixelCount
                if planes[index].pixelArea == 0 { planes[index].pixelArea = slice.pixelAreaMm2 }
            } else {
                planes.append(Plane(s: s, area: slice.areaCm2, components: slice.componentCount,
                                    maskPixels: slice.maskPixelCount, pixelArea: slice.pixelAreaMm2))
            }
        }
        planes.sort { $0.s < $1.s }
        guard planes.count >= 2 else { return nil }

        let series = (seriesOrigins ?? []).compactMap { point -> Double? in
            let s = simd_dot(point.vector, normal)
            return s.isFinite ? s : nil
        }.sorted()

        var volume = 0.0
        var gapCount = 0
        var interpolated = false
        for index in 1..<planes.count {
            let previous = planes[index - 1]
            let current = planes[index]
            let delta = abs(current.s - previous.s)
            guard delta.isFinite else { return nil }
            let intervening = series.contains { position in
                let lo = min(previous.s, current.s) + planeToleranceMm
                let hi = max(previous.s, current.s) - planeToleranceMm
                return position > lo && position < hi
            }
            if intervening {
                gapCount += 1
                if !interpolateMissing { continue }
                interpolated = true
            }
            volume += (delta / 10) * (previous.area + current.area) / 2
        }
        guard volume.isFinite else { return nil }

        let maskConsistent = planes.allSatisfy(maskMatches)
        let components = planes.reduce(0) { $0 + $1.components }
        let summary = String(format: "%.4f cm3 physical-trapezoid (%d planes, %d gaps)",
                             abs(volume), planes.count, gapCount)
        return ROIVolumeResult(
            volumeCm3: abs(volume), method: "physical-trapezoid", unit: "cm3",
            occupiedPlaneCount: planes.count, componentCount: components,
            gapCount: gapCount, interpolated: interpolated,
            maskConsistent: maskConsistent, meshPointCount: meshPointCount,
            usedImagePositionPatient: true, usedSpacingBetweenSlices: false,
            summary: summary)
    }

    private static func maskMatches(_ plane: Plane) -> Bool {
        if plane.maskPixels == 0 && plane.pixelArea == 0 { return true }
        let expected = Double(plane.maskPixels) * plane.pixelArea / 100
        let scale = max(abs(plane.area), abs(expected), 1)
        return abs(plane.area - expected) <= 1e-6 * scale
    }

    private static func normalizedOrAxial(_ vector: SIMD3<Double>) -> SIMD3<Double> {
        let length = simd_length(vector)
        return length > 0 && length.isFinite ? vector / length : SIMD3(0, 0, 1)
    }
}

private struct Plane {
    var s: Double
    var area: Double
    var components: Int
    var maskPixels: Int
    var pixelArea: Double
}
