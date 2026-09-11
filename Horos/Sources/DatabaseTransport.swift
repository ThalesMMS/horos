import Foundation
import Network

/// The shared-database request client (#607).
///
/// Each request used to get its own `NSThread` and its own run loop: the thread
/// ran `NSRunLoop` in one-second slices while an `N2Connection` filled a buffer,
/// and the caller blocked on a condition lock. Around it sat a five-attempt
/// retry that replayed *any* request, including the ones that change the remote
/// database or that have already written local files.
///
/// This is the same protocol on `NWConnection`: the six-byte command, the
/// integer order, the archives and the end-of-response-by-close are untouched.
/// What changes is how the bytes move — bounded sends and receives on one
/// queue, no run loop, no thread per request — and what happens when something
/// goes wrong: a partial response is an error, never a short success.
@objc(HorosDatabaseTransport)
public final class DatabaseTransport: NSObject {
    /// A streaming consumer: it is handed everything buffered so far and
    /// returns how many bytes it took, or -1 with an error. Called on the
    /// calling thread, never on the network queue, so the existing
    /// Objective-C handlers keep their threading assumptions.
    public typealias Receiver = (Data?, AutoreleasingUnsafeMutablePointer<NSError?>) -> Int

    /// The idle timeout of the legacy contract. A request that has heard
    /// nothing for this long fails; it never waits forever.
    @objc public static let idleTimeout: TimeInterval = 45
    @objc public static let chunkSize = 128 * 1024

    @objc(sendRequest:toHost:port:receiving:cancelled:error:)
    public static func sendRequest(_ request: Data, toHost host: String, port: Int,
                                   receiving: Receiver?, cancelled: @escaping () -> Bool) throws -> Data {
        guard !host.isEmpty, let number = UInt16(exactly: port), number != 0,
              let endpointPort = NWEndpoint.Port(rawValue: number) else {
            throw error("Invalid shared-database address or port.")
        }
        let session = Session(host: host, port: endpointPort, cancelled: cancelled)
        defer { session.cancel() }
        try session.start()
        try session.send(request)

        var buffer = Data()
        while true {
            let finished: Bool = try autoreleasepool {
                let (data, complete) = try session.receive()
                if let data, !data.isEmpty {
                    buffer.append(data)
                    if let receiving {
                        let consumed = try consume(buffer, using: receiving)
                        buffer.removeFirst(consumed)
                        // What is left is an incomplete header. A response whose
                        // header never completes must not grow without bound.
                        guard buffer.count <= chunkSize else {
                            throw error("The shared-database response contains an oversized header.")
                        }
                    }
                }
                if complete {
                    if let receiving {
                        guard buffer.isEmpty else {
                            throw error("The shared-database response ended inside a header.")
                        }
                        _ = try consume(nil, using: receiving)
                    }
                    return true
                }
                guard let data, !data.isEmpty else {
                    throw error("The shared-database connection returned no data before completion.")
                }
                return false
            }
            if finished { return buffer }
        }
    }

    private static func consume(_ data: Data?, using receiver: Receiver) throws -> Int {
        var failure: NSError?
        let count = receiver(data, &failure)
        if let failure { throw failure }
        guard count >= 0, count <= (data?.count ?? 0) else {
            throw error("Invalid shared-database response consumption.")
        }
        return count
    }

    static func error(_ description: String) -> NSError {
        NSError(domain: "HorosDatabaseTransport", code: 1, userInfo: [NSLocalizedDescriptionKey: description])
    }

    private final class Session {
        private static let queue = DispatchQueue(label: "org.horosproject.database-client")
        let connection: NWConnection
        private let cancelled: () -> Bool
        private let condition = NSCondition()
        // Every field below is written on the network queue and read by the
        // calling thread, always under `condition`.
        private var ready = false
        private var sent = false
        private var received: (Data?, Bool)?
        private var failure: Error?
        private var closed = false

        init(host: String, port: NWEndpoint.Port, cancelled: @escaping () -> Bool) {
            self.cancelled = cancelled
            let tcp = NWProtocolTCP.Options()
            tcp.noDelay = true
            // The legacy shared-database protocol is plaintext, as it always was.
            // Nothing here promises otherwise, and no TLS caller is routed here.
            connection = NWConnection(host: NWEndpoint.Host(host), port: port, using: NWParameters(tls: nil, tcp: tcp))
        }

        /// Exactly once, whatever happened.
        func cancel() {
            condition.lock()
            let alreadyClosed = closed
            closed = true
            condition.unlock()
            if !alreadyClosed {
                connection.stateUpdateHandler = nil
                connection.cancel()
            }
        }

        func start() throws {
            connection.stateUpdateHandler = { [weak self] state in
                guard let self else { return }
                self.condition.lock()
                defer { self.condition.unlock() }
                switch state {
                case .ready: self.ready = true
                case .failed(let error): self.failure = error
                case .cancelled: self.failure = URLError(.cancelled)
                case .waiting(let error):
                    // NWConnection waits and retries when a host refuses or is
                    // unreachable. The legacy client failed at once, and the
                    // callers already decide when to try again: a refusal must
                    // not consume the whole idle timeout.
                    if !self.ready { self.failure = error }
                default: break
                }
                self.condition.broadcast()
            }
            connection.start(queue: Self.queue)
            _ = try wait { ready ? true : nil }
        }

        /// Bounded sends: the next chunk goes only after the previous one was
        /// processed, so a large request cannot queue without limit.
        func send(_ data: Data) throws {
            guard !data.isEmpty else { return }
            for offset in stride(from: 0, to: data.count, by: DatabaseTransport.chunkSize) {
                condition.lock(); sent = false; condition.unlock()
                let end = min(data.count, offset + DatabaseTransport.chunkSize)
                connection.send(content: data.subdata(in: offset..<end), completion: .contentProcessed { [weak self] error in
                    guard let self else { return }
                    self.condition.lock()
                    if let error { self.failure = error }
                    self.sent = true
                    self.condition.broadcast()
                    self.condition.unlock()
                })
                _ = try wait { sent ? true : nil }
            }
        }

        func receive() throws -> (Data?, Bool) {
            condition.lock(); received = nil; condition.unlock()
            connection.receive(minimumIncompleteLength: 1, maximumLength: DatabaseTransport.chunkSize) { [weak self] data, _, complete, error in
                guard let self else { return }
                self.condition.lock()
                if let error { self.failure = error }
                self.received = (data, complete)
                self.condition.broadcast()
                self.condition.unlock()
            }
            return try wait { received }
        }

        /// Waits for one callback, and gives up on cancellation, on failure or
        /// after the idle timeout. Never an unbounded wait.
        private func wait<Value>(_ result: () -> Value?) throws -> Value {
            let deadline = ProcessInfo.processInfo.systemUptime + DatabaseTransport.idleTimeout
            while true {
                if cancelled() { throw URLError(.cancelled) }
                condition.lock()
                defer { condition.unlock() }
                if let failure { throw failure }
                if let value = result() { return value }
                guard ProcessInfo.processInfo.systemUptime < deadline else { throw URLError(.timedOut) }
                _ = condition.wait(until: Date(timeIntervalSinceNow: 0.1))
            }
        }
    }
}

/// Which shared-database commands may be sent again by the client itself.
///
/// The old client replayed every failed request up to five times. A read that
/// answers the same thing twice is safe to repeat once its partial local state
/// has been discarded; a command that changes the remote database, or that
/// uploads, is not — repeating it can duplicate what it did. A failed one is
/// reported to the operator instead.
@objc(HorosSharedDatabaseCommand)
public final class SharedDatabaseCommand: NSObject {
    /// Reads: version, capability, index, sizes, file fetches.
    @objc public static let idempotentCommands: Set<String> = [
        "DBVER", "ISPWD", "AUTHV", "PASWD", "DBSIZ", "DATAB", "VERSI", "GETDI", "MFILE", "DICOM",
    ]
    /// Mutations: album membership, key images and comments, incoming files.
    @objc public static let mutatingCommands: Set<String> = ["SETVA", "NEWMS", "DCMSE"]

    /// The six-byte command at the head of a request, or nil.
    @objc(commandInRequest:)
    public static func command(in request: Data) -> String? {
        guard request.count >= 6, request[request.startIndex + 5] == 0 else { return nil }
        let letters = request.prefix(5)
        guard letters.allSatisfy({ $0 >= 0x20 && $0 <= 0x7e }) else { return nil }
        return String(decoding: letters, as: UTF8.self)
    }

    /// Whether the client may send this request again on its own.
    @objc(isRetryableRequest:)
    public static func isRetryable(_ request: Data) -> Bool {
        guard let command = command(in: request) else { return false }
        if mutatingCommands.contains(command) { return false }
        return idempotentCommands.contains(command)
    }

    /// What the operator is told about a command that failed and will not be
    /// repeated by the client.
    @objc(actionRequiredForRequest:)
    public static func actionRequired(for request: Data) -> String? {
        guard let command = command(in: request), mutatingCommands.contains(command) else { return nil }
        switch command {
        case "SETVA":
            return NSLocalizedString("The change was not applied to the shared database. Check the other computer and make it again.", comment: "")
        case "NEWMS", "DCMSE":
            return NSLocalizedString("The files were not sent to the shared database. Check the other computer and send them again.", comment: "")
        default:
            return NSLocalizedString("The shared-database operation did not complete. Check the other computer before repeating it.", comment: "")
        }
    }
}
