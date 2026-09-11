import Foundation

/// Whether a ROI menu command applies to the current selection (#373, A255).
///
/// A255 asks that selecting a viewer, a series and a ROI produce *predictable*
/// enablement, and that a mode which does not apply be refused explicitly rather
/// than by enabling everything. The brush merge is the case where that went
/// wrong: its validation walked the selection assigning the answer on every
/// element, so only the **last** one decided. A selection of a brush followed by
/// a polygon disabled the command, and the same two ROIs selected the other way
/// round enabled it — and the merge would then run over a ROI that is not a
/// brush.
///
/// The rule is the one the command can actually honour: at least one ROI, and
/// every one of them a brush.
@objc(HorosROIMenuEnablement)
public final class ROIMenuEnablement: NSObject {
    /// `tPlain` in `ToolMode` (DCMView.h) — the brush ROI.
    @objc public static let brushToolMode = 20

    /// `types` carries one `ToolMode` per selected ROI, in selection order.
    /// The answer must not depend on that order.
    @objc(mayMergeBrushROIsWithTypes:)
    public static func mayMergeBrushROIs(types: [NSNumber]) -> Bool {
        guard !types.isEmpty else { return false }
        return types.allSatisfy { $0.intValue == brushToolMode }
    }
}
