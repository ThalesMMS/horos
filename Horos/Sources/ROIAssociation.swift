import Foundation
import CoreGraphics
import simd

@objc(HorosROIAssociationStatus)
public enum ROIAssociationStatus: Int {
    case mapped = 0
    case ambiguous
    case insufficient
    case missingReference
    case geometryMismatch
    case orientationIncompatible
    case transformFailed
}

@objc(HorosROIAssociationImage)
@objcMembers public final class ROIAssociationImage: NSObject {
    public var index: Int = 0
    public var temporalIndex: Int = 0
    public var sopInstanceUID: String?
    public var frame: Int = 0
    public var seriesInstanceUID: String?
    public var frameOfReferenceUID: String?
    public var rows: Int = 0
    public var columns: Int = 0
    public var pixelSpacingX: Double = 0
    public var pixelSpacingY: Double = 0
    public var imagePosition: [Double] = []
    public var imageOrientation: [Double] = []
    public var hasImageOrigin: Bool = false
    public var imageOriginX: Double = 0
    public var imageOriginY: Double = 0
}

@objc(HorosROIAssociationItem)
@objcMembers public final class ROIAssociationItem: NSObject {
    public var sourceIndex: Int = 0
    public var name: String = ""
    public var typeCode: Int = 0
    public var fileName: String?
    public var image: ROIAssociationImage = ROIAssociationImage()
    public var points: [[Double]] = []
    public var patientPoints: [[Double]] = []
    public var red: Double = 1
    public var green: Double = 0
    public var blue: Double = 0
    public var thickness: Double = 1
    public var opacity: Double = 1
    public var hasRect: Bool = false
    public var rect: NSRect = NSRect(x: 0, y: 0, width: 0, height: 0)
    public var isSpline: Bool = false
    public var groupID: Double = 0
    public var comments: String?
    public var brushWidth: Int = 0
    public var brushHeight: Int = 0
    public var brushOriginX: Int = 0
    public var brushOriginY: Int = 0
    public var brushMask: Data?
}

@objc(HorosROIAssociationBinding)
@objcMembers public final class ROIAssociationBinding: NSObject {
    public var sourceIndex: Int = 0
    public var targetIndex: Int = -1
    public var status: ROIAssociationStatus = .insufficient
    public var reason: String = ""
    public var points: [[Double]] = []
    public var reoriented: Bool = false
}

@objc(HorosROIAssociationPlan)
@objcMembers public final class ROIAssociationPlan: NSObject {
    public var bindings: [ROIAssociationBinding] = []

    public var canApply: Bool {
        !bindings.isEmpty && bindings.allSatisfy { $0.status == .mapped }
    }

    public var summary: String {
        let problems = bindings.filter { $0.status != .mapped }
        if problems.isEmpty {
            return "Matched \(bindings.count) ROI(s) by image identity."
        }
        let lines = problems.map { binding -> String in
            let label = binding.sourceIndex + 1
            return "ROI \(label): \(binding.reason)"
        }
        return lines.joined(separator: "\n")
    }

    public var error: NSError {
        let code = bindings.first(where: { $0.status != .mapped })?.status.rawValue ?? ROIAssociationStatus.insufficient.rawValue
        return NSError(domain: ROIAssociation.errorDomain, code: code,
                       userInfo: [NSLocalizedDescriptionKey: summary])
    }
}

/// Identity matching, archive origin fallback and patient-space reorientation
/// for ROI import (issue #231). Never binds by file name, file order or slice index.
@objc(HorosROIAssociation)
public final class ROIAssociation: NSObject {
    @objc public static let errorDomain = "org.horosproject.roi-association"
    @objc public static let positionToleranceMM = 0.05
    @objc public static let spacingTolerance = 0.001
    @objc public static let planeToleranceMM = 0.5
    @objc public static let orientationDotTolerance = 0.9

    @objc public static func targets(from series: ROIInterchangeSeries) -> [ROIAssociationImage] {
        series.images.map { associationImage(from: $0, series: series) }
    }

    @objc public static func items(from series: ROIInterchangeSeries) -> [ROIAssociationItem] {
        var result: [ROIAssociationItem] = []
        var index = 0
        for image in series.images {
            let identity = associationImage(from: image, series: series)
            for roi in image.rois {
                let item = ROIAssociationItem()
                item.sourceIndex = index
                item.name = roi.name
                item.typeCode = roi.typeCode
                item.image = copyImage(identity)
                item.points = roi.points.map { [Double($0.pointValue.x), Double($0.pointValue.y)] }
                item.patientPoints = roi.patientPoints
                item.red = roi.red
                item.green = roi.green
                item.blue = roi.blue
                item.thickness = roi.thickness
                item.opacity = roi.opacity
                item.hasRect = roi.hasRect
                item.rect = roi.rect
                item.isSpline = roi.isSpline
                item.groupID = roi.groupID
                item.comments = roi.comments
                item.brushWidth = roi.brushWidth
                item.brushHeight = roi.brushHeight
                item.brushOriginX = roi.brushOriginX
                item.brushOriginY = roi.brushOriginY
                item.brushMask = roi.brushMask
                result.append(item)
                index += 1
            }
        }
        return result
    }

    @objc public static func plan(sources: [ROIAssociationItem],
                                  targets: [ROIAssociationImage]) -> ROIAssociationPlan {
        let plan = ROIAssociationPlan()
        plan.bindings = sources.enumerated().map { offset, source in
            bind(source, sourceIndex: source.sourceIndex != 0 ? source.sourceIndex : offset, targets: targets)
        }
        return plan
    }

    @objc public static func plan(document: ROIInterchangeSeries,
                                  against target: ROIInterchangeSeries) -> ROIAssociationPlan {
        plan(sources: items(from: document), targets: targets(from: target))
    }

    private static func bind(_ source: ROIAssociationItem, sourceIndex: Int,
                             targets: [ROIAssociationImage]) -> ROIAssociationBinding {
        let binding = ROIAssociationBinding()
        binding.sourceIndex = sourceIndex
        binding.points = source.points

        if let key = sopKey(source.image) {
            let hits = targets.indices.filter { sopKey(targets[$0]) == key }
            if hits.count > 1 {
                return fail(binding, .ambiguous,
                            "SOP Instance UID \(key) is ambiguous: it matches \(hits.count) images; not applied by order or name.")
            }
            if hits.count == 1 {
                return finish(source, onto: hits[0], targets: targets, binding: binding)
            }
            if let reoriented = reorient(source, targets: targets, binding: binding,
                                         requireDifferentOrientation: true) {
                return reoriented
            }
            return fail(binding, .missingReference,
                        "SOP Instance UID \(source.image.sopInstanceUID ?? key) is not part of the open series.")
        }

        if let hits = ippMatches(source.image, targets: targets) {
            if hits.count > 1 {
                return fail(binding, .ambiguous,
                            "Image Position (Patient) matches \(hits.count) images; not applied by order or name.")
            }
            if hits.count == 1 {
                return finish(source, onto: hits[0], targets: targets, binding: binding)
            }
        }

        if source.image.hasImageOrigin {
            let hits = originMatches(source.image, targets: targets)
            if hits.count > 1 {
                return fail(binding, .ambiguous,
                            "Image origin matches \(hits.count) images; not applied by order or name.")
            }
            if hits.count == 1 {
                return finish(source, onto: hits[0], targets: targets, binding: binding)
            }
        }

        if let reoriented = reorient(source, targets: targets, binding: binding,
                                     requireDifferentOrientation: true) {
            return reoriented
        }

        if source.image.sopInstanceUID?.isEmpty == false {
            return fail(binding, .missingReference,
                        "SOP Instance UID \(source.image.sopInstanceUID ?? "") is not part of the open series.")
        }
        return fail(binding, .insufficient,
                    "ROI \"\(source.name)\" has no SOP/frame, Image Position or unique origin; not applied by name, file order or slice index.")
    }

    private static func finish(_ source: ROIAssociationItem, onto index: Int,
                               targets: [ROIAssociationImage],
                               binding: ROIAssociationBinding) -> ROIAssociationBinding {
        let target = targets[index]
        if orientationsAlign(source.image, target) {
            if let geometry = geometryProblem(source.image, target) {
                return fail(binding, .geometryMismatch, geometry)
            }
            binding.status = .mapped
            binding.targetIndex = index
            binding.points = source.points
            binding.reason = "Matched by image identity."
            return binding
        }
        if cannotReorient(source) {
            return fail(binding, .orientationIncompatible,
                        "ROI \"\(source.name)\" is a \(typeName(source.typeCode)) saved on a different orientation; brush/rect geometry is not resampled.")
        }
        guard let transformed = transformedPoints(source, onto: target) else {
            return fail(binding, .transformFailed,
                        "Could not reproject ROI \"\(source.name)\" onto the matched image.")
        }
            if transformed.through > planeToleranceMM {
            if let reoriented = reorient(source, targets: targets, binding: binding,
                                         requireDifferentOrientation: true) {
                return reoriented
            }
            return fail(binding, .orientationIncompatible,
                        String(format: "ROI \"%@\" does not lie on the open image plane (%.2f mm through-plane).",
                               source.name, transformed.through))
        }
        binding.status = .mapped
        binding.targetIndex = index
        binding.points = transformed.points
        binding.reoriented = true
        binding.reason = "Reprojected into the open orientation."
        return binding
    }

    private static func reorient(_ source: ROIAssociationItem,
                                 targets: [ROIAssociationImage],
                                 binding: ROIAssociationBinding,
                                 requireDifferentOrientation: Bool) -> ROIAssociationBinding? {
        guard canSearchPlanes(source) else { return nil }
        if cannotReorient(source) {
            return fail(binding, .orientationIncompatible,
                        "ROI \"\(source.name)\" is a \(typeName(source.typeCode)) saved on a different orientation; brush/rect geometry is not resampled.")
        }
        let frame = source.image.frameOfReferenceUID ?? ""
        var accepted: [(Int, [[Double]], Double)] = []
        var consideredDifferentOrientation = false
        for (index, target) in targets.enumerated() {
            guard let targetFrame = target.frameOfReferenceUID, !targetFrame.isEmpty, targetFrame == frame else { continue }
            guard target.temporalIndex == source.image.temporalIndex else { continue }
            if requireDifferentOrientation && orientationsAlign(source.image, target) { continue }
            consideredDifferentOrientation = true
            guard let transformed = transformedPoints(source, onto: target) else { continue }
            if transformed.through <= planeToleranceMM {
                accepted.append((index, transformed.points, transformed.through))
            }
        }
        if accepted.count > 1 {
            return fail(binding, .ambiguous,
                        "ROI \"\(source.name)\" lies on \(accepted.count) images after reorientation; not applied by order.")
        }
        if let only = accepted.first {
            binding.status = .mapped
            binding.targetIndex = only.0
            binding.points = only.1
            binding.reoriented = true
            binding.reason = "Reprojected into the open orientation."
            return binding
        }
        if consideredDifferentOrientation {
            return fail(binding, .orientationIncompatible,
                        "ROI \"\(source.name)\" has no matching image plane in the open orientation.")
        }
        return nil
    }

    private static func fail(_ binding: ROIAssociationBinding, _ status: ROIAssociationStatus,
                             _ reason: String) -> ROIAssociationBinding {
        binding.status = status
        binding.targetIndex = -1
        binding.reason = reason
        return binding
    }

    private static func sopKey(_ image: ROIAssociationImage) -> String? {
        guard let sop = image.sopInstanceUID, !sop.isEmpty else { return nil }
        return "\(sop)#\(image.frame)"
    }

    private static func ippMatches(_ source: ROIAssociationImage,
                                   targets: [ROIAssociationImage]) -> [Int]? {
        guard source.imagePosition.count == 3,
              let frame = source.frameOfReferenceUID, !frame.isEmpty else { return nil }
        var hits: [Int] = []
        for (index, target) in targets.enumerated() {
            guard let targetFrame = target.frameOfReferenceUID, targetFrame == frame, !targetFrame.isEmpty else { continue }
            guard target.temporalIndex == source.temporalIndex else { continue }
            guard target.imagePosition.count == 3 else { continue }
            if hypot3(target.imagePosition, source.imagePosition) <= positionToleranceMM {
                hits.append(index)
            }
        }
        return hits
    }

    private static func originMatches(_ source: ROIAssociationImage,
                                      targets: [ROIAssociationImage]) -> [Int] {
        var hits: [Int] = []
        for (index, target) in targets.enumerated() {
            guard target.hasImageOrigin, target.temporalIndex == source.temporalIndex else { continue }
            let dx = target.imageOriginX - source.imageOriginX
            let dy = target.imageOriginY - source.imageOriginY
            if (dx * dx + dy * dy).squareRoot() <= positionToleranceMM {
                hits.append(index)
            }
        }
        return hits
    }

    private static func orientationsAlign(_ source: ROIAssociationImage, _ target: ROIAssociationImage) -> Bool {
        guard let sn = normal(of: source), let tn = normal(of: target) else { return true }
        return abs(simd_dot(sn, tn)) >= orientationDotTolerance
    }

    private static func geometryProblem(_ source: ROIAssociationImage, _ target: ROIAssociationImage) -> String? {
        if source.rows > 0, source.columns > 0,
           (source.rows != target.rows || source.columns != target.columns) {
            return "The document expects \(source.columns)x\(source.rows) pixels but the open image is \(target.columns)x\(target.rows)."
        }
        if source.pixelSpacingX > 0, source.pixelSpacingY > 0,
           target.pixelSpacingX > 0, target.pixelSpacingY > 0 {
            let sx = relativeDifference(source.pixelSpacingX, target.pixelSpacingX)
            let sy = relativeDifference(source.pixelSpacingY, target.pixelSpacingY)
            if sx > spacingTolerance || sy > spacingTolerance {
                return String(format: "The document expects a pixel spacing of %.4f x %.4f mm but the open image has %.4f x %.4f mm.",
                              source.pixelSpacingX, source.pixelSpacingY, target.pixelSpacingX, target.pixelSpacingY)
            }
        }
        return nil
    }

    private static func cannotReorient(_ source: ROIAssociationItem) -> Bool {
        source.hasRect || source.typeCode == ROIInterchangeType.brush.rawValue
            || source.typeCode == ROIInterchangeType.rectangle.rawValue
            || source.typeCode == ROIInterchangeType.oval.rawValue
            || source.typeCode == ROIInterchangeType.point2D.rawValue
    }

    private static func canSearchPlanes(_ source: ROIAssociationItem) -> Bool {
        guard let frame = source.image.frameOfReferenceUID, !frame.isEmpty else { return false }
        if source.patientPoints.contains(where: { $0.count == 3 }) { return true }
        return source.image.imagePosition.count == 3 && source.image.imageOrientation.count == 6 && !source.points.isEmpty
    }

    private static func transformedPoints(_ source: ROIAssociationItem,
                                          onto target: ROIAssociationImage) -> (points: [[Double]], through: Double)? {
        guard let targetSlice = slicePoint(for: target) else { return nil }
        let patients: [[Double]]
        if source.patientPoints.count == source.points.count, source.patientPoints.allSatisfy({ $0.count == 3 }) {
            patients = source.patientPoints
        } else if !source.points.isEmpty, let sourceSlice = slicePoint(for: source.image) {
            patients = source.points.compactMap { pixel -> [Double]? in
                guard pixel.count == 2 else { return nil }
                let point = ROISlicePoint(pixelX: pixel[0], pixelY: pixel[1],
                                          originX: sourceSlice.originX, originY: sourceSlice.originY, originZ: sourceSlice.originZ,
                                          rowX: sourceSlice.rowX, rowY: sourceSlice.rowY, rowZ: sourceSlice.rowZ,
                                          colX: sourceSlice.colX, colY: sourceSlice.colY, colZ: sourceSlice.colZ,
                                          normalX: sourceSlice.normalX, normalY: sourceSlice.normalY, normalZ: sourceSlice.normalZ,
                                          spacingX: sourceSlice.spacingX, spacingY: sourceSlice.spacingY,
                                          pixelCenter: false)
                let patient = ROIIntersliceGeometry.patientPoint(from: point)
                return [patient.x, patient.y, patient.z]
            }
            guard patients.count == source.points.count else { return nil }
        } else {
            return nil
        }
        var out: [[Double]] = []
        var maxThrough = 0.0
        for patient in patients {
            guard patient.count == 3 else { return nil }
            guard let projection = ROIIntersliceGeometry.projection(
                of: ROIPatientPoint(x: patient[0], y: patient[1], z: patient[2]),
                onto: targetSlice) else { return nil }
            out.append([projection.pixelX, projection.pixelY])
            maxThrough = max(maxThrough, abs(projection.throughPlane))
        }
        return (out, maxThrough)
    }

    private static func slicePoint(for image: ROIAssociationImage) -> ROISlicePoint? {
        guard image.imagePosition.count == 3, image.imageOrientation.count == 6 else { return nil }
        let iop = image.imageOrientation
        let row = SIMD3(iop[0], iop[1], iop[2])
        let col = SIMD3(iop[3], iop[4], iop[5])
        let normal = simd_cross(row, col)
        return ROISlicePoint(pixelX: 0, pixelY: 0,
                             originX: image.imagePosition[0], originY: image.imagePosition[1], originZ: image.imagePosition[2],
                             rowX: iop[0], rowY: iop[1], rowZ: iop[2],
                             colX: iop[3], colY: iop[4], colZ: iop[5],
                             normalX: normal.x, normalY: normal.y, normalZ: normal.z,
                             spacingX: image.pixelSpacingX, spacingY: image.pixelSpacingY,
                             pixelCenter: false)
    }

    private static func normal(of image: ROIAssociationImage) -> SIMD3<Double>? {
        guard image.imageOrientation.count == 6 else { return nil }
        let iop = image.imageOrientation
        let crossed = simd_cross(SIMD3(iop[0], iop[1], iop[2]), SIMD3(iop[3], iop[4], iop[5]))
        let length = simd_length(crossed)
        guard length > 0, length.isFinite else { return nil }
        return crossed / length
    }

    private static func associationImage(from image: ROIInterchangeImage,
                                         series: ROIInterchangeSeries) -> ROIAssociationImage {
        let result = ROIAssociationImage()
        result.index = image.index
        result.temporalIndex = image.temporalIndex
        result.sopInstanceUID = image.sopInstanceUID
        result.frame = image.frame
        result.seriesInstanceUID = series.seriesInstanceUID
        result.frameOfReferenceUID = series.frameOfReferenceUID
        result.rows = image.rows
        result.columns = image.columns
        result.pixelSpacingX = image.pixelSpacingX
        result.pixelSpacingY = image.pixelSpacingY
        result.imagePosition = image.imagePosition
        result.imageOrientation = image.imageOrientation
        if image.imagePosition.count == 3, image.imageOrientation.count == 6 {
            let origin = image.imagePosition
            let iop = image.imageOrientation
            result.hasImageOrigin = true
            result.imageOriginX = origin[0] * iop[0] + origin[1] * iop[1] + origin[2] * iop[2]
            result.imageOriginY = origin[0] * iop[3] + origin[1] * iop[4] + origin[2] * iop[5]
        }
        return result
    }

    private static func copyImage(_ image: ROIAssociationImage) -> ROIAssociationImage {
        let copy = ROIAssociationImage()
        copy.index = image.index
        copy.temporalIndex = image.temporalIndex
        copy.sopInstanceUID = image.sopInstanceUID
        copy.frame = image.frame
        copy.seriesInstanceUID = image.seriesInstanceUID
        copy.frameOfReferenceUID = image.frameOfReferenceUID
        copy.rows = image.rows
        copy.columns = image.columns
        copy.pixelSpacingX = image.pixelSpacingX
        copy.pixelSpacingY = image.pixelSpacingY
        copy.imagePosition = image.imagePosition
        copy.imageOrientation = image.imageOrientation
        copy.hasImageOrigin = image.hasImageOrigin
        copy.imageOriginX = image.imageOriginX
        copy.imageOriginY = image.imageOriginY
        return copy
    }

    private static func hypot3(_ a: [Double], _ b: [Double]) -> Double {
        zip(a, b).map { $0 - $1 }.map { $0 * $0 }.reduce(0, +).squareRoot()
    }

    private static func relativeDifference(_ a: Double, _ b: Double) -> Double {
        let scale = max(abs(a), abs(b))
        return scale == 0 ? 0 : abs(a - b) / scale
    }

    private static func typeName(_ code: Int) -> String {
        ROIInterchangeType(rawValue: code)?.name ?? "type \(code)"
    }
}
