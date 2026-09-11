import Foundation

/// File-level classification of a ROI import payload (issue #231 / I240).
@objc(HorosROIArchiveKind)
public enum ROIArchiveKind: Int {
    case jsonInterchange = 1
    case typedstream
    case keyedArchive
    case empty
    case unknown
}

/// Structure of an unarchived or decoded payload.
@objc(HorosROIArchivePayloadKind)
public enum ROIArchivePayloadKind: Int {
    case roiList = 1
    case roisSeries
    case jsonInterchange
    case empty
    case incompatible
}

@objc(HorosROIArchiveInspection)
@objcMembers public final class ROIArchiveInspection: NSObject {
    public var kind: ROIArchiveKind = .unknown
    public var payload: ROIArchivePayloadKind = .incompatible
    public var movieCount: Int = 0
    public var sliceCount: Int = 0
    public var roiCount: Int = 0
    public var reason: String = ""
    public var canImport: Bool = false
}

/// Format diagnosis for `.roi` / `.rois_series` / JSON. Incompatible or empty
/// archives produce a reason; they are never reported as a successful import.
@objc(HorosROIArchiveFormat)
public final class ROIArchiveFormat: NSObject {
    /// Fields Horos actually writes into NSArchiver ROI objects (ROIVERSION 11).
    @objc public static let persistedROIArchiveFields = [
        "points", "rect", "type", "thickness", "fill", "opacity", "color", "name", "comments",
        "pixelSpacingX", "pixelSpacingY", "imageOrigin", "brushMask", "zPositions",
        "groupID", "isSpline"
    ]

    /// Identity the archive does not persist. Matching by SOP/series/frame must
    /// come from JSON interchange or be refused as insufficient, never guessed.
    @objc public static let absentROIArchiveIdentityFields = [
        "sopInstanceUID", "seriesInstanceUID", "frameOfReferenceUID", "frame",
        "temporalIndex", "imagePositionPatient", "imageOrientationPatient", "studyInstanceUID"
    ]

    @objc public static func classify(_ data: Data) -> ROIArchiveKind {
        if data.isEmpty { return .empty }
        if looksLikeJSON(data) { return .jsonInterchange }
        if looksLikeTypedstream(data) { return .typedstream }
        if looksLikeKeyedArchive(data) { return .keyedArchive }
        return .unknown
    }

    @objc public static func inspectJSON(_ data: Data) -> ROIArchiveInspection {
        let inspection = ROIArchiveInspection()
        inspection.kind = .jsonInterchange
        do {
            let series = try ROIInterchange.decode(data)
            let rois = series.images.reduce(0) { $0 + $1.rois.count }
            inspection.roiCount = rois
            inspection.sliceCount = series.images.count
            if rois == 0 {
                inspection.payload = .empty
                inspection.reason = "The JSON document decoded but contains no ROIs."
                return inspection
            }
            inspection.payload = .jsonInterchange
            inspection.canImport = true
            return inspection
        } catch let error as ROIInterchangeError {
            inspection.payload = .incompatible
            inspection.reason = error.reason
            return inspection
        } catch {
            inspection.payload = .incompatible
            inspection.reason = "The file is not a valid ROI interchange document: \(error.localizedDescription)"
            return inspection
        }
    }

    @objc public static func inspectUnarchived(_ object: Any?) -> ROIArchiveInspection {
        let inspection = ROIArchiveInspection()
        inspection.kind = .typedstream
        guard let object else {
            inspection.payload = .empty
            inspection.reason = "The archive decoded to nothing."
            return inspection
        }
        if object is String || object is NSNumber || object is Data {
            inspection.payload = .incompatible
            inspection.reason = "The archive is not a rois_series or .roi list of ROI objects (root is \(type(of: object)))."
            return inspection
        }
        guard let root = asArray(object) else {
            inspection.payload = .incompatible
            inspection.reason = "The archive root is \(type(of: object)), not an array."
            return inspection
        }
        if root.isEmpty {
            return emptyDecoded(inspection)
        }

        let first = root[0]
        if let inner = asArray(first) {
            if let innerFirst = inner.first, asArray(innerFirst) != nil {
                return inspectSeries(root, inspection: inspection)
            }
            return inspectSeries([root], inspection: inspection)
        }

        guard root.allSatisfy(isROILike) else {
            inspection.payload = .incompatible
            inspection.reason = "The .roi archive contains values that are not ROI objects."
            return inspection
        }
        inspection.payload = .roiList
        inspection.roiCount = root.count
        inspection.canImport = root.count > 0
        if root.isEmpty { return emptyDecoded(inspection) }
        return inspection
    }

    private static func inspectSeries(_ movies: [Any],
                                      inspection: ROIArchiveInspection) -> ROIArchiveInspection {
        var sliceCount = 0
        var roiCount = 0
        for movie in movies {
            guard let slices = asArray(movie) else {
                inspection.payload = .incompatible
                inspection.reason = "A rois_series movie entry is not an array of slices."
                return inspection
            }
            sliceCount += slices.count
            for slice in slices {
                guard let rois = asArray(slice) else {
                    inspection.payload = .incompatible
                    inspection.reason = "A rois_series slice entry is not an array of ROIs."
                    return inspection
                }
                if !rois.allSatisfy(isROILike) {
                    inspection.payload = .incompatible
                    inspection.reason = "A rois_series slice contains values that are not ROI objects."
                    return inspection
                }
                roiCount += rois.count
            }
        }
        inspection.movieCount = movies.count
        inspection.sliceCount = sliceCount
        inspection.roiCount = roiCount
        if roiCount == 0 { return emptyDecoded(inspection) }
        inspection.payload = .roisSeries
        inspection.canImport = true
        return inspection
    }

    private static func emptyDecoded(_ inspection: ROIArchiveInspection) -> ROIArchiveInspection {
        inspection.payload = .empty
        inspection.canImport = false
        inspection.reason = "The archive decoded but contains no ROIs."
        return inspection
    }

    private static func asArray(_ value: Any) -> [Any]? {
        if let array = value as? [Any] { return array }
        if let array = value as? NSArray {
            return (0..<array.count).map { array[$0] as Any }
        }
        return nil
    }

    private static func isROILike(_ value: Any) -> Bool {
        if asArray(value) != nil { return false }
        if value is String || value is NSString { return false }
        if value is NSNumber { return false }
        if value is Data || value is NSData { return false }
        return true
    }

    private static func looksLikeJSON(_ data: Data) -> Bool {
        var bytes = data
        if bytes.starts(with: [0xEF, 0xBB, 0xBF]) { bytes = bytes.dropFirst(3) }
        guard let text = String(data: bytes, encoding: .utf8) else { return false }
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmed.first == "{"
    }

    private static func looksLikeTypedstream(_ data: Data) -> Bool {
        if data.count >= 13, data[0] == 0x04, data[1] == 0x0b {
            return true
        }
        return data.range(of: Data("streamtyped".utf8)) != nil
    }

    private static func looksLikeKeyedArchive(_ data: Data) -> Bool {
        if data.starts(with: Data("bplist".utf8)) { return true }
        guard let prefix = String(data: data.prefix(80), encoding: .utf8) else { return false }
        return prefix.contains("plist") || prefix.contains("NSKeyedArchiver")
    }
}
