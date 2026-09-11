import Foundation
import simd

/// Triangle mesh in patient millimetres. Faces are (i, j, k) into `vertices`.
public struct ROISurfaceMesh {
    public var vertices: [SIMD3<Double>]
    public var faces: [(Int, Int, Int)]
}

public struct ROISurfaceInspection {
    public let closed: Bool
    public let volumeCm3: Double
    public let componentCount: Int
    public let boundaryEdgeCount: Int
}

/// Decision for `UseDelaunayFor3DRoi` before VTK runs.
@objc(HorosROISurfaceChoice)
public final class ROISurfaceChoice: NSObject {
    @objc public let preference: Int
    @objc public let available: Bool
    @objc public let name: String
    @objc public let diagnosis: String

    @objc public init(preference: Int, available: Bool, name: String, diagnosis: String) {
        self.preference = preference
        self.available = available
        self.name = name
        self.diagnosis = diagnosis
    }
}

/// Preference 0 is Iso Contour, 1 is Delaunay. Preference 2 is Power Crust in
/// `ROIVolume.xib`; that VTK path is not built and must not fall through to Iso.
@objc(HorosROISurfaceAlgorithm)
public final class ROISurfaceAlgorithm: NSObject {
    @objc public static let isoContourPreference = 0
    @objc public static let delaunayPreference = 1
    @objc public static let powerCrustPreference = 2

    @objc(isAvailableForPreference:)
    public static func isAvailable(forPreference value: Int) -> Bool {
        value == isoContourPreference || value == delaunayPreference
    }

    @objc(nameForPreference:)
    public static func name(forPreference value: Int) -> String {
        switch value {
        case isoContourPreference: return "iso-contour"
        case delaunayPreference: return "delaunay"
        case powerCrustPreference: return "power-crust"
        default: return "unknown"
        }
    }

    @objc(unavailabilityReasonForPreference:)
    public static func unavailabilityReason(forPreference value: Int) -> String? {
        guard !isAvailable(forPreference: value) else { return nil }
        if value == powerCrustPreference {
            return NSLocalizedString(
                "The Power Crust 3D ROI algorithm is not available. Use Iso Contour or Delaunay.",
                comment: "alert when the ROI volume window asks for Power Crust")
        }
        return NSLocalizedString(
            "The selected 3D ROI surface algorithm is not available. Use Iso Contour or Delaunay.",
            comment: "alert when UseDelaunayFor3DRoi is not Iso Contour or Delaunay")
    }

    @objc(resolvePreference:)
    public static func resolvePreference(_ value: Int) -> ROISurfaceChoice {
        let reason = unavailabilityReason(forPreference: value) ?? ""
        return ROISurfaceChoice(preference: value,
                                available: isAvailable(forPreference: value),
                                name: name(forPreference: value),
                                diagnosis: reason)
    }

    @objc(shouldReplaceUnavailableAlgorithmWithIsoContour)
    public static func shouldReplaceUnavailableAlgorithmWithIsoContour() -> Bool {
        false
    }

    @objc(shouldRewritePreferenceAfterFailure:)
    public static func shouldRewritePreference(afterFailure value: Int) -> Bool {
        _ = value
        return false
    }

    public static func cube(origin: SIMD3<Double>, sideMm: Double) -> ROISurfaceMesh {
        let s = sideMm
        let vertices = [
            origin,
            origin + SIMD3(s, 0, 0),
            origin + SIMD3(s, s, 0),
            origin + SIMD3(0, s, 0),
            origin + SIMD3(0, 0, s),
            origin + SIMD3(s, 0, s),
            origin + SIMD3(s, s, s),
            origin + SIMD3(0, s, s)
        ]
        let faces: [(Int, Int, Int)] = [
            (0, 3, 2), (0, 2, 1),
            (4, 5, 6), (4, 6, 7),
            (0, 1, 5), (0, 5, 4),
            (3, 7, 6), (3, 6, 2),
            (0, 4, 7), (0, 7, 3),
            (1, 2, 6), (1, 6, 5)
        ]
        return ROISurfaceMesh(vertices: vertices, faces: faces)
    }

    public static func droppingLastFaces(_ mesh: ROISurfaceMesh, count: Int) -> ROISurfaceMesh {
        var copy = mesh
        let kept = max(0, mesh.faces.count - max(0, count))
        copy.faces = Array(mesh.faces.prefix(kept))
        return copy
    }

    public static func disjointCubes(sideMm: Double, gapMm: Double) -> ROISurfaceMesh {
        let first = cube(origin: .zero, sideMm: sideMm)
        let second = cube(origin: SIMD3(sideMm + gapMm, 0, 0), sideMm: sideMm)
        let offset = first.vertices.count
        return ROISurfaceMesh(
            vertices: first.vertices + second.vertices,
            faces: first.faces + second.faces.map { (i, j, k) in
                (i + offset, j + offset, k + offset)
            })
    }

    public static func isClosed(_ mesh: ROISurfaceMesh) -> Bool {
        guard !mesh.faces.isEmpty, mesh.vertices.count >= 4 else { return false }
        var unpaired = Set<DirectedEdge>()
        for (a, b, c) in mesh.faces {
            guard a != b, b != c, c != a else { return false }
            guard mesh.vertices.indices.contains(a),
                  mesh.vertices.indices.contains(b),
                  mesh.vertices.indices.contains(c) else { return false }
            for pair in [(a, b), (b, c), (c, a)] {
                let edge = DirectedEdge(from: pair.0, to: pair.1)
                let reverse = DirectedEdge(from: pair.1, to: pair.0)
                if unpaired.contains(reverse) {
                    unpaired.remove(reverse)
                } else if unpaired.contains(edge) {
                    return false
                } else {
                    unpaired.insert(edge)
                }
            }
        }
        return unpaired.isEmpty
    }

    public static func volumeCm3(_ mesh: ROISurfaceMesh) -> Double? {
        guard isClosed(mesh) else { return nil }
        var mm3TimesSix = 0.0
        for (a, b, c) in mesh.faces {
            mm3TimesSix += simd_dot(mesh.vertices[a],
                                     simd_cross(mesh.vertices[b], mesh.vertices[c]))
        }
        let mm3 = mm3TimesSix / 6
        guard mm3.isFinite else { return nil }
        return abs(mm3) / 1000
    }

    public static func volumeIsCoherent(meshCm3: Double, trapezoidCm3: Double,
                                         tolerance: Double) -> Bool {
        guard meshCm3.isFinite, trapezoidCm3.isFinite, tolerance >= 0 else { return false }
        return abs(meshCm3 - trapezoidCm3) <= tolerance
    }

    public static func meshVolume(_ meshCm3: Double, matchesTrapezoid trapezoidCm3: Double) -> Bool {
        volumeIsCoherent(meshCm3: meshCm3, trapezoidCm3: trapezoidCm3, tolerance: 1e-6)
    }

    public static func inspectMesh(points: [SIMD3<Double>], faces: [[Int]]) -> ROISurfaceInspection {
        var triples: [(Int, Int, Int)] = []
        for face in faces {
            guard face.count >= 3 else {
                return ROISurfaceInspection(closed: false, volumeCm3: 0,
                                            componentCount: 0, boundaryEdgeCount: 0)
            }
            for index in 1..<(face.count - 1) {
                triples.append((face[0], face[index], face[index + 1]))
            }
        }
        let mesh = ROISurfaceMesh(vertices: points, faces: triples)
        var unpaired = Set<DirectedEdge>()
        var parent: [Int: Int] = [:]
        var used = Set<Int>()
        func find(_ value: Int) -> Int {
            if parent[value, default: value] != value {
                parent[value] = find(parent[value, default: value])
            }
            return parent[value, default: value]
        }
        func join(_ lhs: Int, _ rhs: Int) {
            let a = find(lhs)
            let b = find(rhs)
            if a != b { parent[a] = b }
        }
        for (a, b, c) in triples {
            for vertex in [a, b, c] {
                if parent[vertex] == nil { parent[vertex] = vertex }
                used.insert(vertex)
            }
            join(a, b)
            join(b, c)
            for pair in [(a, b), (b, c), (c, a)] {
                let edge = DirectedEdge(from: pair.0, to: pair.1)
                let reverse = DirectedEdge(from: pair.1, to: pair.0)
                if unpaired.contains(reverse) {
                    unpaired.remove(reverse)
                } else {
                    unpaired.insert(edge)
                }
            }
        }
        let closed = isClosed(mesh)
        let volume = closed ? (volumeCm3(mesh) ?? 0) : 0
        return ROISurfaceInspection(
            closed: closed,
            volumeCm3: volume,
            componentCount: Set(used.map(find)).count,
            boundaryEdgeCount: unpaired.count)
    }

    private struct DirectedEdge: Hashable {
        let from: Int
        let to: Int
    }
}
