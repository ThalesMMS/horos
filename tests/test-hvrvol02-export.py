#!/usr/bin/env python3
"""HVRVOL02 packages a prepared volume for a fixture receptor, not a DICOM send."""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
code = r'''
import Foundation
import Darwin

func sampleVolume() -> HorosHVRVOL02Volume {
    HorosHVRVOL02Volume(
        id: "vol-1",
        name: "CT volume",
        seriesUID: "1.2.840.series",
        studyUID: "1.2.840.study",
        frameOfReferenceUID: "1.2.840.for",
        modality: "CT",
        width: 2,
        height: 2,
        depth: 2,
        spacing: [0.5, 0.5, 1.0],
        imageToPatient: [1, 0, 0, 10, 0, 1, 0, 20, 0, 0, 1, 30, 0, 0, 0, 1],
        windowLevel: 40,
        windowWidth: 400,
        invertDisplay: false,
        voxels: [0, 1, 2, 3, 4, 5, 6, 7],
        rois: [
            HorosHVRVOL02ROI(
                id: "roi-1",
                name: "vessel",
                color: [1, 0, 0, 0.65],
                vertices: [0, 0, 0, 1, 0, 0, 0, 1, 0]
            )
        ]
    )
}

func expectFailure(_ body: () throws -> Void, _ matches: (HorosHVRVOL02Error) -> Bool, _ label: String) {
    do {
        try body()
        precondition(false, "\(label): succeeded")
    } catch let error as HorosHVRVOL02Error {
        precondition(matches(error), "\(label): \(error)")
    } catch {
        precondition(false, "\(label): unexpected \(error)")
    }
}

final class SocketIO: HorosHVRVOL02IO {
    let fd: Int32
    init(_ fd: Int32) { self.fd = fd }
    func write(_ data: Data) throws {
        try data.withUnsafeBytes { raw in
            var sent = 0
            let base = raw.bindMemory(to: UInt8.self).baseAddress!
            while sent < data.count {
                let n = Darwin.write(fd, base + sent, data.count - sent)
                if n <= 0 { throw HorosHVRVOL02Error.transferFailed("write") }
                sent += n
            }
        }
    }
    func readExactly(_ count: Int) throws -> Data {
        var buffer = [UInt8](repeating: 0, count: count)
        var received = 0
        while received < count {
            let n = buffer.withUnsafeMutableBytes { Darwin.read(fd, $0.baseAddress! + received, count - received) }
            if n <= 0 { throw HorosHVRVOL02Error.transferFailed("read") }
            received += n
        }
        return Data(buffer)
    }
    deinit { Darwin.close(fd) }
}

func socketPair() -> (SocketIO, SocketIO) {
    var fds: [Int32] = [0, 0]
    precondition(socketpair(AF_UNIX, SOCK_STREAM, 0, &fds) == 0)
    return (SocketIO(fds[0]), SocketIO(fds[1]))
}

func authorized(_ host: String = "127.0.0.1", port: UInt16 = 9, protocolName: String = HorosHVRVOL02Exporter.protocolName) -> HorosHVRVOL02Destination {
    HorosHVRVOL02Destination(
        host: host,
        port: port,
        protocolName: protocolName,
        explicitlyAuthorized: true,
        discoveredViaBonjour: false
    )
}

// --- package is calibrated float32 in patient space, not DICOM ---------------
let directory = FileManager.default.temporaryDirectory
    .appendingPathComponent("hvrvol02-\(UUID().uuidString)", isDirectory: true)
try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
defer { try? FileManager.default.removeItem(at: directory) }

let names = try HorosHVRVOL02Exporter.writePackage(sampleVolume(), to: directory)
precondition(names.first == "manifest.json")
precondition(names.contains("volume.f32"))
precondition(!names.contains { $0.hasSuffix(".dcm") })

let manifestData = try Data(contentsOf: directory.appendingPathComponent("manifest.json"))
func numbers(_ any: Any?) -> [Double] {
    (any as? [NSNumber])?.map(\.doubleValue) ?? (any as? [Double]) ?? []
}
func ints(_ any: Any?) -> [Int] {
    (any as? [NSNumber])?.map(\.intValue) ?? (any as? [Int]) ?? []
}
let manifest = try JSONSerialization.jsonObject(with: manifestData) as! [String: Any]
precondition((manifest["version"] as? NSNumber)?.intValue == 2 || manifest["version"] as? Int == 2)
precondition(manifest["coordinateSystem"] as? String == "DICOM_LPS_mm")
precondition(manifest["sampleType"] as? String == "float32-le")
precondition(manifest["volumes"] is [Any])
let volume = (manifest["volumes"] as! [[String: Any]])[0]
precondition(volume["modality"] as? String == "CT")
precondition(ints(volume["dimensions"]) == [2, 2, 2])
precondition(numbers(volume["spacing"]) == [0.5, 0.5, 1.0])
precondition(numbers(volume["imageToPatient"]) == [1, 0, 0, 10, 0, 1, 0, 20, 0, 0, 1, 30, 0, 0, 0, 1])
precondition((volume["windowLevel"] as? NSNumber)?.doubleValue == 40 || volume["windowLevel"] as? Double == 40)
precondition((volume["windowWidth"] as? NSNumber)?.doubleValue == 400 || volume["windowWidth"] as? Double == 400)
precondition(volume["voxels"] as? String == "volume.f32")
let rois = volume["rois"] as! [[String: Any]]
precondition(rois.count == 1)
precondition(rois[0]["primitive"] as? String == "triangles")
precondition(rois[0]["name"] as? String == "vessel")

let voxelBytes = try Data(contentsOf: directory.appendingPathComponent("volume.f32"))
precondition(voxelBytes.count == 8 * 4)
var decoded = [Float](repeating: 0, count: 8)
decoded.withUnsafeMutableBytes { _ = voxelBytes.copyBytes(to: $0) }
precondition(decoded == [0, 1, 2, 3, 4, 5, 6, 7])

let assets = manifest["assets"] as! [[String: Any]]
precondition(assets.contains { ($0["name"] as? String) == "volume.f32" })
precondition(assets.contains { ($0["name"] as? String)?.hasPrefix("roi-") == true })

// --- Bonjour is not authorization; HVRVOL02 is not a generic DICOM send ------
precondition(HorosHVRVOL02Exporter.bonjourServiceType == "_horosiphone._tcp")
precondition(HorosHVRVOL02Exporter.protocolName == "HVRVOL02")

expectFailure({
    try HorosHVRVOL02Exporter.authorize(HorosHVRVOL02Destination(
        host: "10.0.0.8", port: 4242, protocolName: "HVRVOL02",
        explicitlyAuthorized: false, discoveredViaBonjour: true))
}, { if case .unauthorized = $0 { return true }; return false }, "bonjour without consent")

expectFailure({
    try HorosHVRVOL02Exporter.authorize(HorosHVRVOL02Destination(
        host: "10.0.0.8", port: 104, protocolName: "DICOM",
        explicitlyAuthorized: true, discoveredViaBonjour: false))
}, { if case .incompatibleProtocol = $0 { return true }; return false }, "DICOM protocol")

expectFailure({
    try HorosHVRVOL02Exporter.authorize(HorosHVRVOL02Destination(
        host: "", port: 4242, protocolName: "HVRVOL02",
        explicitlyAuthorized: true, discoveredViaBonjour: false))
}, { if case .missingDestination = $0 { return true }; return false }, "empty host")

// --- incoherent prepared volume is refused ----------------------------------
var broken = sampleVolume()
broken.voxels = [0, 1]
expectFailure({ _ = try HorosHVRVOL02Exporter.writePackage(broken, to: directory) },
              { if case .incoherentVolume = $0 { return true }; return false }, "voxel count")

var fourD = sampleVolume()
fourD.modality = "CT"
fourD.depth = 2
fourD.voxels = sampleVolume().voxels + sampleVolume().voxels
expectFailure({ _ = try HorosHVRVOL02Exporter.writePackage(fourD, to: directory) },
              { if case .incoherentVolume = $0 { return true }; return false }, "extra samples")

var pet = sampleVolume()
pet.modality = "PT"
expectFailure({ _ = try HorosHVRVOL02Exporter.writePackage(pet, to: directory) },
              { if case .incoherentVolume = $0 { return true }; return false }, "PT")

// --- fixture receptor compares voxels, matrix and ROI over a real socket ---
let (sender, receptor) = socketPair()
let ack = DispatchGroup()
var received: HorosHVRVOL02ReceivedPackage?
ack.enter()
DispatchQueue.global().async {
    received = try? HorosHVRVOL02Receptor.receive(from: receptor, acknowledge: 1)
    ack.leave()
}
try HorosHVRVOL02Exporter.send(sampleVolume(), to: authorized(), over: sender, cancelled: { false })
precondition(ack.wait(timeout: .now() + 5) == .success)
let package = received!
precondition(package.volume.voxels == [0, 1, 2, 3, 4, 5, 6, 7])
precondition(package.volume.imageToPatient == [1, 0, 0, 10, 0, 1, 0, 20, 0, 0, 1, 30, 0, 0, 0, 1])
precondition(package.volume.rois.count == 1)
precondition(package.volume.rois[0].vertices == [0, 0, 0, 1, 0, 0, 0, 1, 0])
precondition(package.checksumsMatch)

// --- incomplete ACK and cancel are failures, and temps are removed ----------
let (sender2, receptor2) = socketPair()
let ack2 = DispatchGroup()
ack2.enter()
DispatchQueue.global().async {
    _ = try? HorosHVRVOL02Receptor.receive(from: receptor2, acknowledge: 0)
    ack2.leave()
}
expectFailure({
    try HorosHVRVOL02Exporter.send(sampleVolume(), to: authorized(), over: sender2, cancelled: { false })
}, { if case .incompleteAcknowledgement = $0 { return true }; return false }, "ACK 0")
precondition(ack2.wait(timeout: .now() + 5) == .success)

let leftovers = try FileManager.default.contentsOfDirectory(
    at: FileManager.default.temporaryDirectory,
    includingPropertiesForKeys: nil
).filter { $0.lastPathComponent.hasPrefix("HorosPhone-") || $0.lastPathComponent.hasPrefix("HVRVOL02-") }
precondition(leftovers.isEmpty, "leftover packages: \(leftovers.map(\.lastPathComponent))")

expectFailure({
    try HorosHVRVOL02Exporter.send(sampleVolume(), to: authorized(), over: socketPair().0, cancelled: { true })
}, { if case .cancelled = $0 { return true }; return false }, "cancel")

print("PASS: HVRVOL02 package, authorization, fixture receptor, ACK and cleanup")
'''

with tempfile.TemporaryDirectory(prefix='horos-hvrvol02-') as directory:
    path = Path(directory)
    (path / 'main.swift').write_text(code)
    subprocess.run(
        ['xcrun', 'swiftc',
         str(root / 'Horos/Sources/HorosHVRVOL02.swift'),
         str(path / 'main.swift'),
         '-o', str(path / 'test')],
        check=True,
    )
    subprocess.run([str(path / 'test')], check=True)
