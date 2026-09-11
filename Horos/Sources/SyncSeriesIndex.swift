import Foundation

/// Where a synchronised viewer goes when another one moves (#373, A294).
///
/// `-[DCMView sync:]` maps the key viewer's slice onto its own in one of the
/// `syncro` modes of `DCMView.h`. The same two formulas were written four times
/// in that method — twice for volumic series and twice again in the fallback for
/// non-volumic ones — which is how two copies of one rule drift apart. They are
/// here once.
///
/// `syncroLOC`, the default, is not here: it maps by patient geometry rather
/// than by index, and belongs with the reference lines.
@objc(HorosSyncSeriesIndex)
public final class SyncSeriesIndex: NSObject {

    /// `-1` means *do not move*: there is no slice to go to.
    @objc public static let noIndex = -1

    private static func clamp(_ index: Int, count: Int) -> Int {
        min(max(index, 0), count - 1)
    }

    private static func oriented(_ index: Int, count: Int, flippedData: Bool) -> Int {
        flippedData ? count - 1 - index : index
    }

    /// `syncroABS`: the same slice number, counted from the other end when this
    /// series is reversed.
    @objc(absoluteIndexForPosition:count:flippedData:)
    public static func absoluteIndex(position: Int, count: Int, flippedData: Bool) -> Int {
        guard count > 0 else { return noIndex }
        return clamp(oriented(position, count: count, flippedData: flippedData), count: count)
    }

    /// `syncroRatio`: the same fraction of the way through, for series of
    /// different lengths.
    ///
    /// `sourceCount` is the other viewer's length, and it divides. It was
    /// dividing without a guard, so an empty source produced a NaN and then an
    /// undefined conversion to `int`; an empty source now means *do not move*.
    @objc(ratioIndexForPosition:sourceCount:count:flippedData:)
    public static func ratioIndex(position: Int, sourceCount: Int, count: Int,
                                  flippedData: Bool) -> Int
    {
        guard count > 0, sourceCount > 0 else { return noIndex }
        let ratio = Double(position) / Double(sourceCount)
        let scaled = Int((ratio * Double(count)).rounded())
        return clamp(oriented(scaled, count: count, flippedData: flippedData), count: count)
    }

    /// `syncroREL`: move by the same number of slices, in this series' own
    /// direction, wrapping around the ends even when the source moves through
    /// several lengths of this series (#560).
    @objc(relativeIndexForCurrent:difference:count:flippedData:)
    public static func relativeIndex(current: Int, difference: Int, count: Int,
                                     flippedData: Bool) -> Int
    {
        guard count > 0 else { return noIndex }
        let remainder = current % count
        let start = remainder < 0 ? remainder + count : remainder
        // Reduce before negating or adding: Int.min cannot be negated and two
        // valid indices can overflow when the series count approaches Int.max.
        let delta = difference % count
        let directed = flippedData ? -delta : delta
        let step = directed < 0 ? directed + count : directed
        let distanceToWrap = count - step
        return start >= distanceToWrap ? start - distanceToWrap : start + step
    }

    /// Retained for callers interested in the size of a move. Long moves are
    /// supported by `relativeIndex`; this is not an admission check.
    @objc(relativeMoveFitsInOneWrapWithDifference:count:)
    public static func relativeMoveFitsInOneWrap(difference: Int, count: Int) -> Bool {
        count > 0 && difference > -count && difference < count
    }
}
