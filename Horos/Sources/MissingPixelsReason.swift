import Foundation

/// Why a frame has no picture in it.
///
/// An object can be listed as an image and carry nothing to show: a Hardcopy
/// record with no Pixel Data element at all, a multi-frame object whose later
/// frames decode to nothing, a frame the codec refused. Until now all of those
/// looked the same on screen as a dark image, and the only thing that said
/// otherwise was a line in the console.
///
/// The sentences are short because they are drawn over the image, beside
/// "Vertically Flipped" and "VOI LUT Applied", where there is room for one line.
@objc(HorosMissingPixelsReason)
public final class MissingPixelsReason: NSObject {
    /// The object carries no `Pixel Data` element at all, so there was never a
    /// picture to decode.
    @objc public static func reasonForAbsentPixelData() -> String {
        return NSLocalizedString("This object carries no image data",
                                 comment: "shown over an empty frame")
    }

    /// The object's SOP class is not an image class at all - a spectrum, raw
    /// data, a private class the manufacturer defines. It is a legitimate thing
    /// to receive and keep; it just has no picture in it, and inventing one is
    /// worse than saying so.
    @objc(reasonForNonImageStorage:)
    public static func reasonForNonImageStorage(_ sopClassUID: String?) -> String {
        let text = NSLocalizedString("This object is not an image",
                                     comment: "shown over an empty frame")
        guard let uid = sopClassUID?.trimmingCharacters(in: .whitespacesAndNewlines),
              !uid.isEmpty else { return text }
        return text + " (" + uid + ")"
    }

    /// The frame could not be loaded, for a reason nothing further up named.
    @objc public static func reasonForUnreadableFrame() -> String {
        return NSLocalizedString("This image could not be read",
                                 comment: "shown over an empty frame")
    }

    /// The Pixel Data element holds a whole video stream rather than frames -
    /// the MPEG and HEVC transfer syntaxes - and the stream could not be turned
    /// into pictures: a codec this build does not decode, or bytes the decoder
    /// refused. Handing the compressed stream to the colour conversion instead
    /// drew the bytes of the stream as though they were pixels.
    @objc(reasonForUndecodableVideoStream:)
    public static func reasonForUndecodableVideoStream(_ transferSyntaxUID: String?) -> String {
        let text = NSLocalizedString("This video stream could not be decoded",
                                     comment: "shown over an empty frame")
        guard let uid = transferSyntaxUID?.trimmingCharacters(in: .whitespacesAndNewlines),
              !uid.isEmpty else { return text }
        return text + " (" + uid + ")"
    }

    /// The stream decodes, and to a picture of a different size than the object
    /// says it carries. Copying it into the frame the header describes would
    /// read past the end of it or leave part of it behind.
    @objc(reasonForVideoSizeMismatch:by:expectedWidth:by:)
    public static func reasonForVideoSizeMismatch(_ width: Int, by height: Int,
                                                  expectedWidth: Int, by expectedHeight: Int) -> String {
        let format = NSLocalizedString("The video is %d by %d, not %d by %d",
                                       comment: "shown over an empty frame; the sizes are in pixels")
        return String(format: format, width, height, expectedWidth, expectedHeight)
    }

    /// The frame is there and is shorter than the picture it has to fill. The
    /// rest is left black rather than filled with whatever was in the buffer,
    /// and saying so is the difference between a dark examination and a frame
    /// that arrived incomplete.
    @objc(reasonForShortFrame:of:)
    public static func reasonForShortFrame(_ carried: Int, of needed: Int) -> String {
        let format = NSLocalizedString("The frame carries %d of %d bytes",
                                       comment: "shown over a frame shorter than the image")
        return String(format: format, carried, needed)
    }

    /// The element is there and this frame of it decoded to nothing.
    @objc(reasonForEmptyFrame:)
    public static func reasonForEmptyFrame(_ frame: Int) -> String {
        let format = NSLocalizedString("Frame %d carries no pixels",
                                       comment: "shown over an empty frame; %d is the frame number")
        // The frames are numbered from zero inside, and from one on screen,
        // where they are already shown that way as "Im: 3/8".
        return String(format: format, frame + 1)
    }
}
