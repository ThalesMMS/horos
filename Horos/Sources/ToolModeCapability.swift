import Foundation

/// What each 2D tool mode can do to ROIs (#373, A255).
///
/// A255 comes from #255 — *"investigar opções ROI desabilitadas ao remover mesa
/// de CT"*. Removing a CT table is done by drawing a region around the patient
/// and setting the pixels outside it to air, and the sheet that does it offers
/// the inside/outside choice only when a ROI is selected. Whether a ROI *can* be
/// selected is decided by the tool mode, in `-[DCMView roiTool:]` and in the two
/// tools each of its callers had to name by hand.
///
/// The criterion asks that a mode which does not apply be refused explicitly
/// rather than resolved by enabling everything. That needs the modes written
/// down with a reason each, which is what this is: one row per `ToolMode` in
/// `DCMView.h`, in the same order, so a mode added there without a decision here
/// is a test failure rather than a silent default.
@objc(HorosToolModeCapability)
public final class ToolModeCapability: NSObject {

    /// What a mode does with ROIs. Only the first two can leave one selected,
    /// and only those two enable the ROI-dependent commands.
    public enum Role: String {
        /// Draws a new ROI, and clicking an existing one selects it.
        case drawsROIs
        /// Never draws one, but works on those already there — so it selects.
        case actsOnROIs
        /// A ROI *type* that no 2D tool draws: a command or another viewer
        /// produces it. Selecting it as a 2D tool is not possible.
        case roiTypeOnly
        /// Belongs to another viewer's handler (3D, MPR, CPR), not this one.
        case otherViewer
        /// Changes how the image is shown, not what is on it.
        case presentation
    }

    public struct Mode {
        public let value: Int
        public let name: String
        public let role: Role
        /// Why that role, in terms a reader can check against the code.
        public let reason: String
    }

    /// Same order as `ToolMode` in `DCMView.h`; `value` is the enum's own.
    public static let modes: [Mode] = [
        Mode(value: 0, name: "tWL", role: .presentation,
             reason: "the drag changes window width and level"),
        Mode(value: 1, name: "tTranslate", role: .presentation,
             reason: "the drag pans the image"),
        Mode(value: 2, name: "tZoom", role: .presentation,
             reason: "the drag zooms"),
        Mode(value: 3, name: "tRotate", role: .presentation,
             reason: "the drag rotates the image"),
        Mode(value: 4, name: "tNext", role: .presentation,
             reason: "the drag scrolls through the series"),
        Mode(value: 5, name: "tMesure", role: .drawsROIs,
             reason: "draws a length ROI"),
        Mode(value: 6, name: "tROI", role: .drawsROIs,
             reason: "draws a rectangle ROI"),
        Mode(value: 7, name: "t3DRotate", role: .otherViewer,
             reason: "rotates a 3D scene; the 2D view has no such drag"),
        Mode(value: 8, name: "tCross", role: .presentation,
             reason: "moves the orthogonal MPR crosshair, which is not a ROI"),
        Mode(value: 9, name: "tOval", role: .drawsROIs,
             reason: "draws an oval ROI"),
        Mode(value: 10, name: "tOPolygon", role: .drawsROIs,
             reason: "draws an open polygon ROI"),
        Mode(value: 11, name: "tCPolygon", role: .drawsROIs,
             reason: "draws a closed polygon ROI"),
        Mode(value: 12, name: "tAngle", role: .drawsROIs,
             reason: "draws an angle ROI"),
        Mode(value: 13, name: "tText", role: .drawsROIs,
             reason: "draws a text ROI"),
        Mode(value: 14, name: "tArrow", role: .drawsROIs,
             reason: "draws an arrow ROI"),
        Mode(value: 15, name: "tPencil", role: .drawsROIs,
             reason: "draws a freehand ROI"),
        Mode(value: 16, name: "t3Dpoint", role: .otherViewer,
             reason: "places a point in a 3D scene"),
        Mode(value: 17, name: "t3DCut", role: .otherViewer,
             reason: "the 3D scissors"),
        Mode(value: 18, name: "tCamera3D", role: .otherViewer,
             reason: "moves a 3D camera"),
        Mode(value: 19, name: "t2DPoint", role: .drawsROIs,
             reason: "draws a point ROI"),
        Mode(value: 20, name: "tPlain", role: .drawsROIs,
             reason: "paints a brush ROI"),
        Mode(value: 21, name: "tBonesRemoval", role: .otherViewer,
             reason: "removes bone in the 3D renderers"),
        Mode(value: 22, name: "tWLBlended", role: .presentation,
             reason: "window level on the blended layer"),
        Mode(value: 23, name: "tRepulsor", role: .actsOnROIs,
             reason: "pushes the points of ROIs already on the image; it draws none, so every caller of -roiTool: has to name it"),
        Mode(value: 24, name: "tLayerROI", role: .roiTypeOnly,
             reason: "the type -createLayerROIFromSelectedROI: produces; no tool draws it and the hot-key table gives it none"),
        Mode(value: 25, name: "tROISelector", role: .actsOnROIs,
             reason: "rubber-bands a selection over ROIs already there; it draws none, so every caller of -roiTool: has to name it"),
        Mode(value: 26, name: "tAxis", role: .drawsROIs,
             reason: "draws an axis ROI"),
        Mode(value: 27, name: "tDynAngle", role: .drawsROIs,
             reason: "draws a dynamic angle ROI"),
        Mode(value: 28, name: "tCurvedROI", role: .otherViewer,
             reason: "the curved path tool of the CPR window; CPRMPRDCMView handles it, this view never sees it"),
        Mode(value: 29, name: "tTAGT", role: .drawsROIs,
             reason: "draws a TAGT ROI"),
    ]

    public static func mode(_ toolMode: Int) -> Mode? {
        modes.first { $0.value == toolMode }
    }

    /// `-[DCMView roiTool:]`: the modes that draw a ROI.
    @objc(drawsROIsWithToolMode:)
    public static func drawsROIs(toolMode: Int) -> Bool {
        mode(toolMode)?.role == .drawsROIs
    }

    /// The two that work on ROIs without drawing one. Callers of `roiTool:` have
    /// always had to add these by hand; naming them here is what lets a test
    /// check that they were not forgotten.
    @objc(actsOnROIsWithToolMode:)
    public static func actsOnROIs(toolMode: Int) -> Bool {
        mode(toolMode)?.role == .actsOnROIs
    }

    /// Whether a ROI can be selected at all in this mode — and therefore whether
    /// the ROI-dependent commands, including the inside/outside choice of
    /// -roiSetPixelsSetup:, can be offered. Every other mode is refused for a
    /// stated reason rather than by enabling everything.
    @objc(mayLeaveAROISelectedWithToolMode:)
    public static func mayLeaveAROISelected(toolMode: Int) -> Bool {
        guard let role = mode(toolMode)?.role else { return false }
        return role == .drawsROIs || role == .actsOnROIs
    }
}
