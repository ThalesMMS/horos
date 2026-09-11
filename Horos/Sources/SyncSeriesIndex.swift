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
    /// direction, wrapping once around the ends.
    ///
    /// The single step is what the viewer has always done, and it is only enough
    /// while the move is shorter than the series: a larger one lands outside and
    /// `-setIndex:` then clamps a high index to the last slice and *ignores* a
    /// negative one, so the viewer silently does not follow. Kept as it is here
    /// so that behaviour has one place to be seen — see #560.
    @objc(relativeIndexForCurrent:difference:count:flippedData:)
    public static func relativeIndex(current: Int, difference: Int, count: Int,
                                     flippedData: Bool) -> Int
    {
        guard count > 0 else { return noIndex }
        var index = flippedData ? current - difference : current + difference
        if index < 0 { index += count }
        if index >= count { index -= count }
        return index
    }

    /// Whether `relativeIndex` could answer at all: `false` when the move is as
    /// long as the series or longer, which one wrap cannot bring back.
    @objc(relativeMoveFitsInOneWrapWithDifference:count:)
    public static func relativeMoveFitsInOneWrap(difference: Int, count: Int) -> Bool {
        count > 0 && abs(difference) < count
    }
}
