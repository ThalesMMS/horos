import Foundation
import simd

/// View kinds that share one surface presentation. ViewerSEGSurface consumes
/// the same mesh for native VTK actors and DCMView plane intersections.
public enum HorosSEGSurfaceView: String, Equatable, CaseIterable {
    case planar
    case mpr
    case volume
    case scout
}

public struct HorosSEGSurfaceOverlay: Equatable {
    public var segmentNumber: UInt16
    public var trackingUID: String
    public var name: String
    public var color: (r: Double, g: Double, b: Double)
    public var opacity: Double
    public var visible: Bool
    public var mesh: ROISurfaceMesh
    public var inspection: ROISurfaceInspection
    public var maskVolumeCm3: Double
    public var pinnedLandmarks: [SIMD3<Double>]

    public static func == (lhs: HorosSEGSurfaceOverlay, rhs: HorosSEGSurfaceOverlay) -> Bool {
        lhs.segmentNumber == rhs.segmentNumber
            && lhs.trackingUID == rhs.trackingUID
            && lhs.name == rhs.name
            && lhs.color.r == rhs.color.r && lhs.color.g == rhs.color.g && lhs.color.b == rhs.color.b
            && lhs.opacity == rhs.opacity
            && lhs.visible == rhs.visible
            && lhs.inspection.closed == rhs.inspection.closed
            && lhs.inspection.componentCount == rhs.inspection.componentCount
            && lhs.maskVolumeCm3 == rhs.maskVolumeCm3
            && lhs.pinnedLandmarks == rhs.pinnedLandmarks
    }

    public func appears(in view: HorosSEGSurfaceView) -> Bool {
        switch view {
        case .planar, .mpr, .volume, .scout:
            return visible
        }
    }
}

/// Extract voxel-face meshes from #376 binary masks without a second ROI store.
@objc(HorosSEGSurface)
public final class HorosSEGSurface: NSObject {
    @objc public static let usesSharedSEGModel = true
    @objc public static let buildsParallelROIStore = false
    @objc public static let nativeViewerOverlayImplemented = true
    @objc public static let simplificationForcesSphericalTopology = false

    /// Voxel-face meshes match the mask volume exactly; keep a documented
    /// tolerance for later simplification that must not force a sphere.
    public static let volumeToleranceFraction = 0.05

    private struct Corner: Hashable {
        let i: Int
        let j: Int
        let k: Int
    }

    public static func maskVolumeCm3(segment: DicomSEGSegment, geometry: DicomSEGGeometry) -> Double {
        guard geometry.frames > 0 else { return 0 }
        let areaMm2 = abs(geometry.spacingCol * geometry.spacingRow)
        let col = SIMD3(geometry.orientation[0], geometry.orientation[1], geometry.orientation[2])
        let row = SIMD3(geometry.orientation[3], geometry.orientation[4], geometry.orientation[5])
        let normal = simd_normalize(simd_cross(col, row))
        return segment.frames.prefix(geometry.frames).enumerated().reduce(0) { total, item in
            let depth = abs(simd_dot(normal, frameBoundary(geometry, item.offset + 1)
                                     - frameBoundary(geometry, item.offset)))
            return total + Double(item.element.prefix(geometry.rows * geometry.columns)
                .filter { $0 > 0 }.count) * areaMm2 * depth / 1000
        }
    }

    public static func extract(segment: DicomSEGSegment, geometry: DicomSEGGeometry) -> ROISurfaceMesh {
        var indexOf: [Corner: Int] = [:]
        var vertices: [SIMD3<Double>] = []
        var faces: [(Int, Int, Int)] = []

        func vertex(_ corner: Corner) -> Int {
            if let existing = indexOf[corner] { return existing }
            vertices.append(Self.corner(geometry: geometry, column: corner.i, row: corner.j, frame: corner.k))
            let index = vertices.count - 1
            indexOf[corner] = index
            return index
        }

        func quad(_ a: Corner, _ b: Corner, _ c: Corner, _ d: Corner) {
            let ia = vertex(a), ib = vertex(b), ic = vertex(c), id = vertex(d)
            faces.append((ia, ib, ic))
            faces.append((ia, ic, id))
        }

        for k in 0..<geometry.frames {
            for j in 0..<geometry.rows {
                for i in 0..<geometry.columns {
                    guard occupied(segment, geometry: geometry, column: i, row: j, frame: k) else { continue }
                    if !occupied(segment, geometry: geometry, column: i + 1, row: j, frame: k) {
                        quad(Corner(i: i + 1, j: j, k: k),
                             Corner(i: i + 1, j: j + 1, k: k),
                             Corner(i: i + 1, j: j + 1, k: k + 1),
                             Corner(i: i + 1, j: j, k: k + 1))
                    }
                    if !occupied(segment, geometry: geometry, column: i - 1, row: j, frame: k) {
                        quad(Corner(i: i, j: j, k: k),
                             Corner(i: i, j: j, k: k + 1),
                             Corner(i: i, j: j + 1, k: k + 1),
                             Corner(i: i, j: j + 1, k: k))
                    }
                    if !occupied(segment, geometry: geometry, column: i, row: j + 1, frame: k) {
                        quad(Corner(i: i, j: j + 1, k: k),
                             Corner(i: i, j: j + 1, k: k + 1),
                             Corner(i: i + 1, j: j + 1, k: k + 1),
                             Corner(i: i + 1, j: j + 1, k: k))
                    }
                    if !occupied(segment, geometry: geometry, column: i, row: j - 1, frame: k) {
                        quad(Corner(i: i, j: j, k: k),
                             Corner(i: i + 1, j: j, k: k),
                             Corner(i: i + 1, j: j, k: k + 1),
                             Corner(i: i, j: j, k: k + 1))
                    }
                    if !occupied(segment, geometry: geometry, column: i, row: j, frame: k + 1) {
                        quad(Corner(i: i, j: j, k: k + 1),
                             Corner(i: i + 1, j: j, k: k + 1),
                             Corner(i: i + 1, j: j + 1, k: k + 1),
                             Corner(i: i, j: j + 1, k: k + 1))
                    }
                    if !occupied(segment, geometry: geometry, column: i, row: j, frame: k - 1) {
                        quad(Corner(i: i, j: j, k: k),
                             Corner(i: i, j: j + 1, k: k),
                             Corner(i: i + 1, j: j + 1, k: k),
                             Corner(i: i + 1, j: j, k: k))
                    }
                }
            }
        }
        return ROISurfaceMesh(vertices: vertices, faces: faces)
    }

    public static func inspect(_ mesh: ROISurfaceMesh) -> ROISurfaceInspection {
        let faces = mesh.faces.map { [$0.0, $0.1, $0.2] }
        return ROISurfaceAlgorithm.inspectMesh(points: mesh.vertices, faces: faces)
    }

    public static func eulerCharacteristic(_ mesh: ROISurfaceMesh) -> Int {
        var used = Set<Int>()
        var undirected = Set<UInt64>()
        func pack(_ a: Int, _ b: Int) -> UInt64 {
            let lo = UInt64(min(a, b))
            let hi = UInt64(max(a, b))
            return (hi << 32) | lo
        }
        for (a, b, c) in mesh.faces {
            used.insert(a); used.insert(b); used.insert(c)
            undirected.insert(pack(a, b))
            undirected.insert(pack(b, c))
            undirected.insert(pack(c, a))
        }
        return used.count - undirected.count + mesh.faces.count
    }

    public static func isSpherical(_ mesh: ROISurfaceMesh) -> Bool {
        let inspection = inspect(mesh)
        return inspection.closed && inspection.componentCount == 1 && eulerCharacteristic(mesh) == 2
    }

    /// Weld coincident vertices. Never adds caps or joins disconnected components.
    public static func refine(_ mesh: ROISurfaceMesh, keeping landmarks: [SIMD3<Double>] = []) -> ROISurfaceMesh {
        _ = landmarks
        if simplificationForcesSphericalTopology {
            return mesh
        }
        var indexOf: [String: Int] = [:]
        var vertices: [SIMD3<Double>] = []
        var remap: [Int] = Array(repeating: 0, count: mesh.vertices.count)
        for (old, point) in mesh.vertices.enumerated() {
            let key = String(format: "%.9f,%.9f,%.9f", point.x, point.y, point.z)
            if let existing = indexOf[key] {
                remap[old] = existing
            } else {
                remap[old] = vertices.count
                indexOf[key] = vertices.count
                vertices.append(point)
            }
        }
        let faces = mesh.faces.map { (remap[$0.0], remap[$0.1], remap[$0.2]) }
        return ROISurfaceMesh(vertices: vertices, faces: faces)
    }

    public static func volumeIsCoherent(meshCm3: Double, maskCm3: Double) -> Bool {
        guard meshCm3.isFinite, maskCm3.isFinite else { return false }
        let scale = max(abs(maskCm3), abs(meshCm3), 1e-9)
        return abs(meshCm3 - maskCm3) <= volumeToleranceFraction * scale
    }

    public static func overlay(segment: DicomSEGSegment, geometry: DicomSEGGeometry,
                              opacity: Double = 1.0,
                              pinnedLandmarks: [SIMD3<Double>] = []) -> HorosSEGSurfaceOverlay {
        let extracted = extract(segment: segment, geometry: geometry)
        let refined = refine(extracted, keeping: pinnedLandmarks)
        return HorosSEGSurfaceOverlay(
            segmentNumber: segment.number,
            trackingUID: segment.trackingUID,
            name: segment.label,
            color: segment.color,
            opacity: opacity,
            visible: segment.visible,
            mesh: refined,
            inspection: inspect(refined),
            maskVolumeCm3: maskVolumeCm3(segment: segment, geometry: geometry),
            pinnedLandmarks: pinnedLandmarks)
    }

    private static func occupied(_ segment: DicomSEGSegment, geometry: DicomSEGGeometry,
                               column: Int, row: Int, frame: Int) -> Bool {
        guard frame >= 0, frame < geometry.frames, frame < segment.frames.count else { return false }
        guard row >= 0, row < geometry.rows, column >= 0, column < geometry.columns else { return false }
        let bytes = segment.frames[frame]
        let offset = row * geometry.columns + column
        guard offset < bytes.count else { return false }
        return bytes[offset] > 0
    }

    /// DICOM positions locate sample centres. Mesh boundaries are halfway
    /// between adjacent planes; edge planes extend by half the nearest spacing.
    private static func frameBoundary(_ geometry: DicomSEGGeometry, _ k: Int) -> SIMD3<Double> {
        func origin(_ index: Int) -> SIMD3<Double> {
            let p = geometry.frameOrigin(index)
            return SIMD3(p[0], p[1], p[2])
        }
        if geometry.frames > 1 {
            if k <= 0 { return origin(0) - (origin(1) - origin(0)) / 2 }
            if k >= geometry.frames {
                return origin(geometry.frames - 1)
                    + (origin(geometry.frames - 1) - origin(geometry.frames - 2)) / 2
            }
            return (origin(k - 1) + origin(k)) / 2
        }
        let col = SIMD3(geometry.orientation[0], geometry.orientation[1], geometry.orientation[2])
        let row = SIMD3(geometry.orientation[3], geometry.orientation[4], geometry.orientation[5])
        return origin(0) + simd_normalize(simd_cross(col, row))
            * (Double(k) - 0.5) * geometry.sliceThickness
    }

    private static func corner(geometry: DicomSEGGeometry, column i: Int, row j: Int, frame k: Int) -> SIMD3<Double> {
        let col = SIMD3(geometry.orientation[0], geometry.orientation[1], geometry.orientation[2])
        let row = SIMD3(geometry.orientation[3], geometry.orientation[4], geometry.orientation[5])
        return frameBoundary(geometry, k)
            + col * ((Double(i) - 0.5) * geometry.spacingCol)
            + row * ((Double(j) - 0.5) * geometry.spacingRow)
    }

    /// Legacy rasterized ROI masks use the same extractor as SEG. Coordinates
    /// stay in the viewer's local frame; its existing actor transform is retained.
    @objc(meshForBinaryFrames:rows:columns:spacingX:spacingY:frameOffsets:singleFrameThickness:)
    public static func mesh(binaryFrames: [Data], rows: Int, columns: Int,
                            spacingX: Double, spacingY: Double, frameOffsets: [NSNumber],
                            singleFrameThickness: Double) -> HorosSEGSurfaceMesh? {
        guard rows > 0, columns > 0, rows <= Int.max / columns,
              !binaryFrames.isEmpty, binaryFrames.count == frameOffsets.count,
              binaryFrames.allSatisfy({ $0.count == rows * columns }),
              spacingX.isFinite, spacingY.isFinite, spacingX > 0, spacingY > 0,
              frameOffsets.allSatisfy({ $0.doubleValue.isFinite }),
              singleFrameThickness.isFinite, singleFrameThickness > 0 else { return nil }
        let offsets = frameOffsets.map(\.doubleValue)
        if offsets.count > 1 {
            let increasing = offsets[1] > offsets[0]
            guard zip(offsets, offsets.dropFirst()).allSatisfy({
                increasing ? $0 < $1 : $0 > $1
            }) else { return nil }
        }
        let geometry = DicomSEGGeometry(
            rows: rows, columns: columns, frames: binaryFrames.count,
            spacingRow: spacingY, spacingCol: spacingX, sliceThickness: singleFrameThickness,
            origin: [0, 0, offsets[0]], orientation: [1, 0, 0, 0, 1, 0],
            frameOfReferenceUID: "", frameOrigins: offsets.map { [0, 0, $0] })
        let segment = DicomSEGSegment(
            number: 1, label: "", trackingUID: "", color: (1, 1, 1), visible: true,
            kind: .binary, algorithm: "MANUAL", provenance: "legacy-roi-raster",
            referencedSOPInstanceUIDs: [], frames: binaryFrames, maximumFractionalValue: 1)
        return HorosSEGSurfaceMesh(mesh: extract(segment: segment, geometry: geometry),
                                  maskVolumeCm3: maskVolumeCm3(segment: segment, geometry: geometry))
    }

}

/// Surfaces for every segment in a store. Presentation (opacity, pinned
/// landmarks) is keyed by tracking UID so store commands stay the source of
/// name, colour, visibility, duplication and deletion.
@objc(HorosSEGSurfaceSet)
public final class HorosSEGSurfaceSet: NSObject {
    public private(set) var overlays: [HorosSEGSurfaceOverlay] = []
    private weak var store: DicomSEGStore?
    private var landmarks: [String: [SIMD3<Double>]] = [:]
    private var sourceMasks: [String: [Data]] = [:]
    private var geometry: DicomSEGGeometry?

    public init(store: DicomSEGStore) {
        self.store = store
        super.init()
        reload(from: store)
    }

    public func overlay(segment number: UInt16) -> HorosSEGSurfaceOverlay? {
        overlays.first { $0.segmentNumber == number }
    }

    public func setOpacity(_ opacity: Double, trackingUID: String) {
        guard let store, let segment = store.document.segments.first(where: { $0.trackingUID == trackingUID }) else { return }
        store.setOpacity(opacity, segment: segment.number)
    }

    public func pinLandmark(_ point: SIMD3<Double>, trackingUID: String) {
        var current = landmarks[trackingUID] ?? []
        current.append(point)
        landmarks[trackingUID] = current
    }

    public func reload(from store: DicomSEGStore) {
        self.store = store
        let previous = Dictionary(overlays.map { ($0.trackingUID, $0) }, uniquingKeysWith: { first, _ in first })
        overlays = store.document.segments.map { segment in
            if geometry == store.document.geometry, sourceMasks[segment.trackingUID] == segment.frames,
               var overlay = previous[segment.trackingUID] {
                overlay.segmentNumber = segment.number; overlay.name = segment.label
                overlay.color = segment.color; overlay.visible = segment.visible
                overlay.opacity = store.opacity(segment: segment.number)
                overlay.pinnedLandmarks = landmarks[segment.trackingUID] ?? []
                return overlay
            }
            return HorosSEGSurface.overlay(
                segment: segment, geometry: store.document.geometry,
                opacity: store.opacity(segment: segment.number),
                pinnedLandmarks: landmarks[segment.trackingUID] ?? [])
        }
        geometry = store.document.geometry
        sourceMasks = Dictionary(store.document.segments.map { ($0.trackingUID, $0.frames) },
                                 uniquingKeysWith: { first, _ in first })
    }
}

/// Immutable transfer to VTK, retaining double precision and original topology.
/// Buffers contain native-endian xyz Double triples and UInt64 triangle indices.
@objc(HorosSEGSurfaceMesh)
public final class HorosSEGSurfaceMesh: NSObject {
    @objc public let vertices: Data
    @objc public let triangles: Data
    @objc public let maskVolumeCm3: Double
    @objc public let meshVolumeCm3: Double
    @objc public let closed: Bool

    public init(mesh: ROISurfaceMesh, maskVolumeCm3: Double) {
        let positions = mesh.vertices.flatMap { [$0.x, $0.y, $0.z] }
        let indices = mesh.faces.flatMap { [UInt64($0.0), UInt64($0.1), UInt64($0.2)] }
        vertices = positions.withUnsafeBytes { Data($0) }
        triangles = indices.withUnsafeBytes { Data($0) }
        self.maskVolumeCm3 = maskVolumeCm3
        closed = ROISurfaceAlgorithm.isClosed(mesh)
        meshVolumeCm3 = ROISurfaceAlgorithm.volumeCm3(mesh) ?? 0
        super.init()
    }
}
