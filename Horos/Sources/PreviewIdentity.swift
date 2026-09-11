import Foundation

/// What the database preview is allowed to show, and what it is (#380 D).
///
/// The browser's preview reuses pixels from an open viewer when the same file
/// is already loaded, and keeps an array of frames for the selected study or
/// series. Both are identity questions: the frame drawn must be the frame that
/// was asked for, and a series-wide preview must be one series of image frames
/// with the same geometry — not a mixture, and not a Structured Report or a
/// Segmentation, which have no displayable pixel frame of their own.
///
/// This type answers those questions from numbers and identifiers only. It
/// loads nothing, owns no cache, and never decides what to draw: the caller
/// asks, and on a refusal falls back to the single image it can prove.

/// One frame, as the database knows it before any pixel is read.
@objc(HorosPreviewFrame)
public final class PreviewFrame: NSObject {
    @objc public let path: String
    @objc public let sopInstanceUID: String
    @objc public let seriesInstanceUID: String
    @objc public let sopClassUID: String
    @objc public let modality: String
    @objc public let frameNumber: Int
    @objc public let frameCount: Int
    @objc public let rows: Int
    @objc public let columns: Int
    @objc public let seriesID: Int

    @objc public init(path: String, sopInstanceUID: String, seriesInstanceUID: String, sopClassUID: String,
                      modality: String, frameNumber: Int, frameCount: Int, rows: Int, columns: Int, seriesID: Int) {
        self.path = path; self.sopInstanceUID = sopInstanceUID; self.seriesInstanceUID = seriesInstanceUID
        self.sopClassUID = sopClassUID; self.modality = modality; self.frameNumber = frameNumber
        self.frameCount = frameCount; self.rows = rows; self.columns = columns; self.seriesID = seriesID
    }

    @objc public var description_: String {
        "\(path)#\(frameNumber) [\(seriesInstanceUID)]"
    }
}

@objc(HorosPreviewIdentity)
public final class PreviewIdentity: NSObject {
    /// Modalities whose instances carry no displayable frame of their own.
    @objc public static let nonPixelModalities: Set<String> = ["SR", "SEG", "PR", "KO", "RTSTRUCT", "RTPLAN", "AU", "DOC"]

    /// SOP classes of the same, by their DICOM UID roots: Structured Reports
    /// (1.2.840.10008.5.1.4.1.1.88.*), Segmentation (…66.4), Presentation
    /// States (…11.*), Key Object Selection (…88.59) and Encapsulated PDF
    /// (…104.1).
    @objc public static let nonPixelSOPClassPrefixes: [String] = [
        "1.2.840.10008.5.1.4.1.1.88.", "1.2.840.10008.5.1.4.1.1.66.4",
        "1.2.840.10008.5.1.4.1.1.11.", "1.2.840.10008.5.1.4.1.1.104.",
    ]

    /// True when this frame is a pixel frame the preview can render.
    @objc public static func isPreviewable(_ frame: PreviewFrame) -> Bool {
        refusalForPreviewing(frame) == nil
    }

    /// The reason this frame cannot be previewed as an image, or nil.
    @objc public static func refusalForPreviewing(_ frame: PreviewFrame) -> String? {
        let modality = frame.modality.trimmingCharacters(in: .whitespacesAndNewlines).uppercased()
        if nonPixelModalities.contains(modality) {
            return "\(modality) instances carry no displayable frame; the preview keeps its icon."
        }
        for prefix in nonPixelSOPClassPrefixes where frame.sopClassUID.hasPrefix(prefix) {
            return "SOP class \(frame.sopClassUID) carries no displayable frame; the preview keeps its icon."
        }
        if frame.rows <= 0 || frame.columns <= 0 {
            return "The frame has no dimensions (\(frame.columns)×\(frame.rows))."
        }
        if frame.frameNumber < 0 || (frame.frameCount > 0 && frame.frameNumber >= frame.frameCount) {
            return "Frame \(frame.frameNumber) is outside the \(frame.frameCount) frame(s) of \(frame.sopInstanceUID)."
        }
        return nil
    }

    /// Whether a candidate already loaded elsewhere — a copy of an open
    /// viewer's pixels — really is the requested frame. Path alone is not
    /// enough: a multiframe file appears once per frame, and the same file can
    /// be indexed under more than one series.
    @objc public static func refusalForReusing(_ candidate: PreviewFrame, asRequested requested: PreviewFrame) -> String? {
        if candidate.path != requested.path {
            return "A preview frame from \(candidate.path) cannot stand for \(requested.path)."
        }
        if candidate.frameNumber != requested.frameNumber {
            return "Frame \(candidate.frameNumber) of \(candidate.path) is not frame \(requested.frameNumber)."
        }
        if !candidate.seriesInstanceUID.isEmpty && !requested.seriesInstanceUID.isEmpty
            && candidate.seriesInstanceUID != requested.seriesInstanceUID {
            return "The loaded frame belongs to series \(candidate.seriesInstanceUID), not \(requested.seriesInstanceUID)."
        }
        if candidate.seriesID != requested.seriesID && candidate.seriesID >= 0 && requested.seriesID >= 0 {
            return "The loaded frame belongs to series number \(candidate.seriesID), not \(requested.seriesID)."
        }
        if candidate.rows != requested.rows || candidate.columns != requested.columns {
            return "The loaded frame is \(candidate.columns)×\(candidate.rows), the requested one \(requested.columns)×\(requested.rows)."
        }
        return nil
    }

    /// Whether these frames may be treated as one series for whole-series
    /// preview work (scrubbing, a volume, a thickness): one series, image
    /// frames only, same size, no repeated frame.
    @objc public static func refusalForSeriesPreview(_ frames: [PreviewFrame]) -> String? {
        guard let first = frames.first else { return "There is no frame to preview." }
        if let refusal = refusalForPreviewing(first) { return refusal }
        var seen = Set<String>()
        for frame in frames {
            if let refusal = refusalForPreviewing(frame) { return refusal }
            if frame.seriesInstanceUID != first.seriesInstanceUID {
                return "The preview would mix series \(first.seriesInstanceUID) and \(frame.seriesInstanceUID)."
            }
            if frame.rows != first.rows || frame.columns != first.columns {
                return "The preview would mix \(first.columns)×\(first.rows) and \(frame.columns)×\(frame.rows) frames."
            }
            let key = "\(frame.path)#\(frame.frameNumber)"
            if !seen.insert(key).inserted {
                return "The preview would show \(key) twice."
            }
        }
        return nil
    }
}
