import Foundation

/// Decision for one step of drawing or concluding a Curved MPR centreline.
@objc(HorosCurvedMPRPathDecision)
public final class CurvedMPRPathDecision: NSObject {
    @objc public let accepted: Bool
    @objc public let phase: String
    @objc public let diagnosis: String
    @objc public let nodeCount: Int

    @objc public init(accepted: Bool, phase: String, diagnosis: String, nodeCount: Int) {
        self.accepted = accepted
        self.phase = phase
        self.diagnosis = diagnosis
        self.nodeCount = nodeCount
    }
}

/// Patient-space nodes for a Curved MPR path. Origin is valid; NaN is not.
/// Three nodes conclude the curve, matching `stopCurvedPathCreationMode`.
@objc(HorosCurvedMPRPathSession)
public final class CurvedMPRPathSession: NSObject {
    private static let nodeSpacingThreshold = 1e-10
    private static let minimumNodesToComplete = 3

    private var nodes: [(Double, Double, Double)] = []

    @objc public var nodeCount: Int { nodes.count }

    @objc(addPatientNodeX:y:z:)
    public func addPatientNodeX(_ x: Double, y: Double, z: Double) -> CurvedMPRPathDecision {
        guard x.isFinite, y.isFinite, z.isFinite else {
            return CurvedMPRPathDecision(accepted: false, phase: "rejected",
                                         diagnosis: "non-finite patient node",
                                         nodeCount: nodes.count)
        }
        if let last = nodes.last {
            let dx = x - last.0, dy = y - last.1, dz = z - last.2
            if (dx * dx + dy * dy + dz * dz).squareRoot() < Self.nodeSpacingThreshold {
                return CurvedMPRPathDecision(accepted: false, phase: "rejected",
                                             diagnosis: "coincident with last node",
                                             nodeCount: nodes.count)
            }
        }
        nodes.append((x, y, z))
        return CurvedMPRPathDecision(accepted: true, phase: "drawing",
                                     diagnosis: "node added",
                                     nodeCount: nodes.count)
    }

    @objc public func complete() -> CurvedMPRPathDecision {
        if nodes.count >= Self.minimumNodesToComplete {
            return CurvedMPRPathDecision(accepted: true, phase: "complete",
                                         diagnosis: "curve concluded",
                                         nodeCount: nodes.count)
        }
        return CurvedMPRPathDecision(accepted: false, phase: "rejected",
                                     diagnosis: "need at least 3 nodes",
                                     nodeCount: nodes.count)
    }

    /// Classify a CT stack. Invalid input is named and not rewritten.
    @objc(diagnoseVolumePixelSpacingX:spacingY:slicePositions:orientationCount:)
    public static func diagnoseVolume(pixelSpacingX: Double, spacingY: Double,
                                      slicePositions: [NSNumber],
                                      orientationCount: Int) -> String {
        let zs = slicePositions.map(\.doubleValue)
        guard orientationCount == 1,
              pixelSpacingX.isFinite, spacingY.isFinite,
              pixelSpacingX > 0, spacingY > 0,
              zs.count >= 2,
              zs.allSatisfy(\.isFinite) else {
            return "invalid"
        }
        let ordered = zs.sorted()
        var intervals: [Double] = []
        intervals.reserveCapacity(ordered.count - 1)
        for index in 1..<ordered.count {
            let step = ordered[index] - ordered[index - 1]
            guard step.isFinite, step > 0 else { return "invalid" }
            intervals.append(step)
        }
        let smallest = intervals.min() ?? 0
        let largest = intervals.max() ?? 0
        if largest - smallest > max(1e-6, 0.01 * smallest) {
            return "incomplete"
        }
        let slice = intervals[0]
        if abs(pixelSpacingX - spacingY) <= 1e-6 && abs(pixelSpacingX - slice) <= 1e-6 {
            return "isotropic"
        }
        return "anisotropic"
    }

    /// Display-to-world length of one pixel. Zero means VTK has no viewport yet.
    @objc(diagnoseViewportWorldLength:)
    public static func diagnoseViewportWorldLength(_ length: Double) -> String {
        if length.isNaN { return "not a number" }
        if length < 0.00001 { return "no viewport yet" }
        if length > 1000 { return "out of range" }
        return "ready"
    }
}
