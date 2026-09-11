import Foundation

/// Whether a DICOM object can be handed to the incoming indexer and the
/// thumbnail stack without a divide-by-zero.
///
/// Detection, enhanced functional-group reading and the thumbnail gate are
/// separate answers. The manufacturer string is metadata: it is never a reason
/// to accept or refuse a file. The 2019 Bruker report crashed on a zero
/// divisor while building a series icon, not because the vendor wrote the
/// pixels.
@objc(HorosEnhancedImportAssessment)
public final class EnhancedImportAssessment: NSObject {
    @objc public let detectedDICOM: Bool
    @objc public let sopClassUID: String?
    @objc public let isEnhanced: Bool
    @objc public let frames: Int
    @objc public let rows: Int
    @objc public let columns: Int
    @objc public let bitsAllocated: Int
    @objc public let bitsStored: Int
    @objc public let samplesPerPixel: Int
    @objc public let pixelDataBytes: Int
    @objc public let expectedPixelBytes: Int
    @objc public let pixelSpacingX: Double
    @objc public let pixelSpacingY: Double
    @objc public let hasSharedFunctionalGroups: Bool
    @objc public let hasPerFrameFunctionalGroups: Bool
    @objc public let manufacturer: String?
    @objc public let transferSyntaxUID: String?
    @objc public let recordedError: String?
    @objc public let incompatibilityReasons: [String]
    @objc public let thumbnailCompatible: Bool
    @objc public let mayMergeIntoIncoming: Bool

    @objc public init(detectedDICOM: Bool,
                      sopClassUID: String?,
                      isEnhanced: Bool,
                      frames: Int,
                      rows: Int,
                      columns: Int,
                      bitsAllocated: Int,
                      bitsStored: Int,
                      samplesPerPixel: Int,
                      pixelDataBytes: Int,
                      expectedPixelBytes: Int,
                      pixelSpacingX: Double,
                      pixelSpacingY: Double,
                      hasSharedFunctionalGroups: Bool,
                      hasPerFrameFunctionalGroups: Bool,
                      manufacturer: String?,
                      transferSyntaxUID: String?,
                      recordedError: String?,
                      incompatibilityReasons: [String],
                      thumbnailCompatible: Bool,
                      mayMergeIntoIncoming: Bool) {
        self.detectedDICOM = detectedDICOM
        self.sopClassUID = sopClassUID
        self.isEnhanced = isEnhanced
        self.frames = frames
        self.rows = rows
        self.columns = columns
        self.bitsAllocated = bitsAllocated
        self.bitsStored = bitsStored
        self.samplesPerPixel = samplesPerPixel
        self.pixelDataBytes = pixelDataBytes
        self.expectedPixelBytes = expectedPixelBytes
        self.pixelSpacingX = pixelSpacingX
        self.pixelSpacingY = pixelSpacingY
        self.hasSharedFunctionalGroups = hasSharedFunctionalGroups
        self.hasPerFrameFunctionalGroups = hasPerFrameFunctionalGroups
        self.manufacturer = manufacturer
        self.transferSyntaxUID = transferSyntaxUID
        self.recordedError = recordedError
        self.incompatibilityReasons = incompatibilityReasons
        self.thumbnailCompatible = thumbnailCompatible
        self.mayMergeIntoIncoming = mayMergeIntoIncoming
        super.init()
    }
}

/// Isolated detection, enhanced read and thumbnail/incoming gate for a DICOM
/// file. The incoming scanner asks this before moving a file into the indexed
/// store; the thumbnail path must not be the first thing to notice a zero size.
@objc(HorosEnhancedImportTriage)
public final class EnhancedImportTriage: NSObject {

    private static let enhancedSOPClasses: Set<String> = [
        "1.2.840.10008.5.1.4.1.1.2.1",
        "1.2.840.10008.5.1.4.1.1.2.2",
        "1.2.840.10008.5.1.4.1.1.4.1",
        "1.2.840.10008.5.1.4.1.1.4.2",
        "1.2.840.10008.5.1.4.1.1.4.4",
        "1.2.840.10008.5.1.4.1.1.128",
        "1.2.840.10008.5.1.4.1.1.130",
        "1.2.840.10008.5.1.4.1.1.6.2",
        "1.2.840.10008.5.1.4.1.1.12.1.1",
        "1.2.840.10008.5.1.4.1.1.12.2.1"
    ]

    @objc(detectDICOMAtPath:)
    public static func detectDICOM(atPath path: String) -> Bool {
        guard let data = try? Data(contentsOf: URL(fileURLWithPath: path), options: .mappedIfSafe) else {
            return false
        }
        return hasDICOMPreamble(data)
    }

    @objc(assessPath:)
    public static func assessPath(_ path: String) -> EnhancedImportAssessment {
        guard let data = try? Data(contentsOf: URL(fileURLWithPath: path), options: .mappedIfSafe),
              hasDICOMPreamble(data),
              let parsed = DICOMTriageMetadata.parse(data) else {
            return EnhancedImportAssessment(
                detectedDICOM: false, sopClassUID: nil, isEnhanced: false,
                frames: 0, rows: 0, columns: 0, bitsAllocated: 0, bitsStored: 0,
                samplesPerPixel: 0, pixelDataBytes: 0, expectedPixelBytes: 0,
                pixelSpacingX: 0, pixelSpacingY: 0,
                hasSharedFunctionalGroups: false, hasPerFrameFunctionalGroups: false,
                manufacturer: nil, transferSyntaxUID: nil,
                recordedError: "was not recognised as DICOM",
                incompatibilityReasons: ["was not recognised as DICOM"],
                thumbnailCompatible: false, mayMergeIntoIncoming: false)
        }

        let sop = parsed.string(group: 0x0008, element: 0x0016)
        let frames = max(parsed.int(group: 0x0028, element: 0x0008) ?? 1, 1)
        let rows = parsed.int(group: 0x0028, element: 0x0010) ?? 0
        let columns = parsed.int(group: 0x0028, element: 0x0011) ?? 0
        let bitsAllocated = parsed.int(group: 0x0028, element: 0x0100) ?? 0
        let bitsStored = parsed.int(group: 0x0028, element: 0x0101) ?? bitsAllocated
        let samples = max(parsed.int(group: 0x0028, element: 0x0002) ?? 1, 1)
        let spacing = parsed.pixelSpacing
        let pixelBytes = parsed.pixelDataBytes
        var expected = 1
        var sizeOverflow = false
        for factor in [rows, columns, frames, bitsAllocated / 8, samples] {
            let product = expected.multipliedReportingOverflow(by: factor)
            if product.overflow { sizeOverflow = true; expected = 0; break }
            expected = product.partialValue
        }
        let shared = parsed.contains(group: 0x5200, element: 0x9229)
        let perFrame = parsed.contains(group: 0x5200, element: 0x9230)
        let enhanced = shared || enhancedSOPClasses.contains(sop ?? "")
        let manufacturer = parsed.string(group: 0x0008, element: 0x0070)

        var reasons: [String] = []
        var error: String?

        let structuredReport = sop?.hasPrefix("1.2.840.10008.5.1.4.1.1.88.") == true
        if structuredReport && !parsed.hasPixelData {
            // SR is persisted and queried without pretending it has a thumbnail.
        } else if rows < 1 || columns < 1 {
            let text = "image size is \(rows) by \(columns), which the thumbnail stack cannot load"
            reasons.append(text)
            error = text
        } else if bitsAllocated != 8 && bitsAllocated != 16 && bitsAllocated != 32 {
            let text = "BitsAllocated is \(bitsAllocated), which the pixel stack cannot load"
            reasons.append(text)
            error = text
        } else if sizeOverflow {
            let text = "image dimensions exceed the supported pixel byte count"
            reasons.append(text)
            error = text
        } else if !parsed.hasPixelData {
            error = "carries no Pixel Data element"
        } else if !parsed.encapsulated && expected > 0 && pixelBytes < expected {
            error = "Pixel Data is \(pixelBytes) bytes where \(expected) are needed"
        }

        let thumbnailOK = reasons.isEmpty
        return EnhancedImportAssessment(
            detectedDICOM: true, sopClassUID: sop, isEnhanced: enhanced,
            frames: frames, rows: rows, columns: columns,
            bitsAllocated: bitsAllocated, bitsStored: bitsStored,
            samplesPerPixel: samples, pixelDataBytes: pixelBytes,
            expectedPixelBytes: expected,
            pixelSpacingX: spacing.x, pixelSpacingY: spacing.y,
            hasSharedFunctionalGroups: shared, hasPerFrameFunctionalGroups: perFrame,
            manufacturer: manufacturer,
            transferSyntaxUID: parsed.string(group: 0x0002, element: 0x0010),
            recordedError: error, incompatibilityReasons: reasons,
            thumbnailCompatible: thumbnailOK, mayMergeIntoIncoming: thumbnailOK)
    }

    private static func hasDICOMPreamble(_ data: Data) -> Bool {
        guard data.count >= 132 else { return false }
        return data[128..<132].elementsEqual("DICM".utf8)
    }

}
