import Foundation

/// Frame, transfer syntax and per-frame geometry for Philips Ingenuity CT/ECG.
///
/// A study that Horos labels CT/ECG is a CT series plus an ECG waveform. The
/// CT frames stay pictures. The waveform is not. Encapsulated pixel data is
/// not native samples. A cardiac phase is not a frame index. A frame's own
/// Image Position / Orientation wins over the shared functional group and
/// over the object-level tags a legacy-converted file also carries.
@objc(HorosPhilipsCTECG)
public final class PhilipsCTECG: NSObject {
    private static let imageStorage: Set<String> = [
        "1.2.840.10008.5.1.4.1.1.2",
        "1.2.840.10008.5.1.4.1.1.2.1",
        "1.2.840.10008.5.1.4.1.1.2.2",
        "1.3.46.670589.5.0.9",
    ]

    private static let waveformStorage: Set<String> = [
        "1.2.840.10008.5.1.4.1.1.9.1.1",
        "1.2.840.10008.5.1.4.1.1.9.1.2",
        "1.2.840.10008.5.1.4.1.1.9.1.3",
        "1.2.840.10008.5.1.4.1.1.9.2.1",
        "1.2.840.10008.5.1.4.1.1.9.3.1",
    ]

    private static let uncompressedSyntax: Set<String> = [
        "1.2.840.10008.1.2",
        "1.2.840.10008.1.2.1",
        "1.2.840.10008.1.2.2",
    ]

    private static let encapsulatedSyntax: Set<String> = [
        "1.2.840.10008.1.2.4.50",
        "1.2.840.10008.1.2.4.51",
        "1.2.840.10008.1.2.4.57",
        "1.2.840.10008.1.2.4.70",
        "1.2.840.10008.1.2.4.80",
        "1.2.840.10008.1.2.4.81",
        "1.2.840.10008.1.2.4.90",
        "1.2.840.10008.1.2.4.91",
        "1.2.840.10008.1.2.5",
    ]

    private static func trimmed(_ value: String?) -> String? {
        guard let text = value?.trimmingCharacters(in: .whitespacesAndNewlines),
              !text.isEmpty else { return nil }
        return text
    }

    @objc(isImageStorage:)
    public static func isImageStorage(_ sopClassUID: String?) -> Bool {
        guard let uid = trimmed(sopClassUID) else { return false }
        return imageStorage.contains(uid)
    }

    @objc(isWaveformStorage:)
    public static func isWaveformStorage(_ sopClassUID: String?) -> Bool {
        guard let uid = trimmed(sopClassUID) else { return false }
        return waveformStorage.contains(uid)
    }

    /// CT/ECG as a study modality is still an image when the SOP is CT.
    @objc(displaysAsImageWithSOPClassUID:modality:)
    public static func displaysAsImage(sopClassUID: String?, modality: String?) -> Bool {
        _ = modality
        return isImageStorage(sopClassUID) && !isWaveformStorage(sopClassUID)
    }

    @objc(isUncompressedTransferSyntax:)
    public static func isUncompressed(_ transferSyntaxUID: String?) -> Bool {
        guard let uid = trimmed(transferSyntaxUID) else { return false }
        return uncompressedSyntax.contains(uid)
    }

    @objc(isEncapsulatedTransferSyntax:)
    public static func isEncapsulated(_ transferSyntaxUID: String?) -> Bool {
        guard let uid = trimmed(transferSyntaxUID) else { return false }
        return encapsulatedSyntax.contains(uid)
    }

    /// Encapsulated bytes must not be read as native samples (the gradient failure).
    @objc(samplesAreNativeForTransferSyntax:)
    public static func samplesAreNative(forTransferSyntax transferSyntaxUID: String?) -> Bool {
        isUncompressed(transferSyntaxUID)
    }

    @objc(frameIndexForRequested:frameCount:)
    public static func frameIndex(requested: Int, frameCount: Int) -> NSNumber? {
        guard frameCount > 0, requested >= 0, requested < frameCount else { return nil }
        return NSNumber(value: requested)
    }

    @objc(byteLengthForRows:columns:bitsAllocated:samplesPerPixel:)
    public static func byteLength(rows: Int, columns: Int, bitsAllocated: Int,
                                  samplesPerPixel: Int) -> Int {
        guard rows > 0, columns > 0, bitsAllocated > 0, bitsAllocated % 8 == 0,
              samplesPerPixel > 0 else { return 0 }
        return rows * columns * samplesPerPixel * (bitsAllocated / 8)
    }

    /// Per-frame tags win, then the shared group, then the object. Nothing
    /// writes the object back over a frame that already spoke.
    @objc(geometryWithFramePosition:frameOrientation:sharedPosition:sharedOrientation:objectPosition:objectOrientation:)
    public static func geometry(framePosition: [NSNumber]?,
                                frameOrientation: [NSNumber]?,
                                sharedPosition: [NSNumber]?,
                                sharedOrientation: [NSNumber]?,
                                objectPosition: [NSNumber]?,
                                objectOrientation: [NSNumber]?) -> [String: [NSNumber]]? {
        guard let position = firstVector([framePosition, sharedPosition, objectPosition], count: 3),
              let orientation = firstVector([frameOrientation, sharedOrientation, objectOrientation], count: 6)
        else { return nil }

        let origin = position.map(\.doubleValue)
        let along = orientation.map(\.doubleValue)
        let normal = [
            along[1] * along[5] - along[2] * along[4],
            along[2] * along[3] - along[0] * along[5],
            along[0] * along[4] - along[1] * along[3],
        ]
        let dominant = (0..<3).max(by: { abs(normal[$0]) < abs(normal[$1]) }) ?? 2
        let location = origin[dominant]
        return [
            "position": position,
            "orientation": orientation,
            "normal": normal.map { NSNumber(value: $0) },
            "sliceLocation": [NSNumber(value: location)],
        ]
    }

    @objc(pixelIdentityOfSamples:)
    public static func pixelIdentity(_ samples: [NSNumber]) -> NSNumber {
        guard let first = samples.first else { return 0 }
        if samples.allSatisfy({ $0 == first }) { return first }
        var total: Int64 = 0
        for sample in samples { total = total &+ Int64(sample.intValue) }
        return NSNumber(value: total)
    }

    private static func firstVector(_ candidates: [[NSNumber]?], count: Int) -> [NSNumber]? {
        for candidate in candidates {
            guard let values = candidate, values.count == count,
                  values.allSatisfy({ $0.doubleValue.isFinite }) else { continue }
            return values
        }
        return nil
    }
}
