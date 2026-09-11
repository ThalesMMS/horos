import Darwin
import Foundation

/// Horos–Horos bulk/session framing (HOROSFT1 / HOROSFT2) and the DIMSE fallback.
/// Does not replace the local DICOMweb client (QIDO/WADO-RS). Retrieve mode 3
/// stays on that HTTP path.
@objc(HorosDirectTransferPolicy)
public final class DirectTransferPolicy: NSObject {
    @objc public static let routeDirect = "direct"
    @objc public static let routeDIMSE = "dimse"
    @objc public static let routeRefuse = "refuse"

    @objc public static let outcomeSuccess = "success"
    @objc public static let outcomePartial = "partial"
    @objc public static let outcomeCancelled = "cancelled"
    @objc public static let outcomeRejected = "rejected"
    @objc public static let outcomeWriteError = "write-error"

    @objc public static let bulkProtocolVersion: UInt32 = 1
    @objc public static let sessionProtocolVersion: UInt32 = 4
    public static let bulkMagic = Data("HOROSFT1".utf8)
    public static let sessionMagic = Data("HOROSFT2".utf8)
    public static let maximumFiles = 1_000_000
    public static let maximumFilenameBytes = 1_024
    public static let maximumFileBytes: UInt64 = 1 << 40
    public static let maximumTokenBytes = 256

    @objc(routeForServer:destinationChosen:authorized:)
    public static func route(server: [String: Any], destinationChosen: Bool, authorized: Bool) -> String {
        if retrieveMode(server) == 3 { return routeDIMSE }
        if !destinationChosen { return routeRefuse }
        if isCapable(server) {
            return authorized ? routeDirect : routeRefuse
        }
        return routeDIMSE
    }

    @objc(fallbackReasonFor:)
    public static func fallbackReason(for server: [String: Any]) -> String? {
        if retrieveMode(server) == 3 {
            return "DICOMweb nodes keep QIDO/WADO-RS; Horos direct transfer is not a substitute."
        }
        if isCapable(server) { return nil }
        return "Peer does not advertise Horos direct transfer; using DICOM C-STORE."
    }

    @objc(bonjourTXTFields)
    public static func bonjourTXTFields() -> [String: String] {
        var fields = ["HorosDirectTransferVersion": "\(sessionProtocolVersion)"]
        let port = DirectTransferService.shared.port
        if port > 0 {
            fields["HorosDirectTransferPort"] = "\(port)"
        }
        return fields
    }

    @objc(sessionCompatibleWithAdvertisedVersion:)
    public static func sessionCompatible(advertisedVersion: Int) -> Bool {
        advertisedVersion >= Int(sessionProtocolVersion)
    }

    @objc(statusWithFileCount:patientName:)
    public static func status(fileCount: Int, patientName: String) -> String {
        _ = patientName
        let format = NSLocalizedString("Sending %d files", comment: "direct transfer status without PHI")
        return String(format: format, fileCount)
    }

    @objc(outcomeExpectedUIDs:receivedUIDs:fileCount:frameCount:cancelled:ackStatus:writeError:)
    public static func outcome(expectedUIDs: [String],
                               receivedUIDs: [String],
                               fileCount: Int,
                               frameCount: Int,
                               cancelled: Bool,
                               ackStatus: UInt32,
                               writeError: Bool) -> String {
        _ = fileCount
        _ = frameCount
        if cancelled { return outcomeCancelled }
        if writeError { return outcomeWriteError }
        if ackStatus != 0 { return outcomeRejected }
        let expected = Set(expectedUIDs)
        let received = Set(receivedUIDs)
        if expected == received { return outcomeSuccess }
        return outcomePartial
    }

    public static func encodeBulkHeader(fileCount: Int, totalBytes: UInt64, token: String) throws -> Data {
        guard fileCount > 0, fileCount <= maximumFiles else { throw DirectTransferError.invalidProtocol }
        let tokenData = Data(token.utf8)
        guard !tokenData.isEmpty, tokenData.count <= maximumTokenBytes else { throw DirectTransferError.invalidProtocol }
        var header = Data()
        header.append(bulkMagic)
        header.appendNetwork(bulkProtocolVersion)
        header.appendNetwork(UInt32(fileCount))
        header.appendNetwork(totalBytes)
        header.appendNetwork(UInt32(tokenData.count))
        header.append(tokenData)
        return header
    }

    public static func decodeBulkHeader(_ data: Data) throws -> (version: UInt32, fileCount: Int, totalBytes: UInt64, token: String) {
        guard data.count >= 28, data.prefix(8) == bulkMagic else { throw DirectTransferError.invalidProtocol }
        let version = data.networkUInt32(at: 8)
        let fileCount = Int(data.networkUInt32(at: 12))
        let totalBytes = data.networkUInt64(at: 16)
        let tokenLength = Int(data.networkUInt32(at: 24))
        guard tokenLength > 0, tokenLength <= maximumTokenBytes, data.count >= 28 + tokenLength else {
            throw DirectTransferError.invalidProtocol
        }
        guard let token = String(data: data.subdata(in: 28..<(28 + tokenLength)), encoding: .utf8), !token.isEmpty else {
            throw DirectTransferError.invalidProtocol
        }
        guard fileCount > 0, fileCount <= maximumFiles else { throw DirectTransferError.invalidProtocol }
        return (version, fileCount, totalBytes, token)
    }

    public static func encodeSessionHeader(operation: DirectTransferSessionOperation, token: String) throws -> Data {
        let tokenData = Data(token.utf8)
        guard !tokenData.isEmpty, tokenData.count <= maximumTokenBytes else { throw DirectTransferError.invalidProtocol }
        var header = Data()
        header.append(sessionMagic)
        header.appendNetwork(sessionProtocolVersion)
        header.appendNetwork(operation.rawValue)
        header.appendNetwork(UInt32(tokenData.count))
        header.append(tokenData)
        return header
    }

    public static func decodeSessionHeader(_ data: Data) throws -> (version: UInt32, operation: DirectTransferSessionOperation, token: String) {
        guard data.count >= 20, data.prefix(8) == sessionMagic else { throw DirectTransferError.invalidProtocol }
        let version = data.networkUInt32(at: 8)
        guard version == sessionProtocolVersion,
              let operation = DirectTransferSessionOperation(rawValue: data.networkUInt32(at: 12)) else {
            throw DirectTransferError.invalidProtocol
        }
        let tokenLength = Int(data.networkUInt32(at: 16))
        guard tokenLength > 0, tokenLength <= maximumTokenBytes, data.count >= 20 + tokenLength else {
            throw DirectTransferError.invalidProtocol
        }
        guard let token = String(data: data.subdata(in: 20..<(20 + tokenLength)), encoding: .utf8) else {
            throw DirectTransferError.invalidProtocol
        }
        return (version, operation, token)
    }

    public static func encodeFileFrame(name: String, bytes: Data) throws -> Data {
        try validateFileName(name)
        guard !bytes.isEmpty, UInt64(bytes.count) <= maximumFileBytes else { throw DirectTransferError.invalidFile(name) }
        let nameData = Data(name.utf8)
        guard nameData.count <= maximumFilenameBytes else { throw DirectTransferError.invalidFile(name) }
        var frame = Data()
        frame.appendNetwork(UInt32(nameData.count))
        frame.appendNetwork(UInt64(bytes.count))
        frame.append(nameData)
        frame.append(bytes)
        return frame
    }

    public static func decodeFileFrame(_ data: Data) throws -> (name: String, bytes: Data) {
        guard data.count >= 12 else { throw DirectTransferError.invalidProtocol }
        let nameLength = Int(data.networkUInt32(at: 0))
        let size = data.networkUInt64(at: 4)
        guard nameLength > 0, nameLength <= maximumFilenameBytes, data.count >= 12 + nameLength else {
            throw DirectTransferError.invalidProtocol
        }
        guard let name = String(data: data.subdata(in: 12..<(12 + nameLength)), encoding: .utf8) else {
            throw DirectTransferError.invalidProtocol
        }
        try validateFileName(name)
        let start = 12 + nameLength
        guard UInt64(data.count - start) >= size, size > 0, size <= maximumFileBytes else {
            throw DirectTransferError.invalidProtocol
        }
        return (name, data.subdata(in: start..<(start + Int(size))))
    }

    public static func validateFileName(_ name: String) throws {
        let trimmed = (name as NSString).lastPathComponent
        guard trimmed == name, !name.isEmpty, !name.contains(".."), !name.contains("/"), !name.contains("\\") else {
            throw DirectTransferError.pathTraversal
        }
    }

    public static func isCapable(_ server: [String: Any]) -> Bool {
        let version = intValue(server, "HorosDirectTransferVersion")
        let port = intValue(server, "HorosDirectTransferPort")
        let token = stringValue(server, "HorosDirectTransferToken")
        let address = stringValue(server, "Address")
        return version >= 1 && port > 0 && port <= Int(UInt16.max) && !(token?.isEmpty ?? true) && !(address?.isEmpty ?? true)
    }

    public static func retrieveMode(_ server: [String: Any]) -> Int {
        if let value = server["retrieveMode"] as? Int { return value }
        if let value = server["retrieveMode"] as? NSNumber { return value.intValue }
        return 0
    }

    public static func intValue(_ server: [String: Any], _ key: String) -> Int {
        if let value = server[key] as? Int { return value }
        if let value = server[key] as? NSNumber { return value.intValue }
        if let value = server[key] as? String, let parsed = Int(value) { return parsed }
        return 0
    }

    public static func stringValue(_ server: [String: Any], _ key: String) -> String? {
        if let value = server[key] as? String, !value.isEmpty { return value }
        return nil
    }
}

@objc
public enum DirectTransferSessionOperation: UInt32 {
    case checkIn = 1
}

public enum DirectTransferError: Error {
    case cancelled
    case unauthorized
    case invalidProtocol
    case invalidFile(String)
    case receiverRejected
    case pathTraversal
    case listenFailed
}

public struct DirectTransferSendResult {
    public let outcome: String
}

public struct ReceivedFile {
    public let name: String
}

public enum DirectTransferListenInterface {
    case loopbackIPv4
    case loopbackIPv6
    case sharingAny
}

/// Check-in and Bonjour sources, kept apart from saved PACS nodes.
@objc(HorosDirectTransferSourceCatalog)
public final class DirectTransferSourceCatalog: NSObject {
    private struct Source {
        var identifier: String
        var aeTitle: String
        var address: String
        var peerUID: String?
    }

    private var permanent: [String: Source] = [:]
    private var bonjour: [String: Source] = [:]
    private var sessions: [String: Source] = [:]

    @objc(addPermanentIdentifier:aeTitle:address:)
    public func addPermanent(identifier: String, aeTitle: String, address: String) {
        permanent[identifier] = Source(identifier: identifier, aeTitle: aeTitle, address: address, peerUID: nil)
    }

    @objc(addBonjourIdentifier:aeTitle:address:)
    public func addBonjour(identifier: String, aeTitle: String, address: String) {
        bonjour[identifier] = Source(identifier: identifier, aeTitle: aeTitle, address: address, peerUID: nil)
    }

    @objc(addSessionIdentifier:peerUID:aeTitle:address:)
    public func addSession(identifier: String, peerUID: String, aeTitle: String, address: String) {
        sessions = sessions.filter { $0.value.peerUID?.caseInsensitiveCompare(peerUID) != .orderedSame }
        sessions[identifier] = Source(identifier: identifier, aeTitle: aeTitle, address: address, peerUID: peerUID)
    }

    @objc(dropBonjourIdentifier:)
    public func dropBonjour(identifier: String) {
        bonjour.removeValue(forKey: identifier)
    }

    @objc(dropSessionIdentifier:)
    public func dropSession(identifier: String) {
        sessions.removeValue(forKey: identifier)
    }

    @objc public var permanentIdentifiers: [String] { permanent.keys.sorted() }
    @objc public var sessionIdentifiers: [String] { sessions.keys.sorted() }
    @objc public var identifiers: [String] {
        Array(Set(permanent.keys).union(bonjour.keys).union(sessions.keys)).sorted()
    }
}

@objc(HorosDirectTransferListener)
public final class DirectTransferListener: NSObject {
    private let token: String
    private let lock = NSLock()
    private var listenFD: Int32 = -1
    private var running = false
    private var staged: [(name: String, data: Data)] = []
    private let acceptQueue = DispatchQueue(label: "org.horos.direct-transfer.accept")
    @objc public private(set) var port: UInt16 = 0

    @objc(initWithToken:)
    public init(token: String) {
        self.token = token
        super.init()
    }

    public func start(interface: DirectTransferListenInterface) throws {
        stop()
        let bound = try POSIXTCP.bindListen(interface: interface)
        listenFD = bound.fd
        port = bound.port
        running = true
        let fd = listenFD
        acceptQueue.async { [weak self] in
            while let self, self.running {
                var address = sockaddr_storage()
                var length = socklen_t(MemoryLayout<sockaddr_storage>.size)
                let client = withUnsafeMutablePointer(to: &address) {
                    $0.withMemoryRebound(to: sockaddr.self, capacity: 1) {
                        Darwin.accept(fd, $0, &length)
                    }
                }
                if client < 0 { break }
                self.handle(client: client)
            }
        }
    }

    @objc public func stop() {
        running = false
        if listenFD >= 0 {
            Darwin.close(listenFD)
            listenFD = -1
        }
        port = 0
    }

    public func takeReceivedFiles(into directory: URL) throws -> [ReceivedFile] {
        lock.lock()
        let files = staged
        staged.removeAll()
        lock.unlock()
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        var received: [ReceivedFile] = []
        for file in files {
            try file.data.write(to: directory.appendingPathComponent(file.name), options: .atomic)
            received.append(ReceivedFile(name: file.name))
        }
        return received
    }

    private func handle(client: Int32) {
        defer { Darwin.close(client) }
        do {
            try POSIXTCP.setTimeouts(client)
            let headerPrefix = try POSIXTCP.receiveExact(client, count: 8)
            guard headerPrefix == DirectTransferPolicy.bulkMagic else { throw DirectTransferError.invalidProtocol }
            let restHead = try POSIXTCP.receiveExact(client, count: 20)
            var header = headerPrefix
            header.append(restHead)
            let tokenLength = Int(header.networkUInt32(at: 24))
            guard tokenLength > 0, tokenLength <= DirectTransferPolicy.maximumTokenBytes else {
                throw DirectTransferError.invalidProtocol
            }
            header.append(try POSIXTCP.receiveExact(client, count: tokenLength))
            let decoded = try DirectTransferPolicy.decodeBulkHeader(header)
            guard decoded.token == token else {
                try POSIXTCP.sendAll(client, DirectTransferPolicy.ack(1))
                return
            }
            var receivedBytes: UInt64 = 0
            var incoming: [(name: String, data: Data)] = []
            for _ in 0..<decoded.fileCount {
                let nameLengthData = try POSIXTCP.receiveExact(client, count: 4)
                let nameLength = Int(nameLengthData.networkUInt32(at: 0))
                let sizeData = try POSIXTCP.receiveExact(client, count: 8)
                let size = sizeData.networkUInt64(at: 0)
                guard nameLength > 0, nameLength <= DirectTransferPolicy.maximumFilenameBytes,
                      size > 0, size <= DirectTransferPolicy.maximumFileBytes else {
                    throw DirectTransferError.invalidProtocol
                }
                let nameData = try POSIXTCP.receiveExact(client, count: nameLength)
                guard let name = String(data: nameData, encoding: .utf8) else { throw DirectTransferError.invalidProtocol }
                try DirectTransferPolicy.validateFileName(name)
                let bytes = try POSIXTCP.receiveExact(client, count: Int(size))
                incoming.append((name, bytes))
                receivedBytes += size
            }
            guard receivedBytes == decoded.totalBytes else { throw DirectTransferError.invalidProtocol }
            try POSIXTCP.sendAll(client, DirectTransferPolicy.ack(0))
            lock.lock()
            staged.append(contentsOf: incoming)
            lock.unlock()
        } catch {
            try? POSIXTCP.sendAll(client, DirectTransferPolicy.ack(1))
        }
    }
}

@objc(HorosDirectTransferClient)
public final class DirectTransferClient: NSObject {
    public static func send(files: [String],
                            host: String,
                            port: Int,
                            token: String,
                            expectedUIDs: [String],
                            cancelled: Bool) throws -> DirectTransferSendResult {
        if cancelled { throw DirectTransferError.cancelled }
        guard port > 0, port <= Int(UInt16.max), !host.isEmpty, !token.isEmpty else {
            throw DirectTransferError.invalidProtocol
        }
        var entries: [(name: String, bytes: Data)] = []
        for path in files {
            let url = URL(fileURLWithPath: path)
            try DirectTransferPolicy.validateFileName(url.lastPathComponent)
            let bytes = try Data(contentsOf: url)
            guard !bytes.isEmpty else { throw DirectTransferError.invalidFile(path) }
            entries.append((url.lastPathComponent, bytes))
        }
        let total = entries.reduce(UInt64(0)) { $0 + UInt64($1.bytes.count) }
        let header = try DirectTransferPolicy.encodeBulkHeader(fileCount: entries.count, totalBytes: total, token: token)
        let fd = try POSIXTCP.connect(host: host, port: UInt16(port))
        defer { Darwin.close(fd) }
        try POSIXTCP.setTimeouts(fd)
        try POSIXTCP.sendAll(fd, header)
        for entry in entries {
            try POSIXTCP.sendAll(fd, try DirectTransferPolicy.encodeFileFrame(name: entry.name, bytes: entry.bytes))
        }
        let ack = try POSIXTCP.receiveExact(fd, count: 4).networkUInt32(at: 0)
        guard ack == 0 else { throw DirectTransferError.unauthorized }
        let receivedUIDs = entries.map { ($0.name as NSString).deletingPathExtension }
        let outcome = DirectTransferPolicy.outcome(expectedUIDs: expectedUIDs,
                                                    receivedUIDs: receivedUIDs,
                                                    fileCount: entries.count,
                                                    frameCount: entries.count,
                                                    cancelled: false,
                                                    ackStatus: ack,
                                                    writeError: false)
        return DirectTransferSendResult(outcome: outcome)
    }
}

@objc(HorosDirectTransferService)
public final class DirectTransferService: NSObject {
    @objc(sharedService)
    public static let shared = DirectTransferService()

    private let lock = NSLock()
    private var listener: DirectTransferListener?
    @objc public var token: String = UUID().uuidString
    @objc public var port: Int {
        lock.lock(); defer { lock.unlock() }
        return Int(listener?.port ?? 0)
    }

    @objc(startIfSharingActive)
    public func startIfSharingActive() {
        lock.lock()
        if listener == nil {
            let next = DirectTransferListener(token: token)
            listener = next
            lock.unlock()
            try? next.start(interface: .sharingAny)
            return
        }
        lock.unlock()
    }

    @objc public func stop() {
        lock.lock()
        listener?.stop()
        listener = nil
        lock.unlock()
    }

    @objc(sendFiles:toHost:port:token:activityThread:)
    public func send(files: [String], toHost host: String, port: Int, token: String, activityThread: Thread?) -> Bool {
        if activityThread?.isCancelled == true { return false }
        do {
            _ = try DirectTransferClient.send(files: files,
                                             host: host,
                                             port: port,
                                             token: token,
                                             expectedUIDs: files.map { (URL(fileURLWithPath: $0).lastPathComponent as NSString).deletingPathExtension },
                                             cancelled: activityThread?.isCancelled == true)
            return true
        } catch {
            return false
        }
    }
}

extension DirectTransferPolicy {
    public static func ack(_ status: UInt32) -> Data {
        var data = Data()
        data.appendNetwork(status)
        return data
    }
}

private enum POSIXTCP {
    static func bindListen(interface: DirectTransferListenInterface) throws -> (fd: Int32, port: UInt16) {
        switch interface {
        case .loopbackIPv4:
            return try bindIPv4(address: in_addr(s_addr: inet_addr("127.0.0.1")))
        case .sharingAny:
            return try bindIPv4(address: in_addr(s_addr: INADDR_ANY.bigEndian))
        case .loopbackIPv6:
            return try bindIPv6(loopback: true)
        }
    }

    static func bindIPv4(address: in_addr) throws -> (fd: Int32, port: UInt16) {
        let fd = Darwin.socket(AF_INET, SOCK_STREAM, IPPROTO_TCP)
        guard fd >= 0 else { throw DirectTransferError.listenFailed }
        var yes: Int32 = 1
        setsockopt(fd, SOL_SOCKET, SO_REUSEADDR, &yes, socklen_t(MemoryLayout<Int32>.size))
        var addr = sockaddr_in()
        addr.sin_len = UInt8(MemoryLayout<sockaddr_in>.size)
        addr.sin_family = sa_family_t(AF_INET)
        addr.sin_port = 0
        addr.sin_addr = address
        let bound = withUnsafePointer(to: &addr) {
            $0.withMemoryRebound(to: sockaddr.self, capacity: 1) {
                Darwin.bind(fd, $0, socklen_t(MemoryLayout<sockaddr_in>.size))
            }
        }
        guard bound == 0, Darwin.listen(fd, 8) == 0 else {
            Darwin.close(fd)
            throw DirectTransferError.listenFailed
        }
        var named = sockaddr_in()
        var namedLength = socklen_t(MemoryLayout<sockaddr_in>.size)
        let got = withUnsafeMutablePointer(to: &named) {
            $0.withMemoryRebound(to: sockaddr.self, capacity: 1) {
                Darwin.getsockname(fd, $0, &namedLength)
            }
        }
        guard got == 0 else {
            Darwin.close(fd)
            throw DirectTransferError.listenFailed
        }
        return (fd, UInt16(bigEndian: named.sin_port))
    }

    static func bindIPv6(loopback: Bool) throws -> (fd: Int32, port: UInt16) {
        let fd = Darwin.socket(AF_INET6, SOCK_STREAM, IPPROTO_TCP)
        guard fd >= 0 else { throw DirectTransferError.listenFailed }
        var yes: Int32 = 1
        setsockopt(fd, SOL_SOCKET, SO_REUSEADDR, &yes, socklen_t(MemoryLayout<Int32>.size))
        var only: Int32 = 1
        setsockopt(fd, IPPROTO_IPV6, IPV6_V6ONLY, &only, socklen_t(MemoryLayout<Int32>.size))
        var addr = sockaddr_in6()
        addr.sin6_len = UInt8(MemoryLayout<sockaddr_in6>.size)
        addr.sin6_family = sa_family_t(AF_INET6)
        addr.sin6_port = 0
        if loopback {
            inet_pton(AF_INET6, "::1", &addr.sin6_addr)
        }
        let bound = withUnsafePointer(to: &addr) {
            $0.withMemoryRebound(to: sockaddr.self, capacity: 1) {
                Darwin.bind(fd, $0, socklen_t(MemoryLayout<sockaddr_in6>.size))
            }
        }
        guard bound == 0, Darwin.listen(fd, 8) == 0 else {
            Darwin.close(fd)
            throw DirectTransferError.listenFailed
        }
        var named = sockaddr_in6()
        var namedLength = socklen_t(MemoryLayout<sockaddr_in6>.size)
        let got = withUnsafeMutablePointer(to: &named) {
            $0.withMemoryRebound(to: sockaddr.self, capacity: 1) {
                Darwin.getsockname(fd, $0, &namedLength)
            }
        }
        guard got == 0 else {
            Darwin.close(fd)
            throw DirectTransferError.listenFailed
        }
        return (fd, UInt16(bigEndian: named.sin6_port))
    }

    static func connect(host: String, port: UInt16) throws -> Int32 {
        if host.contains(":") {
            let fd = Darwin.socket(AF_INET6, SOCK_STREAM, IPPROTO_TCP)
            guard fd >= 0 else { throw DirectTransferError.listenFailed }
            var addr = sockaddr_in6()
            addr.sin6_len = UInt8(MemoryLayout<sockaddr_in6>.size)
            addr.sin6_family = sa_family_t(AF_INET6)
            addr.sin6_port = port.bigEndian
            guard inet_pton(AF_INET6, host, &addr.sin6_addr) == 1 else {
                Darwin.close(fd)
                throw DirectTransferError.invalidProtocol
            }
            let ok = withUnsafePointer(to: &addr) {
                $0.withMemoryRebound(to: sockaddr.self, capacity: 1) {
                    Darwin.connect(fd, $0, socklen_t(MemoryLayout<sockaddr_in6>.size))
                }
            }
            guard ok == 0 else {
                Darwin.close(fd)
                throw DirectTransferError.receiverRejected
            }
            return fd
        }
        let fd = Darwin.socket(AF_INET, SOCK_STREAM, IPPROTO_TCP)
        guard fd >= 0 else { throw DirectTransferError.listenFailed }
        var addr = sockaddr_in()
        addr.sin_len = UInt8(MemoryLayout<sockaddr_in>.size)
        addr.sin_family = sa_family_t(AF_INET)
        addr.sin_port = port.bigEndian
        guard inet_pton(AF_INET, host, &addr.sin_addr) == 1 else {
            Darwin.close(fd)
            throw DirectTransferError.invalidProtocol
        }
        let ok = withUnsafePointer(to: &addr) {
            $0.withMemoryRebound(to: sockaddr.self, capacity: 1) {
                Darwin.connect(fd, $0, socklen_t(MemoryLayout<sockaddr_in>.size))
            }
        }
        guard ok == 0 else {
            Darwin.close(fd)
            throw DirectTransferError.receiverRejected
        }
        return fd
    }

    static func setTimeouts(_ fd: Int32) throws {
        var timeout = timeval(tv_sec: 8, tv_usec: 0)
        setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &timeout, socklen_t(MemoryLayout<timeval>.size))
        setsockopt(fd, SOL_SOCKET, SO_SNDTIMEO, &timeout, socklen_t(MemoryLayout<timeval>.size))
        var nodelay: Int32 = 1
        setsockopt(fd, IPPROTO_TCP, TCP_NODELAY, &nodelay, socklen_t(MemoryLayout<Int32>.size))
    }

    static func sendAll(_ fd: Int32, _ data: Data) throws {
        var offset = 0
        while offset < data.count {
            let sent: Int = data.withUnsafeBytes { raw in
                let base = raw.bindMemory(to: UInt8.self).baseAddress! + offset
                return Darwin.send(fd, base, data.count - offset, 0)
            }
            if sent <= 0 { throw DirectTransferError.receiverRejected }
            offset += sent
        }
    }

    static func receiveExact(_ fd: Int32, count: Int) throws -> Data {
        var data = Data()
        data.reserveCapacity(count)
        var buffer = [UInt8](repeating: 0, count: min(count, 64 * 1024))
        while data.count < count {
            let wanted = min(buffer.count, count - data.count)
            let got = Darwin.recv(fd, &buffer, wanted, 0)
            if got <= 0 { throw DirectTransferError.invalidProtocol }
            data.append(buffer, count: got)
        }
        return data
    }
}

private extension Data {
    mutating func appendNetwork(_ value: UInt32) {
        var encoded = value.bigEndian
        append(Data(bytes: &encoded, count: 4))
    }

    mutating func appendNetwork(_ value: UInt64) {
        var encoded = value.bigEndian
        append(Data(bytes: &encoded, count: 8))
    }

    func networkUInt32(at offset: Int) -> UInt32 {
        let slice = subdata(in: offset..<(offset + 4))
        return slice.withUnsafeBytes { UInt32(bigEndian: $0.load(as: UInt32.self)) }
    }

    func networkUInt64(at offset: Int) -> UInt64 {
        let slice = subdata(in: offset..<(offset + 8))
        return slice.withUnsafeBytes { UInt64(bigEndian: $0.load(as: UInt64.self)) }
    }
}
