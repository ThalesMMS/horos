import Foundation
import Network

/// What a shared-database server tells its owner, on the main queue (#615).
@objc(HorosDatabaseServerDelegate)
public protocol HorosDatabaseServerDelegate: AnyObject {
    /// The listener accepts connections on `server.port`.
    func databaseServerDidStart(_ server: HorosDatabaseServer)
    /// The listener failed and the server stopped. `posixError` is the errno behind it (EADDRINUSE when
    /// the port is taken), 0 when the failure is not a POSIX one.
    func databaseServer(_ server: HorosDatabaseServer, didFailWithPOSIXError posixError: Int32, description: String)
    /// The listener waits for the network and accepts nothing until it is ready again, when
    /// `databaseServerDidStart` follows.
    func databaseServer(_ server: HorosDatabaseServer, isWaitingWithPOSIXError posixError: Int32, description: String)
}

/// The shared-database server's listener (#615): a Network.framework listener that hands every accepted
/// connection to a handler on a bounded worker pool.
///
/// Adapted from the donor fork's HorosDatabaseServer.swift; provenance in NOTICE. What a request may do - the
/// protocol, its limits and its authorization - stays in the handler (O2DatabaseConnection, #614, #637);
/// this class only decides how many connections exist, where they run and how long they may wait.
///
/// - The owner starts and stops the server and hears from it on the main queue. The listener and the connection
///   table live on a queue of their own: a main-queue block that runs a modal alert (the app's report-import
///   alert does) holds every other main-queue block until it is dismissed, and a listener there accepted
///   nothing for as long.
/// - At most `maximumConnections` connections exist at once, counting the ones waiting for a worker; the
///   next one is refused by closing it.
/// - At most `maximumWorkers` handlers run at once, each on its own operation.
/// - Every wait of a handler for the network is bounded by `idleTimeout` of monotonic time.
/// - `stop()` closes the listener and every connection, running or waiting; a callback of a stopped
///   listener changes nothing, so a restarted server is not touched by its predecessor.
@objc(HorosDatabaseServer)
public final class HorosDatabaseServer: NSObject {
    @objc public weak var delegate: HorosDatabaseServerDelegate?
    /// The port the listener is ready on, as the main queue last heard; 0 while it is not.
    @objc public private(set) var port = 0
    @objc public let maximumConnections: Int
    @objc public let maximumWorkers: Int
    @objc public let chunkSize: Int
    @objc public let idleTimeout: TimeInterval

    private let requestedPort: NWEndpoint.Port
    private let handler: (HorosDatabasePeer) -> Void
    private let workers: OperationQueue
    private let queue = DispatchQueue(label: "org.horosproject.database-server")
    // On `queue`.
    private var listener: NWListener?
    private var peers: [UUID: HorosDatabasePeer] = [:]
    // On the main queue: every start and stop begins a generation, and a report of an earlier one is dropped.
    private var generation = 0

    @objc(initWithPort:handler:)
    public convenience init(port: UInt16, handler: @escaping (HorosDatabasePeer) -> Void) {
        self.init(port: port, maximumConnections: 32, maximumWorkers: 8, chunkSize: 128 * 1024, idleTimeout: 45,
                  handler: handler)
    }

    @objc(initWithPort:maximumConnections:maximumWorkers:chunkSize:idleTimeout:handler:)
    public init(port: UInt16, maximumConnections: Int, maximumWorkers: Int, chunkSize: Int, idleTimeout: TimeInterval,
         handler: @escaping (HorosDatabasePeer) -> Void) {
        requestedPort = NWEndpoint.Port(rawValue: port) ?? .any
        self.maximumConnections = max(1, maximumConnections)
        self.maximumWorkers = max(1, maximumWorkers)
        self.chunkSize = max(1, chunkSize)
        self.idleTimeout = max(0.001, idleTimeout)
        self.handler = handler
        workers = OperationQueue()
        workers.name = "org.horosproject.database-server-workers"
        workers.qualityOfService = .userInitiated
        workers.maxConcurrentOperationCount = self.maximumWorkers
        super.init()
    }

    /// Connections accepted and not yet finished, waiting for a worker or running.
    @objc public var connectionCount: Int {
        queue.sync { peers.count }
    }

    @objc public func start() {
        dispatchPrecondition(condition: .onQueue(.main))
        guard queue.sync(execute: { listener == nil }) else { return }
        let listener: NWListener
        do {
            let tcp = NWProtocolTCP.Options()
            tcp.noDelay = true
            let parameters = NWParameters(tls: nil, tcp: tcp)
            parameters.allowLocalEndpointReuse = true
            listener = try NWListener(using: parameters, on: requestedPort)
        } catch {
            delegate?.databaseServer(self, didFailWithPOSIXError: Self.posixCode(error),
                                     description: String(describing: error))
            return
        }
        generation += 1
        let current = generation
        listener.stateUpdateHandler = { [weak self, weak listener] state in
            guard let self, let listener, self.listener === listener else { return }
            switch state {
            case .ready:
                let port = Int(listener.port?.rawValue ?? 0)
                report(current) { $0.port = port; $0.delegate?.databaseServerDidStart($0) }
            case .waiting(let error):
                report(current) {
                    $0.port = 0
                    $0.delegate?.databaseServer($0, isWaitingWithPOSIXError: Self.posixCode(error),
                                                description: String(describing: error))
                }
            case .failed(let error):
                // A port that is taken fails the listener, and the server stops.
                close()
                report(current) {
                    $0.port = 0
                    $0.delegate?.databaseServer($0, didFailWithPOSIXError: Self.posixCode(error),
                                                description: String(describing: error))
                }
            default:
                break
            }
        }
        listener.newConnectionHandler = { [weak self, weak listener] connection in
            guard let self, let listener, self.listener === listener else {
                connection.cancel()
                return
            }
            accept(connection)
        }
        queue.sync {
            self.listener = listener
            listener.start(queue: queue)
        }
    }

    @objc public func stop() {
        dispatchPrecondition(condition: .onQueue(.main))
        generation += 1
        port = 0
        queue.sync { close() }
    }

    /// Tells the owner, on the main queue, unless the server was stopped or started again since `generation`.
    private func report(_ generation: Int, _ body: @escaping (HorosDatabaseServer) -> Void) {
        DispatchQueue.main.async { [weak self] in
            guard let self, self.generation == generation else { return }
            body(self)
        }
    }

    /// On `queue`: the listener and every connection, running or waiting, are closed.
    private func close() {
        listener?.stateUpdateHandler = nil
        listener?.newConnectionHandler = nil
        listener?.cancel()
        listener = nil
        workers.cancelAllOperations()
        for peer in peers.values { peer.cancel() }
        peers.removeAll()
    }

    /// On `queue`.
    private func accept(_ connection: NWConnection) {
        guard peers.count < maximumConnections else {
            NSLog("Shared database: connection refused, %ld already open", peers.count)
            connection.cancel()
            return
        }
        let identifier = UUID()
        let peer = HorosDatabasePeer(connection: connection, chunkSize: chunkSize, idleTimeout: idleTimeout)
        peers[identifier] = peer
        let handler = handler
        let operation = BlockOperation()
        operation.addExecutionBlock { [weak self, weak operation] in
            autoreleasepool {
                defer {
                    peer.cancel()
                    self?.queue.async { [weak self] in
                        // A stopped server already emptied its table; a new connection has a new identifier.
                        _ = self?.peers.removeValue(forKey: identifier)
                    }
                }
                if operation?.isCancelled == true { return }
                do {
                    try peer.start()
                    handler(peer)
                } catch {
                    NSLog("Shared database: connection from %@ failed: %@", peer.address, String(describing: error))
                }
            }
        }
        workers.addOperation(operation)
    }

    private static func posixCode(_ error: Error) -> Int32 {
        if let error = error as? NWError, case .posix(let code) = error { return code.rawValue }
        if let error = error as? POSIXError { return error.code.rawValue }
        return 0
    }

    deinit {
        listener?.stateUpdateHandler = nil
        listener?.newConnectionHandler = nil
        listener?.cancel()
        workers.cancelAllOperations()
        for peer in peers.values { peer.cancel() }
    }
}

/// One accepted connection, used synchronously by the one handler that owns it (#615).
///
/// The handler blocks in `receiveData`, `writeData` and `finish` while the network callbacks, on a queue of
/// their own, fill in the result. Each wait ends by `idleTimeout` of monotonic time without progress, by
/// the connection failing, or by `cancel()`. Receives take at most `chunkSize` bytes. `writeData` sends in
/// pieces of `sendPieceSize`, without copying, and waits for each to be processed before the next, so a
/// slow reader holds back the writer instead of a growing buffer, and a long answer times out only when
/// a piece makes no progress. Waiting on every 128 KiB piece instead cost the shared-database fetch
/// about half again its time per MiB in the #615 campaign.
@objc(HorosDatabasePeer)
public final class HorosDatabasePeer: NSObject {
    @objc public let address: String
    private static let networkQueue = DispatchQueue(label: "org.horosproject.database-server-io")
    @objc public static let sendPieceSize = 8 << 20
    private let chunkSize: Int
    private let idleTimeout: TimeInterval
    private let connection: NWConnection
    private let condition = NSCondition()
    // Guarded by condition.
    private var failure: Error?
    private var ready = false
    private var sent = false
    private var received: (Data?, Bool)?
    // Only the handler reads and writes this.
    private var remoteFinished = false

    init(connection: NWConnection, chunkSize: Int, idleTimeout: TimeInterval) {
        self.connection = connection
        self.chunkSize = chunkSize
        self.idleTimeout = idleTimeout
        var host = String(describing: connection.endpoint)
        if case .hostPort(let endpointHost, _) = connection.endpoint {
            switch endpointHost {
            case .ipv4(let address): host = "\(address)"
            case .ipv6(let address): host = "\(address)"
            default: host = String(describing: endpointHost)
            }
        }
        // The textual host without an interface suffix, as N2ConnectionListener reported it.
        address = host.split(separator: "%").first.map(String.init) ?? host
        super.init()
    }

    func start() throws {
        condition.lock()
        let cancelled = failure != nil
        condition.unlock()
        guard !cancelled else { throw POSIXError(.ECANCELED) }
        connection.stateUpdateHandler = { [weak self] state in
            guard let self else { return }
            self.condition.lock()
            defer { self.condition.unlock() }
            switch state {
            case .ready: self.ready = true
            case .failed(let error): self.failure = error
            case .cancelled: if self.failure == nil { self.failure = POSIXError(.ECANCELED) }
            default: break
            }
            self.condition.broadcast()
        }
        connection.start(queue: Self.networkQueue)
        _ = try wait { ready ? true : nil }
    }

    /// The next bytes from the client; empty once the client has finished sending.
    @objc(receiveDataWithError:)
    public func receiveData() throws -> Data {
        try receiveNext() ?? Data()
    }

    /// Appends the next bytes from the client to `buffer`, where a request is parsed, without an
    /// intermediate object; appends nothing once the client has finished sending.
    @objc(appendReceivedDataTo:error:)
    public func appendReceivedData(to buffer: NSMutableData) throws {
        guard let data = try receiveNext(), !data.isEmpty else { return }
        data.withUnsafeBytes { raw in
            if let base = raw.baseAddress { buffer.append(base, length: raw.count) }
        }
    }

    private func receiveNext() throws -> Data? {
        if remoteFinished { return nil }
        condition.lock()
        received = nil
        condition.unlock()
        connection.receive(minimumIncompleteLength: 1, maximumLength: chunkSize) { [weak self] data, _, complete, error in
            guard let self else { return }
            self.condition.lock()
            if let error { self.failure = error }
            self.received = (data, complete)
            self.condition.broadcast()
            self.condition.unlock()
        }
        let (data, complete) = try wait { received }
        if complete { remoteFinished = true }
        return data
    }

    @objc(writeData:error:)
    public func writeData(_ data: Data) throws {
        var offset = data.startIndex
        while offset < data.endIndex {
            let end = min(offset + Self.sendPieceSize, data.endIndex)
            try autoreleasepool { try send(data[offset..<end], final: false) }
            offset = end
        }
    }

    /// Ends the response: the client reads end of stream once everything written has gone.
    @objc(finishWithError:)
    public func finish() throws {
        try send(nil, final: true)
    }

    private func send(_ data: Data?, final: Bool) throws {
        condition.lock()
        sent = false
        condition.unlock()
        connection.send(content: data, contentContext: final ? .finalMessage : .defaultMessage, isComplete: true,
                        completion: .contentProcessed { [weak self] error in
            guard let self else { return }
            self.condition.lock()
            if let error { self.failure = error }
            self.sent = true
            self.condition.broadcast()
            self.condition.unlock()
        })
        _ = try wait { sent ? true : nil }
    }

    /// Wakes a waiting handler with a cancellation and closes the connection.
    @objc public func cancel() {
        condition.lock()
        if failure == nil { failure = POSIXError(.ECANCELED) }
        condition.broadcast()
        condition.unlock()
        connection.cancel()
    }

    private func wait<Value>(_ result: () -> Value?) throws -> Value {
        let deadline = ProcessInfo.processInfo.systemUptime + idleTimeout
        condition.lock()
        defer { condition.unlock() }
        while true {
            if let failure { throw failure }
            if let value = result() { return value }
            let remaining = deadline - ProcessInfo.processInfo.systemUptime
            guard remaining > 0 else { throw POSIXError(.ETIMEDOUT) }
            _ = condition.wait(until: Date(timeIntervalSinceNow: min(remaining, 1)))
        }
    }
}
