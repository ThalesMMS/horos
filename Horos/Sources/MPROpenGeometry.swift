import Foundation

/// Named outcome of a 3D MPR open attempt. Invalid geometry is not rewritten.
@objc(HorosMPROpenDecision)
public final class MPROpenDecision: NSObject {
    @objc public let accepted: Bool
    @objc public let phase: String
    @objc public let diagnosis: String

    @objc public init(accepted: Bool, phase: String, diagnosis: String) {
        self.accepted = accepted
        self.phase = phase
        self.diagnosis = diagnosis
    }
}

/// Volume and overlay gates for 3D MPR. CTA, ROIs and migrated prefs are not refusals.
@objc(HorosMPROpenGeometry)
public final class MPROpenGeometry: NSObject {
    private static let minimumVolumicSlices = 5
    private static let irregularIntervalDelta = 0.01
    /// Same threshold as `ORIENTATION_SENSIBILITY` in `DCMPix.h`.
    public static let orientationSensibility = 0.001

    @objc(openingWithSliceCount:spacingX:spacingY:sliceInterval:minInterval:maxInterval:width:height:mismatchedSlices:roiCount:)
    public static func opening(withSliceCount sliceCount: Int,
                               spacingX: Double, spacingY: Double,
                               sliceInterval: Double, minInterval: Double, maxInterval: Double,
                               width: Int, height: Int, mismatchedSlices: Int,
                               roiCount: Int) -> MPROpenDecision {
        return opening(withSliceCount: sliceCount, spacingX: spacingX, spacingY: spacingY,
                       sliceInterval: sliceInterval, minInterval: minInterval, maxInterval: maxInterval,
                       width: width, height: height, mismatchedSlices: mismatchedSlices,
                       roiCount: roiCount, mismatchedOrientations: 0)
    }

    @objc(openingWithSliceCount:spacingX:spacingY:sliceInterval:minInterval:maxInterval:width:height:mismatchedSlices:roiCount:mismatchedOrientations:)
    public static func opening(withSliceCount sliceCount: Int,
                               spacingX: Double, spacingY: Double,
                               sliceInterval: Double, minInterval: Double, maxInterval: Double,
                               width: Int, height: Int, mismatchedSlices: Int,
                               roiCount: Int, mismatchedOrientations: Int) -> MPROpenDecision {
        _ = roiCount
        let scalars = [spacingX, spacingY, sliceInterval, minInterval, maxInterval]
        if scalars.contains(where: { $0.isNaN || $0.isInfinite }) {
            return MPROpenDecision(accepted: false, phase: "refused",
                                   diagnosis: "non-finite slice interval or spacing")
        }
        if spacingX <= 0 || spacingY <= 0 {
            return MPROpenDecision(accepted: false, phase: "calibrate",
                                   diagnosis: "pixel spacing is missing; enter a positive spacing")
        }
        if sliceCount > 1 && sliceInterval == 0 {
            return MPROpenDecision(accepted: false, phase: "calibrate",
                                   diagnosis: "slice interval is missing; enter a voxel interval")
        }
        if sliceCount < minimumVolumicSlices {
            return MPROpenDecision(accepted: false, phase: "refused",
                                   diagnosis: "MPR requires volumic data.")
        }
        if width <= 0 || height <= 0 || mismatchedSlices > 0 {
            return MPROpenDecision(accepted: false, phase: "refused",
                                   diagnosis: "images do not share a single matrix")
        }
        if mismatchedOrientations > 0 {
            return MPROpenDecision(accepted: false, phase: "refused",
                                   diagnosis: "images do not share a single orientation")
        }
        if sliceCount > 1 && maxInterval - minInterval > irregularIntervalDelta {
            return MPROpenDecision(accepted: true, phase: "open",
                                   diagnosis: String(format: "slice interval varies from %.3f mm to %.3f mm",
                                                      minInterval, maxInterval))
        }
        return MPROpenDecision(accepted: true, phase: "open", diagnosis: "ready")
    }

    /// Count slices whose 9-component orientation differs from slice 1, matching `isDataVolumicIn4D`.
    public static func mismatchedOrientations(among orientations: [[Double]],
                                              sensibility: Double = orientationSensibility) -> Int {
        guard !orientations.isEmpty else { return 0 }
        let referenceIndex = orientations.count > 1 ? 1 : 0
        let reference = orientations[referenceIndex]
        guard reference.count == 9 else { return orientations.count }
        var mismatches = 0
        for orientation in orientations {
            if orientation.count != 9 {
                mismatches += 1
                continue
            }
            for k in 0..<9 {
                if abs(orientation[k] - reference[k]) > sensibility {
                    mismatches += 1
                    break
                }
            }
        }
        return mismatches
    }

    /// `convertDICOMCoords:toSliceCoords:pixelCenter:` is only safe on live companions.
    @objc(canConvertSliceCoordsWithDestinationPix:companionA:companionB:spacingX:spacingY:vrAttached:displayMousePosition:)
    public static func canConvertSliceCoords(destinationPix: Bool, companionA: Bool, companionB: Bool,
                                              spacingX: Double, spacingY: Double,
                                              vrAttached: Bool, displayMousePosition: Bool) -> Bool {
        guard displayMousePosition, vrAttached, destinationPix, companionA, companionB else { return false }
        return spacingX.isFinite && spacingY.isFinite && spacingX > 0 && spacingY > 0
    }

    /// horos#391: NSRunCriticalAlertPanel during hidden-MPR `computeMinMax` re-enters drawing.
    @objc(shouldPresentHighDynamicPromptDuringHiddenInit:)
    public static func shouldPresentHighDynamicPrompt(duringHiddenInit hiddenInit: Bool) -> Bool {
        !hiddenInit
    }
}
