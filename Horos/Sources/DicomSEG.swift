import Foundation

/// Shared ROI/SEG model, identities, commands and DICOM SEG persistence (#376).
/// Classic JSON interchange (#233) and archive identity (#231) keep their own
/// types; this type uses the same UID keys so a second patient-name matcher is
/// never introduced. Overlay in planar/MPR viewers is not implemented here.
/// Surface meshes for #377 A are extracted by `HorosSEGSurface` from these masks.

public enum DicomSEGKind: String, Equatable {
    case binary = "BINARY"
    case fractional = "FRACTIONAL"
}

public enum DicomSEGDiagnosis: String, Equatable, Hashable, Error {
    case emptySegment = "empty-segment"
    case truncatedFrames = "truncated-frames"
    case missingReferencedSOP = "missing-referenced-sop"
    case incompatibleGeometry = "incompatible-geometry"
    case missingFrameOfReference = "missing-frame-of-reference"
    case unsupportedTransferSyntax = "unsupported-transfer-syntax"
    case notSegmentation = "not-segmentation"
    case silentBinarize = "fractional-requires-explicit-threshold"
    case notDICOM = "not-dicom"
}

public struct DicomSEGIdentity: Equatable {
    public var sopInstanceUID: String
    public var seriesInstanceUID: String
    public var studyInstanceUID: String
    public var frameOfReferenceUID: String
    public var sourceSOPInstanceUIDs: [String]

    public static let jsonKeys = [
        "sopInstanceUID", "seriesInstanceUID", "studyInstanceUID",
        "frameOfReferenceUID", "frame"
    ]
}

public struct DicomSEGGeometry: Equatable {
    public var rows: Int
    public var columns: Int
    public var frames: Int
    public var spacingRow: Double
    public var spacingCol: Double
    public var sliceThickness: Double
    public var origin: [Double]
    public var orientation: [Double]
    public var frameOfReferenceUID: String
    public var frameOrigins: [[Double]]

    public var voxelCount: Int { max(0, rows) * max(0, columns) * max(0, frames) }

    public func patientPoint(column i: Int, row j: Int, frame k: Int) -> [Double]? {
        guard orientation.count >= 6 else { return nil }
        let origin = frameOrigin(k)
        guard origin.count >= 3 else { return nil }
        let col = [orientation[0], orientation[1], orientation[2]]
        let rowC = [orientation[3], orientation[4], orientation[5]]
        return [
            origin[0] + Double(i) * spacingCol * col[0] + Double(j) * spacingRow * rowC[0],
            origin[1] + Double(i) * spacingCol * col[1] + Double(j) * spacingRow * rowC[1],
            origin[2] + Double(i) * spacingCol * col[2] + Double(j) * spacingRow * rowC[2]
        ]
    }

    public func frameOrigin(_ k: Int) -> [Double] {
        if k >= 0 && k < frameOrigins.count && frameOrigins[k].count >= 3 {
            return frameOrigins[k]
        }
        return origin
    }

    public func indexOfFrame(matchingOrigin candidate: [Double], tolerance: Double = 0.05) -> Int? {
        guard candidate.count >= 3 else { return nil }
        for (index, origin) in frameOrigins.enumerated() where origin.count >= 3 {
            let d = hypot(hypot(origin[0] - candidate[0], origin[1] - candidate[1]), origin[2] - candidate[2])
            if d <= tolerance { return index }
        }
        return nil
    }
}

public struct DicomSEGSegment: Equatable {
    public var number: UInt16
    public var label: String
    public var trackingUID: String
    public var color: (r: Double, g: Double, b: Double)
    public var visible: Bool
    public var kind: DicomSEGKind
    public var algorithm: String
    public var provenance: String
    public var referencedSOPInstanceUIDs: [String]
    /// Planar frames in file order. Binary: 0/1. Fractional: 0...maximumFractionalValue.
    public var frames: [Data]
    public var maximumFractionalValue: UInt8

    public static func == (lhs: DicomSEGSegment, rhs: DicomSEGSegment) -> Bool {
        lhs.number == rhs.number
            && lhs.label == rhs.label
            && lhs.trackingUID == rhs.trackingUID
            && lhs.color.r == rhs.color.r && lhs.color.g == rhs.color.g && lhs.color.b == rhs.color.b
            && lhs.visible == rhs.visible
            && lhs.kind == rhs.kind
            && lhs.algorithm == rhs.algorithm
            && lhs.provenance == rhs.provenance
            && lhs.referencedSOPInstanceUIDs == rhs.referencedSOPInstanceUIDs
            && lhs.frames == rhs.frames
            && lhs.maximumFractionalValue == rhs.maximumFractionalValue
    }

    public var occupiedVoxels: Int {
        frames.reduce(0) { $0 + $1.reduce(0) { $0 + ($1 > 0 ? 1 : 0) } }
    }
}

public struct DicomSEGDocument: Equatable {
    public var identity: DicomSEGIdentity
    public var geometry: DicomSEGGeometry
    public var kind: DicomSEGKind
    public var segments: [DicomSEGSegment]
    public var diagnoses: [DicomSEGDiagnosis]
    public var sourceBytes: Data?
    /// SEG is never a scalar acquisition in preview.
    public var previewKind: String { "segmentation" }
}

public enum DicomSEGCommand: Equatable {
    case setLabel(number: UInt16, from: String, to: String)
    case setColor(number: UInt16, from: (Double, Double, Double), to: (Double, Double, Double))
    case setVisibility(number: UInt16, from: Bool, to: Bool)
    case setMask(number: UInt16, from: [Data], to: [Data], explicit: Bool)
    case duplicate(from: UInt16, created: DicomSEGSegment)
    case remove(index: Int, segment: DicomSEGSegment)

    public static func == (lhs: DicomSEGCommand, rhs: DicomSEGCommand) -> Bool {
        switch (lhs, rhs) {
        case let (.setLabel(n1, a1, b1), .setLabel(n2, a2, b2)):
            return n1 == n2 && a1 == a2 && b1 == b2
        case let (.setColor(n1, a1, b1), .setColor(n2, a2, b2)):
            return n1 == n2 && a1 == a2 && b1 == b2
        case let (.setVisibility(n1, a1, b1), .setVisibility(n2, a2, b2)):
            return n1 == n2 && a1 == a2 && b1 == b2
        case let (.setMask(n1, a1, b1, e1), .setMask(n2, a2, b2, e2)):
            return n1 == n2 && a1 == a2 && b1 == b2 && e1 == e2
        case let (.duplicate(a, s1), .duplicate(b, s2)):
            return a == b && s1 == s2
        case let (.remove(i1, s1), .remove(i2, s2)):
            return i1 == i2 && s1 == s2
        default:
            return false
        }
    }
}

@objc(HorosDicomSEGStore)
public final class DicomSEGStore: NSObject {
    public private(set) var document: DicomSEGDocument
    private var undoStack: [DicomSEGCommand] = []
    private var redoStack: [DicomSEGCommand] = []

    public init(document: DicomSEGDocument) {
        self.document = document
        super.init()
    }

    public var canUndo: Bool { !undoStack.isEmpty }
    public var canRedo: Bool { !redoStack.isEmpty }

    @discardableResult
    public func setLabel(_ label: String, segment number: UInt16) -> Bool {
        guard let index = index(of: number) else { return false }
        let previous = document.segments[index].label
        apply(.setLabel(number: number, from: previous, to: label), record: true)
        return true
    }

    @discardableResult
    public func setColor(_ color: (Double, Double, Double), segment number: UInt16) -> Bool {
        guard let index = index(of: number) else { return false }
        let previous = document.segments[index].color
        apply(.setColor(number: number, from: (previous.r, previous.g, previous.b), to: color), record: true)
        return true
    }

    @discardableResult
    public func setVisibility(_ visible: Bool, segment number: UInt16) -> Bool {
        guard let index = index(of: number) else { return false }
        let previous = document.segments[index].visible
        apply(.setVisibility(number: number, from: previous, to: visible), record: true)
        return true
    }

    public func setMask(_ frames: [Data], segment number: UInt16, explicit: Bool) -> DicomSEGDiagnosis? {
        guard let index = index(of: number) else { return .emptySegment }
        let segment = document.segments[index]
        if segment.kind == .fractional && !explicit {
            return .silentBinarize
        }
        apply(.setMask(number: number, from: segment.frames, to: frames, explicit: explicit), record: true)
        return nil
    }

    public func binarize(segment number: UInt16, threshold: UInt8) -> DicomSEGDiagnosis? {
        guard let index = index(of: number) else { return .emptySegment }
        let segment = document.segments[index]
        let converted = segment.frames.map { frame in
            Data(frame.map { $0 >= threshold ? UInt8(1) : 0 })
        }
        apply(.setMask(number: number, from: segment.frames, to: converted, explicit: true), record: true)
        document.segments[index].kind = .binary
        document.segments[index].provenance += "; thresholded at \(threshold)"
        return nil
    }

    public func duplicate(segment number: UInt16) -> UInt16? {
        guard let index = index(of: number) else { return nil }
        var copy = document.segments[index]
        let created = nextNumber()
        copy.number = created
        copy.trackingUID = DicomSEGCodec.makeUID()
        copy.label += " copy"
        copy.provenance = "duplicated from segment \(number) of \(document.identity.sopInstanceUID)"
        apply(.duplicate(from: number, created: copy), record: true)
        return created
    }

    @discardableResult
    public func remove(segment number: UInt16) -> Bool {
        guard let index = index(of: number) else { return false }
        let segment = document.segments[index]
        apply(.remove(index: index, segment: segment), record: true)
        return true
    }

    public func undo() -> Bool {
        guard let command = undoStack.popLast() else { return false }
        invert(command)
        redoStack.append(command)
        return true
    }

    public func redo() -> Bool {
        guard let command = redoStack.popLast() else { return false }
        apply(command, record: false)
        undoStack.append(command)
        return true
    }

    public func exportDerived() throws -> Data {
        var derived = document
        derived.identity.sopInstanceUID = DicomSEGCodec.makeUID()
        derived.identity.seriesInstanceUID = DicomSEGCodec.makeUID()
        derived.sourceBytes = nil
        for i in derived.segments.indices {
            if derived.segments[i].algorithm == "MANUAL" { continue }
            derived.segments[i].algorithm = "SEMIAUTOMATIC"
            if !derived.segments[i].provenance.contains("derived from") {
                derived.segments[i].provenance = "derived from \(document.identity.sopInstanceUID); " + derived.segments[i].provenance
            }
        }
        return try DicomSEGCodec.encode(derived)
    }

    private func index(of number: UInt16) -> Int? {
        document.segments.firstIndex { $0.number == number }
    }

    private func nextNumber() -> UInt16 {
        (document.segments.map(\.number).max() ?? 0) + 1
    }

    private func apply(_ command: DicomSEGCommand, record: Bool) {
        switch command {
        case let .setLabel(number, _, to):
            if let i = index(of: number) { document.segments[i].label = to }
        case let .setColor(number, _, to):
            if let i = index(of: number) { document.segments[i].color = (to.0, to.1, to.2) }
        case let .setVisibility(number, _, to):
            if let i = index(of: number) { document.segments[i].visible = to }
        case let .setMask(number, _, to, _):
            if let i = index(of: number) { document.segments[i].frames = to }
        case let .duplicate(_, created):
            if document.segments.contains(where: { $0.number == created.number }) == false {
                document.segments.append(created)
            }
        case let .remove(_, segment):
            document.segments.removeAll { $0.number == segment.number }
        }
        if record {
            undoStack.append(command)
            redoStack.removeAll()
        }
    }

    private func invert(_ command: DicomSEGCommand) {
        switch command {
        case let .setLabel(number, from, _):
            if let i = index(of: number) { document.segments[i].label = from }
        case let .setColor(number, from, _):
            if let i = index(of: number) { document.segments[i].color = (from.0, from.1, from.2) }
        case let .setVisibility(number, from, _):
            if let i = index(of: number) { document.segments[i].visible = from }
        case let .setMask(number, from, _, _):
            if let i = index(of: number) {
                document.segments[i].frames = from
                if let range = document.segments[i].provenance.range(of: "; thresholded at ") {
                    document.segments[i].provenance.removeSubrange(range.lowerBound...)
                    document.segments[i].kind = .fractional
                }
            }
        case let .duplicate(_, created):
            document.segments.removeAll { $0.number == created.number }
        case let .remove(index, segment):
            let clamped = min(max(index, 0), document.segments.count)
            if document.segments.contains(where: { $0.number == segment.number }) == false {
                document.segments.insert(segment, at: clamped)
            }
        }
    }
}

public enum DicomSEGGeometryMap {
    public static func map(segment: DicomSEGSegment,
                            from source: DicomSEGGeometry,
                            onto destination: DicomSEGGeometry) -> Result<[Data], DicomSEGDiagnosis> {
        if source.frameOfReferenceUID.isEmpty || destination.frameOfReferenceUID.isEmpty {
            return .failure(.missingFrameOfReference)
        }
        if source.frameOfReferenceUID != destination.frameOfReferenceUID {
            return .failure(.incompatibleGeometry)
        }
        var output: [Data] = []
        for destFrame in 0..<destination.frames {
            var plane = Data(repeating: 0, count: destination.rows * destination.columns)
            for row in 0..<destination.rows {
                for column in 0..<destination.columns {
                    guard let patient = destination.patientPoint(column: column, row: row, frame: destFrame) else { continue }
                    if let sample = sample(segment: segment, source: source, patient: patient) {
                        plane[row * destination.columns + column] = sample
                    }
                }
            }
            output.append(plane)
        }
        return .success(output)
    }

    private static func sample(segment: DicomSEGSegment, source: DicomSEGGeometry, patient: [Double]) -> UInt8? {
        guard source.orientation.count >= 6, source.spacingCol != 0, source.spacingRow != 0 else { return nil }
        let col = [source.orientation[0], source.orientation[1], source.orientation[2]]
        let rowC = [source.orientation[3], source.orientation[4], source.orientation[5]]
        var best: (Int, Double)? = nil
        for (index, origin) in source.frameOrigins.enumerated() where origin.count >= 3 {
            let d = hypot(hypot(origin[0] - patient[0], origin[1] - patient[1]), origin[2] - patient[2])
            if best == nil || d < best!.1 { best = (index, d) }
        }
        guard let frame = best?.0, frame < segment.frames.count else { return nil }
        let origin = source.frameOrigin(frame)
        let dx = patient[0] - origin[0], dy = patient[1] - origin[1], dz = patient[2] - origin[2]
        let i = Int((dx * col[0] + dy * col[1] + dz * col[2]) / source.spacingCol + 0.5)
        let j = Int((dx * rowC[0] + dy * rowC[1] + dz * rowC[2]) / source.spacingRow + 0.5)
        guard i >= 0, j >= 0, i < source.columns, j < source.rows else { return nil }
        let bytes = segment.frames[frame]
        let offset = j * source.columns + i
        guard offset < bytes.count else { return nil }
        return bytes[offset]
    }
}

public enum DicomSEGCodec {
    public static let sopClassUID = "1.2.840.10008.5.1.4.1.1.66.4"
    public static let explicitLittleEndian = "1.2.840.10008.1.2.1"

    public static func makeUID() -> String {
        let millis = UInt64(Date().timeIntervalSince1970 * 1000)
        let random = UInt64.random(in: 1...999_999_999)
        return "2.25.\(millis).\(random)"
    }

    public static func decode(_ data: Data) -> DicomSEGDocument {
        var diagnoses: [DicomSEGDiagnosis] = []
        guard data.count >= 132, data[128..<132] == Data("DICM".utf8) else {
            return emptyDocument(diagnoses: [.notDICOM])
        }
        let elements = DicomBinary.parse(data)
        let ts = DicomBinary.string(elements, 0x0002, 0x0010)
        if !ts.isEmpty && ts != explicitLittleEndian {
            diagnoses.append(.unsupportedTransferSyntax)
        }
        let sopClass = DicomBinary.string(elements, 0x0008, 0x0016)
        if sopClass != sopClassUID {
            diagnoses.append(.notSegmentation)
        }
        let identity = DicomSEGIdentity(
            sopInstanceUID: DicomBinary.string(elements, 0x0008, 0x0018),
            seriesInstanceUID: DicomBinary.string(elements, 0x0020, 0x000E),
            studyInstanceUID: DicomBinary.string(elements, 0x0020, 0x000D),
            frameOfReferenceUID: DicomBinary.string(elements, 0x0020, 0x0052),
            sourceSOPInstanceUIDs: referencedSOPs(elements)
        )
        let rows = Int(DicomBinary.us(elements, 0x0028, 0x0010) ?? 0)
        let columns = Int(DicomBinary.us(elements, 0x0028, 0x0011) ?? 0)
        let pixelFrames = max(1, Int(DicomBinary.string(elements, 0x0028, 0x0008)) ?? 1)
        let kind = DicomBinary.string(elements, 0x0062, 0x0001) == "FRACTIONAL" ? DicomSEGKind.fractional : .binary
        let bits = Int(DicomBinary.us(elements, 0x0028, 0x0100) ?? (kind == .binary ? 1 : 8))
        let maxFrac = UInt8(min(255, DicomBinary.us(elements, 0x0062, 0x000E) ?? 255))
        let shared = DicomBinary.sequence(elements, 0x5200, 0x9229).first ?? []
        let pixelMeasures = DicomBinary.sequence(shared, 0x0028, 0x9110).first ?? []
        let spacing = DicomBinary.doubles(DicomBinary.string(pixelMeasures, 0x0028, 0x0030))
        let thickness = DicomBinary.doubles(DicomBinary.string(pixelMeasures, 0x0018, 0x0050)).first ?? spacing.last ?? 1
        let orientationSeq = DicomBinary.sequence(shared, 0x0020, 0x9116).first ?? []
        let orientation = DicomBinary.doubles(DicomBinary.string(orientationSeq, 0x0020, 0x0037))
        let perFrame = DicomBinary.sequence(elements, 0x5200, 0x9230)
        var frameOrigins: [[Double]] = []
        var frameSegment: [UInt16] = []
        var frameSOPs: [String] = []
        for item in perFrame {
            let position = DicomBinary.sequence(item, 0x0020, 0x9113).first ?? []
            let origin = DicomBinary.doubles(DicomBinary.string(position, 0x0020, 0x0032))
            frameOrigins.append(origin)
            let ident = DicomBinary.sequence(item, 0x0062, 0x000A).first ?? []
            frameSegment.append(DicomBinary.us(ident, 0x0062, 0x000B) ?? 1)
            let derivation = DicomBinary.sequence(item, 0x0008, 0x9124).first ?? []
            let source = DicomBinary.sequence(derivation, 0x0008, 0x2112).first ?? []
            frameSOPs.append(DicomBinary.string(source, 0x0008, 0x1155))
        }
        if frameOrigins.isEmpty {
            frameOrigins = [Array(repeating: 0, count: 3)]
        }
        var spatialOrigins: [[Double]] = []
        for origin in frameOrigins {
            if !spatialOrigins.contains(where: { closeOrigin($0, origin) }) {
                spatialOrigins.append(origin)
            }
        }
        let geometry = DicomSEGGeometry(
            rows: rows, columns: columns, frames: spatialOrigins.count,
            spacingRow: spacing.count > 1 ? spacing[0] : 1,
            spacingCol: spacing.count > 1 ? spacing[1] : (spacing.first ?? 1),
            sliceThickness: thickness,
            origin: spatialOrigins.first ?? [0, 0, 0],
            orientation: orientation.isEmpty ? [1, 0, 0, 0, 1, 0] : orientation,
            frameOfReferenceUID: identity.frameOfReferenceUID,
            frameOrigins: spatialOrigins
        )
        let pixel = DicomBinary.data(elements, 0x7FE0, 0x0010)
        let unpacked = unpack(pixel, rows: rows, columns: columns, frames: pixelFrames, bits: bits, kind: kind)
        if unpacked.truncated { diagnoses.append(.truncatedFrames) }
        if frameSOPs.contains(where: { $0.isEmpty }) && !identity.sourceSOPInstanceUIDs.isEmpty {
            diagnoses.append(.missingReferencedSOP)
        }
        var segments: [DicomSEGSegment] = []
        let emptyPlane = Data(repeating: 0, count: max(0, rows * columns))
        for item in DicomBinary.sequence(elements, 0x0062, 0x0002) {
            let number = DicomBinary.us(item, 0x0062, 0x0004) ?? 1
            let color = DicomBinary.usArray(item, 0x0062, 0x000D)
            let rgb: (Double, Double, Double) = color.count >= 3
                ? (Double(color[0]) / 65535, Double(color[1]) / 65535, Double(color[2]) / 65535)
                : (1, 0, 0)
            var planes = Array(repeating: emptyPlane, count: spatialOrigins.count)
            var refs = Array(repeating: "", count: spatialOrigins.count)
            for (index, assigned) in frameSegment.enumerated() where assigned == number {
                let origin = index < frameOrigins.count ? frameOrigins[index] : []
                let spatial = spatialOrigins.firstIndex(where: { closeOrigin($0, origin) }) ?? min(index, max(0, spatialOrigins.count - 1))
                if index < unpacked.frames.count {
                    planes[spatial] = unpacked.frames[index]
                }
                if index < frameSOPs.count {
                    refs[spatial] = frameSOPs[index]
                }
            }
            if planes.allSatisfy({ $0.allSatisfy { $0 == 0 } }) {
                diagnoses.append(.emptySegment)
            }
            segments.append(DicomSEGSegment(
                number: number,
                label: DicomBinary.string(item, 0x0062, 0x0005),
                trackingUID: DicomBinary.string(item, 0x0062, 0x0021),
                color: rgb,
                visible: true,
                kind: kind,
                algorithm: DicomBinary.string(item, 0x0062, 0x0008),
                provenance: DicomBinary.string(item, 0x0062, 0x0009),
                referencedSOPInstanceUIDs: refs,
                frames: planes,
                maximumFractionalValue: maxFrac
            ))
        }
        if segments.contains(where: { $0.occupiedVoxels == 0 }) && !diagnoses.contains(.emptySegment) {
            diagnoses.append(.emptySegment)
        }
        if identity.frameOfReferenceUID.isEmpty {
            diagnoses.append(.missingFrameOfReference)
        }
        return DicomSEGDocument(
            identity: identity,
            geometry: geometry,
            kind: kind,
            segments: segments,
            diagnoses: Array(Set(diagnoses)),
            sourceBytes: data
        )
    }

    private static func closeOrigin(_ a: [Double], _ b: [Double]) -> Bool {
        guard a.count >= 3, b.count >= 3 else { return false }
        return hypot(hypot(a[0] - b[0], a[1] - b[1]), a[2] - b[2]) <= 0.05
    }

    public static func encode(_ document: DicomSEGDocument) throws -> Data {
        let bits: UInt16 = document.kind == .binary ? 1 : 8
        var frameItems: [[DicomBinary.Element]] = []
        var pixel = Data()
        for segment in document.segments {
            for (index, plane) in segment.frames.enumerated() {
                let origin = document.geometry.frameOrigin(index)
                let sop = index < segment.referencedSOPInstanceUIDs.count ? segment.referencedSOPInstanceUIDs[index] : (segment.referencedSOPInstanceUIDs.first ?? "")
                frameItems.append(perFrameItem(origin: origin, segment: segment.number, referencedSOP: sop))
                if document.kind == .binary {
                    pixel.append(packBinary(plane, rows: document.geometry.rows, columns: document.geometry.columns))
                } else {
                    pixel.append(plane)
                }
            }
        }
        var dataset: [DicomBinary.Element] = [
            DicomBinary.ui(0x0008, 0x0016, sopClassUID),
            DicomBinary.ui(0x0008, 0x0018, document.identity.sopInstanceUID),
            DicomBinary.ui(0x0020, 0x000D, document.identity.studyInstanceUID),
            DicomBinary.ui(0x0020, 0x000E, document.identity.seriesInstanceUID),
            DicomBinary.ui(0x0020, 0x0052, document.geometry.frameOfReferenceUID),
            DicomBinary.cs(0x0008, 0x0060, "SEG"),
            DicomBinary.cs(0x0062, 0x0001, document.kind.rawValue),
            DicomBinary.us(0x0028, 0x0002, 1),
            DicomBinary.cs(0x0028, 0x0004, "MONOCHROME2"),
            DicomBinary.is(0x0028, 0x0008, "\(max(1, document.segments.reduce(0) { $0 + $1.frames.count }))"),
            DicomBinary.us(0x0028, 0x0010, UInt16(document.geometry.rows)),
            DicomBinary.us(0x0028, 0x0011, UInt16(document.geometry.columns)),
            DicomBinary.us(0x0028, 0x0100, bits),
            DicomBinary.us(0x0028, 0x0101, bits),
            DicomBinary.us(0x0028, 0x0102, bits == 1 ? 0 : 7),
            DicomBinary.us(0x0028, 0x0103, 0)
        ]
        if document.kind == .fractional {
            dataset.append(DicomBinary.us(0x0062, 0x000E, UInt16(document.segments.first?.maximumFractionalValue ?? 255)))
        }
        dataset.append(DicomBinary.sq(0x0062, 0x0002, document.segments.map(segmentItem)))
        dataset.append(DicomBinary.sq(0x5200, 0x9229, [sharedItem(document.geometry)]))
        dataset.append(DicomBinary.sq(0x5200, 0x9230, frameItems))
        if !document.identity.sourceSOPInstanceUIDs.isEmpty {
            dataset.append(DicomBinary.sq(0x0008, 0x1115, [referencedSeries(document.identity)]))
        }
        dataset.append(DicomBinary.ob(0x7FE0, 0x0010, pixel))
        return DicomBinary.file(classUID: sopClassUID, instanceUID: document.identity.sopInstanceUID, dataset: dataset)
    }

    private static func emptyDocument(diagnoses: [DicomSEGDiagnosis]) -> DicomSEGDocument {
        DicomSEGDocument(
            identity: DicomSEGIdentity(sopInstanceUID: "", seriesInstanceUID: "", studyInstanceUID: "", frameOfReferenceUID: "", sourceSOPInstanceUIDs: []),
            geometry: DicomSEGGeometry(rows: 0, columns: 0, frames: 0, spacingRow: 1, spacingCol: 1, sliceThickness: 1, origin: [0, 0, 0], orientation: [1, 0, 0, 0, 1, 0], frameOfReferenceUID: "", frameOrigins: []),
            kind: .binary,
            segments: [],
            diagnoses: diagnoses,
            sourceBytes: nil
        )
    }

    private static func referencedSOPs(_ elements: [DicomBinary.Element]) -> [String] {
        var uids: [String] = []
        for series in DicomBinary.sequence(elements, 0x0008, 0x1115) {
            for instance in DicomBinary.sequence(series, 0x0008, 0x1140) {
                let uid = DicomBinary.string(instance, 0x0008, 0x1155)
                if !uid.isEmpty { uids.append(uid) }
            }
        }
        return uids
    }

    private static func unpack(_ pixel: Data, rows: Int, columns: Int, frames: Int, bits: Int, kind: DicomSEGKind) -> (frames: [Data], truncated: Bool) {
        let plane = max(0, rows * columns)
        if plane == 0 { return ([], pixel.isEmpty) }
        if kind == .binary && bits == 1 {
            let packed = (plane + 7) / 8
            var out: [Data] = []
            var truncated = false
            for frame in 0..<frames {
                let start = frame * packed
                if start >= pixel.count {
                    truncated = true
                    out.append(Data(repeating: 0, count: plane))
                    continue
                }
                let slice = pixel.subdata(in: start..<min(pixel.count, start + packed))
                if slice.count < packed { truncated = true }
                var unpacked = Data(repeating: 0, count: plane)
                for i in 0..<plane {
                    let byte = i / 8
                    if byte < slice.count {
                        let bit = (slice[byte] >> (7 - (i % 8))) & 1
                        unpacked[i] = bit
                    }
                }
                out.append(unpacked)
            }
            return (out, truncated)
        }
        var out: [Data] = []
        var truncated = false
        for frame in 0..<frames {
            let start = frame * plane
            if start >= pixel.count {
                truncated = true
                out.append(Data(repeating: 0, count: plane))
                continue
            }
            let end = min(pixel.count, start + plane)
            var slice = pixel.subdata(in: start..<end)
            if slice.count < plane {
                truncated = true
                slice.append(Data(repeating: 0, count: plane - slice.count))
            }
            out.append(slice)
        }
        return (out, truncated)
    }

    private static func packBinary(_ plane: Data, rows: Int, columns: Int) -> Data {
        let count = rows * columns
        var packed = Data(repeating: 0, count: (count + 7) / 8)
        for i in 0..<min(count, plane.count) where plane[i] != 0 {
            packed[i / 8] |= 1 << (7 - (i % 8))
        }
        return packed
    }

    private static func segmentItem(_ segment: DicomSEGSegment) -> [DicomBinary.Element] {
        let r = UInt16(max(0, min(65535, segment.color.r * 65535)))
        let g = UInt16(max(0, min(65535, segment.color.g * 65535)))
        let b = UInt16(max(0, min(65535, segment.color.b * 65535)))
        return [
            DicomBinary.us(0x0062, 0x0004, segment.number),
            DicomBinary.lo(0x0062, 0x0005, segment.label),
            DicomBinary.cs(0x0062, 0x0008, segment.algorithm.isEmpty ? "MANUAL" : segment.algorithm),
            DicomBinary.lo(0x0062, 0x0009, segment.provenance),
            DicomBinary.usArray(0x0062, 0x000D, [r, g, b]),
            DicomBinary.ui(0x0062, 0x0021, segment.trackingUID)
        ]
    }

    private static func sharedItem(_ geometry: DicomSEGGeometry) -> [DicomBinary.Element] {
        let spacing = String(format: "%.6g\\%.6g", geometry.spacingRow, geometry.spacingCol)
        let orientation = geometry.orientation.prefix(6).map { String(format: "%.8g", $0) }.joined(separator: "\\")
        return [
            DicomBinary.sq(0x0028, 0x9110, [[
                DicomBinary.ds(0x0028, 0x0030, spacing),
                DicomBinary.ds(0x0018, 0x0050, String(format: "%.6g", geometry.sliceThickness))
            ]]),
            DicomBinary.sq(0x0020, 0x9116, [[
                DicomBinary.ds(0x0020, 0x0037, orientation)
            ]])
        ]
    }

    private static func perFrameItem(origin: [Double], segment: UInt16, referencedSOP: String) -> [DicomBinary.Element] {
        let position = origin.prefix(3).map { String(format: "%.8g", $0) }.joined(separator: "\\")
        var items: [DicomBinary.Element] = [
            DicomBinary.sq(0x0020, 0x9113, [[DicomBinary.ds(0x0020, 0x0032, position)]]),
            DicomBinary.sq(0x0062, 0x000A, [[DicomBinary.us(0x0062, 0x000B, segment)]])
        ]
        if !referencedSOP.isEmpty {
            items.append(DicomBinary.sq(0x0008, 0x9124, [[
                DicomBinary.sq(0x0008, 0x2112, [[
                    DicomBinary.ui(0x0008, 0x1150, "1.2.840.10008.5.1.4.1.1.2"),
                    DicomBinary.ui(0x0008, 0x1155, referencedSOP)
                ]])
            ]]))
        }
        return items
    }

    private static func referencedSeries(_ identity: DicomSEGIdentity) -> [DicomBinary.Element] {
        let instances = identity.sourceSOPInstanceUIDs.map { uid -> [DicomBinary.Element] in
            [DicomBinary.ui(0x0008, 0x1150, "1.2.840.10008.5.1.4.1.1.2"),
             DicomBinary.ui(0x0008, 0x1155, uid)]
        }
        return [
            DicomBinary.ui(0x0020, 0x000E, identity.seriesInstanceUID),
            DicomBinary.sq(0x0008, 0x1140, instances)
        ]
    }
}

enum DicomBinary {
    struct Element {
        var group: UInt16
        var element: UInt16
        var vr: String
        var value: Data
        var items: [[Element]]
    }

    static func file(classUID: String, instanceUID: String, dataset: [Element]) -> Data {
        let metaBody = encode([
            ob(0x0002, 0x0001, Data([0x00, 0x01])),
            ui(0x0002, 0x0002, classUID),
            ui(0x0002, 0x0003, instanceUID),
            ui(0x0002, 0x0010, DicomSEGCodec.explicitLittleEndian),
            ui(0x0002, 0x0012, "2.25.376")
        ])
        var length = Data()
        length.append(contentsOf: u16(0x0002))
        length.append(contentsOf: u16(0x0000))
        length.append(contentsOf: Array("UL".utf8))
        length.append(contentsOf: u16(UInt16(metaBody.count)))
        length.append(metaBody)
        var file = Data(repeating: 0, count: 128)
        file.append(contentsOf: Array("DICM".utf8))
        file.append(length)
        file.append(encode(dataset))
        return file
    }

    static func parse(_ data: Data) -> [Element] {
        var offset = 132
        var elements: [Element] = []
        while offset + 8 <= data.count {
            guard let parsed = readElement(data, offset: &offset) else { break }
            elements.append(parsed)
        }
        return elements
    }

    static func string(_ elements: [Element], _ group: UInt16, _ element: UInt16) -> String {
        guard let bytes = elements.first(where: { $0.group == group && $0.element == element })?.value else { return "" }
        return String(data: bytes, encoding: .ascii)?.trimmingCharacters(in: CharacterSet(charactersIn: " \0")) ?? ""
    }

    static func data(_ elements: [Element], _ group: UInt16, _ element: UInt16) -> Data {
        elements.first(where: { $0.group == group && $0.element == element })?.value ?? Data()
    }

    static func us(_ elements: [Element], _ group: UInt16, _ element: UInt16) -> UInt16? {
        let bytes = data(elements, group, element)
        guard bytes.count >= 2 else { return nil }
        return UInt16(bytes[0]) | UInt16(bytes[1]) << 8
    }

    static func usArray(_ elements: [Element], _ group: UInt16, _ element: UInt16) -> [UInt16] {
        let bytes = data(elements, group, element)
        var values: [UInt16] = []
        var i = 0
        while i + 1 < bytes.count {
            values.append(UInt16(bytes[i]) | UInt16(bytes[i + 1]) << 8)
            i += 2
        }
        return values
    }

    static func sequence(_ elements: [Element], _ group: UInt16, _ element: UInt16) -> [[Element]] {
        elements.first(where: { $0.group == group && $0.element == element })?.items ?? []
    }

    static func doubles(_ text: String) -> [Double] {
        text.split(separator: "\\").compactMap { Double($0) }
    }

    static func ui(_ g: UInt16, _ e: UInt16, _ value: String) -> Element { make(g, e, "UI", padUID(value)) }
    static func cs(_ g: UInt16, _ e: UInt16, _ value: String) -> Element { make(g, e, "CS", pad(value)) }
    static func lo(_ g: UInt16, _ e: UInt16, _ value: String) -> Element { make(g, e, "LO", pad(value)) }
    static func ds(_ g: UInt16, _ e: UInt16, _ value: String) -> Element { make(g, e, "DS", pad(value)) }
    static func `is`(_ g: UInt16, _ e: UInt16, _ value: String) -> Element { make(g, e, "IS", pad(value)) }
    static func ob(_ g: UInt16, _ e: UInt16, _ value: Data) -> Element { Element(group: g, element: e, vr: "OB", value: value, items: []) }
    static func us(_ g: UInt16, _ e: UInt16, _ value: UInt16) -> Element {
        var bytes = Data(count: 2)
        bytes[0] = UInt8(value & 0xff)
        bytes[1] = UInt8(value >> 8)
        return Element(group: g, element: e, vr: "US", value: bytes, items: [])
    }
    static func usArray(_ g: UInt16, _ e: UInt16, _ values: [UInt16]) -> Element {
        var bytes = Data()
        for value in values {
            bytes.append(UInt8(value & 0xff))
            bytes.append(UInt8(value >> 8))
        }
        return Element(group: g, element: e, vr: "US", value: bytes, items: [])
    }
    static func sq(_ g: UInt16, _ e: UInt16, _ items: [[Element]]) -> Element {
        Element(group: g, element: e, vr: "SQ", value: Data(), items: items)
    }

    private static func make(_ g: UInt16, _ e: UInt16, _ vr: String, _ value: Data) -> Element {
        Element(group: g, element: e, vr: vr, value: value, items: [])
    }

    private static func pad(_ text: String) -> Data {
        var data = Data(text.utf8)
        if data.count % 2 == 1 { data.append(0x20) }
        return data
    }

    private static func padUID(_ text: String) -> Data {
        var data = Data(text.utf8)
        if data.count % 2 == 1 { data.append(0x00) }
        return data
    }

    private static func encode(_ elements: [Element]) -> Data {
        var data = Data()
        for element in elements { data.append(encode(element)) }
        return data
    }

    private static func encode(_ element: Element) -> Data {
        var data = Data()
        data.append(contentsOf: u16(element.group))
        data.append(contentsOf: u16(element.element))
        data.append(contentsOf: Array(element.vr.utf8))
        let long = ["OB", "OW", "SQ", "UN", "UT", "UC", "UR"].contains(element.vr)
        let payload: Data
        if element.vr == "SQ" {
            payload = encodeSequence(element.items)
        } else {
            payload = element.value
        }
        if long {
            data.append(contentsOf: u16(0))
            data.append(contentsOf: u32(UInt32(payload.count)))
        } else {
            data.append(contentsOf: u16(UInt16(payload.count)))
        }
        data.append(payload)
        return data
    }

    private static func encodeSequence(_ items: [[Element]]) -> Data {
        var data = Data()
        for item in items {
            let content = encode(item)
            data.append(contentsOf: u16(0xFFFE))
            data.append(contentsOf: u16(0xE000))
            data.append(contentsOf: u32(UInt32(content.count)))
            data.append(content)
        }
        return data
    }

    private static func boundedEnd(_ offset: Int, _ length: Int, _ count: Int) -> Int? {
        guard offset >= 0, length >= 0, offset <= count else { return nil }
        let end = offset + length
        guard end >= offset else { return nil }
        return min(count, end)
    }

    private static func readElement(_ data: Data, offset: inout Int) -> Element? {
        guard offset + 8 <= data.count else { return nil }
        let group = u16(data, offset); offset += 2
        let element = u16(data, offset); offset += 2
        if group == 0xFFFE {
            let length = Int(u32(data, offset)); offset += 4
            if element == 0xE00D || element == 0xE0DD { return nil }
            guard let end = boundedEnd(offset, length, data.count) else { return nil }
            var nested: [Element] = []
            while offset + 8 <= end {
                if let nestedElement = readElement(data, offset: &offset) {
                    nested.append(nestedElement)
                } else {
                    break
                }
            }
            offset = end
            return Element(group: group, element: element, vr: "UN", value: Data(), items: [nested])
        }
        guard offset + 2 <= data.count else { return nil }
        let vr = String(data: data.subdata(in: offset..<offset + 2), encoding: .ascii) ?? "UN"
        offset += 2
        let long = ["OB", "OW", "SQ", "UN", "UT", "UC", "UR"].contains(vr)
        let length: Int
        if long {
            guard offset + 6 <= data.count else { return nil }
            offset += 2
            length = Int(u32(data, offset)); offset += 4
        } else {
            guard offset + 2 <= data.count else { return nil }
            length = Int(u16(data, offset)); offset += 2
        }
        guard length >= 0 else { return nil }
        if vr == "SQ" {
            var items: [[Element]] = []
            guard let end = boundedEnd(offset, length, data.count) else { return nil }
            while offset + 8 <= end {
                let itemGroup = u16(data, offset); offset += 2
                let itemElement = u16(data, offset); offset += 2
                let itemLength = Int(u32(data, offset)); offset += 4
                if itemGroup == 0xFFFE && itemElement == 0xE0DD { break }
                guard let itemEnd = boundedEnd(offset, itemLength, data.count) else { break }
                var nested: [Element] = []
                while offset + 8 <= itemEnd {
                    if let nestedElement = readElement(data, offset: &offset) {
                        nested.append(nestedElement)
                    } else {
                        break
                    }
                }
                offset = itemEnd
                items.append(nested)
            }
            offset = end
            return Element(group: group, element: element, vr: vr, value: Data(), items: items)
        }
        guard let end = boundedEnd(offset, length, data.count) else { return nil }
        let value = data.subdata(in: offset..<end)
        offset = end
        return Element(group: group, element: element, vr: vr, value: value, items: [])
    }

    private static func u16(_ value: UInt16) -> [UInt8] { [UInt8(value & 0xff), UInt8(value >> 8)] }
    private static func u32(_ value: UInt32) -> [UInt8] {
        [UInt8(value & 0xff), UInt8((value >> 8) & 0xff), UInt8((value >> 16) & 0xff), UInt8((value >> 24) & 0xff)]
    }
    private static func u16(_ data: Data, _ offset: Int) -> UInt16 {
        guard offset + 1 < data.count else { return 0 }
        return UInt16(data[offset]) | UInt16(data[offset + 1]) << 8
    }
    private static func u32(_ data: Data, _ offset: Int) -> UInt32 {
        guard offset + 3 < data.count else { return 0 }
        return UInt32(data[offset]) | UInt32(data[offset + 1]) << 8 | UInt32(data[offset + 2]) << 16 | UInt32(data[offset + 3]) << 24
    }
}
