//
//  ROIInterchange.swift
//  Horos
//
//  Open, documented JSON interchange format for regions of interest.
//  See docs/roi-interchange-json.md for the schema. This file owns the schema,
//  validation and matching rules; the Objective-C category
//  ViewerController+ROIInterchange converts between these records and ROI/DCMPix.
//

import Foundation

// MARK: - Errors

@objc public enum ROIInterchangeErrorCode: Int {
    case invalidJSON = 1
    case unsupportedFormat
    case unsupportedVersion
    case missingSeries
    case noROIs
    case invalidImage
    case invalidROI
    case unsupportedROIType
    case imageNotFound
    case geometryMismatch
    case seriesMismatch
}

public struct ROIInterchangeError: LocalizedError, CustomNSError {
    public let code: ROIInterchangeErrorCode
    public let reason: String

    public static var errorDomain: String { "org.horosproject.roi-interchange" }
    public var errorCode: Int { code.rawValue }
    public var errorDescription: String? { reason }
    public var errorUserInfo: [String: Any] { [NSLocalizedDescriptionKey: reason] }
}

// MARK: - ROI types

/// Stable names for the ROI tool codes (ToolMode in DCMView.h). The numeric code is
/// also written so that readers do not need this table.
@objc public enum ROIInterchangeType: Int {
    case length = 5
    case rectangle = 6
    case oval = 9
    case openPolygon = 10
    case closedPolygon = 11
    case angle = 12
    case text = 13
    case arrow = 14
    case pencil = 15
    case point3D = 16
    case point2D = 19
    case brush = 20
    case axis = 26
    case dynamicAngle = 27
    case tagt = 29

    public var name: String {
        switch self {
        case .length: return "length"
        case .rectangle: return "rectangle"
        case .oval: return "oval"
        case .openPolygon: return "openPolygon"
        case .closedPolygon: return "closedPolygon"
        case .angle: return "angle"
        case .text: return "text"
        case .arrow: return "arrow"
        case .pencil: return "pencil"
        case .point3D: return "point3D"
        case .point2D: return "point2D"
        case .brush: return "brush"
        case .axis: return "axis"
        case .dynamicAngle: return "dynamicAngle"
        case .tagt: return "tagt"
        }
    }

    public static func from(name: String) -> ROIInterchangeType? {
        let all: [ROIInterchangeType] = [.length, .rectangle, .oval, .openPolygon, .closedPolygon, .angle, .text, .arrow,
                                         .pencil, .point3D, .point2D, .brush, .axis, .dynamicAngle, .tagt]
        return all.first { $0.name == name }
    }

    /// Types whose geometry is defined by a rectangle rather than by a point list.
    public var usesRect: Bool { self == .rectangle || self == .oval || self == .point2D }
}

// MARK: - Objective-C visible records

@objcMembers public final class ROIInterchangeROI: NSObject {
    public var name: String = ""
    public var typeCode: Int = ROIInterchangeType.closedPolygon.rawValue
    public var comments: String?
    /// Vertices in image pixel coordinates (x to the right, y down, origin at the top-left corner of pixel 0,0).
    public var points: [NSValue] = []
    /// The same vertices in the DICOM patient coordinate system, millimetres, when the image geometry is known.
    public var patientPoints: [[Double]] = []
    public var hasRect: Bool = false
    public var rect: NSRect = NSZeroRect
    public var thickness: Double = 1
    public var opacity: Double = 1
    /// Colour components in 0...1.
    public var red: Double = 1
    public var green: Double = 0
    public var blue: Double = 0
    public var isSpline: Bool = false
    public var groupID: Double = 0
    /// Brush ROIs: mask dimensions, position of the mask's top-left pixel in image coordinates and the mask bytes (1 byte per pixel, non-zero = inside).
    public var brushWidth: Int = 0
    public var brushHeight: Int = 0
    public var brushOriginX: Int = 0
    public var brushOriginY: Int = 0
    public var brushMask: Data?

    public var interchangeType: ROIInterchangeType? { ROIInterchangeType(rawValue: typeCode) }
}

@objcMembers public final class ROIInterchangeImage: NSObject {
    /// Zero-based position of the image in the series as displayed by Horos.
    public var index: Int = 0
    /// Zero-based temporal position (4D series); 0 otherwise.
    public var temporalIndex: Int = 0
    public var sopInstanceUID: String?
    /// Zero-based frame number inside a multi-frame file.
    public var frame: Int = 0
    /// DICOM Instance Number, -1 when unknown.
    public var instanceNumber: Int = -1
    public var rows: Int = 0
    public var columns: Int = 0
    public var pixelSpacingX: Double = 0
    public var pixelSpacingY: Double = 0
    public var sliceThickness: Double = 0
    public var sliceLocation: Double = 0
    /// Image Position (Patient), millimetres. Empty when unknown.
    public var imagePosition: [Double] = []
    /// Image Orientation (Patient), six direction cosines. Empty when unknown.
    public var imageOrientation: [Double] = []
    public var rois: [ROIInterchangeROI] = []
}

@objcMembers public final class ROIInterchangeSeries: NSObject {
    public var studyInstanceUID: String?
    public var seriesInstanceUID: String?
    public var frameOfReferenceUID: String?
    public var modality: String?
    public var seriesDescription: String?
    public var images: [ROIInterchangeImage] = []
}

// MARK: - Codable document

private struct Document: Codable {
    var format: String
    var version: Int
    var generator: String?
    var created: String?
    var coordinateSystems: CoordinateSystems
    var series: SeriesRecord
    var images: [ImageRecord]
}

private struct CoordinateSystems: Codable {
    var pixel: String
    var patient: String
}

private struct SeriesRecord: Codable {
    var studyInstanceUID: String?
    var seriesInstanceUID: String?
    var frameOfReferenceUID: String?
    var modality: String?
    var seriesDescription: String?
}

private struct ImageRecord: Codable {
    var index: Int
    var temporalIndex: Int?
    var sopInstanceUID: String?
    var frame: Int?
    var instanceNumber: Int?
    var rows: Int
    var columns: Int
    var pixelSpacing: [Double]
    var sliceThickness: Double?
    var sliceLocation: Double?
    var imagePositionPatient: [Double]?
    var imageOrientationPatient: [Double]?
    var rois: [ROIRecord]
}

private struct BrushRecord: Codable {
    var width: Int
    var height: Int
    var originX: Int
    var originY: Int
    var maskBase64: String
}

private struct ROIRecord: Codable {
    var name: String
    var type: String?
    var typeCode: Int?
    var comments: String?
    var points: [[Double]]
    var pointsPatient: [[Double]]?
    var rect: [Double]?
    var thickness: Double?
    var opacity: Double?
    var color: [Double]?
    var isSpline: Bool?
    var groupID: Double?
    var brush: BrushRecord?
}

// MARK: - Public API

@objc public final class ROIInterchange: NSObject {
    @objc public static let formatIdentifier = "org.horosproject.roi-interchange"
    @objc public static let formatVersion = 1
    @objc public static let fileExtension = "json"
    @objc public static let pixelCoordinateSystem = "image pixels: x right, y down, origin at the top-left corner of pixel (0,0), one unit per pixel"
    @objc public static let patientCoordinateSystem = "DICOM patient coordinates (LPS), millimetres"

    /// Serialises a series and its ROIs. Images without ROIs are omitted.
    @objc public static func encode(_ series: ROIInterchangeSeries, generator: String?) throws -> Data {
        let images = series.images.filter { !$0.rois.isEmpty }
        guard !images.isEmpty else {
            throw ROIInterchangeError(code: .noROIs, reason: "There is no ROI to export in this series.")
        }

        var records: [ImageRecord] = []
        for image in images {
            var rois: [ROIRecord] = []
            for roi in image.rois {
                guard let type = roi.interchangeType else {
                    throw ROIInterchangeError(code: .unsupportedROIType,
                                              reason: "ROI \"\(roi.name)\" on image \(image.index + 1) has an unsupported type (code \(roi.typeCode)).")
                }
                var record = ROIRecord(name: roi.name,
                                       type: type.name,
                                       typeCode: type.rawValue,
                                       comments: roi.comments?.isEmpty == false ? roi.comments : nil,
                                       points: roi.points.map { [Double($0.pointValue.x), Double($0.pointValue.y)] },
                                       pointsPatient: roi.patientPoints.isEmpty ? nil : roi.patientPoints,
                                       rect: roi.hasRect ? [Double(roi.rect.origin.x), Double(roi.rect.origin.y), Double(roi.rect.size.width), Double(roi.rect.size.height)] : nil,
                                       thickness: roi.thickness,
                                       opacity: roi.opacity,
                                       color: [roi.red, roi.green, roi.blue],
                                       isSpline: roi.isSpline ? true : nil,
                                       groupID: roi.groupID != 0 ? roi.groupID : nil,
                                       brush: nil)
                if type == .brush {
                    guard let mask = roi.brushMask, roi.brushWidth > 0, roi.brushHeight > 0,
                          mask.count == roi.brushWidth * roi.brushHeight else {
                        throw ROIInterchangeError(code: .invalidROI,
                                                  reason: "Brush ROI \"\(roi.name)\" on image \(image.index + 1) has no valid mask.")
                    }
                    record.brush = BrushRecord(width: roi.brushWidth, height: roi.brushHeight,
                                               originX: roi.brushOriginX, originY: roi.brushOriginY,
                                               maskBase64: mask.base64EncodedString())
                }
                rois.append(record)
            }
            records.append(ImageRecord(index: image.index,
                                       temporalIndex: image.temporalIndex != 0 ? image.temporalIndex : nil,
                                       sopInstanceUID: image.sopInstanceUID,
                                       frame: image.frame != 0 ? image.frame : nil,
                                       instanceNumber: image.instanceNumber >= 0 ? image.instanceNumber : nil,
                                       rows: image.rows,
                                       columns: image.columns,
                                       pixelSpacing: [image.pixelSpacingX, image.pixelSpacingY],
                                       sliceThickness: image.sliceThickness != 0 ? image.sliceThickness : nil,
                                       sliceLocation: image.sliceLocation,
                                       imagePositionPatient: image.imagePosition.count == 3 ? image.imagePosition : nil,
                                       imageOrientationPatient: image.imageOrientation.count == 6 ? image.imageOrientation : nil,
                                       rois: rois))
        }

        let formatter = ISO8601DateFormatter()
        let document = Document(format: formatIdentifier,
                                version: formatVersion,
                                generator: generator,
                                created: formatter.string(from: Date()),
                                coordinateSystems: CoordinateSystems(pixel: pixelCoordinateSystem, patient: patientCoordinateSystem),
                                series: SeriesRecord(studyInstanceUID: series.studyInstanceUID,
                                                     seriesInstanceUID: series.seriesInstanceUID,
                                                     frameOfReferenceUID: series.frameOfReferenceUID,
                                                     modality: series.modality,
                                                     seriesDescription: series.seriesDescription),
                                images: records)
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        return try encoder.encode(document)
    }

    /// Parses and validates a document. Structural problems are reported with a reason; matching
    /// against a loaded series is a separate step (`resolve`).
    @objc public static func decode(_ data: Data) throws -> ROIInterchangeSeries {
        let document: Document
        do {
            document = try JSONDecoder().decode(Document.self, from: data)
        } catch let error as DecodingError {
            throw ROIInterchangeError(code: .invalidJSON, reason: "The file is not a valid ROI interchange document: \(describe(error))")
        } catch {
            throw ROIInterchangeError(code: .invalidJSON, reason: "The file is not a valid ROI interchange document: \(error.localizedDescription)")
        }

        guard document.format == formatIdentifier else {
            throw ROIInterchangeError(code: .unsupportedFormat, reason: "Unsupported format identifier \"\(document.format)\" (expected \"\(formatIdentifier)\").")
        }
        guard document.version >= 1 && document.version <= formatVersion else {
            throw ROIInterchangeError(code: .unsupportedVersion, reason: "Unsupported format version \(document.version); this Horos reads versions 1 to \(formatVersion).")
        }

        let series = ROIInterchangeSeries()
        series.studyInstanceUID = document.series.studyInstanceUID
        series.seriesInstanceUID = document.series.seriesInstanceUID
        series.frameOfReferenceUID = document.series.frameOfReferenceUID
        series.modality = document.series.modality
        series.seriesDescription = document.series.seriesDescription

        var totalROIs = 0
        for record in document.images {
            let image = ROIInterchangeImage()
            image.index = record.index
            image.temporalIndex = record.temporalIndex ?? 0
            image.sopInstanceUID = record.sopInstanceUID
            image.frame = record.frame ?? 0
            image.instanceNumber = record.instanceNumber ?? -1
            image.rows = record.rows
            image.columns = record.columns
            guard record.rows > 0, record.columns > 0 else {
                throw ROIInterchangeError(code: .invalidImage, reason: "Image \(record.index + 1) has invalid dimensions \(record.columns)x\(record.rows).")
            }
            guard record.pixelSpacing.count == 2, record.pixelSpacing.allSatisfy({ $0 > 0 && $0.isFinite }) else {
                throw ROIInterchangeError(code: .invalidImage, reason: "Image \(record.index + 1) has an invalid pixel spacing \(record.pixelSpacing).")
            }
            image.pixelSpacingX = record.pixelSpacing[0]
            image.pixelSpacingY = record.pixelSpacing[1]
            image.sliceThickness = record.sliceThickness ?? 0
            image.sliceLocation = record.sliceLocation ?? 0
            if let position = record.imagePositionPatient {
                guard position.count == 3, position.allSatisfy({ $0.isFinite }) else {
                    throw ROIInterchangeError(code: .invalidImage, reason: "Image \(record.index + 1) has an invalid Image Position (Patient).")
                }
                image.imagePosition = position
            }
            if let orientation = record.imageOrientationPatient {
                guard orientation.count == 6, orientation.allSatisfy({ $0.isFinite }) else {
                    throw ROIInterchangeError(code: .invalidImage, reason: "Image \(record.index + 1) has an invalid Image Orientation (Patient).")
                }
                image.imageOrientation = orientation
            }

            for roiRecord in record.rois {
                let roi = ROIInterchangeROI()
                roi.name = roiRecord.name
                let type: ROIInterchangeType
                if let code = roiRecord.typeCode, let byCode = ROIInterchangeType(rawValue: code) {
                    type = byCode
                } else if let name = roiRecord.type, let byName = ROIInterchangeType.from(name: name) {
                    type = byName
                } else {
                    throw ROIInterchangeError(code: .unsupportedROIType,
                                              reason: "ROI \"\(roiRecord.name)\" on image \(record.index + 1) has an unsupported type \"\(roiRecord.type ?? String(describing: roiRecord.typeCode))\".")
                }
                roi.typeCode = type.rawValue
                roi.comments = roiRecord.comments

                for (i, point) in roiRecord.points.enumerated() {
                    guard point.count == 2, point.allSatisfy({ $0.isFinite }) else {
                        throw ROIInterchangeError(code: .invalidROI, reason: "ROI \"\(roiRecord.name)\" on image \(record.index + 1): point \(i + 1) is not a finite [x, y] pair.")
                    }
                    roi.points.append(NSValue(point: NSMakePoint(point[0], point[1])))
                }
                if let patient = roiRecord.pointsPatient {
                    guard patient.count == roiRecord.points.count, patient.allSatisfy({ $0.count == 3 && $0.allSatisfy { $0.isFinite } }) else {
                        throw ROIInterchangeError(code: .invalidROI, reason: "ROI \"\(roiRecord.name)\" on image \(record.index + 1): pointsPatient must hold one finite [x, y, z] triplet per point.")
                    }
                    roi.patientPoints = patient
                }
                if let rect = roiRecord.rect {
                    guard rect.count == 4, rect.allSatisfy({ $0.isFinite }) else {
                        throw ROIInterchangeError(code: .invalidROI, reason: "ROI \"\(roiRecord.name)\" on image \(record.index + 1): rect must be [x, y, width, height].")
                    }
                    roi.hasRect = true
                    roi.rect = NSMakeRect(rect[0], rect[1], rect[2], rect[3])
                }
                if type.usesRect && !roi.hasRect {
                    if type == .point2D, roi.points.count == 1 {
                        roi.hasRect = true
                        roi.rect = NSMakeRect(roi.points[0].pointValue.x, roi.points[0].pointValue.y, 0, 0)
                    } else {
                        throw ROIInterchangeError(code: .invalidROI, reason: "ROI \"\(roiRecord.name)\" on image \(record.index + 1) is a \(type.name) and needs a rect.")
                    }
                }
                if !type.usesRect && type != .brush && roi.points.isEmpty {
                    throw ROIInterchangeError(code: .invalidROI, reason: "ROI \"\(roiRecord.name)\" on image \(record.index + 1) has no points.")
                }
                roi.thickness = roiRecord.thickness ?? 1
                roi.opacity = min(max(roiRecord.opacity ?? 1, 0), 1)
                if let color = roiRecord.color {
                    guard color.count == 3, color.allSatisfy({ $0 >= 0 && $0 <= 1 }) else {
                        throw ROIInterchangeError(code: .invalidROI, reason: "ROI \"\(roiRecord.name)\" on image \(record.index + 1): color must be three components in 0...1.")
                    }
                    roi.red = color[0]; roi.green = color[1]; roi.blue = color[2]
                }
                roi.isSpline = roiRecord.isSpline ?? false
                roi.groupID = roiRecord.groupID ?? 0

                if type == .brush {
                    guard let brush = roiRecord.brush else {
                        throw ROIInterchangeError(code: .invalidROI, reason: "Brush ROI \"\(roiRecord.name)\" on image \(record.index + 1) has no mask.")
                    }
                    guard brush.width > 0, brush.height > 0,
                          let mask = Data(base64Encoded: brush.maskBase64),
                          mask.count == brush.width * brush.height else {
                        throw ROIInterchangeError(code: .invalidROI, reason: "Brush ROI \"\(roiRecord.name)\" on image \(record.index + 1): mask size does not match \(brush.width)x\(brush.height).")
                    }
                    roi.brushWidth = brush.width
                    roi.brushHeight = brush.height
                    roi.brushOriginX = brush.originX
                    roi.brushOriginY = brush.originY
                    roi.brushMask = mask
                }
                image.rois.append(roi)
                totalROIs += 1
            }
            series.images.append(image)
        }

        guard totalROIs > 0 else {
            throw ROIInterchangeError(code: .noROIs, reason: "The document does not contain any ROI.")
        }
        return series
    }

    /// Maps every document image onto an image of the loaded series.
    ///
    /// Rules, in order: same SOP Instance UID and frame; otherwise, when both share a Frame of Reference,
    /// the same Image Position (Patient) within `positionTolerance` millimetres and the same temporal index.
    /// Every matched image must have the same dimensions and pixel spacing (within `spacingTolerance`, relative).
    /// Returns the index into `target.images` for each document image, in document order.
    @objc public static func resolve(_ document: ROIInterchangeSeries,
                                     against target: ROIInterchangeSeries,
                                     positionTolerance: Double,
                                     spacingTolerance: Double) throws -> [NSNumber] {
        if let expected = document.seriesInstanceUID, let actual = target.seriesInstanceUID,
           !expected.isEmpty, !actual.isEmpty, expected != actual {
            let sameFrame = document.frameOfReferenceUID.flatMap { d in target.frameOfReferenceUID.map { d == $0 && !d.isEmpty } } ?? false
            if !sameFrame {
                throw ROIInterchangeError(code: .seriesMismatch,
                                          reason: "The document was exported from series \(expected), but the open series is \(actual) and they do not share a Frame of Reference.")
            }
        }

        var byUID: [String: Int] = [:]
        for (i, image) in target.images.enumerated() {
            if let uid = image.sopInstanceUID, !uid.isEmpty {
                byUID["\(uid)#\(image.frame)"] = i
            }
        }

        var result: [NSNumber] = []
        for image in document.images {
            var found: Int?
            if let uid = image.sopInstanceUID, !uid.isEmpty, let i = byUID["\(uid)#\(image.frame)"] {
                found = i
            } else if image.imagePosition.count == 3,
                      let docFrame = document.frameOfReferenceUID, let targetFrame = target.frameOfReferenceUID,
                      !docFrame.isEmpty, docFrame == targetFrame {
                var best: (Int, Double)?
                for (i, candidate) in target.images.enumerated() where candidate.imagePosition.count == 3 && candidate.temporalIndex == image.temporalIndex {
                    let d = zip(candidate.imagePosition, image.imagePosition).map { $0 - $1 }.map { $0 * $0 }.reduce(0, +).squareRoot()
                    if d <= positionTolerance && (best == nil || d < best!.1) { best = (i, d) }
                }
                found = best?.0
            }

            guard let index = found else {
                let identity = image.sopInstanceUID.map { "SOP Instance UID \($0)" } ?? "position \(image.imagePosition)"
                throw ROIInterchangeError(code: .imageNotFound,
                                          reason: "Image \(image.index + 1) of the document (\(identity)) is not part of the open series.")
            }

            let candidate = target.images[index]
            guard candidate.rows == image.rows, candidate.columns == image.columns else {
                throw ROIInterchangeError(code: .geometryMismatch,
                                          reason: "Image \(image.index + 1): the document expects \(image.columns)x\(image.rows) pixels but the open image is \(candidate.columns)x\(candidate.rows).")
            }
            let sx = relativeDifference(candidate.pixelSpacingX, image.pixelSpacingX)
            let sy = relativeDifference(candidate.pixelSpacingY, image.pixelSpacingY)
            guard sx <= spacingTolerance, sy <= spacingTolerance else {
                throw ROIInterchangeError(code: .geometryMismatch,
                                          reason: String(format: "Image %d: the document expects a pixel spacing of %.4f x %.4f mm but the open image has %.4f x %.4f mm.",
                                                         image.index + 1, image.pixelSpacingX, image.pixelSpacingY, candidate.pixelSpacingX, candidate.pixelSpacingY))
            }
            result.append(NSNumber(value: index))
        }
        return result
    }

    private static func relativeDifference(_ a: Double, _ b: Double) -> Double {
        let scale = max(abs(a), abs(b))
        return scale == 0 ? 0 : abs(a - b) / scale
    }

    private static func describe(_ error: DecodingError) -> String {
        func path(_ context: DecodingError.Context) -> String {
            let p = context.codingPath.map { $0.intValue.map { "[\($0)]" } ?? $0.stringValue }.joined(separator: ".")
            return p.isEmpty ? "document" : p
        }
        switch error {
        case .keyNotFound(let key, let context):
            return "missing key \"\(key.stringValue)\" in \(path(context))."
        case .typeMismatch(_, let context):
            return "wrong value type at \(path(context)): \(context.debugDescription)"
        case .valueNotFound(_, let context):
            return "missing value at \(path(context))."
        case .dataCorrupted(let context):
            return context.debugDescription
        @unknown default:
            return error.localizedDescription
        }
    }
}
