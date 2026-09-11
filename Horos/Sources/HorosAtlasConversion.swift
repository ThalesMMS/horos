import Foundation

/// NIfTI atlas → DICOM geometry and label SEG (#377 C).
/// Reuses the shared DicomSEG model; does not reimplement the codec.
/// The conversion never claims registration to a patient study (#378).

public enum HorosAtlasConversionError: String, Error, Equatable {
    case incompleteHeader = "incomplete-header"
    case notNifti1 = "not-nifti1"
    case notThreeDimensional = "not-three-dimensional"
    case unsupportedDatatype = "unsupported-datatype"
    case incompleteVoxels = "incomplete-voxels"
    case missingSform = "missing-sform"
    case zeroLengthDirection = "zero-length-direction"
    case labelShapeMismatch = "label-shape-mismatch"
    case affineMismatch = "affine-mismatch"
}

public struct HorosAtlasNiftiVolume {
    public var shape: [Int]
    public var affineRAS: [[Double]]
    public var raw: [Double]

    public var nx: Int { shape[0] }
    public var ny: Int { shape[1] }
    public var nz: Int { shape[2] }

    public static func parse(_ data: Data) throws -> HorosAtlasNiftiVolume {
        guard data.count >= 348 else { throw HorosAtlasConversionError.incompleteHeader }
        let little = int32(data, 0, little: true) == 348
        let big = int32(data, 0, little: false) == 348
        guard little || big else { throw HorosAtlasConversionError.notNifti1 }
        let le = little
        let dims = (0..<8).map { int16(data, 40 + 2 * $0, little: le) }
        guard dims[0] >= 3 else { throw HorosAtlasConversionError.notThreeDimensional }
        let shape = [Int(dims[1]), Int(dims[2]), Int(dims[3])]
        let datatype = int16(data, 70, little: le)
        let bitpix = int16(data, 72, little: le)
        guard let sample = sampleSize(datatype: datatype, bitpix: bitpix) else {
            throw HorosAtlasConversionError.unsupportedDatatype
        }
        let voxOffset = Int(float32(data, 108, little: le).rounded())
        let sform = int16(data, 254, little: le)
        guard sform > 0 else { throw HorosAtlasConversionError.missingSform }
        var affine: [[Double]] = []
        for row in 0..<3 {
            let base = 280 + row * 16
            affine.append((0..<4).map { Double(float32(data, base + 4 * $0, little: le)) })
        }
        affine.append([0, 0, 0, 1])
        let count = shape[0] * shape[1] * shape[2]
        let start = max(voxOffset, 348)
        let bytes = count * sample.stride
        guard start >= 0, data.count >= start + bytes else { throw HorosAtlasConversionError.incompleteVoxels }
        var raw: [Double] = []
        raw.reserveCapacity(count)
        let payload = Data(data[start..<(start + bytes)])
        for index in 0..<count {
            let offset = index * sample.stride
            raw.append(sample.read(payload, offset, le))
        }
        return HorosAtlasNiftiVolume(shape: shape, affineRAS: affine, raw: raw)
    }

    public func linearIndex(_ x: Int, _ y: Int, _ z: Int) -> Int {
        x + nx * (y + ny * z)
    }

    public func value(_ indices: [Int]) -> Double {
        raw[linearIndex(indices[0], indices[1], indices[2])]
    }

    public func axisVectorRAS(_ axis: Int) -> [Double] {
        [affineRAS[0][axis], affineRAS[1][axis], affineRAS[2][axis]]
    }

    public func positionRAS(_ indices: [Int]) -> [Double] {
        (0..<3).map { row in
            affineRAS[row][0] * Double(indices[0])
                + affineRAS[row][1] * Double(indices[1])
                + affineRAS[row][2] * Double(indices[2])
                + affineRAS[row][3]
        }
    }
}

public struct HorosAtlasGeometry: Equatable {
    public var rows: Int
    public var columns: Int
    public var frames: Int
    public var spacingRow: Double
    public var spacingCol: Double
    public var sliceThickness: Double
    public var originLPS: [Double]
    public var orientation: [Double]
    public var frameOriginsLPS: [[Double]]
    public var sliceAxis: Int
}

public struct HorosAtlasLabel: Equatable {
    public var value: Int
    public var name: String
    public var occupiedVoxels: Int
}

public struct HorosAtlasDICOMReferences: Equatable {
    public var studyInstanceUID: String
    public var seriesInstanceUID: String
    public var frameOfReferenceUID: String
    public var sourceSOPInstanceUIDs: [String]
}

public struct HorosAtlasConversion {
    public static let notRegisteredProvenance = "atlas-nifti; not-registered-to-patient"

    public var geometry: HorosAtlasGeometry
    public var labels: [HorosAtlasLabel]
    public var dicom: HorosAtlasDICOMReferences
    public var registeredToPatient: Bool
    public var provenance: String

    var segmentFrames: [(value: Int, name: String, frames: [Data])]

    public static func convert(
        image: HorosAtlasNiftiVolume,
        labels: HorosAtlasNiftiVolume,
        labelNames: [Int: String],
        sliceAxis: Int = 2,
        patientStudyUID: String? = nil,
        patientFrameOfReferenceUID: String? = nil
    ) throws -> HorosAtlasConversion {
        guard image.shape == labels.shape else {
            throw HorosAtlasConversionError.labelShapeMismatch
        }
        for row in 0..<3 {
            for column in 0..<4 {
                if abs(image.affineRAS[row][column] - labels.affineRAS[row][column]) > 1e-4 {
                    throw HorosAtlasConversionError.affineMismatch
                }
            }
        }
        let mapped = try mapGeometry(image, sliceAxis: sliceAxis)
        var occupancies: [Int: Int] = [:]
        for raw in labels.raw {
            let value = Int(raw.rounded())
            if value != 0 {
                occupancies[value, default: 0] += 1
            }
        }
        let orderedValues = occupancies.keys.sorted()
        var named: [HorosAtlasLabel] = []
        var frames: [(Int, String, [Data])] = []
        for value in orderedValues {
            let name = labelNames[value] ?? "label-\(value)"
            var planes: [Data] = []
            for slice in mapped.sliceIndices {
                var plane = Data(repeating: 0, count: mapped.rows * mapped.columns)
                for row in 0..<mapped.rows {
                    for column in 0..<mapped.columns {
                        let indices = voxelIndices(
                            column: column, row: row, slice: slice,
                            columnAxis: mapped.columnAxis, rowAxis: mapped.rowAxis,
                            sliceAxis: sliceAxis, rows: mapped.rows,
                            reverseRows: mapped.reverseRows
                        )
                        if Int(labels.value(indices).rounded()) == value {
                            plane[row * mapped.columns + column] = 1
                        }
                    }
                }
                planes.append(plane)
            }
            let occupied = planes.reduce(0) { $0 + $1.reduce(0) { $0 + ($1 > 0 ? 1 : 0) } }
            if occupied == 0 { continue }
            named.append(HorosAtlasLabel(value: value, name: name, occupiedVoxels: occupied))
            frames.append((value, name, planes))
        }

        var study = DicomSEGCodec.makeUID()
        var frameOfReference = DicomSEGCodec.makeUID()
        if study == patientStudyUID { study = DicomSEGCodec.makeUID() }
        if frameOfReference == patientFrameOfReferenceUID { frameOfReference = DicomSEGCodec.makeUID() }
        let sources = mapped.frameOriginsLPS.map { _ in DicomSEGCodec.makeUID() }
        return HorosAtlasConversion(
            geometry: HorosAtlasGeometry(
                rows: mapped.rows, columns: mapped.columns, frames: mapped.frameOriginsLPS.count,
                spacingRow: mapped.spacingRow, spacingCol: mapped.spacingCol,
                sliceThickness: mapped.sliceSpacing,
                originLPS: mapped.frameOriginsLPS.first ?? [0, 0, 0],
                orientation: mapped.columnDirection + mapped.rowDirection,
                frameOriginsLPS: mapped.frameOriginsLPS,
                sliceAxis: sliceAxis
            ),
            labels: named,
            dicom: HorosAtlasDICOMReferences(
                studyInstanceUID: study,
                seriesInstanceUID: DicomSEGCodec.makeUID(),
                frameOfReferenceUID: frameOfReference,
                sourceSOPInstanceUIDs: sources
            ),
            registeredToPatient: false,
            provenance: notRegisteredProvenance,
            segmentFrames: frames
        )
    }

    public func segmentationDocument() throws -> DicomSEGDocument {
        let geometry = DicomSEGGeometry(
            rows: geometry.rows, columns: geometry.columns, frames: geometry.frames,
            spacingRow: geometry.spacingRow, spacingCol: geometry.spacingCol,
            sliceThickness: geometry.sliceThickness,
            origin: geometry.originLPS,
            orientation: geometry.orientation,
            frameOfReferenceUID: dicom.frameOfReferenceUID,
            frameOrigins: geometry.frameOriginsLPS
        )
        let colors: [(Double, Double, Double)] = [
            (1.0, 0.78, 0.0), (0.2, 0.85, 0.3), (0.2, 0.65, 1.0),
            (0.8, 0.35, 1.0), (1.0, 0.35, 0.35)
        ]
        var segments: [DicomSEGSegment] = []
        for (index, item) in segmentFrames.enumerated() {
            let color = colors[index % colors.count]
            segments.append(DicomSEGSegment(
                number: UInt16(index + 1),
                label: item.name,
                trackingUID: DicomSEGCodec.makeUID(),
                color: color,
                visible: true,
                kind: .binary,
                algorithm: "ATLAS",
                provenance: provenance,
                referencedSOPInstanceUIDs: dicom.sourceSOPInstanceUIDs,
                frames: item.frames,
                maximumFractionalValue: 255
            ))
        }
        return DicomSEGDocument(
            identity: DicomSEGIdentity(
                sopInstanceUID: DicomSEGCodec.makeUID(),
                seriesInstanceUID: DicomSEGCodec.makeUID(),
                studyInstanceUID: dicom.studyInstanceUID,
                frameOfReferenceUID: dicom.frameOfReferenceUID,
                sourceSOPInstanceUIDs: dicom.sourceSOPInstanceUIDs
            ),
            geometry: geometry,
            kind: .binary,
            segments: segments,
            diagnoses: [],
            sourceBytes: nil
        )
    }
}

private struct MappedAtlasGeometry {
    var rows: Int
    var columns: Int
    var columnAxis: Int
    var rowAxis: Int
    var reverseRows: Bool
    var spacingRow: Double
    var spacingCol: Double
    var sliceSpacing: Double
    var columnDirection: [Double]
    var rowDirection: [Double]
    var sliceIndices: [Int]
    var frameOriginsLPS: [[Double]]
}

private func mapGeometry(_ volume: HorosAtlasNiftiVolume, sliceAxis: Int) throws -> MappedAtlasGeometry {
    guard sliceAxis >= 0 && sliceAxis <= 2 else { throw HorosAtlasConversionError.notThreeDimensional }
    let remaining = [0, 1, 2].filter { $0 != sliceAxis }
    let columnAxis = remaining[0]
    let rowAxis = remaining[1]
    let columns = volume.shape[columnAxis]
    let rows = volume.shape[rowAxis]
    let columnVector = rasToLPS(volume.axisVectorRAS(columnAxis))
    var rowVector = rasToLPS(volume.axisVectorRAS(rowAxis))
    let sliceVector = rasToLPS(volume.axisVectorRAS(sliceAxis))
    let columnDirection = try normalize(columnVector)
    var rowDirection = try normalize(rowVector)
    let reverseRows = rowDirection[2] > 0
        && abs(rowDirection[2]) >= max(abs(rowDirection[0]), abs(rowDirection[1]))
    if reverseRows {
        rowVector = rowVector.map { -$0 }
        rowDirection = try normalize(rowVector)
    }
    let normal = try normalize(cross(columnDirection, rowDirection))
    var sliceIndices = Array(0..<volume.shape[sliceAxis])
    if dot(try normalize(sliceVector), normal) < 0 {
        sliceIndices.reverse()
    }
    let origins = sliceIndices.map { slice -> [Double] in
        let indices = voxelIndices(
            column: 0, row: 0, slice: slice,
            columnAxis: columnAxis, rowAxis: rowAxis,
            sliceAxis: sliceAxis, rows: rows, reverseRows: reverseRows
        )
        return rasToLPS(volume.positionRAS(indices))
    }
    return MappedAtlasGeometry(
        rows: rows, columns: columns, columnAxis: columnAxis, rowAxis: rowAxis,
        reverseRows: reverseRows,
        spacingRow: length(rowVector), spacingCol: length(columnVector),
        sliceSpacing: length(sliceVector),
        columnDirection: columnDirection, rowDirection: rowDirection,
        sliceIndices: sliceIndices, frameOriginsLPS: origins
    )
}

private func voxelIndices(
    column: Int, row: Int, slice: Int,
    columnAxis: Int, rowAxis: Int, sliceAxis: Int,
    rows: Int, reverseRows: Bool
) -> [Int] {
    var indices = [0, 0, 0]
    indices[columnAxis] = column
    indices[rowAxis] = reverseRows ? (rows - 1 - row) : row
    indices[sliceAxis] = slice
    return indices
}

private func rasToLPS(_ vector: [Double]) -> [Double] {
    [-vector[0], -vector[1], vector[2]]
}

private func length(_ vector: [Double]) -> Double {
    sqrt(vector.reduce(0) { $0 + $1 * $1 })
}

private func normalize(_ vector: [Double]) throws -> [Double] {
    let mag = length(vector)
    if mag <= 0 { throw HorosAtlasConversionError.zeroLengthDirection }
    return vector.map { $0 / mag }
}

private func cross(_ lhs: [Double], _ rhs: [Double]) -> [Double] {
    [
        lhs[1] * rhs[2] - lhs[2] * rhs[1],
        lhs[2] * rhs[0] - lhs[0] * rhs[2],
        lhs[0] * rhs[1] - lhs[1] * rhs[0]
    ]
}

private func dot(_ lhs: [Double], _ rhs: [Double]) -> Double {
    zip(lhs, rhs).reduce(0) { $0 + $1.0 * $1.1 }
}

private struct NiftiSample {
    var stride: Int
    var read: (Data, Data.Index, Bool) -> Double
}

private func sampleSize(datatype: Int16, bitpix: Int16) -> NiftiSample? {
    switch datatype {
    case 2: return NiftiSample(stride: 1) { data, offset, _ in Double(byte(data, offset)) }
    case 4: return NiftiSample(stride: 2) { data, offset, le in Double(int16(data, offset, little: le)) }
    case 8: return NiftiSample(stride: 4) { data, offset, le in Double(int32(data, offset, little: le)) }
    case 16: return NiftiSample(stride: 4) { data, offset, le in Double(float32(data, offset, little: le)) }
    case 256: return NiftiSample(stride: 1) { data, offset, _ in Double(Int8(bitPattern: byte(data, offset))) }
    case 512: return NiftiSample(stride: 2) { data, offset, le in Double(UInt16(bitPattern: int16(data, offset, little: le))) }
    default:
        _ = bitpix
        return nil
    }
}

private func byte(_ data: Data, _ offset: Int) -> UInt8 {
    data[data.index(data.startIndex, offsetBy: offset)]
}

private func int16(_ data: Data, _ offset: Int, little: Bool) -> Int16 {
    let start = data.index(data.startIndex, offsetBy: offset)
    let b0 = data[start]
    let b1 = data[data.index(after: start)]
    let value = little ? UInt16(b0) | UInt16(b1) << 8 : UInt16(b1) | UInt16(b0) << 8
    return Int16(bitPattern: value)
}

private func int32(_ data: Data, _ offset: Int, little: Bool) -> Int32 {
    let start = data.index(data.startIndex, offsetBy: offset)
    let b0 = data[start]
    let b1 = data[data.index(start, offsetBy: 1)]
    let b2 = data[data.index(start, offsetBy: 2)]
    let b3 = data[data.index(start, offsetBy: 3)]
    let value: UInt32
    if little {
        value = UInt32(b0) | UInt32(b1) << 8 | UInt32(b2) << 16 | UInt32(b3) << 24
    } else {
        value = UInt32(b3) | UInt32(b2) << 8 | UInt32(b1) << 16 | UInt32(b0) << 24
    }
    return Int32(bitPattern: value)
}

private func float32(_ data: Data, _ offset: Int, little: Bool) -> Float {
    Float(bitPattern: UInt32(bitPattern: int32(data, offset, little: little)))
}
