import Foundation
import AppKit

/// Converts identified Horos/OsiriX ROI interchange documents into a derived
/// DICOM SEG that reuses the shared #376 model (#377 B).
///
/// Typedstream `.roi` / `.rois_series` archives do not persist SOP or patient
/// geometry, so they are refused rather than matched by patient name. Lengths
/// and text stay measurements. The original name, type, colour and vertices or
/// brush mask stay in Segment Description so the conversion can be reversed.
@objc(HorosLegacyROISeg)
public final class HorosLegacyROISeg: NSObject {
    public enum Refusal: String, Equatable, Error {
        case missingIdentity
        case missingGeometry
        case emptyMask
        case unsupportedType
    }

    /// B adds SEG persistence to the existing ROI model; it does not invent another.
    @objc public static let usesSharedSEGModel = true

    /// Archives without SOP/FoR are not associated by looking at the patient's name.
    @objc public static let mayGuessIdentityFromPatientName = false

    private static let regionTypes: Set<ROIInterchangeType> = [
        .brush, .closedPolygon, .rectangle, .oval, .pencil
    ]

    public static func convertTypedstreamArchive(_ data: Data) -> Refusal {
        let kind = ROIArchiveFormat.classify(data)
        if kind == .jsonInterchange { return .unsupportedType }
        return .missingIdentity
    }

    public static func convert(_ series: ROIInterchangeSeries) -> Result<DicomSEGDocument, Refusal> {
        guard !series.images.isEmpty else { return .failure(Refusal.missingGeometry) }
        for image in series.images {
            let sop = image.sopInstanceUID?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
            if sop.isEmpty { return .failure(Refusal.missingIdentity) }
            if image.rows <= 0 || image.columns <= 0 { return .failure(Refusal.missingGeometry) }
        }
        let rows = series.images[0].rows
        let columns = series.images[0].columns
        if series.images.contains(where: { $0.rows != rows || $0.columns != columns }) {
            return .failure(Refusal.missingGeometry)
        }

        var segments: [DicomSEGSegment] = []
        var sawRegion = false
        var sawUnsupported = false
        var number: UInt16 = 1
        for image in series.images {
            for roi in image.rois {
                guard let type = roi.interchangeType, regionTypes.contains(type) else {
                    sawUnsupported = true
                    continue
                }
                sawRegion = true
                guard let plane = mask(for: roi, rows: rows, columns: columns),
                      plane.contains(where: { $0 > 0 }) else {
                    return .failure(Refusal.emptyMask)
                }
                var frames = Array(repeating: Data(repeating: 0, count: rows * columns), count: series.images.count)
                frames[image.index >= 0 && image.index < series.images.count ? image.index : 0] = plane
                let sop = image.sopInstanceUID ?? ""
                segments.append(DicomSEGSegment(
                    number: number,
                    label: roi.name,
                    trackingUID: trackingUID(series: series, image: image, roi: roi),
                    color: (roi.red, roi.green, roi.blue),
                    visible: true,
                    kind: .binary,
                    algorithm: "MANUAL",
                    provenance: provenance(for: roi),
                    referencedSOPInstanceUIDs: [sop],
                    frames: frames,
                    maximumFractionalValue: 255
                ))
                number += 1
            }
        }
        if segments.isEmpty {
            return .failure(sawUnsupported && !sawRegion ? Refusal.unsupportedType : Refusal.emptyMask)
        }

        let sops = series.images.compactMap { $0.sopInstanceUID }.filter { !$0.isEmpty }
        var uniqueSOPs: [String] = []
        for sop in sops where uniqueSOPs.contains(sop) == false { uniqueSOPs.append(sop) }
        let geometry = DicomSEGGeometry(
            rows: rows, columns: columns, frames: series.images.count,
            spacingRow: series.images[0].pixelSpacingY,
            spacingCol: series.images[0].pixelSpacingX,
            sliceThickness: series.images[0].sliceThickness,
            origin: origin(series.images[0]),
            orientation: orientation(series.images[0]),
            frameOfReferenceUID: series.frameOfReferenceUID ?? "",
            frameOrigins: series.images.map { origin($0) }
        )
        let document = DicomSEGDocument(
            identity: DicomSEGIdentity(
                sopInstanceUID: DicomSEGCodec.makeUID(),
                seriesInstanceUID: DicomSEGCodec.makeUID(),
                studyInstanceUID: series.studyInstanceUID ?? "",
                frameOfReferenceUID: series.frameOfReferenceUID ?? "",
                sourceSOPInstanceUIDs: uniqueSOPs
            ),
            geometry: geometry,
            kind: .binary,
            segments: segments,
            diagnoses: [],
            sourceBytes: nil
        )
        return .success(document)
    }

    public static func originalROI(from segment: DicomSEGSegment) -> ROIInterchangeROI? {
        guard segment.provenance.hasPrefix("derived-from-legacy-roi") else { return nil }
        let roi = ROIInterchangeROI()
        roi.name = segment.label
        roi.red = segment.color.r
        roi.green = segment.color.g
        roi.blue = segment.color.b
        var typeCode = ROIInterchangeType.closedPolygon.rawValue
        for token in segment.provenance.split(separator: ";") {
            if token.hasPrefix("t="), let value = Int(token.dropFirst(2)) {
                typeCode = value
            } else if token.hasPrefix("b=") {
                let body = String(token.dropFirst(2))
                let parts = body.split(separator: "@")
                guard parts.count == 2 else { continue }
                let size = parts[0].split(separator: "x")
                let origin = parts[1].split(separator: ",")
                guard size.count == 2, origin.count == 2,
                      let width = Int(size[0]), let height = Int(size[1]),
                      let x = Int(origin[0]), let y = Int(origin[1]) else { continue }
                roi.brushWidth = width
                roi.brushHeight = height
                roi.brushOriginX = x
                roi.brushOriginY = y
            } else if token.hasPrefix("m=") {
                let bits = token.dropFirst(2)
                roi.brushMask = Data(bits.map { $0 == "0" ? 0 : 1 })
            } else if token.hasPrefix("p=") {
                let numbers = String(token.dropFirst(2)).split(separator: ",").compactMap { Double($0) }
                guard numbers.count >= 2, numbers.count % 2 == 0 else { continue }
                var points: [NSValue] = []
                var index = 0
                while index + 1 < numbers.count {
                    points.append(NSValue(point: NSPoint(x: numbers[index], y: numbers[index + 1])))
                    index += 2
                }
                roi.points = points
            }
        }
        roi.typeCode = typeCode
        return roi
    }

    private static func mask(for roi: ROIInterchangeROI, rows: Int, columns: Int) -> Data? {
        guard let type = roi.interchangeType else { return nil }
        switch type {
        case .brush:
            return stampBrush(roi, rows: rows, columns: columns)
        case .closedPolygon, .pencil:
            return fillPolygon(roi.points.map { $0.pointValue }, rows: rows, columns: columns)
        case .rectangle, .oval:
            guard roi.hasRect else {
                return fillPolygon(roi.points.map { $0.pointValue }, rows: rows, columns: columns)
            }
            return fillRect(roi.rect, oval: type == .oval, rows: rows, columns: columns)
        default:
            return nil
        }
    }

    private static func stampBrush(_ roi: ROIInterchangeROI, rows: Int, columns: Int) -> Data? {
        guard let mask = roi.brushMask, roi.brushWidth > 0, roi.brushHeight > 0,
              mask.count == roi.brushWidth * roi.brushHeight else { return nil }
        var plane = Data(repeating: 0, count: rows * columns)
        for row in 0..<roi.brushHeight {
            for column in 0..<roi.brushWidth {
                if mask[row * roi.brushWidth + column] == 0 { continue }
                let x = roi.brushOriginX + column
                let y = roi.brushOriginY + row
                if x >= 0, y >= 0, x < columns, y < rows {
                    plane[y * columns + x] = 1
                }
            }
        }
        return plane
    }

    private static func fillPolygon(_ points: [NSPoint], rows: Int, columns: Int) -> Data? {
        guard points.count >= 3 else { return nil }
        var plane = Data(repeating: 0, count: rows * columns)
        for row in 0..<rows {
            for column in 0..<columns {
                if contains(points, x: Double(column) + 0.5, y: Double(row) + 0.5) {
                    plane[row * columns + column] = 1
                }
            }
        }
        return plane
    }

    private static func fillRect(_ rect: NSRect, oval: Bool, rows: Int, columns: Int) -> Data {
        var plane = Data(repeating: 0, count: rows * columns)
        let cx = rect.midX, cy = rect.midY
        let rx = max(rect.width / 2, 0.5), ry = max(rect.height / 2, 0.5)
        for row in 0..<rows {
            for column in 0..<columns {
                let x = Double(column) + 0.5, y = Double(row) + 0.5
                let inside: Bool
                if oval {
                    let dx = (x - cx) / rx, dy = (y - cy) / ry
                    inside = dx * dx + dy * dy <= 1
                } else {
                    inside = x >= rect.minX && x < rect.maxX && y >= rect.minY && y < rect.maxY
                }
                if inside { plane[row * columns + column] = 1 }
            }
        }
        return plane
    }

    private static func contains(_ polygon: [NSPoint], x: Double, y: Double) -> Bool {
        var inside = false
        var previous = polygon.count - 1
        for index in 0..<polygon.count {
            let current = polygon[index], last = polygon[previous]
            if (current.y > y) != (last.y > y) {
                let crossing = (last.x - current.x) * (y - current.y) / (last.y - current.y) + current.x
                if x < crossing { inside.toggle() }
            }
            previous = index
        }
        return inside
    }

    private static func origin(_ image: ROIInterchangeImage) -> [Double] {
        image.imagePosition.count >= 3 ? Array(image.imagePosition.prefix(3)) : [0, 0, 0]
    }

    private static func orientation(_ image: ROIInterchangeImage) -> [Double] {
        image.imageOrientation.count >= 6 ? Array(image.imageOrientation.prefix(6)) : [1, 0, 0, 0, 1, 0]
    }

    private static func trackingUID(series: ROIInterchangeSeries, image: ROIInterchangeImage, roi: ROIInterchangeROI) -> String {
        let mask = roi.brushMask?.map { $0 == 0 ? "0" : "1" }.joined() ?? ""
        let points = roi.points.map { "\($0.pointValue.x),\($0.pointValue.y)" }.joined(separator: ",")
        let key = [
            series.studyInstanceUID ?? "",
            series.seriesInstanceUID ?? "",
            image.sopInstanceUID ?? "",
            "\(image.frame)",
            roi.name,
            "\(roi.typeCode)",
            mask,
            points
        ].joined(separator: "|")
        var hash: UInt64 = 1_469_598_103_934_665_603_7
        for byte in key.utf8 {
            hash ^= UInt64(byte)
            hash = hash &* 1_099_511_628_211
        }
        return "2.25.\(hash)"
    }

    private static func provenance(for roi: ROIInterchangeROI) -> String {
        var parts = ["derived-from-legacy-roi"]
        if let type = roi.interchangeType {
            parts.append(type.name)
            parts.append("t=\(roi.typeCode)")
        } else {
            parts.append("t=\(roi.typeCode)")
        }
        if roi.interchangeType == .brush, let mask = roi.brushMask {
            parts.append("b=\(roi.brushWidth)x\(roi.brushHeight)@\(roi.brushOriginX),\(roi.brushOriginY)")
            parts.append("m=" + mask.map { $0 == 0 ? "0" : "1" }.joined())
        } else if !roi.points.isEmpty {
            let numbers = roi.points.map { point -> String in
                let x = point.pointValue.x, y = point.pointValue.y
                return "\(format(x)),\(format(y))"
            }.joined(separator: ",")
            parts.append("p=" + numbers)
        }
        return parts.joined(separator: ";")
    }

    private static func format(_ value: Double) -> String {
        if value == value.rounded() { return String(Int(value)) }
        return String(value)
    }
}
