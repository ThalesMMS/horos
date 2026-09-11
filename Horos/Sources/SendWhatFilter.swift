import Foundation

/// Radio values for `Send.xib` / `lastSendWhat`.
///
/// The matrix tags are 0 (all images), 1 (key images) and 2 (secondary
/// capture). `initWithFiles:` used to recede an unavailable option with
/// `index == 1` for both Key Images and SC. A selection of key images then
/// fell back to “all” whenever the study had no SC, and SC never receded.
@objc(HorosSendWhatFilter)
public final class SendWhatFilter: NSObject {
    @objc public static let allImages = 0
    @objc public static let keyImages = 1
    @objc public static let secondaryCapture = 2

    @objc(isKnownIndex:)
    public static func isKnown(_ index: Int) -> Bool {
        index == allImages || index == keyImages || index == secondaryCapture
    }

    /// Preference to show on the radio and to use when sending.
    /// Unavailable categories recede to all images. Unknown values do too.
    /// Key images do not recede just because SC is missing.
    @objc(resolvedIndex:hasKeyImages:hasSecondaryCaptures:)
    public static func resolvedIndex(_ requested: Int,
                                     hasKeyImages: Bool,
                                     hasSecondaryCaptures: Bool) -> Int {
        switch requested {
        case keyImages:
            return hasKeyImages ? keyImages : allImages
        case secondaryCapture:
            return hasSecondaryCaptures ? secondaryCapture : allImages
        case allImages:
            return allImages
        default:
            return allImages
        }
    }

    @objc(filtersKeyImagesForIndex:)
    public static func filtersKeyImages(forIndex index: Int) -> Bool {
        index == keyImages
    }

    @objc(filtersSecondaryCaptureForIndex:)
    public static func filtersSecondaryCapture(forIndex index: Int) -> Bool {
        index == secondaryCapture
    }
}
