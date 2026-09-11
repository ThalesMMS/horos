import Foundation

/// Outcome of evaluating or running a CPR straightened generation.
@objc(HorosCPRStraightenedDecision)
public final class CPRStraightenedDecision: NSObject {
    @objc public let accepted: Bool
    @objc public let phase: String
    @objc public let diagnosis: String
    @objc public let nodeCount: Int
    @objc public let lengthMillimetres: Double
    @objc public let sampleSpacing: Double
    @objc public let originalVolumePreserved: Bool
    @objc public let markingsPreserved: Bool

    @objc public init(accepted: Bool, phase: String, diagnosis: String, nodeCount: Int,
                      lengthMillimetres: Double, sampleSpacing: Double,
                      originalVolumePreserved: Bool, markingsPreserved: Bool) {
        self.accepted = accepted
        self.phase = phase
        self.diagnosis = diagnosis
        self.nodeCount = nodeCount
        self.lengthMillimetres = lengthMillimetres
        self.sampleSpacing = sampleSpacing
        self.originalVolumePreserved = originalVolumePreserved
        self.markingsPreserved = markingsPreserved
    }
}

/// Patient-space centerline gate for straightened CPR.
/// Short or degenerate curves get a recoverable diagnosis; a valid curve may
/// generate asynchronously and cancel without dropping nodes or the original volume.
@objc(HorosCPRStraightenedSession)
public final class CPRStraightenedSession: NSObject {
    private static let minimumNodes = 3
    private static let minimumLength = 1.0
    private static let minimumSampleSpacing = 1e-4
    private static let degenerateSegment = 1e-8
    private static let loopProximity = 0.5

    private var nodes: [(Double, Double, Double)] = []
    private var phase = "idle"

    @objc public var nodeCount: Int { nodes.count }
    @objc public var originalVolumePreserved: Bool { true }

    @objc(replacePackedNodes:)
    public func replacePackedNodes(_ packed: [NSNumber]) {
        var next: [(Double, Double, Double)] = []
        var index = 0
        while index + 2 < packed.count {
            next.append((packed[index].doubleValue,
                         packed[index + 1].doubleValue,
                         packed[index + 2].doubleValue))
            index += 3
        }
        nodes = next
        if phase != "generating" {
            phase = "idle"
        }
    }

    @objc(evaluatePackedNodes:pixelsWide:)
    public static func evaluatePackedNodes(_ packed: [NSNumber], pixelsWide: Int) -> CPRStraightenedDecision {
        let session = CPRStraightenedSession()
        session.replacePackedNodes(packed)
        return session.evaluate(pixelsWide: pixelsWide)
    }

    @objc(evaluatePixelsWide:)
    public func evaluate(pixelsWide: Int) -> CPRStraightenedDecision {
        diagnose(pixelsWide: pixelsWide)
    }

    @objc(beginGenerationWithPixelsWide:)
    public func beginGeneration(pixelsWide: Int) -> CPRStraightenedDecision {
        let decision = diagnose(pixelsWide: pixelsWide)
        if decision.accepted == false {
            phase = "rejected"
            return decision
        }
        phase = "generating"
        return makeDecision(accepted: true, phase: "generating",
                             diagnosis: "straightened requested",
                             pixelsWide: pixelsWide)
    }

    @objc public func cancel() -> CPRStraightenedDecision {
        let nodeCountBefore = nodes.count
        if phase == "generating" {
            phase = "cancelled"
            return makeDecision(accepted: true, phase: "cancelled",
                                 diagnosis: "generation cancelled; markings kept",
                                 pixelsWide: 0)
        }
        return makeDecision(accepted: false, phase: phase,
                            diagnosis: "nothing to cancel",
                            pixelsWide: 0,
                            nodeCountOverride: nodeCountBefore)
    }

    @objc public func completeGeneration() -> CPRStraightenedDecision {
        if phase != "generating" {
            return makeDecision(accepted: false, phase: phase,
                                 diagnosis: "generation is not running",
                                 pixelsWide: 0)
        }
        phase = "complete"
        return makeDecision(accepted: true, phase: "complete",
                            diagnosis: "straightened generated",
                            pixelsWide: 0)
    }

    private func diagnose(pixelsWide: Int) -> CPRStraightenedDecision {
        if nodes.contains(where: { !$0.0.isFinite || !$0.1.isFinite || !$0.2.isFinite }) {
            return refused("non-finite patient node", pixelsWide: pixelsWide)
        }
        if nodes.count < Self.minimumNodes {
            return refused("need at least 3 nodes", pixelsWide: pixelsWide)
        }
        if pixelsWide <= 0 {
            return refused("pixelsWide is zero", pixelsWide: pixelsWide)
        }
        var length = 0.0
        for index in 1..<nodes.count {
            let step = distance(nodes[index - 1], nodes[index])
            if step < Self.degenerateSegment {
                return refused("degenerate spacing", pixelsWide: pixelsWide)
            }
            length += step
        }
        if length < Self.minimumLength {
            return refused("curve too short", pixelsWide: pixelsWide)
        }
        let spacing = length / Double(pixelsWide)
        if spacing < Self.minimumSampleSpacing {
            return refused("degenerate spacing", pixelsWide: pixelsWide)
        }
        if hasSelfIntersection() {
            return refused("self-intersecting loop", pixelsWide: pixelsWide)
        }
        return makeDecision(accepted: true, phase: "ready",
                            diagnosis: "valid centerline",
                            pixelsWide: pixelsWide)
    }

    private func refused(_ diagnosis: String, pixelsWide: Int) -> CPRStraightenedDecision {
        makeDecision(accepted: false, phase: "rejected", diagnosis: diagnosis,
                     pixelsWide: pixelsWide)
    }

    private func makeDecision(accepted: Bool, phase: String, diagnosis: String,
                              pixelsWide: Int,
                              nodeCountOverride: Int? = nil) -> CPRStraightenedDecision {
        let length = polylineLength()
        let spacing = pixelsWide > 0 ? length / Double(pixelsWide) : 0
        return CPRStraightenedDecision(
            accepted: accepted,
            phase: phase,
            diagnosis: diagnosis,
            nodeCount: nodeCountOverride ?? nodes.count,
            lengthMillimetres: length,
            sampleSpacing: spacing,
            originalVolumePreserved: true,
            markingsPreserved: true
        )
    }

    private func polylineLength() -> Double {
        guard nodes.count >= 2 else { return 0 }
        var length = 0.0
        for index in 1..<nodes.count {
            length += distance(nodes[index - 1], nodes[index])
        }
        return length
    }

    private func hasSelfIntersection() -> Bool {
        guard nodes.count >= 4 else { return false }
        if polylineLength() >= 10, distance(nodes[0], nodes[nodes.count - 1]) < Self.loopProximity {
            return true
        }
        let lastSegment = nodes.count - 2
        for i in 0...lastSegment {
            if i + 2 > lastSegment { break }
            for j in (i + 2)...lastSegment {
                if interiorSegmentDistance(nodes[i], nodes[i + 1], nodes[j], nodes[j + 1]) < Self.loopProximity {
                    return true
                }
            }
        }
        return false
    }

    private func distance(_ a: (Double, Double, Double), _ b: (Double, Double, Double)) -> Double {
        let dx = a.0 - b.0, dy = a.1 - b.1, dz = a.2 - b.2
        return (dx * dx + dy * dy + dz * dz).squareRoot()
    }

    private func interiorSegmentDistance(_ a0: (Double, Double, Double), _ a1: (Double, Double, Double),
                                         _ b0: (Double, Double, Double), _ b1: (Double, Double, Double)) -> Double {
        let u = (a1.0 - a0.0, a1.1 - a0.1, a1.2 - a0.2)
        let v = (b1.0 - b0.0, b1.1 - b0.1, b1.2 - b0.2)
        let w = (a0.0 - b0.0, a0.1 - b0.1, a0.2 - b0.2)
        let uu = u.0 * u.0 + u.1 * u.1 + u.2 * u.2
        let vv = v.0 * v.0 + v.1 * v.1 + v.2 * v.2
        let uv = u.0 * v.0 + u.1 * v.1 + u.2 * v.2
        let uw = u.0 * w.0 + u.1 * w.1 + u.2 * w.2
        let vw = v.0 * w.0 + v.1 * w.1 + v.2 * w.2
        let denom = uu * vv - uv * uv
        var s: Double
        var t: Double
        if denom < 1e-18 {
            s = 0
            t = vv > 1e-18 ? vw / vv : 0
        } else {
            s = (uv * vw - vv * uw) / denom
            t = (uu * vw - uv * uw) / denom
        }
        let interior = (s > 0.02 && s < 0.98 && t > 0.02 && t < 0.98)
        guard interior else { return Double.greatestFiniteMagnitude }
        s = min(1, max(0, s))
        t = min(1, max(0, t))
        let dx = (a0.0 + u.0 * s) - (b0.0 + v.0 * t)
        let dy = (a0.1 + u.1 * s) - (b0.1 + v.1 * t)
        let dz = (a0.2 + u.2 * s) - (b0.2 + v.2 * t)
        return (dx * dx + dy * dy + dz * dz).squareRoot()
    }
}
