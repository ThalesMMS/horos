import Foundation
import simd

/// Identity of a decoded frame already owned by the native viewer. Frame
/// numbers use DICOM's one-based convention, unlike DCMPix/DicomImage.frameID.
@objc(HorosSEGSourceFrame)
public final class SEGSourceFrame: NSObject {
    public let sopInstanceUID: String
    public let frameNumber: Int
    public let frameCount: Int
    @objc public init?(sopInstanceUID: String, frameNumber: Int, frameCount: Int) {
        guard !sopInstanceUID.isEmpty, frameCount > 0,
              frameNumber > 0, frameNumber <= frameCount else { return nil }
        self.sopInstanceUID = sopInstanceUID
        self.frameNumber = frameNumber; self.frameCount = frameCount
        super.init()
    }
}

/// SEG state belongs to the existing volume session, with the #376 codec and
/// command history as its only model. Native views consume immutable snapshots.
@objc(HorosSEGViewerSession)
public final class SEGViewerSession: NSObject {
    private weak var volume: VolumeSession?
    private let identity: VolumeIdentity
    private let sourceSOPs: Set<String>
    private let sourceFrames: [String: Set<Int>]
    private let sourceFrameCounts: [String: Int]
    private let preferences: UserDefaults
    private let presentationKey: String
    public private(set) var store: DicomSEGStore?
    private var surfaces: HorosSEGSurfaceSet?
    @objc public private(set) var snapshots: [SEGViewerSurface] = []
    @objc public static let changedNotification = "HorosSEGViewerSessionChanged"

    @objc public convenience init(volume: VolumeSession, sourceSOPInstanceUIDs: [String]) {
        self.init(volume: volume, sourceSOPInstanceUIDs: sourceSOPInstanceUIDs, preferences: .standard)
    }

    public convenience init(volume: VolumeSession, sourceSOPInstanceUIDs: [String], preferences: UserDefaults) {
        self.init(volume: volume, sourceFrames: sourceSOPInstanceUIDs.compactMap {
            SEGSourceFrame(sopInstanceUID: $0, frameNumber: 1, frameCount: 1)
        }, preferences: preferences)
    }

    @objc public convenience init(volume: VolumeSession, sourceFrames: [SEGSourceFrame]) {
        self.init(volume: volume, sourceFrames: sourceFrames, preferences: .standard)
    }

    public init(volume: VolumeSession, sourceFrames: [SEGSourceFrame], preferences: UserDefaults) {
        self.preferences = preferences
        presentationKey = "HorosSEGSurfacePresentation:" + volume.identity.description
        self.volume = volume
        identity = volume.identity
        let grouped = Dictionary(grouping: sourceFrames, by: \.sopInstanceUID)
            .filter { Set($0.value.map(\.frameCount)).count == 1 }
        sourceSOPs = Set(grouped.keys)
        self.sourceFrames = grouped.mapValues { Set($0.map(\.frameNumber)) }
        sourceFrameCounts = grouped.mapValues { $0[0].frameCount }
        super.init()
    }

    @objc public var isCurrent: Bool {
        volume?.isOpen == true && volume?.isStale == false && volume?.identity == identity
    }

    /// Refusal is transactional: invalid input cannot replace the current SEG.
    @objc(loadData:)
    public func load(_ data: Data) -> String? {
        guard isCurrent else { return "The source volume is no longer available." }
        // #377 B: identified ROI interchange documents go through the existing
        // legacy converter and then the same SEG checks as any other file.
        // Typedstream archives carry no SOP identity and are refused as such.
        var bytes = data
        switch ROIArchiveFormat.classify(data) {
        case .jsonInterchange:
            let series: ROIInterchangeSeries
            do { series = try ROIInterchange.decode(data) } catch {
                return "ROI: " + error.localizedDescription
            }
            switch HorosLegacyROISeg.convert(series) {
            case .failure(let refusal): return "ROI: " + SEGViewerSession.describe(refusal)
            case .success(let converted):
                do { bytes = try DicomSEGCodec.encode(converted) } catch {
                    return "ROI: " + error.localizedDescription
                }
            }
        case .typedstream, .keyedArchive:
            return "ROI: " + SEGViewerSession.describe(HorosLegacyROISeg.convertTypedstreamArchive(data))
        case .empty, .unknown:
            break
        }
        var document = DicomSEGCodec.decode(bytes)
        guard document.diagnoses.isEmpty else {
            return "SEG: " + document.diagnoses.map(\.rawValue).joined(separator: ", ")
        }
        guard !document.segments.isEmpty,
              Set(document.segments.map(\.number)).count == document.segments.count,
              Set(document.segments.map(\.trackingUID)).count == document.segments.count,
              document.segments.allSatisfy({ !$0.trackingUID.isEmpty }) else {
            return "The SEG segment identities are missing or duplicated."
        }
        guard document.kind == .binary,
              document.segments.allSatisfy({ $0.kind == .binary }) else {
            return "A fractional SEG requires an explicit threshold before surface extraction."
        }
        guard document.identity.studyInstanceUID == identity.studyInstanceUID,
              !identity.frameOfReferenceUID.isEmpty,
              document.identity.frameOfReferenceUID == identity.frameOfReferenceUID else {
            return "The SEG belongs to a different study or frame of reference."
        }
        let references = Set(document.identity.sourceSOPInstanceUIDs)
        guard !references.isEmpty, references.isSubset(of: sourceSOPs) else {
            return "The SEG references images outside the open source volume."
        }
        // The general series reference is not a substitute for functional-group
        // provenance: inspect every SourceImage item, including multiframe SOPs.
        for reference in document.segments.flatMap(\.frameReferences).flatMap({ $0 }) {
            guard references.contains(reference.sopInstanceUID),
                  let available = sourceFrames[reference.sopInstanceUID],
                  let count = sourceFrameCounts[reference.sopInstanceUID] else {
                return "The SEG frame references images outside the open source volume."
            }
            if reference.frameNumbers.isEmpty {
                guard available.count == count else {
                    return "The SEG references a complete multiframe image outside the open timepoint."
                }
            } else if !Set(reference.frameNumbers).isSubset(of: available) {
                return "The SEG references frames outside the open source volume."
            }
        }
        let geometry = document.geometry
        guard geometry.rows > 0, geometry.columns > 0, geometry.frames > 0,
              geometry.rows <= Int.max / geometry.columns,
              geometry.spacingRow.isFinite, geometry.spacingRow > 0,
              geometry.spacingCol.isFinite, geometry.spacingCol > 0,
              geometry.sliceThickness.isFinite, geometry.sliceThickness > 0,
              geometry.orientation.count == 6,
              geometry.orientation.allSatisfy(\.isFinite),
              geometry.frameOrigins.count == geometry.frames,
              geometry.frameOrigins.allSatisfy({ $0.count == 3 && $0.allSatisfy(\.isFinite) }),
              document.segments.allSatisfy({ $0.frames.count == geometry.frames &&
                  $0.frames.allSatisfy({ $0.count == geometry.rows * geometry.columns }) }) else {
            return "The SEG geometry is incomplete or invalid."
        }
        let col = SIMD3(geometry.orientation[0], geometry.orientation[1], geometry.orientation[2])
        let row = SIMD3(geometry.orientation[3], geometry.orientation[4], geometry.orientation[5])
        guard abs(simd_length(col) - 1) < 1e-5, abs(simd_length(row) - 1) < 1e-5,
              abs(simd_dot(col, row)) < 1e-5 else { return "The SEG orientation is invalid." }
        let normal = simd_cross(col, row)
        let positions = geometry.frameOrigins.map { simd_dot(SIMD3($0[0], $0[1], $0[2]), normal) }
        if positions.count > 1 {
            let increasing = positions[1] > positions[0]
            guard zip(positions, positions.dropFirst()).allSatisfy({ increasing ? $0 < $1 : $0 > $1 }) else {
                return "The SEG planes are coincident or unordered."
            }
        }
        let saved = preferences.dictionary(forKey: presentationKey) as? [String: [String: Double]] ?? [:]
        var opacities: [String: Double] = [:]
        for index in document.segments.indices {
            let uid = document.segments[index].trackingUID
            if let state = saved[uid] {
                if let visible = state["visible"] { document.segments[index].visible = visible != 0 }
                opacities[uid] = state["opacity"]
            }
        }
        let next = DicomSEGStore(document: document, surfaceOpacities: opacities)
        let surfaceSet = HorosSEGSurfaceSet(store: next)
        guard surfaceSet.overlays.allSatisfy({ $0.inspection.closed &&
            HorosSEGSurface.volumeIsCoherent(meshCm3: $0.inspection.volumeCm3,
                                             maskCm3: $0.maskVolumeCm3) }) else {
            return "This SEG mask does not produce a closed surface."
        }
        store = next
        surfaces = surfaceSet
        reload()
        return nil
    }

    static func describe(_ refusal: HorosLegacyROISeg.Refusal) -> String {
        switch refusal {
        case .missingIdentity:
            return "This ROI archive has no SOP or Frame of Reference identity and cannot be matched to the open volume; export it as ROI interchange JSON from its series first."
        case .missingGeometry: return "The ROI document has no image geometry."
        case .emptyMask: return "No ROI in the document covers any pixel."
        case .unsupportedType: return "Only brush, closed polygon, rectangle, oval and pencil ROIs become SEG regions."
        }
    }

    @objc public func rename(_ number: UInt16, label: String) {
        guard isCurrent else { return }; _ = store?.setLabel(label, segment: number); reload()
    }
    @objc public func recolor(_ number: UInt16, red: Double, green: Double, blue: Double) {
        guard isCurrent, [red, green, blue].allSatisfy({ $0.isFinite && (0...1).contains($0) }) else { return }
        _ = store?.setColor((red, green, blue), segment: number); reload()
    }
    @objc public func setVisible(_ number: UInt16, visible: Bool) {
        guard isCurrent else { return }; _ = store?.setVisibility(visible, segment: number); reload()
    }
    @objc public func duplicate(_ number: UInt16) {
        guard isCurrent else { return }; _ = store?.duplicate(segment: number); reload()
    }
    @objc public func remove(_ number: UInt16) {
        guard isCurrent else { return }; _ = store?.remove(segment: number); reload()
    }
    @objc public func setOpacity(_ number: UInt16, opacity: Double) {
        guard isCurrent, opacity.isFinite,
              let segment = store?.document.segments.first(where: { $0.number == number }) else { return }
        surfaces?.setOpacity(opacity, trackingUID: segment.trackingUID); reload()
    }
    @objc public func undo() { guard isCurrent else { return }; _ = store?.undo(); reload() }
    @objc public func redo() { guard isCurrent else { return }; _ = store?.redo(); reload() }
    @objc public var canUndo: Bool { isCurrent && store?.canUndo == true }
    @objc public var canRedo: Bool { isCurrent && store?.canRedo == true }
    @objc public func exportDerived() throws -> Data {
        guard isCurrent, let store else { throw DicomSEGDiagnosis.incompatibleGeometry }
        return try store.exportDerived()
    }
    @objc public func close() {
        store = nil; surfaces = nil; snapshots = []
        NotificationCenter.default.post(name: Notification.Name(Self.changedNotification), object: self)
    }
    private func reload() {
        guard let store, let surfaces else { return }
        surfaces.reload(from: store)
        snapshots = surfaces.overlays.map(SEGViewerSurface.init)
        var saved = preferences.dictionary(forKey: presentationKey) as? [String: [String: Double]] ?? [:]
        for surface in snapshots {
            saved[surface.trackingUID] = ["opacity": surface.opacity, "visible": surface.visible ? 1 : 0]
        }
        preferences.set(saved, forKey: presentationKey)
        NotificationCenter.default.post(name: Notification.Name(Self.changedNotification), object: self)
    }
}

@objc(HorosSEGViewerSurface)
public final class SEGViewerSurface: NSObject {
    @objc public let number: UInt16
    @objc public let trackingUID: String
    @objc public let label: String
    @objc public let red: Double
    @objc public let green: Double
    @objc public let blue: Double
    @objc public let opacity: Double
    @objc public let visible: Bool
    @objc public let mesh: HorosSEGSurfaceMesh
    init(_ overlay: HorosSEGSurfaceOverlay) {
        number = overlay.segmentNumber; trackingUID = overlay.trackingUID
        label = overlay.name; red = overlay.color.r; green = overlay.color.g; blue = overlay.color.b
        opacity = overlay.opacity; visible = overlay.visible
        mesh = HorosSEGSurfaceMesh(mesh: overlay.mesh, maskVolumeCm3: overlay.maskVolumeCm3)
        super.init()
    }
}
