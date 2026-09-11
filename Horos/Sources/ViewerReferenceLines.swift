import AppKit

/// Slice-cut lines on a related 2D viewer, and why they are absent.
///
/// This is not the interactive crosshair. The host still intersects planes in
/// `DCMView`; this type is the one convention for who may show a line, where
/// that line is drawn, and the sentence that replaces a missing one. Keyboard
/// and wheel already post the same sync: the line is a function of the source
/// plane, not of the gesture that selected it.
@objc(HorosViewerReferenceLines)
public final class ViewerReferenceLines: NSObject {
    @objc public static let displayPreferenceKey = "DisplayCrossReferenceLines"
    @objc public static let frameOfReferencePreferenceKey = "UseFrameofReferenceUID"
    @objc public static let sameStudyPreferenceKey = "SAMESTUDY"

    private static func trimmed(_ value: String?) -> String {
        value?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
    }

    private static func sameIdentifier(_ first: String?, _ second: String?) -> Bool {
        let left = trimmed(first)
        let right = trimmed(second)
        return !left.isEmpty && left == right
    }

    private static func named(_ text: String, source: String?, destination: String?) -> String {
        let src = shortened(source)
        let dst = shortened(destination)
        if src.isEmpty && dst.isEmpty { return text }
        if src.isEmpty { return text + " (" + dst + ")" }
        if dst.isEmpty { return text + " (" + src + ")" }
        return text + " (" + src + " vs " + dst + ")"
    }

    private static func shortened(_ value: String?) -> String {
        let uid = trimmed(value)
        if uid.isEmpty || uid.count <= 24 { return uid }
        return String(uid.suffix(12))
    }

    @objc(reasonForIncompatibleFrameWithSource:destination:)
    public static func reasonForIncompatibleFrame(source: String?, destination: String?) -> String {
        named(NSLocalizedString("Different frame of reference",
                                comment: "why a related 2D viewer shows no reference line"),
              source: source, destination: destination)
    }

    @objc public static func reasonForDifferentStudy() -> String {
        NSLocalizedString("Different study",
                          comment: "why a related 2D viewer shows no reference line")
    }

    @objc public static func reasonForLinesDisabled() -> String {
        NSLocalizedString("Reference lines are turned off",
                          comment: "why a related 2D viewer shows no reference line")
    }

    @objc public static func reasonForParallelPlanes() -> String {
        NSLocalizedString("Planes do not intersect",
                          comment: "why a related 2D viewer shows no reference line")
    }

    @objc public static func logPrefix() -> String {
        "Reference lines hidden: "
    }

    @objc(sameThreeDWorldDestinationFrame:sourceFrame:destinationStudy:sourceStudy:useFrameOfReference:)
    public static func sameThreeDWorld(destinationFrame: String?, sourceFrame: String?,
                                       destinationStudy: String?, sourceStudy: String?,
                                       useFrameOfReference: Bool) -> Bool {
        guard sameIdentifier(destinationStudy, sourceStudy) else { return false }
        guard useFrameOfReference else { return true }
        let dest = trimmed(destinationFrame)
        let src = trimmed(sourceFrame)
        if dest.isEmpty || src.isEmpty { return true }
        return dest == src
    }

    @objc(absenceReasonDestinationFrame:sourceFrame:destinationStudy:sourceStudy:useFrameOfReference:sameStudyOnly:registered:)
    public static func absenceReason(destinationFrame: String?, sourceFrame: String?,
                                     destinationStudy: String?, sourceStudy: String?,
                                     useFrameOfReference: Bool, sameStudyOnly: Bool,
                                     registered: Bool) -> String? {
        let sameWorld = sameThreeDWorld(destinationFrame: destinationFrame, sourceFrame: sourceFrame,
                                        destinationStudy: destinationStudy, sourceStudy: sourceStudy,
                                        useFrameOfReference: useFrameOfReference)
        if shouldComputeLines(sameWorld: sameWorld, registered: registered) { return nil }
        if useFrameOfReference {
            let dest = trimmed(destinationFrame)
            let src = trimmed(sourceFrame)
            if !dest.isEmpty && !src.isEmpty && dest != src {
                return reasonForIncompatibleFrame(source: src, destination: dest)
            }
        }
        return reasonForDifferentStudy()
    }

    @objc(admitSynchronizationSameWorld:registered:sameStudyOnly:manualSync:)
    public static func admitSynchronization(sameWorld: Bool, registered: Bool,
                                            sameStudyOnly: Bool, manualSync: Bool) -> Bool {
        sameWorld || registered || !sameStudyOnly || manualSync
    }

    @objc(shouldComputeLinesSameWorld:registered:)
    public static func shouldComputeLines(sameWorld: Bool, registered: Bool) -> Bool {
        sameWorld || registered
    }

    @objc(shouldDisplaySourceLinesDestinationIsKey:sourceIsKey:sourceIsFullscreen:)
    public static func shouldDisplaySourceLines(destinationIsKey: Bool, sourceIsKey: Bool,
                                                sourceIsFullscreen: Bool) -> Bool {
        (!destinationIsKey && sourceIsKey) || sourceIsFullscreen
    }

    @objc(bothWindowsActivelySourcingDestinationIsKey:sourceIsKey:)
    public static func bothWindowsActivelySourcing(destinationIsKey: Bool, sourceIsKey: Bool) -> Bool {
        destinationIsKey && sourceIsKey
    }

    /// Pixel-centre convention of the fixture: sagittal plane x = k meets axial
    /// at column centre k + 0.5 mm.
    @objc(fixtureAxialSliceXForSagittalIndex:)
    public static func fixtureAxialSliceX(forSagittalIndex index: Int) -> Double {
        Double(index) + 0.5
    }

    @objc(fixtureAxialSliceYForCoronalPhysicalY:)
    public static func fixtureAxialSliceY(forCoronalPhysicalY y: Double) -> Double {
        y + 0.5
    }

    /// OpenGL vertex used by `drawCrossLines:` for a slice-millimetre endpoint.
    @objc(renderedPointSliceX:sliceY:pixelSpacingX:pixelSpacingY:width:height:scale:)
    public static func renderedPoint(sliceX: Double, sliceY: Double,
                                     pixelSpacingX: Double, pixelSpacingY: Double,
                                     width: Double, height: Double, scale: Double) -> NSPoint {
        guard [sliceX, sliceY, pixelSpacingX, pixelSpacingY, width, height, scale].allSatisfy({ $0.isFinite }),
              pixelSpacingX > 0, pixelSpacingY > 0 else {
            return NSPoint(x: CGFloat.nan, y: CGFloat.nan)
        }
        return NSPoint(x: scale * (sliceX / pixelSpacingX - width / 2),
                       y: scale * (sliceY / pixelSpacingY - height / 2))
    }

    /// Keyboard and wheel feed this the same source index; the line cannot differ.
    public static func fixtureRenderedLine(sagittalIndex: Int, scale: Double) -> (NSPoint, NSPoint) {
        let sliceX = fixtureAxialSliceX(forSagittalIndex: sagittalIndex)
        return (renderedPoint(sliceX: sliceX, sliceY: 0, pixelSpacingX: 1, pixelSpacingY: 1,
                              width: 32, height: 32, scale: scale),
                renderedPoint(sliceX: sliceX, sliceY: 32, pixelSpacingX: 1, pixelSpacingY: 1,
                              width: 32, height: 32, scale: scale))
    }

    /// `annotNone` and `annotGraphics` keep the image clean; base/full show why.
    @objc(overlayTextDisplayingLines:annotationType:hasFiniteLine:relationshipReason:)
    public static func overlayText(displayingLines: Bool, annotationType: Int,
                                   hasFiniteLine: Bool, relationshipReason: String?) -> String? {
        guard annotationType > 1 else { return nil }
        if !displayingLines { return reasonForLinesDisabled() }
        if hasFiniteLine { return nil }
        return relationshipReason
    }
}
