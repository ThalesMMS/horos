import Foundation

/// Window level and width on a flythrough path, after interpolation.
///
/// `FlyThru` interpolates WL and WW as independent scalars through the same
/// spline it uses for the camera. Cardinal splines overshoot: between a wide
/// window and a narrow one the width can pass through zero or go negative, and
/// the level can leave the range of the keyframes. The path then stored those
/// values as `long`, so a width of 1.7 became 1. `VRView setCamera:` only
/// applied the transfer function when `ww > 1`, so those frames kept a stale
/// or degenerate window. The black pixels in the exported movie were voxels
/// mapped outside the transfer interval; they were not the framebuffer crop.
///
/// Keyframes themselves were fine: they used the stored camera, not the
/// overshot samples. This keeps interpolated windows inside the keyframe
/// envelope, never zero, and as floats. `setCamera:` applies the transfer
/// before the capture path reads the drawable.
@objc(HorosFlyThruWindow)
public final class FlyThruWindow: NSObject {

    /// Smallest width the VR transfer table will accept. Zero is the camera
    /// sentinel for "no window stored"; applying it would reset to full window.
    @objc public static let minimumWidth: Double = 1

    /// `value` kept inside `[rangeMin, rangeMax]`. Non-finite input becomes
    /// the lower bound when that bound is finite, otherwise 0.
    @objc(clampedLevel:rangeMin:rangeMax:)
    public static func clampedLevel(_ value: Double, rangeMin: Double, rangeMax: Double) -> Double {
        let lo = min(rangeMin, rangeMax)
        let hi = max(rangeMin, rangeMax)
        guard value.isFinite else { return lo.isFinite ? lo : 0 }
        if lo.isFinite && value < lo { return lo }
        if hi.isFinite && value > hi { return hi }
        return value
    }

    /// Like `clampedLevel`, then never narrower than `minimumWidth`.
    @objc(clampedWidth:rangeMin:rangeMax:)
    public static func clampedWidth(_ value: Double, rangeMin: Double, rangeMax: Double) -> Double {
        let lo = min(rangeMin, rangeMax)
        let hi = max(rangeMin, rangeMax)
        let floor = lo.isFinite ? max(lo, minimumWidth) : minimumWidth
        let ceiling = hi.isFinite ? max(hi, floor) : floor
        let clamped = clampedLevel(value, rangeMin: floor, rangeMax: ceiling)
        if !clamped.isFinite || clamped < minimumWidth { return minimumWidth }
        return clamped
    }

    /// Lower end of the VR color/opacity table: `level - width/2`.
    @objc(transferLowerBoundForLevel:width:)
    public static func transferLowerBound(level: Double, width: Double) -> Double {
        return level - width / 2
    }

    /// Upper end of the VR color/opacity table: `level + width/2`.
    @objc(transferUpperBoundForLevel:width:)
    public static func transferUpperBound(level: Double, width: Double) -> Double {
        return level + width / 2
    }

    /// Whether a sample of `value` falls inside the transfer interval.
    /// VTK's `BuildFunctionFromTable` maps everything below the lower bound
    /// to the first entry; typical opacity-0 there is the black voxel.
    /// A non-positive width does not cover anything: that was the black frame.
    @objc(transferCoversValue:level:width:)
    public static func transferCovers(_ value: Double, level: Double, width: Double) -> Bool {
        guard value.isFinite, level.isFinite, width.isFinite, width > 0 else { return false }
        let lo = transferLowerBound(level: level, width: width)
        let hi = transferUpperBound(level: level, width: width)
        return value >= min(lo, hi) && value <= max(lo, hi)
    }

    /// Resolve the window `setCamera:` should apply. Returns false only for
    /// the unset sentinel (level and width both zero). A non-positive or
    /// non-finite width is lifted to `minimumWidth` so a spline overshoot
    /// still updates the transfer instead of leaving a stale one.
    @objc(resolveLevel:width:)
    public static func resolve(level: UnsafeMutablePointer<Double>,
                               width: UnsafeMutablePointer<Double>) -> Bool {
        let incomingLevel = level.pointee
        let incomingWidth = width.pointee
        if incomingWidth == 0 && incomingLevel == 0 {
            return false
        }
        if !incomingWidth.isFinite || incomingWidth <= 0 {
            width.pointee = minimumWidth
            level.pointee = incomingLevel.isFinite ? incomingLevel : 0
            return true
        }
        level.pointee = incomingLevel.isFinite ? incomingLevel : 0
        width.pointee = incomingWidth
        return true
    }
}
