import CryptoKit
import Foundation

public protocol HorosHVRVOL02IO {
    func write(_ data: Data) throws
    func readExactly(_ count: Int) throws -> Data
}

public enum HorosHVRVOL02Error: Error, Equatable {
    case unauthorized
    case incompatibleProtocol
    case missingDestination
    case incoherentVolume(String)
    case cancelled
    case incompleteAcknowledgement
    case transferFailed(String)
}

public struct HorosHVRVOL02ROI: Equatable {
    public var id: String
    public var name: String
    public var color: [Double]
    public var vertices: [Float]

    public init(id: String, name: String, color: [Double], vertices: [Float]) {
        self.id = id
        self.name = name
        self.color = color
        self.vertices = vertices
    }
}

public struct HorosHVRVOL02Volume: Equatable {
    public var id: String
    public var name: String
    public var seriesUID: String
    public var studyUID: String
    public var frameOfReferenceUID: String
    public var modality: String
    public var width: Int
    public var height: Int
    public var depth: Int
    public var spacing: [Double]
    public var imageToPatient: [Double]
    public var windowLevel: Double
    public var windowWidth: Double
    public var invertDisplay: Bool
    public var voxels: [Float]
    public var rois: [HorosHVRVOL02ROI]

    public init(
        id: String, name: String, seriesUID: String, studyUID: String,
        frameOfReferenceUID: String, modality: String, width: Int, height: Int, depth: Int,
        spacing: [Double], imageToPatient: [Double], windowLevel: Double, windowWidth: Double,
        invertDisplay: Bool, voxels: [Float], rois: [HorosHVRVOL02ROI]
    ) {
        self.id = id
        self.name = name
        self.seriesUID = seriesUID
        self.studyUID = studyUID
        self.frameOfReferenceUID = frameOfReferenceUID
        self.modality = modality
        self.width = width
        self.height = height
        self.depth = depth
        self.spacing = spacing
        self.imageToPatient = imageToPatient
        self.windowLevel = windowLevel
        self.windowWidth = windowWidth
        self.invertDisplay = invertDisplay
        self.voxels = voxels
        self.rois = rois
    }
}

public struct HorosHVRVOL02Destination: Equatable {
    public var host: String
    public var port: UInt16
    public var protocolName: String
    public var explicitlyAuthorized: Bool
    public var discoveredViaBonjour: Bool

    public init(
        host: String, port: UInt16, protocolName: String,
        explicitlyAuthorized: Bool, discoveredViaBonjour: Bool
    ) {
        self.host = host
        self.port = port
        self.protocolName = protocolName
        self.explicitlyAuthorized = explicitlyAuthorized
        self.discoveredViaBonjour = discoveredViaBonjour
    }
}

public struct HorosHVRVOL02ReceivedPackage: Equatable {
    public var volume: HorosHVRVOL02Volume
    public var checksumsMatch: Bool
}

/// Host exporter for the HVRVOL02 phone-volume contract. It packages a volume
/// already prepared in patient space; it does not decode DICOM or replace DIMSE.
@objc(HorosHVRVOL02Exporter)
public final class HorosHVRVOL02Exporter: NSObject {
    @objc public static let protocolName = "HVRVOL02"
    @objc public static let bonjourServiceType = "_horosiphone._tcp"

    public static func authorize(_ destination: HorosHVRVOL02Destination) throws {
        guard destination.explicitlyAuthorized else { throw HorosHVRVOL02Error.unauthorized }
        guard destination.protocolName == protocolName else { throw HorosHVRVOL02Error.incompatibleProtocol }
        guard !destination.host.isEmpty, destination.port != 0 else { throw HorosHVRVOL02Error.missingDestination }
    }

    public static func writePackage(_ volume: HorosHVRVOL02Volume, to directory: URL) throws -> [String] {
        try validate(volume)
        var assets: [[String: Any]] = []
        var assetNames: [String] = []

        let voxelName = "volume.f32"
        let voxelData = floatData(volume.voxels)
        try voxelData.write(to: directory.appendingPathComponent(voxelName), options: .atomic)
        assets.append(["name": voxelName, "byteCount": voxelData.count, "sha256": sha256(voxelData)])
        assetNames.append(voxelName)

        var roiRecords: [[String: Any]] = []
        for roi in volume.rois {
            let file = "roi-\(assetNames.count).f32"
            let data = floatData(roi.vertices)
            try data.write(to: directory.appendingPathComponent(file), options: .atomic)
            assets.append(["name": file, "byteCount": data.count, "sha256": sha256(data)])
            assetNames.append(file)
            roiRecords.append([
                "id": roi.id,
                "name": roi.name.isEmpty ? "ROI" : roi.name,
                "color": roi.color,
                "primitive": "triangles",
                "vertices": file
            ])
        }

        let descriptor: [String: Any] = [
            "id": volume.id,
            "name": volume.name,
            "seriesUID": volume.seriesUID,
            "studyUID": volume.studyUID,
            "frameOfReferenceUID": volume.frameOfReferenceUID,
            "modality": volume.modality.uppercased(),
            "dimensions": [volume.width, volume.height, volume.depth],
            "spacing": volume.spacing,
            "imageToPatient": volume.imageToPatient,
            "windowLevel": volume.windowLevel,
            "windowWidth": volume.windowWidth,
            "invertDisplay": volume.invertDisplay,
            "voxels": voxelName,
            "rois": roiRecords
        ]
        let manifest: [String: Any] = [
            "version": 2,
            "coordinateSystem": "DICOM_LPS_mm",
            "sampleType": "float32-le",
            "volumes": [descriptor],
            "assets": assets
        ]
        let json = try JSONSerialization.data(withJSONObject: manifest, options: [.sortedKeys])
        try json.write(to: directory.appendingPathComponent("manifest.json"), options: .atomic)
        return ["manifest.json"] + assetNames
    }

    public static func send(
        _ volume: HorosHVRVOL02Volume,
        to destination: HorosHVRVOL02Destination,
        over io: HorosHVRVOL02IO,
        cancelled: () -> Bool
    ) throws {
        try authorize(destination)
        if cancelled() { throw HorosHVRVOL02Error.cancelled }
        let scratch = FileManager.default.temporaryDirectory
            .appendingPathComponent("HVRVOL02-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: scratch, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: scratch) }
        if cancelled() { throw HorosHVRVOL02Error.cancelled }
        let names = try writePackage(volume, to: scratch)
        if cancelled() { throw HorosHVRVOL02Error.cancelled }
        try writeWire(names, from: scratch, to: io, cancelled: cancelled)
        let acknowledgement = try io.readExactly(1)
        if cancelled() { throw HorosHVRVOL02Error.cancelled }
        guard acknowledgement.first == 1 else { throw HorosHVRVOL02Error.incompleteAcknowledgement }
    }

    private static func writeWire(
        _ names: [String], from directory: URL, to io: HorosHVRVOL02IO, cancelled: () -> Bool
    ) throws {
        try io.write(Data("HVRVOL02".utf8))
        try io.write(be32(UInt32(names.count)))
        for name in names {
            if cancelled() { throw HorosHVRVOL02Error.cancelled }
            let url = directory.appendingPathComponent(name)
            let bytes = try Data(contentsOf: url)
            let nameData = Data(name.utf8)
            try io.write(be32(UInt32(nameData.count)))
            try io.write(nameData)
            try io.write(be64(UInt64(bytes.count)))
            try io.write(bytes)
        }
    }

    private static func validate(_ volume: HorosHVRVOL02Volume) throws {
        let modality = volume.modality.uppercased()
        guard ["CT", "MR"].contains(modality) else {
            throw HorosHVRVOL02Error.incoherentVolume("HVRVOL02 accepts one CT or MR volume.")
        }
        guard volume.width > 0, volume.height > 0, volume.depth > 0,
              volume.width <= 4096, volume.height <= 4096, volume.depth <= 4096 else {
            throw HorosHVRVOL02Error.incoherentVolume("Unsupported volume dimensions.")
        }
        let expected = volume.width * volume.height * volume.depth
        guard volume.voxels.count == expected else {
            throw HorosHVRVOL02Error.incoherentVolume("Voxel count does not match the stated dimensions.")
        }
        guard UInt64(volume.width) * UInt64(volume.height) * UInt64(volume.depth) <= 268_435_456 else {
            throw HorosHVRVOL02Error.incoherentVolume("The prepared volume exceeds the 1 GiB transfer limit.")
        }
        guard volume.voxels.allSatisfy(\.isFinite) else {
            throw HorosHVRVOL02Error.incoherentVolume("A voxel is not finite.")
        }
        guard volume.spacing.count == 3, volume.spacing.allSatisfy({ $0.isFinite && $0 > 0 }) else {
            throw HorosHVRVOL02Error.incoherentVolume("Spacing is missing or not physical.")
        }
        guard volume.imageToPatient.count == 16, volume.imageToPatient.allSatisfy(\.isFinite) else {
            throw HorosHVRVOL02Error.incoherentVolume("The patient matrix is incomplete.")
        }
        guard volume.windowWidth.isFinite, volume.windowWidth > 0, volume.windowLevel.isFinite else {
            throw HorosHVRVOL02Error.incoherentVolume("Display window is invalid.")
        }
        guard volume.rois.count <= 512 else {
            throw HorosHVRVOL02Error.incoherentVolume("Too many ROIs for one phone transfer.")
        }
        for roi in volume.rois {
            guard roi.vertices.count % 9 == 0, roi.color.count == 4,
                  roi.vertices.allSatisfy(\.isFinite), roi.color.allSatisfy(\.isFinite) else {
                throw HorosHVRVOL02Error.incoherentVolume("An ROI mesh is not a finite triangle list.")
            }
        }
    }

    private static func floatData(_ values: [Float]) -> Data {
        if values.isEmpty { return Data() }
        return values.withUnsafeBufferPointer { Data(bytes: $0.baseAddress!, count: $0.count * MemoryLayout<Float>.size) }
    }

    private static func sha256(_ data: Data) -> String {
        SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
    }

    private static func be32(_ value: UInt32) -> Data {
        var swapped = value.bigEndian
        return Data(bytes: &swapped, count: 4)
    }

    private static func be64(_ value: UInt64) -> Data {
        var swapped = value.bigEndian
        return Data(bytes: &swapped, count: 8)
    }
}

public enum HorosHVRVOL02Receptor {
    public static func receive(from io: HorosHVRVOL02IO, acknowledge: UInt8) throws -> HorosHVRVOL02ReceivedPackage {
        let magic = try io.readExactly(8)
        guard String(data: magic, encoding: .utf8) == HorosHVRVOL02Exporter.protocolName else {
            throw HorosHVRVOL02Error.transferFailed("handshake")
        }
        let count = Int(try u32(io))
        var files: [String: Data] = [:]
        for _ in 0..<count {
            let nameLength = Int(try u32(io))
            let name = String(data: try io.readExactly(nameLength), encoding: .utf8) ?? ""
            let length = Int(try u64(io))
            files[name] = try io.readExactly(length)
        }
        try io.write(Data([acknowledge]))
        guard acknowledge == 1 else {
            return HorosHVRVOL02ReceivedPackage(
                volume: HorosHVRVOL02Volume(
                    id: "", name: "", seriesUID: "", studyUID: "", frameOfReferenceUID: "",
                    modality: "", width: 0, height: 0, depth: 0, spacing: [], imageToPatient: [],
                    windowLevel: 0, windowWidth: 0, invertDisplay: false, voxels: [], rois: []
                ),
                checksumsMatch: false
            )
        }
        guard let manifestData = files["manifest.json"],
              let manifest = try JSONSerialization.jsonObject(with: manifestData) as? [String: Any],
              let volumes = manifest["volumes"] as? [[String: Any]],
              let descriptor = volumes.first else {
            throw HorosHVRVOL02Error.transferFailed("manifest")
        }
        let dimensions = ints(descriptor["dimensions"])
        let voxelName = descriptor["voxels"] as? String ?? "volume.f32"
        let voxelData = files[voxelName] ?? Data()
        var voxels = [Float](repeating: 0, count: voxelData.count / MemoryLayout<Float>.size)
        voxels.withUnsafeMutableBytes { _ = voxelData.copyBytes(to: $0) }
        let assetList = manifest["assets"] as? [[String: Any]] ?? []
        var checksumsMatch = true
        for asset in assetList {
            guard let name = asset["name"] as? String, let expected = asset["sha256"] as? String,
                  let data = files[name] else {
                checksumsMatch = false
                continue
            }
            let digest = SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
            if digest != expected { checksumsMatch = false }
        }
        var rois: [HorosHVRVOL02ROI] = []
        for record in descriptor["rois"] as? [[String: Any]] ?? [] {
            let file = record["vertices"] as? String ?? ""
            let data = files[file] ?? Data()
            var vertices = [Float](repeating: 0, count: data.count / MemoryLayout<Float>.size)
            vertices.withUnsafeMutableBytes { _ = data.copyBytes(to: $0) }
            rois.append(HorosHVRVOL02ROI(
                id: record["id"] as? String ?? "",
                name: record["name"] as? String ?? "",
                color: doubles(record["color"]),
                vertices: vertices
            ))
        }
        let volume = HorosHVRVOL02Volume(
            id: descriptor["id"] as? String ?? "",
            name: descriptor["name"] as? String ?? "",
            seriesUID: descriptor["seriesUID"] as? String ?? "",
            studyUID: descriptor["studyUID"] as? String ?? "",
            frameOfReferenceUID: descriptor["frameOfReferenceUID"] as? String ?? "",
            modality: descriptor["modality"] as? String ?? "",
            width: dimensions.count > 0 ? dimensions[0] : 0,
            height: dimensions.count > 1 ? dimensions[1] : 0,
            depth: dimensions.count > 2 ? dimensions[2] : 0,
            spacing: doubles(descriptor["spacing"]),
            imageToPatient: doubles(descriptor["imageToPatient"]),
            windowLevel: (descriptor["windowLevel"] as? NSNumber)?.doubleValue ?? 0,
            windowWidth: (descriptor["windowWidth"] as? NSNumber)?.doubleValue ?? 0,
            invertDisplay: (descriptor["invertDisplay"] as? Bool) ?? false,
            voxels: voxels,
            rois: rois
        )
        return HorosHVRVOL02ReceivedPackage(volume: volume, checksumsMatch: checksumsMatch)
    }

    private static func u32(_ io: HorosHVRVOL02IO) throws -> UInt32 {
        let data = try io.readExactly(4)
        return UInt32(bigEndian: data.withUnsafeBytes { $0.loadUnaligned(as: UInt32.self) })
    }

    private static func u64(_ io: HorosHVRVOL02IO) throws -> UInt64 {
        let data = try io.readExactly(8)
        return UInt64(bigEndian: data.withUnsafeBytes { $0.loadUnaligned(as: UInt64.self) })
    }

    private static func ints(_ any: Any?) -> [Int] {
        (any as? [NSNumber])?.map(\.intValue) ?? (any as? [Int]) ?? []
    }

    private static func doubles(_ any: Any?) -> [Double] {
        (any as? [NSNumber])?.map(\.doubleValue) ?? (any as? [Double]) ?? []
    }
}
