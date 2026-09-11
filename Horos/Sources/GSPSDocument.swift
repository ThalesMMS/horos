import Foundation
import AppKit
import CoreGraphics

/// Documented Grayscale Softcopy Presentation State subset (PS 3.3 A.33.1).
///
/// Supported SOP Class:
///   Grayscale Softcopy Presentation State Storage
///   `1.2.840.10008.5.1.4.1.1.11.1`
///
/// Supported modules, applied as view state (never written back into Pixel Data):
///   - Presentation State Relationship: Referenced Series / Image Sequence,
///     `ReferencedSOPInstanceUID` plus optional 1-based `ReferencedFrameNumber`
///   - Softcopy VOI LUT: Window Center/Width, or a VOI LUT Sequence (the table
///     wins when both are present, PS 3.3 C.11.2)
///   - Displayed Area: Top Left / Bottom Right Hand Corner (1-based column\row),
///     Presentation Size Mode
///   - Spatial Transformation: Image Rotation 0/90/180/270, Image Horizontal Flip
///   - Graphic Annotation: POINT, POLYLINE, CIRCLE, ELLIPSE and text with an
///     Anchor Point, in PIXEL or DISPLAY units
///
/// PIXEL is the stored image matrix, origin at the top-left of pixel (0,0),
/// first value column, second row — the same space Horos stores ROI vertices in.
/// DISPLAY is 0...1 inside the applicable displayed-area rectangle.
///
/// Anything else is listed on `unsupportedFeatures` and is not applied:
/// Color / Pseudo-Color / Blending / XA-XRF Softcopy Presentation States,
/// shutter, mask, overlay, compound graphics, interpolated/bitmap graphics,
/// a Presentation LUT other than IDENTITY, and a Modality LUT carried on the
/// GSPS.
@objc(HorosGSPSDocument)
public final class GSPSDocument: NSObject {

    @objc public static let grayscaleSoftcopySOPClassUID = "1.2.840.10008.5.1.4.1.1.11.1"
    @objc public static let colorSoftcopySOPClassUID = "1.2.840.10008.5.1.4.1.1.11.2"
    @objc public static let pseudoColorSoftcopySOPClassUID = "1.2.840.10008.5.1.4.1.1.11.3"
    @objc public static let blendingSoftcopySOPClassUID = "1.2.840.10008.5.1.4.1.1.11.4"
    @objc public static let xaXrfSoftcopySOPClassUID = "1.2.840.10008.5.1.4.1.1.11.5"

    @objc public static let documentedSubset = """
        Grayscale Softcopy Presentation State Storage 1.2.840.10008.5.1.4.1.1.11.1
        Matching: ReferencedSOPInstanceUID and optional ReferencedFrameNumber
        Softcopy VOI LUT: Window Center/Width or VOI LUT Sequence
        Displayed Area: 1-based column\\row corners, SCALE TO FIT / TRUE SIZE / MAGNIFY
        Spatial Transformation: Image Rotation 0/90/180/270, Image Horizontal Flip
        Graphic Annotation units PIXEL or DISPLAY; types POINT, POLYLINE, CIRCLE, ELLIPSE; text Anchor Point
        Unsupported features are flagged and not applied; a missing referenced SOP Instance UID is flagged; Pixel Data is never rewritten
        """

    @objc public static let supportedGraphicTypes = ["POINT", "POLYLINE", "CIRCLE", "ELLIPSE"]

    @objc public private(set) var sopClassUID = ""
    @objc public private(set) var sopInstanceUID = ""
    @objc public private(set) var isSupportedSOPClass = false
    @objc public private(set) var referencedImages: [GSPSImageReference] = []
    @objc public private(set) var unsupportedFeatures: [String] = []

    private var rotationDegrees = 0
    private var horizontalFlip = false
    private var voiItems: [GSPSVOIItem] = []
    private var areaItems: [GSPSDisplayedAreaItem] = []
    private var annotationItems: [GSPSAnnotationItem] = []

    @objc(isSoftcopyPresentationStateSOPClass:)
    public static func isSoftcopyPresentationStateSOPClass(_ uid: String?) -> Bool {
        guard let uid, !uid.isEmpty else { return false }
        return [
            grayscaleSoftcopySOPClassUID,
            colorSoftcopySOPClassUID,
            pseudoColorSoftcopySOPClassUID,
            blendingSoftcopySOPClassUID,
            xaXrfSoftcopySOPClassUID,
        ].contains(uid)
    }

    @objc(documentWithJSON:)
    public static func document(json: Data) -> GSPSDocument? {
        GSPSDocument(json: json)
    }

    @objc(documentWithDictionary:)
    public static func document(dictionary: [String: Any]) -> GSPSDocument? {
        GSPSDocument(dictionary: dictionary)
    }

    @objc public convenience init?(json: Data) {
        guard let object = try? JSONSerialization.jsonObject(with: json),
              let dictionary = object as? [String: Any]
        else { return nil }
        self.init(dictionary: dictionary)
    }

    @objc public init?(dictionary: [String: Any]) {
        super.init()
        sopClassUID = GSPSValue.string(dictionary, "SOPClassUID")
        sopInstanceUID = GSPSValue.string(dictionary, "SOPInstanceUID")
        guard !sopClassUID.isEmpty else { return nil }

        isSupportedSOPClass = (sopClassUID == Self.grayscaleSoftcopySOPClassUID)
        if !isSupportedSOPClass {
            unsupportedFeatures.append(Self.flagForUnsupportedSOP(sopClassUID))
        }

        referencedImages = Self.readReferences(in: dictionary["ReferencedSeriesSequence"])
            + Self.readImageSequence(dictionary["ReferencedImageSequence"])
        rotationDegrees = Self.normalizedRotation(GSPSValue.int(dictionary, "ImageRotation"))
        horizontalFlip = GSPSValue.string(dictionary, "ImageHorizontalFlip").uppercased() == "Y"
        voiItems = Self.readVOIItems(dictionary["SoftcopyVOILUTSequence"])
        areaItems = Self.readAreaItems(dictionary["DisplayedAreaSelectionSequence"])
        annotationItems = Self.readAnnotationItems(dictionary["GraphicAnnotationSequence"])
        unsupportedFeatures.append(contentsOf: Self.scanUnsupported(dictionary))
        unsupportedFeatures = Self.unique(unsupportedFeatures)
    }

    @objc(referencesSOPInstanceUID:frame:)
    public func references(sopInstanceUID: String, frame: Int) -> Bool {
        referencedImages.contains { $0.matches(sopInstanceUID: sopInstanceUID, frame: frame) }
    }

    @objc(applyToImages:)
    public func apply(to images: [GSPSAvailableImage]) -> GSPSApplicationResult {
        let result = GSPSApplicationResult()
        result.unsupportedFeatures = unsupportedFeatures
        result.pixelFingerprints = images.map { $0.pixelFingerprint }

        for image in images {
            guard references(sopInstanceUID: image.sopInstanceUID, frame: max(image.frameNumber, 1)) else {
                continue
            }
            guard isSupportedSOPClass else { continue }

            let before = image.pixelFingerprint
            let presentation = presentation(for: image)
            result.presentations.append(presentation)
            result.originalPixelsUnchanged = result.originalPixelsUnchanged && before == image.pixelFingerprint
        }

        for reference in referencedImages {
            let frames = reference.frameNumbers.isEmpty ? [1] : reference.frameNumbers
            for frame in frames {
                let present = images.contains {
                    $0.sopInstanceUID == reference.sopInstanceUID && max($0.frameNumber, 1) == frame
                }
                if !present {
                    let missing = GSPSImageReference()
                    missing.sopInstanceUID = reference.sopInstanceUID
                    missing.sopClassUID = reference.sopClassUID
                    missing.frameNumbers = [frame]
                    result.missingReferences.append(missing)
                }
            }
            if reference.frameNumbers.isEmpty {
                let present = images.contains { $0.sopInstanceUID == reference.sopInstanceUID }
                if !present && result.missingReferences.contains(where: { $0.sopInstanceUID == reference.sopInstanceUID }) == false {
                    result.missingReferences.append(reference)
                }
            }
        }

        for image in images {
            result.originalPixelsUnchanged = result.originalPixelsUnchanged
                && result.pixelFingerprints.contains(image.pixelFingerprint)
        }
        return result
    }

    private func presentation(for image: GSPSAvailableImage) -> GSPSImagePresentation {
        let frame = max(image.frameNumber, 1)
        let presentation = GSPSImagePresentation()
        presentation.sopInstanceUID = image.sopInstanceUID
        presentation.frameNumber = frame
        presentation.rotationDegrees = rotationDegrees
        presentation.horizontalFlip = horizontalFlip

        if let voi = firstApplicable(voiItems, sop: image.sopInstanceUID, frame: frame) {
            if let table = voi.table {
                presentation.voiLUT = table
                presentation.hasVOI = true
                presentation.windowCenter = table.windowCenter
                presentation.windowWidth = table.windowWidth
            } else if let center = voi.windowCenter, let width = voi.windowWidth {
                presentation.hasVOI = true
                presentation.windowCenter = center
                presentation.windowWidth = width
            }
        }

        if let area = firstApplicable(areaItems, sop: image.sopInstanceUID, frame: frame) {
            presentation.displayedArea = area.resolved(columns: image.columns, rows: image.rows)
        }

        let pixelArea = presentation.displayedArea
            ?? GSPSDisplayedArea.fullImage(columns: image.columns, rows: image.rows)
        for item in annotationItems where item.applies(to: image.sopInstanceUID, frame: frame) {
            presentation.annotations.append(contentsOf: item.annotations(in: pixelArea, columns: image.columns, rows: image.rows))
        }
        return presentation
    }

    private func firstApplicable<T: GSPSApplicable>(_ items: [T], sop: String, frame: Int) -> T? {
        if let exact = items.first(where: { $0.restricts(to: sop, frame: frame) }) {
            return exact
        }
        return items.first(where: { $0.references.isEmpty }) ?? items.first
    }

    private static func flagForUnsupportedSOP(_ uid: String) -> String {
        switch uid {
        case colorSoftcopySOPClassUID:
            return "Color Softcopy Presentation State \(uid) is not in the documented GSPS subset"
        case pseudoColorSoftcopySOPClassUID:
            return "Pseudo-Color Softcopy Presentation State \(uid) is not in the documented GSPS subset"
        case blendingSoftcopySOPClassUID:
            return "Blending Softcopy Presentation State \(uid) is not in the documented GSPS subset"
        case xaXrfSoftcopySOPClassUID:
            return "XA/XRF Grayscale Softcopy Presentation State \(uid) is not in the documented GSPS subset"
        default:
            return "SOP Class \(uid) is not Grayscale Softcopy Presentation State Storage"
        }
    }

    private static func normalizedRotation(_ value: Int) -> Int {
        let turned = ((value % 360) + 360) % 360
        let allowed = [0, 90, 180, 270]
        return allowed.contains(turned) ? turned : 0
    }

    private static func unique(_ items: [String]) -> [String] {
        var seen = Set<String>()
        return items.filter { seen.insert($0).inserted }
    }

    private static func readReferences(in series: Any?) -> [GSPSImageReference] {
        GSPSValue.objects(series).flatMap { readImageSequence($0["ReferencedImageSequence"]) }
    }

    private static func readImageSequence(_ sequence: Any?) -> [GSPSImageReference] {
        GSPSValue.objects(sequence).compactMap { item in
            let uid = GSPSValue.string(item, "ReferencedSOPInstanceUID")
            guard !uid.isEmpty else { return nil }
            let reference = GSPSImageReference()
            reference.sopInstanceUID = uid
            reference.sopClassUID = GSPSValue.string(item, "ReferencedSOPClassUID")
            reference.frameNumbers = GSPSValue.ints(item, "ReferencedFrameNumber")
            if reference.frameNumbers.isEmpty {
                reference.frameNumbers = GSPSValue.ints(item, "ReferencedFrameNumbers")
            }
            return reference
        }
    }

    private static func readVOIItems(_ sequence: Any?) -> [GSPSVOIItem] {
        GSPSValue.objects(sequence).map { item in
            let voi = GSPSVOIItem()
            voi.references = readImageSequence(item["ReferencedImageSequence"])
            let centers = GSPSValue.doubles(item, "WindowCenter")
            let widths = GSPSValue.doubles(item, "WindowWidth")
            if let center = centers.first, let width = widths.first {
                voi.windowCenter = center
                voi.windowWidth = width
            }
            if let tableItem = GSPSValue.objects(item["VOILUTSequence"]).first {
                let descriptor = GSPSValue.numbers(tableItem, "LUTDescriptor")
                let data = tableItem["LUTData"] ?? tableItem["LUTDataUS"] ?? tableItem["LUTDataOW"]
                voi.table = VOILookupTable(descriptor: descriptor, data: data, signed: false)
            }
            return voi
        }
    }

    private static func readAreaItems(_ sequence: Any?) -> [GSPSDisplayedAreaItem] {
        GSPSValue.objects(sequence).map { item in
            let area = GSPSDisplayedAreaItem()
            area.references = readImageSequence(item["ReferencedImageSequence"])
            area.tlhc = GSPSValue.doubles(item, "DisplayedAreaTopLeftHandCorner")
            area.brhc = GSPSValue.doubles(item, "DisplayedAreaBottomRightHandCorner")
            area.sizeMode = GSPSValue.string(item, "PresentationSizeMode")
            area.magnification = GSPSValue.doubles(item, "PresentationPixelMagnificationRatio").first
            area.spacing = GSPSValue.doubles(item, "PresentationPixelSpacing")
            return area
        }
    }

    private static func readAnnotationItems(_ sequence: Any?) -> [GSPSAnnotationItem] {
        GSPSValue.objects(sequence).map { item in
            let annotation = GSPSAnnotationItem()
            annotation.references = readImageSequence(item["ReferencedImageSequence"])
            annotation.graphics = GSPSValue.objects(item["GraphicObjectSequence"])
            annotation.texts = GSPSValue.objects(item["TextObjectSequence"])
            return annotation
        }
    }

    private static func scanUnsupported(_ dictionary: [String: Any]) -> [String] {
        var flags: [String] = []
        let keys = [
            "DisplayShutterSequence": "Display Shutter",
            "FrameDisplayShutterSequence": "Frame Display Shutter",
            "ShutterShape": "Display Shutter",
            "ShutterLeftVerticalEdge": "Display Shutter",
            "BitmapDisplayShutterSequence": "Bitmap Display Shutter",
            "MaskSubtractionSequence": "Mask Subtraction",
            "OverlayRows": "Overlay",
            "OverlayData": "Overlay",
            "CompoundGraphicSequence": "Compound Graphic",
            "ModalityLUTSequence": "Modality LUT on the GSPS",
            "SoftcopyPresentationLUTSequence": "Softcopy Presentation LUT",
            "PresentationLUTSequence": "Presentation LUT",
        ]
        func walk(_ object: [String: Any]) {
            for (key, value) in object {
                if let label = keys[key] {
                    flags.append("\(label) is not in the documented GSPS subset")
                }
                if key == "PresentationLUTShape" {
                    let shape = GSPSValue.string(object, "PresentationLUTShape").uppercased()
                    if !shape.isEmpty && shape != "IDENTITY" {
                        flags.append("Presentation LUT Shape \(shape) is not in the documented GSPS subset")
                    }
                }
                if key == "GraphicType" {
                    let type = GSPSValue.string(object, "GraphicType").uppercased()
                    if !type.isEmpty && !supportedGraphicTypes.contains(type) {
                        flags.append("Graphic Type \(type) is not in the documented GSPS subset")
                    }
                }
                if let nested = value as? [String: Any] {
                    walk(nested)
                } else if let array = value as? [Any] {
                    for item in array {
                        if let nested = item as? [String: Any] { walk(nested) }
                    }
                }
            }
        }
        walk(dictionary)
        return flags
    }
}

private protocol GSPSApplicable {
    var references: [GSPSImageReference] { get }
}

extension GSPSApplicable {
    func restricts(to sop: String, frame: Int) -> Bool {
        !references.isEmpty && references.contains { $0.matches(sopInstanceUID: sop, frame: frame) }
    }

    func applies(to sop: String, frame: Int) -> Bool {
        references.isEmpty || restricts(to: sop, frame: frame)
    }
}

@objc(HorosGSPSImageReference)
public final class GSPSImageReference: NSObject {
    @objc public var sopClassUID = ""
    @objc public var sopInstanceUID = ""
    @objc public var frameNumbers: [Int] = []

    func matches(sopInstanceUID: String, frame: Int) -> Bool {
        guard self.sopInstanceUID == sopInstanceUID else { return false }
        if frameNumbers.isEmpty { return true }
        return frameNumbers.contains(frame)
    }
}

@objc(HorosGSPSAvailableImage)
public final class GSPSAvailableImage: NSObject {
    @objc public var sopInstanceUID = ""
    @objc public var frameNumber: Int = 1
    @objc public var columns: Int = 0
    @objc public var rows: Int = 0
    /// A copy of the stored samples. Apply never writes this buffer.
    @objc public var pixelFingerprint = Data()
}

@objc(HorosGSPSDisplayedArea)
public final class GSPSDisplayedArea: NSObject {
    @objc public var column: Int = 0
    @objc public var row: Int = 0
    @objc public var width: Int = 0
    @objc public var height: Int = 0
    @objc public var sizeMode = "SCALE TO FIT"
    @objc public var magnification: Double = 1
    @objc public var spacing: [Double] = []

    @objc public static func fullImage(columns: Int, rows: Int) -> GSPSDisplayedArea {
        let area = GSPSDisplayedArea()
        area.width = max(columns, 0)
        area.height = max(rows, 0)
        return area
    }
}

@objc(HorosGSPSAnnotation)
public final class GSPSAnnotation: NSObject {
    @objc public var kind = ""
    @objc public var text: String?
    public var points: [CGPoint] = []

    @objc public var pointValues: [NSValue] {
        points.map { NSValue(point: NSPoint(x: $0.x, y: $0.y)) }
    }
}

@objc(HorosGSPSImagePresentation)
public final class GSPSImagePresentation: NSObject {
    @objc public var sopInstanceUID = ""
    @objc public var frameNumber: Int = 1
    @objc public var hasVOI = false
    @objc public var windowCenter: Double = 0
    @objc public var windowWidth: Double = 0
    @objc public var voiLUT: VOILookupTable?
    @objc public var rotationDegrees: Int = 0
    @objc public var horizontalFlip = false
    @objc public var displayedArea: GSPSDisplayedArea?
    @objc public var annotations: [GSPSAnnotation] = []
}

@objc(HorosGSPSApplicationResult)
public final class GSPSApplicationResult: NSObject {
    @objc public var presentations: [GSPSImagePresentation] = []
    @objc public var missingReferences: [GSPSImageReference] = []
    @objc public var unsupportedFeatures: [String] = []
    @objc public var originalPixelsUnchanged = true
    @objc public var pixelFingerprints: [Data] = []
}

private final class GSPSVOIItem: GSPSApplicable {
    var references: [GSPSImageReference] = []
    var windowCenter: Double?
    var windowWidth: Double?
    var table: VOILookupTable?
}

private final class GSPSDisplayedAreaItem: GSPSApplicable {
    var references: [GSPSImageReference] = []
    var tlhc: [Double] = []
    var brhc: [Double] = []
    var sizeMode = ""
    var magnification: Double?
    var spacing: [Double] = []

    func resolved(columns: Int, rows: Int) -> GSPSDisplayedArea {
        let area = GSPSDisplayedArea.fullImage(columns: columns, rows: rows)
        if tlhc.count >= 2 && brhc.count >= 2 {
            let left = Int(tlhc[0].rounded(.towardZero)) - 1
            let top = Int(tlhc[1].rounded(.towardZero)) - 1
            let right = Int(brhc[0].rounded(.towardZero)) - 1
            let bottom = Int(brhc[1].rounded(.towardZero)) - 1
            let column = max(0, min(left, right))
            let row = max(0, min(top, bottom))
            area.column = column
            area.row = row
            area.width = max(0, abs(right - left) + 1)
            area.height = max(0, abs(bottom - top) + 1)
        }
        if !sizeMode.isEmpty { area.sizeMode = sizeMode }
        if let magnification { area.magnification = magnification }
        area.spacing = spacing
        return area
    }
}

private final class GSPSAnnotationItem: GSPSApplicable {
    var references: [GSPSImageReference] = []
    var graphics: [[String: Any]] = []
    var texts: [[String: Any]] = []

    func annotations(in area: GSPSDisplayedArea, columns: Int, rows: Int) -> [GSPSAnnotation] {
        var result: [GSPSAnnotation] = []
        for graphic in graphics {
            let type = GSPSValue.string(graphic, "GraphicType").uppercased()
            guard GSPSDocument.supportedGraphicTypes.contains(type) else { continue }
            let units = GSPSValue.string(graphic, "GraphicAnnotationUnits", "GraphicUnits")
            let data = GSPSValue.doubles(graphic, "GraphicData")
            let annotation = GSPSAnnotation()
            annotation.kind = type
            annotation.points = GSPSValue.points(data).map { GSPSValue.toPixel($0, units: units, area: area, columns: columns, rows: rows) }
            if !annotation.points.isEmpty {
                result.append(annotation)
            }
        }
        for text in texts {
            let units = GSPSValue.string(text, "AnchorPointAnnotationUnits", "BoundingBoxAnnotationUnits")
            let anchor = GSPSValue.doubles(text, "AnchorPoint")
            let annotation = GSPSAnnotation()
            annotation.kind = "TEXT"
            annotation.text = GSPSValue.string(text, "UnformattedTextValue")
            if anchor.count >= 2 {
                annotation.points = [GSPSValue.toPixel(CGPoint(x: anchor[0], y: anchor[1]), units: units, area: area, columns: columns, rows: rows)]
            }
            result.append(annotation)
        }
        return result
    }
}

private enum GSPSValue {
    static func objects(_ value: Any?) -> [[String: Any]] {
        if let object = value as? [String: Any] { return [object] }
        if let array = value as? [Any] {
            return array.compactMap { $0 as? [String: Any] }
        }
        return []
    }

    static func string(_ object: [String: Any], _ keys: String...) -> String {
        for key in keys {
            if let text = scalar(object[key]) { return text }
        }
        return ""
    }

    static func scalar(_ value: Any?) -> String? {
        if let text = value as? String { return text }
        if let number = value as? NSNumber { return number.stringValue }
        if let array = value as? [Any], let first = array.first {
            return scalar(first)
        }
        return nil
    }

    static func int(_ object: [String: Any], _ key: String) -> Int {
        ints(object, key).first ?? 0
    }

    static func ints(_ object: [String: Any], _ key: String) -> [Int] {
        doubles(object, key).map { Int($0.rounded()) }
    }

    static func doubles(_ object: [String: Any], _ key: String) -> [Double] {
        numbers(from: object[key]).map { $0.doubleValue }
    }

    static func numbers(_ object: [String: Any], _ key: String) -> [NSNumber] {
        numbers(from: object[key])
    }

    static func numbers(from value: Any?) -> [NSNumber] {
        if let number = value as? NSNumber { return [number] }
        if let text = value as? String, let number = doubleNumber(text) { return [number] }
        if let data = value as? Data {
            return data.map { NSNumber(value: $0) }
        }
        if let array = value as? [Any] {
            return array.flatMap { numbers(from: $0) }
        }
        return []
    }

    static func doubleNumber(_ text: String) -> NSNumber? {
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        if let value = Double(trimmed) { return NSNumber(value: value) }
        return nil
    }

    static func points(_ data: [Double]) -> [CGPoint] {
        stride(from: 0, to: data.count - 1, by: 2).map { CGPoint(x: data[$0], y: data[$0 + 1]) }
    }

    static func toPixel(_ point: CGPoint, units: String, area: GSPSDisplayedArea, columns: Int, rows: Int) -> CGPoint {
        if units.uppercased() != "DISPLAY" { return point }
        let width = Double(area.width > 0 ? area.width : max(columns, 0))
        let height = Double(area.height > 0 ? area.height : max(rows, 0))
        return CGPoint(
            x: Double(area.column) + point.x * width,
            y: Double(area.row) + point.y * height
        )
    }
}
