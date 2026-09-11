import Foundation

/// The far end of a thick slab, in slice indices (#373, A295).
///
/// A viewer showing a thick slab covers `stack` slices starting at the current
/// one. When it tells another viewer where it is, it sends both ends so the
/// other can draw the band rather than a single line — `DCMPix` for the near
/// end, `DCMPix2` for the far one.
///
/// Which slice is the far end depends on `flippedData`: with the series
/// reversed the slab runs the other way, so the far end is *below* the current
/// index, not above it. `-[DCMView syncMessage:]` knew that and
/// `-sync3DPosition` — the one that carries the patient coordinates of the
/// crosshair — did not, so a flipped series sent the band from the wrong side of
/// the current slice. Both now ask here.
@objc(HorosThickSlabRange)
public final class ThickSlabRange: NSObject {
    /// `-1` when there is no slab: a single slice has no second end to send.
    /// Otherwise the index of the far end, clamped into `0..<count`, because a
    /// slab may reach past either end of a series.
    @objc(farEndIndexForCurrentIndex:stack:count:flippedData:)
    public static func farEndIndex(currentIndex: Int, stack: Int, count: Int,
                                   flippedData: Bool) -> Int
    {
        guard stack > 1, count > 0 else { return -1 }
        let far = flippedData ? currentIndex - (stack - 1) : currentIndex + (stack - 1)
        return min(max(far, 0), count - 1)
    }
}
