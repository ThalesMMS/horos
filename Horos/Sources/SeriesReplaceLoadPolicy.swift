import Foundation

/// Whether replacing the series in a 2D viewer may wait for a load to finish.
///
/// A drop of database XIDs, a thumbnail click and the series popup all end at
/// `loadSelectedSeries` → `changeImageData`. That method copies slice position
/// from another viewer of the same study. Asking that peer `isDataVolumic`
/// runs `checkEverythingLoaded`, which sleeps the main thread until the peer
/// finishes loading. A drop while any same-study viewer is still loading is
/// then a hang — hang 2 of #279, triggered here by `performDragOperation`.
///
/// The two-argument form forwards wait and 4D flags but still corrects
/// (`tryToCorrect:YES`), so the probe passes these values into the
/// three-argument form.
@objc(HorosSeriesReplaceLoadPolicy)
public final class SeriesReplaceLoadPolicy: NSObject {
    /// A peer used only for slice millimetres must not block the drop.
    @objc public static var peerVolumicProbeWaitsForLoad: Bool { false }

    /// Accepting a drop must not correct another viewer's geometry.
    @objc public static var peerVolumicProbeCorrectsPeer: Bool { false }

    /// The drop must not wait for the current series to finish loading first.
    @objc public static var seriesDropWaitsForCurrentLoad: Bool { false }

    /// What `loadSelectedSeries` does with a series that reached a viewer.
    @objc(decisionWhenClosing:alreadyDisplayed:inFourDGroup:)
    public static func decision(closing: Bool, alreadyDisplayed: Bool, inFourDGroup: Bool) -> String {
        if closing { return "ignoreClosing" }
        if alreadyDisplayed {
            return inFourDGroup ? "switchFourDIndex" : "ignoreAlreadyDisplayed"
        }
        return "replaceWithoutWaitingForLoad"
    }
}
