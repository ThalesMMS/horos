import Foundation

/// Errors raised before any DICOM is written. Affine and sform are required:
/// an atlas without explicit geometry is refused rather than guessed.
public enum AtlasConversionError: Error, Equatable {
    case incompleteHeader
    case notNifti1
    case notThreeDimensional
    case missingSform
    case unsupportedDatatype
    case incompleteVoxelData
    case shapeMismatch
    case affineMismatch
    case zeroLengthAxis
    case missingInstance
}

@objc(HorosNiftiAtlasGeometry)
public final class AtlasDicomGeometry: NSObject {
    @objc public let rows: Int
    @objc public let columns: Int
    @objc public let rowSpacingMm: Double
    @objc public let columnSpacingMm: Double
    @objc public let sliceSpacingMm: Double
    @objc public let sliceCount: Int
    @objc public let reverseRows: Bool
    @objc public let imageOrientationPatient: [Double]
    let sliceIndices: [Int]
    let sliceAxis: Int
    let columnAxis: Int
    let rowAxis: Int
    let normal: (Double, Double, Double)

    init(rows: Int, columns: Int, rowSpacingMm: Double, columnSpacingMm: Double,
         sliceSpacingMm: Double, sliceCount: Int, reverseRows: Bool,
         imageOrientationPatient: [Double], sliceIndices: [Int],
         sliceAxis: Int, columnAxis: Int, rowAxis: Int,
         normal: (Double, Double, Double)) {
        self.rows = rows
        self.columns = columns
        self.rowSpacingMm = rowSpacingMm
        self.columnSpacingMm = columnSpacingMm
        self.sliceSpacingMm = sliceSpacingMm
        self.sliceCount = sliceCount
        self.reverseRows = reverseRows
        self.imageOrientationPatient = imageOrientationPatient
        self.sliceIndices = sliceIndices
        self.sliceAxis = sliceAxis
        self.columnAxis = columnAxis
        self.rowAxis = rowAxis
        self.normal = normal
    }

    func voxelIndices(column: Int, row: Int, sliceIndex: Int) -> (Int, Int, Int) {
        var indices = [0, 0, 0]
        indices[columnAxis] = column
        indices[rowAxis] = reverseRows ? rows - 1 - row : row
        indices[sliceAxis] = sliceIndex
        return (indices[0], indices[1], indices[2])
    }
}

@objc(HorosNiftiAtlasMRInstance)
public final class AtlasMRInstance: NSObject {
    @objc public let instanceNumber: Int
    @objc public let sopInstanceUID: String
    @objc public let imagePositionPatient: [Double]
    @objc public let pixelData: Data

    init(instanceNumber: Int, sopInstanceUID: String,
         imagePositionPatient: [Double], pixelData: Data) {
        self.instanceNumber = instanceNumber
        self.sopInstanceUID = sopInstanceUID
        self.imagePositionPatient = imagePositionPatient
        self.pixelData = pixelData
    }
}

@objc(HorosNiftiAtlasSegment)
public final class AtlasSegment: NSObject {
    @objc public let segmentNumber: Int
    @objc public let labelValue: Int
    @objc public let label: String
    @objc public let sopInstanceUID: String
    @objc public let frames: [Data]

    init(segmentNumber: Int, labelValue: Int, label: String,
         sopInstanceUID: String, frames: [Data]) {
        self.segmentNumber = segmentNumber
        self.labelValue = labelValue
        self.label = label
        self.sopInstanceUID = sopInstanceUID
        self.frames = frames
    }
}

/// NIfTI atlas → DICOM MR + SEG. Distinct from general NIfTI import (#151):
/// this path never presents the result as registered to a patient study.
@objc(HorosNiftiAtlasConversion)
public final class NiftiAtlasConversion: NSObject {
    @objc public static let mrSOPClassUID = "1.2.840.10008.5.1.4.1.1.4"
    @objc public static let segmentationSOPClassUID = "1.2.840.10008.5.1.4.1.1.66.4"
    static let explicitLittleEndianUID = "1.2.840.10008.1.2.1"
    static let implementationClassUID = "1.2.826.0.1.3680043.10.543.1"

    @objc public let registeredToPatient: Bool
    @objc public let frameOfReferenceUID: String
    @objc public let studyInstanceUID: String
    @objc public let seriesInstanceUID: String
    @objc public let referencedStudyUID: String?
    @objc public let derivationDescription: String
    @objc public let geometry: AtlasDicomGeometry
    @objc public let mrInstances: [AtlasMRInstance]
    @objc public let segments: [AtlasSegment]

    init(registeredToPatient: Bool, frameOfReferenceUID: String,
         studyInstanceUID: String, seriesInstanceUID: String,
         referencedStudyUID: String?, derivationDescription: String,
         geometry: AtlasDicomGeometry, mrInstances: [AtlasMRInstance],
         segments: [AtlasSegment]) {
        self.registeredToPatient = registeredToPatient
        self.frameOfReferenceUID = frameOfReferenceUID
        self.studyInstanceUID = studyInstanceUID
        self.seriesInstanceUID = seriesInstanceUID
        self.referencedStudyUID = referencedStudyUID
        self.derivationDescription = derivationDescription
        self.geometry = geometry
        self.mrInstances = mrInstances
        self.segments = segments
    }

    public static func convert(imageURL: URL, segmentationURL: URL,
                               labels: [Int: String], atlasIdentity: String,
                               patientStudyUID: String? = nil) throws -> NiftiAtlasConversion {
        let image = try NiftiVolume(url: imageURL)
        let segmentation = try NiftiVolume(url: segmentationURL)
        guard image.nx == segmentation.nx, image.ny == segmentation.ny, image.nz == segmentation.nz else {
            throw AtlasConversionError.shapeMismatch
        }
        for row in 0..<3 {
            for column in 0..<4 {
                if abs(image.affine[row][column] - segmentation.affine[row][column]) > 1e-4 {
                    throw AtlasConversionError.affineMismatch
                }
            }
        }

        let geometry = try AtlasDicomGeometry.from(volume: image, sliceAxis: 2)
        let identity = atlasIdentity.isEmpty ? "atlas" : atlasIdentity
        let studyUID = deterministicUID("\(identity):study")
        let seriesUID = deterministicUID("\(identity):mr-series")
        let frameUID = deterministicUID("\(identity):frame-of-reference")
        let description = "NIfTI atlas conversion; not registered to a patient"

        var instances: [AtlasMRInstance] = []
        for (number, sliceIndex) in geometry.sliceIndices.enumerated() {
            let origin = geometry.voxelIndices(column: 0, row: 0, sliceIndex: sliceIndex)
            let ras = image.positionRAS(origin.0, origin.1, origin.2)
            let lps = rasToLPS(ras)
            var pixels = Data()
            pixels.reserveCapacity(geometry.rows * geometry.columns * 2)
            for row in 0..<geometry.rows {
                for column in 0..<geometry.columns {
                    let voxel = geometry.voxelIndices(column: column, row: row, sliceIndex: sliceIndex)
                    var sample = image.value(x: voxel.0, y: voxel.1, z: voxel.2).littleEndian
                    pixels.append(Data(bytes: &sample, count: 2))
                }
            }
            instances.append(AtlasMRInstance(
                instanceNumber: number + 1,
                sopInstanceUID: deterministicUID("\(seriesUID):\(number + 1)"),
                imagePositionPatient: [lps.0, lps.1, lps.2],
                pixelData: pixels))
        }

        let orderedLabels = labels.keys.filter { $0 != 0 }.sorted()
        var segments: [AtlasSegment] = []
        for (index, value) in orderedLabels.enumerated() {
            let name = labels[value] ?? "Segment \(value)"
            var frames: [Data] = []
            for sliceIndex in geometry.sliceIndices {
                var mask = Data(count: geometry.rows * geometry.columns)
                var offset = 0
                for row in 0..<geometry.rows {
                    for column in 0..<geometry.columns {
                        let voxel = geometry.voxelIndices(column: column, row: row, sliceIndex: sliceIndex)
                        if Int(segmentation.value(x: voxel.0, y: voxel.1, z: voxel.2)) == value {
                            mask[offset] = 1
                        }
                        offset += 1
                    }
                }
                frames.append(mask)
            }
            segments.append(AtlasSegment(
                segmentNumber: index + 1,
                labelValue: value,
                label: name,
                sopInstanceUID: deterministicUID("\(identity):seg:\(value)"),
                frames: frames))
        }

        return NiftiAtlasConversion(
            registeredToPatient: false,
            frameOfReferenceUID: frameUID,
            studyInstanceUID: studyUID,
            seriesInstanceUID: seriesUID,
            referencedStudyUID: patientStudyUID,
            derivationDescription: description,
            geometry: geometry,
            mrInstances: instances,
            segments: segments)
    }

    public func mrDICOM(instanceNumber: Int) -> Data {
        guard let instance = mrInstances.first(where: { $0.instanceNumber == instanceNumber }) else {
            return Data()
        }
        let iop = geometry.imageOrientationPatient.map(formatDecimal).joined(separator: "\\")
        let ipp = instance.imagePositionPatient.map(formatDecimal).joined(separator: "\\")
        let location = dot((instance.imagePositionPatient[0],
                            instance.imagePositionPatient[1],
                            instance.imagePositionPatient[2]), geometry.normal)
        let elements: [(UInt16, UInt16, String, Any)] = [
            (0x0008, 0x0008, "CS", "DERIVED\\SECONDARY\\OTHER"),
            (0x0008, 0x0016, "UI", NiftiAtlasConversion.mrSOPClassUID),
            (0x0008, 0x0018, "UI", instance.sopInstanceUID),
            (0x0008, 0x0060, "CS", "MR"),
            (0x0008, 0x1090, "LO", "NIfTI-derived atlas"),
            (0x0008, 0x2111, "ST", derivationDescription),
            (0x0018, 0x0050, "DS", formatDecimal(geometry.sliceSpacingMm)),
            (0x0018, 0x0088, "DS", formatDecimal(geometry.sliceSpacingMm)),
            (0x0020, 0x000D, "UI", studyInstanceUID),
            (0x0020, 0x000E, "UI", seriesInstanceUID),
            (0x0020, 0x0013, "IS", "\(instance.instanceNumber)"),
            (0x0020, 0x0032, "DS", ipp),
            (0x0020, 0x0037, "DS", iop),
            (0x0020, 0x0052, "UI", frameOfReferenceUID),
            (0x0020, 0x1041, "DS", formatDecimal(location)),
            (0x0028, 0x0002, "US", UInt16(1)),
            (0x0028, 0x0004, "CS", "MONOCHROME2"),
            (0x0028, 0x0010, "US", UInt16(geometry.rows)),
            (0x0028, 0x0011, "US", UInt16(geometry.columns)),
            (0x0028, 0x0030, "DS",
             "\(formatDecimal(geometry.rowSpacingMm))\\\(formatDecimal(geometry.columnSpacingMm))"),
            (0x0028, 0x0100, "US", UInt16(16)),
            (0x0028, 0x0101, "US", UInt16(16)),
            (0x0028, 0x0102, "US", UInt16(15)),
            (0x0028, 0x0103, "US", UInt16(1)),
            (0x7FE0, 0x0010, "OW", instance.pixelData),
        ]
        return dicomFile(sopClass: NiftiAtlasConversion.mrSOPClassUID,
                           sopInstance: instance.sopInstanceUID,
                           elements: elements)
    }

    public func segmentationDICOM(segmentNumber: Int) -> Data {
        guard let segment = segments.first(where: { $0.segmentNumber == segmentNumber }) else {
            return Data()
        }
        var pixels = Data()
        for frame in segment.frames { pixels.append(frame) }
        let iop = geometry.imageOrientationPatient.map(formatDecimal).joined(separator: "\\")
        let ipp = mrInstances.first.map {
            $0.imagePositionPatient.map(formatDecimal).joined(separator: "\\")
        } ?? "0\\0\\0"
        let elements: [(UInt16, UInt16, String, Any)] = [
            (0x0008, 0x0008, "CS", "DERIVED\\PRIMARY"),
            (0x0008, 0x0016, "UI", NiftiAtlasConversion.segmentationSOPClassUID),
            (0x0008, 0x0018, "UI", segment.sopInstanceUID),
            (0x0008, 0x0060, "CS", "SEG"),
            (0x0008, 0x103E, "LO", segment.label),
            (0x0008, 0x2111, "ST", derivationDescription),
            (0x0020, 0x000D, "UI", studyInstanceUID),
            (0x0020, 0x000E, "UI", deterministicUID("\(frameOfReferenceUID):seg-series:\(segmentNumber)")),
            (0x0020, 0x0013, "IS", "1"),
            (0x0020, 0x0032, "DS", ipp),
            (0x0020, 0x0037, "DS", iop),
            (0x0020, 0x0052, "UI", frameOfReferenceUID),
            (0x0028, 0x0002, "US", UInt16(1)),
            (0x0028, 0x0004, "CS", "MONOCHROME2"),
            (0x0028, 0x0008, "IS", "\(segment.frames.count)"),
            (0x0028, 0x0010, "US", UInt16(geometry.rows)),
            (0x0028, 0x0011, "US", UInt16(geometry.columns)),
            (0x0028, 0x0100, "US", UInt16(8)),
            (0x0028, 0x0101, "US", UInt16(8)),
            (0x0028, 0x0102, "US", UInt16(7)),
            (0x0028, 0x0103, "US", UInt16(0)),
            (0x7FE0, 0x0010, "OB", pixels),
        ]
        return dicomFile(sopClass: NiftiAtlasConversion.segmentationSOPClassUID,
                           sopInstance: segment.sopInstanceUID,
                           elements: elements)
    }
}

private struct NiftiVolume {
    let nx: Int
    let ny: Int
    let nz: Int
    let affine: [[Double]]
    let values: [Int16]

    init(url: URL) throws {
        let data = try Data(contentsOf: url)
        guard data.count >= 348 else { throw AtlasConversionError.incompleteHeader }
        let little = data.int32(at: 0, bigEndian: false) == 348
        let big = data.int32(at: 0, bigEndian: true) == 348
        guard little || big else { throw AtlasConversionError.notNifti1 }
        let swap = big && !little
        let dim0 = Int(data.int16(at: 40, bigEndian: swap))
        guard dim0 >= 3 else { throw AtlasConversionError.notThreeDimensional }
        nx = Int(data.int16(at: 42, bigEndian: swap))
        ny = Int(data.int16(at: 44, bigEndian: swap))
        nz = Int(data.int16(at: 46, bigEndian: swap))
        let datatype = data.int16(at: 70, bigEndian: swap)
        guard datatype == 4 else { throw AtlasConversionError.unsupportedDatatype }
        let sform = data.int16(at: 254, bigEndian: swap)
        guard sform > 0 else { throw AtlasConversionError.missingSform }
        affine = [
            data.float4(at: 280, bigEndian: swap),
            data.float4(at: 296, bigEndian: swap),
            data.float4(at: 312, bigEndian: swap),
        ]
        let offset = Int(data.float32(at: 108, bigEndian: swap).rounded())
        let count = nx * ny * nz
        guard offset >= 348, data.count >= offset + count * 2 else {
            throw AtlasConversionError.incompleteVoxelData
        }
        var samples: [Int16] = []
        samples.reserveCapacity(count)
        for index in 0..<count {
            samples.append(data.int16(at: offset + index * 2, bigEndian: swap))
        }
        values = samples
    }

    func value(x: Int, y: Int, z: Int) -> Int16 {
        values[x + nx * (y + ny * z)]
    }

    func axisVectorRAS(_ axis: Int) -> (Double, Double, Double) {
        (affine[0][axis], affine[1][axis], affine[2][axis])
    }

    func positionRAS(_ x: Int, _ y: Int, _ z: Int) -> (Double, Double, Double) {
        (
            affine[0][0] * Double(x) + affine[0][1] * Double(y) + affine[0][2] * Double(z) + affine[0][3],
            affine[1][0] * Double(x) + affine[1][1] * Double(y) + affine[1][2] * Double(z) + affine[1][3],
            affine[2][0] * Double(x) + affine[2][1] * Double(y) + affine[2][2] * Double(z) + affine[2][3]
        )
    }
}

private extension AtlasDicomGeometry {
    static func from(volume: NiftiVolume, sliceAxis: Int) throws -> AtlasDicomGeometry {
        let remaining = [0, 1, 2].filter { $0 != sliceAxis }
        let columnAxis = remaining[0]
        let rowAxis = remaining[1]
        var columnVector = rasToLPS(volume.axisVectorRAS(columnAxis))
        var rowVector = rasToLPS(volume.axisVectorRAS(rowAxis))
        let sliceVector = rasToLPS(volume.axisVectorRAS(sliceAxis))
        var columnDirection = try normalize(columnVector)
        var rowDirection = try normalize(rowVector)
        let reverseRows = rowDirection.2 > 0
            && abs(rowDirection.2) >= max(abs(rowDirection.0), abs(rowDirection.1))
        if reverseRows {
            rowVector = (-rowVector.0, -rowVector.1, -rowVector.2)
            rowDirection = (-rowDirection.0, -rowDirection.1, -rowDirection.2)
        }
        let normal = try normalize(cross(columnDirection, rowDirection))
        var sliceIndices = Array(0..<volume.shape(sliceAxis))
        if dot(try normalize(sliceVector), normal) < 0 {
            sliceIndices.reverse()
        }
        return AtlasDicomGeometry(
            rows: volume.shape(rowAxis),
            columns: volume.shape(columnAxis),
            rowSpacingMm: length(rowVector),
            columnSpacingMm: length(columnVector),
            sliceSpacingMm: length(sliceVector),
            sliceCount: sliceIndices.count,
            reverseRows: reverseRows,
            imageOrientationPatient: [
                columnDirection.0, columnDirection.1, columnDirection.2,
                rowDirection.0, rowDirection.1, rowDirection.2,
            ],
            sliceIndices: sliceIndices,
            sliceAxis: sliceAxis,
            columnAxis: columnAxis,
            rowAxis: rowAxis,
            normal: normal)
    }
}

private extension NiftiVolume {
    func shape(_ axis: Int) -> Int {
        switch axis {
        case 0: return nx
        case 1: return ny
        default: return nz
        }
    }
}

private func rasToLPS(_ vector: (Double, Double, Double)) -> (Double, Double, Double) {
    (-vector.0, -vector.1, vector.2)
}

private func length(_ vector: (Double, Double, Double)) -> Double {
    sqrt(vector.0 * vector.0 + vector.1 * vector.1 + vector.2 * vector.2)
}

private func normalize(_ vector: (Double, Double, Double)) throws -> (Double, Double, Double) {
    let magnitude = length(vector)
    if magnitude <= 0 { throw AtlasConversionError.zeroLengthAxis }
    return (vector.0 / magnitude, vector.1 / magnitude, vector.2 / magnitude)
}

private func cross(_ lhs: (Double, Double, Double),
                   _ rhs: (Double, Double, Double)) -> (Double, Double, Double) {
    (
        lhs.1 * rhs.2 - lhs.2 * rhs.1,
        lhs.2 * rhs.0 - lhs.0 * rhs.2,
        lhs.0 * rhs.1 - lhs.1 * rhs.0
    )
}

private func dot(_ lhs: (Double, Double, Double),
                 _ rhs: (Double, Double, Double)) -> Double {
    lhs.0 * rhs.0 + lhs.1 * rhs.1 + lhs.2 * rhs.2
}

private func formatDecimal(_ value: Double) -> String {
    var number = value
    if abs(number) < 5e-13 { number = 0 }
    var text = String(format: "%.10g", number)
    if text.count > 16 { text = String(text.prefix(16)) }
    return text
}

private func deterministicUID(_ name: String) -> String {
    var hash: UInt64 = 0xcbf29ce484222325
    for byte in name.utf8 {
        hash ^= UInt64(byte)
        hash &*= 0x100000001b3
    }
    return "2.25.\(hash)"
}

private func dicomFile(sopClass: String, sopInstance: String,
                       elements: [(UInt16, UInt16, String, Any)]) -> Data {
    let metaItems: [(UInt16, UInt16, String, Any)] = [
        (0x0002, 0x0001, "OB", Data([0x00, 0x01])),
        (0x0002, 0x0002, "UI", sopClass),
        (0x0002, 0x0003, "UI", sopInstance),
        (0x0002, 0x0010, "UI", NiftiAtlasConversion.explicitLittleEndianUID),
        (0x0002, 0x0012, "UI", NiftiAtlasConversion.implementationClassUID),
        (0x0002, 0x0013, "SH", "HOROSATLAS1"),
    ]
    let metaBody = Data(metaItems.map(dicomElement).joined())
    let meta = dicomElement(0x0002, 0x0000, "UL", UInt32(metaBody.count)) + metaBody
    let dataset = Data(elements.sorted { lhs, rhs in
        lhs.0 != rhs.0 ? lhs.0 < rhs.0 : lhs.1 < rhs.1
    }.map(dicomElement).joined())
    return Data(repeating: 0, count: 128) + Data("DICM".utf8) + meta + dataset
}

private func dicomElement(_ group: UInt16, _ element: UInt16, _ vr: String, _ value: Any) -> Data {
    dicomElement((group, element, vr, value))
}

private func dicomElement(_ item: (UInt16, UInt16, String, Any)) -> Data {
    let encoded = encodeValue(vr: item.2, value: item.3)
    var header = Data()
    header.append(contentsOf: withUnsafeBytes(of: item.0.littleEndian, Array.init))
    header.append(contentsOf: withUnsafeBytes(of: item.1.littleEndian, Array.init))
    header.append(contentsOf: item.2.utf8)
    let longVR = ["OB", "OW", "OF", "SQ", "UT", "UN", "UC", "UR", "OD", "OL", "OV"].contains(item.2)
    if longVR {
        header.append(contentsOf: [0, 0])
        header.append(contentsOf: withUnsafeBytes(of: UInt32(encoded.count).littleEndian, Array.init))
    } else {
        header.append(contentsOf: withUnsafeBytes(of: UInt16(encoded.count).littleEndian, Array.init))
    }
    return header + encoded
}

private func encodeValue(vr: String, value: Any) -> Data {
    var encoded: Data
    if let data = value as? Data {
        encoded = data
    } else if let number = value as? UInt16 {
        encoded = Data(withUnsafeBytes(of: number.littleEndian, Array.init))
    } else if let number = value as? UInt32 {
        encoded = Data(withUnsafeBytes(of: number.littleEndian, Array.init))
    } else {
        encoded = Data(String(describing: value).utf8)
    }
    if encoded.count % 2 == 1 {
        encoded.append(["UI", "OB", "OW", "UN"].contains(vr) ? 0 : 0x20)
    }
    return encoded
}

private extension Data {
    func int16(at offset: Int, bigEndian: Bool) -> Int16 {
        let raw: UInt16 = bigEndian
            ? UInt16(self[offset]) << 8 | UInt16(self[offset + 1])
            : UInt16(self[offset]) | UInt16(self[offset + 1]) << 8
        return Int16(bitPattern: raw)
    }

    func int32(at offset: Int, bigEndian: Bool) -> Int32 {
        let raw: UInt32 = bigEndian
            ? UInt32(self[offset]) << 24 | UInt32(self[offset + 1]) << 16
                | UInt32(self[offset + 2]) << 8 | UInt32(self[offset + 3])
            : UInt32(self[offset]) | UInt32(self[offset + 1]) << 8
                | UInt32(self[offset + 2]) << 16 | UInt32(self[offset + 3]) << 24
        return Int32(bitPattern: raw)
    }

    func float32(at offset: Int, bigEndian: Bool) -> Float {
        let raw: UInt32 = bigEndian
            ? UInt32(self[offset]) << 24 | UInt32(self[offset + 1]) << 16
                | UInt32(self[offset + 2]) << 8 | UInt32(self[offset + 3])
            : UInt32(self[offset]) | UInt32(self[offset + 1]) << 8
                | UInt32(self[offset + 2]) << 16 | UInt32(self[offset + 3]) << 24
        return Float(bitPattern: raw)
    }

    func float4(at offset: Int, bigEndian: Bool) -> [Double] {
        (0..<4).map { Double(float32(at: offset + $0 * 4, bigEndian: bigEndian)) }
    }
}
