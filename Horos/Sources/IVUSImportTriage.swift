import Foundation

/// Whether an IVUS / ultrasound object can be handed to the incoming indexer
/// and the thumbnail stack without taking the process down.
///
/// Detection, region/calibration reading and the thumbnail gate are separate
/// answers. The manufacturer string is metadata: it is never a reason to
/// accept or refuse a file. The 2018 Volcano report crashed while building a
/// series icon, not because the vendor wrote the pixels.
@objc(HorosIVUSImportAssessment)
public final class IVUSImportAssessment: NSObject {
    @objc public let detectedDICOM: Bool
    @objc public let appliesToFile: Bool
    @objc public let sopClassUID: String?
    @objc public let modality: String?
    @objc public let manufacturer: String?
    @objc public let transferSyntaxUID: String?
    @objc public let frames: Int
    @objc public let rows: Int
    @objc public let columns: Int
    @objc public let bitsAllocated: Int
    @objc public let photometricInterpretation: String?
    @objc public let hasUltrasoundRegions: Bool
    @objc public let hasIVUSAcquisition: Bool
    @objc public let physicalDeltaX: Double
    @objc public let physicalDeltaY: Double
    @objc public let pixelDataBytes: Int
    @objc public let hasPixelData: Bool
    @objc public let hasPaletteLUT: Bool
    @objc public let recordedError: String?
    @objc public let incompatibilityReasons: [String]
    @objc public let thumbnailCompatible: Bool
    @objc public let mayMergeIntoIncoming: Bool

    @objc public init(detectedDICOM: Bool,
                      appliesToFile: Bool,
                      sopClassUID: String?,
                      modality: String?,
                      manufacturer: String?,
                      transferSyntaxUID: String?,
                      frames: Int,
                      rows: Int,
                      columns: Int,
                      bitsAllocated: Int,
                      photometricInterpretation: String?,
                      hasUltrasoundRegions: Bool,
                      hasIVUSAcquisition: Bool,
                      physicalDeltaX: Double,
                      physicalDeltaY: Double,
                      pixelDataBytes: Int,
                      hasPixelData: Bool,
                      hasPaletteLUT: Bool,
                      recordedError: String?,
                      incompatibilityReasons: [String],
                      thumbnailCompatible: Bool,
                      mayMergeIntoIncoming: Bool) {
        self.detectedDICOM = detectedDICOM
        self.appliesToFile = appliesToFile
        self.sopClassUID = sopClassUID
        self.modality = modality
        self.manufacturer = manufacturer
        self.transferSyntaxUID = transferSyntaxUID
        self.frames = frames
        self.rows = rows
        self.columns = columns
        self.bitsAllocated = bitsAllocated
        self.photometricInterpretation = photometricInterpretation
        self.hasUltrasoundRegions = hasUltrasoundRegions
        self.hasIVUSAcquisition = hasIVUSAcquisition
        self.physicalDeltaX = physicalDeltaX
        self.physicalDeltaY = physicalDeltaY
        self.pixelDataBytes = pixelDataBytes
        self.hasPixelData = hasPixelData
        self.hasPaletteLUT = hasPaletteLUT
        self.recordedError = recordedError
        self.incompatibilityReasons = incompatibilityReasons
        self.thumbnailCompatible = thumbnailCompatible
        self.mayMergeIntoIncoming = mayMergeIntoIncoming
        super.init()
    }
}

/// Isolated IVUS / ultrasound detection and thumbnail/incoming gate.
/// The incoming scanner and the series-icon path ask this before
/// `loadDICOMDCMFramework` sees the file; a diagnosis is recorded so the next
/// database open does not retry a crash.
@objc(HorosIVUSImportTriage)
public final class IVUSImportTriage: NSObject {

    private static let ultrasoundSOPClasses: Set<String> = [
        "1.2.840.10008.5.1.4.1.1.3.1",
        "1.2.840.10008.5.1.4.1.1.6.1",
        "1.2.840.10008.5.1.4.1.1.6.2"
    ]

    private static let implicitLittleEndian = "1.2.840.10008.1.2"

    @objc(detectDICOMAtPath:)
    public static func detectDICOM(atPath path: String) -> Bool {
        guard let data = try? Data(contentsOf: URL(fileURLWithPath: path), options: .mappedIfSafe) else {
            return false
        }
        return hasDICOMPreamble(data)
    }

    @objc(assessPath:)
    public static func assessPath(_ path: String) -> IVUSImportAssessment {
        guard let data = try? Data(contentsOf: URL(fileURLWithPath: path), options: .mappedIfSafe),
              hasDICOMPreamble(data),
              let parsed = DICOMTriageMetadata.parse(data) else {
            return IVUSImportAssessment(
                detectedDICOM: false, appliesToFile: false,
                sopClassUID: nil, modality: nil, manufacturer: nil,
                transferSyntaxUID: nil, frames: 0, rows: 0, columns: 0,
                bitsAllocated: 0, photometricInterpretation: nil,
                hasUltrasoundRegions: false, hasIVUSAcquisition: false,
                physicalDeltaX: 0, physicalDeltaY: 0,
                pixelDataBytes: 0, hasPixelData: false, hasPaletteLUT: false,
                recordedError: "was not recognised as DICOM",
                incompatibilityReasons: ["was not recognised as DICOM"],
                thumbnailCompatible: false, mayMergeIntoIncoming: false)
        }

        let sop = parsed.string(group: 0x0008, element: 0x0016)
        let modality = parsed.string(group: 0x0008, element: 0x0060)
        let manufacturer = parsed.string(group: 0x0008, element: 0x0070)
        let transfer = parsed.string(group: 0x0002, element: 0x0010)
        let frames = max(parsed.int(group: 0x0028, element: 0x0008) ?? 1, 1)
        let rows = parsed.int(group: 0x0028, element: 0x0010) ?? 0
        let columns = parsed.int(group: 0x0028, element: 0x0011) ?? 0
        let bitsAllocated = parsed.int(group: 0x0028, element: 0x0100) ?? 0
        let samples = max(parsed.int(group: 0x0028, element: 0x0002) ?? 1, 1)
        let photometric = parsed.string(group: 0x0028, element: 0x0004)
        let hasRegions = parsed.contains(group: 0x0018, element: 0x6011)
        let acquisition = parsed.string(group: 0x0018, element: 0x3100)
        let hasAcquisition = acquisition != nil
        let modalityName = (modality ?? "").trimmingCharacters(in: .whitespaces).uppercased()
        let applies = modalityName == "US" || modalityName == "IVUS"
            || ultrasoundSOPClasses.contains(sop ?? "")
            || hasRegions || hasAcquisition
        let hasPaletteLUT = parsed.contains(group: 0x0028, element: 0x1101)
            || parsed.contains(group: 0x0028, element: 0x1102)
            || parsed.contains(group: 0x0028, element: 0x1103)
            || parsed.contains(group: 0x0028, element: 0x1201)

        if applies == false {
            return IVUSImportAssessment(
                detectedDICOM: true, appliesToFile: false,
                sopClassUID: sop, modality: modality, manufacturer: manufacturer,
                transferSyntaxUID: transfer, frames: frames, rows: rows, columns: columns,
                bitsAllocated: bitsAllocated, photometricInterpretation: photometric,
                hasUltrasoundRegions: hasRegions, hasIVUSAcquisition: hasAcquisition,
                physicalDeltaX: parsed.double(group: 0x0018, element: 0x602C) ?? 0,
                physicalDeltaY: parsed.double(group: 0x0018, element: 0x602E) ?? 0,
                pixelDataBytes: parsed.pixelDataBytes, hasPixelData: parsed.hasPixelData,
                hasPaletteLUT: hasPaletteLUT,
                recordedError: nil, incompatibilityReasons: [],
                thumbnailCompatible: true, mayMergeIntoIncoming: true)
        }

        var reasons: [String] = []
        var error: String?

        if rows < 1 || columns < 1 {
            let text = "image size is \(rows) by \(columns), which the thumbnail stack cannot load"
            reasons.append(text)
            error = text
        } else if bitsAllocated != 8 && bitsAllocated != 16 && bitsAllocated != 32 {
            let text = "BitsAllocated is \(bitsAllocated), which the pixel stack cannot load"
            reasons.append(text)
            error = text
        } else if (photometric ?? "").uppercased().contains("PALETTE") && hasPaletteLUT == false {
            let text = "PALETTE COLOR has no lookup table, which the pixel stack cannot load"
            reasons.append(text)
            error = text
        } else if parsed.hasPixelData == false {
            let text = "carries no Pixel Data element"
            reasons.append(text)
            error = text
        } else if parsed.encapsulated == false {
            let bytesPerSample = max(bitsAllocated / 8, 1)
            let oneFrame = rows * columns * bytesPerSample * samples
            if oneFrame > 0 && parsed.pixelDataBytes > 0 && parsed.pixelDataBytes < oneFrame {
                let text = "Pixel Data is \(parsed.pixelDataBytes) bytes where \(oneFrame) are needed for one frame"
                reasons.append(text)
                error = text
            }
        }

        let thumbnailOK = reasons.isEmpty
        return IVUSImportAssessment(
            detectedDICOM: true, appliesToFile: true,
            sopClassUID: sop, modality: modality, manufacturer: manufacturer,
            transferSyntaxUID: transfer, frames: frames, rows: rows, columns: columns,
            bitsAllocated: bitsAllocated, photometricInterpretation: photometric,
            hasUltrasoundRegions: hasRegions, hasIVUSAcquisition: hasAcquisition,
            physicalDeltaX: parsed.double(group: 0x0018, element: 0x602C) ?? 0,
            physicalDeltaY: parsed.double(group: 0x0018, element: 0x602E) ?? 0,
            pixelDataBytes: parsed.pixelDataBytes, hasPixelData: parsed.hasPixelData,
            hasPaletteLUT: hasPaletteLUT,
            recordedError: error, incompatibilityReasons: reasons,
            thumbnailCompatible: thumbnailOK, mayMergeIntoIncoming: thumbnailOK)
    }

    private static func hasDICOMPreamble(_ data: Data) -> Bool {
        guard data.count >= 132 else { return false }
        return data[128..<132].elementsEqual("DICM".utf8)
    }

}
