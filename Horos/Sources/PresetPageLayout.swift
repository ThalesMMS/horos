import Foundation

/// Which preset each slot of the 3D preset panel shows, on a given page.
///
/// The panel has a fixed number of preview slots and a group may have any number
/// of presets, so every refresh has to decide three things: how many pages the
/// group needs, which preset goes in which slot, and which slot starts selected.
/// The loop that did this arithmetic inline got two of them wrong when a group
/// turned out to be empty - the last preset of a group deleted while the panel is
/// open, then any refresh:
///
///   - the loop that blanks the unused slots compared a signed index against an
///     unsigned count, so `-1 < 9` was false and the slots kept the previous
///     group's thumbnails;
///   - slot 0 was selected anyway, and the info panel asked the empty list for
///     its first preset, which raises NSRangeException out of whatever called the
///     refresh.
///
/// Slots that show nothing are `NSNotFound`, and a page with no preset on it has
/// no selectable slot at all - saying so is the point.
@objc(HorosPresetPageLayout)
public final class PresetPageLayout: NSObject {
    /// How many pages a group of this size needs. A group with no presets still
    /// has one page, an empty one, so the panel has something to show.
    @objc(pageCountForPresetCount:slots:)
    public static func pageCount(presetCount: Int, slots: Int) -> Int {
        guard slots > 0 else { return 1 }
        return max(1, (max(presetCount, 0) + slots - 1) / slots)
    }

    /// A page number brought back into range, so a page left over from a larger
    /// group cannot index past the end of a smaller one.
    @objc(clampPage:presetCount:slots:)
    public static func clamp(page: Int, presetCount: Int, slots: Int) -> Int {
        let pages = pageCount(presetCount: presetCount, slots: slots)
        if page < 0 { return 0 }
        return page >= pages ? pages - 1 : page
    }

    /// For each slot, the preset it shows on this page, or `NSNotFound`.
    @objc(presetIndicesForPage:presetCount:slots:)
    public static func presetIndices(page: Int, presetCount: Int, slots: Int) -> [Int] {
        guard slots > 0 else { return [] }
        let first = clamp(page: page, presetCount: presetCount, slots: slots) * slots
        return (0 ..< slots).map { slot in
            let index = first + slot
            return index < max(presetCount, 0) ? index : NSNotFound
        }
    }

    /// The slot that should start selected, or -1 when this page carries no
    /// preset. Selecting an empty slot is what asked the info panel for a preset
    /// that is not there.
    @objc(selectableSlotForPage:presetCount:slots:)
    public static func selectableSlot(page: Int, presetCount: Int, slots: Int) -> Int {
        presetIndices(page: page, presetCount: presetCount, slots: slots)
            .firstIndex { $0 != NSNotFound } ?? -1
    }
}
