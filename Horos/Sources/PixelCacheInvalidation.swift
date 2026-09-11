import Foundation

/// Whether drawing a frame writes display pixels into the buffer a ROI measures
/// (#373, A111).
///
/// `DCMPix.baseAddr` is a cache: `-compute8bitRepresentation` rebuilds it from
/// `fImage` whenever `needToCompute8bitRepresentation` is set, and the getter
/// clears the flag as it rebuilds. For an RGB image, `-getROIValue:::` reads
/// that same buffer — so the cache is not only what is shown, it is also what is
/// measured.
///
/// `-[DCMView loadTextureIn:…]` runs the RGB colour transfer **in place** over
/// it, and the read that supplies the destination pointer has already cleared
/// the flag. Left alone, the draw therefore hands the next mean, min, max and
/// standard deviation the CLUT'd display pixels. A111 requires the opposite:
/// ROIs and measurements keep the original values.
///
/// This states which draws do that writing, so the view can mark the cache stale
/// once the texture is uploaded. It costs nothing on the drawing path: those
/// same draws already begin by invalidating the cache through
/// `-reapplyWindowLevel`.
@objc(HorosPixelCacheInvalidation)
public final class PixelCacheInvalidation: NSObject {
    /// Mirrors the branch structure of `loadTextureIn:`. `isRGB` is the view's
    /// local, which `isLUT12Bit` may have forced true; that 12-bit branch is the
    /// one RGB case that writes nothing, so it has to be named separately.
    /// `colorTransfer` is the raw flag — the factors are folded in here, as the
    /// view folds them into its `localColorTransfer`.
    @objc(displayTransformWritesIntoPixelCacheWithIsRGB:isLUT12Bit:colorTransfer:blending:redFactor:greenFactor:blueFactor:)
    public static func displayTransformWritesIntoPixelCache(
        isRGB: Bool,
        isLUT12Bit: Bool,
        colorTransfer: Bool,
        blending: Bool,
        redFactor: Float,
        greenFactor: Float,
        blueFactor: Float) -> Bool
    {
        guard isRGB, !isLUT12Bit else { return false }
        let factored = redFactor != 1 || greenFactor != 1 || blueFactor != 1
        return colorTransfer || blending || factored
    }
}
