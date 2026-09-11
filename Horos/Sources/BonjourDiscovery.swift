import Foundation
import Network
import dnssd

/// Native Bonjour discovery, resolution and publication for the host (#606).
///
/// The Sources list browsed with two `NSNetServiceBrowser`s and resolved with
/// `NSNetService`. Both work, and both hide what this issue is about: a peer
/// reachable on Wi-Fi and on Ethernet arrives as two observations, an interface
/// going away removes a row for a peer still present elsewhere, and a resolution
/// that answers late can overwrite the current address of a peer that has since
/// changed port.
///
/// `HorosBonjourBrowser` browses with `NWBrowser` and hands the existing
/// consumers **one service per name/type/domain**, with every interface that
/// observed it, updating that service in place when its interfaces or TXT
/// change. `HorosBonjourService` is an `NSNetService` subclass whose resolution
/// is `DNSServiceResolve` + `DNSServiceGetAddrInfo`: numeric addresses, no
/// connection to the advertised listener, IPv4 preferred within what arrived,
/// IPv6 link-local carrying its scope, and address/host/port/TXT committed as
/// one snapshot under a generation. Subclassing keeps every caller typed on
/// `NSNetService` — including the DCM framework's public API and plugins —
/// working unchanged.
///
/// `HorosBonjourAdvertisement` publishes with `DNSServiceRegister`, refuses a
/// port no listener is on, and retries only transient daemon failures.

// MARK: - Resolution

@objc(HorosBonjourService)
public final class BonjourService: NetService {
    public struct Address: Hashable {
        public let host: String
        public let isIPv4: Bool
        public let socketAddress: Data
    }

    private struct Snapshot {
        let addresses: [Data]
        let hostName: String
        let port: Int
        let txt: Data
    }

    private final class Lookup {
        weak var owner: BonjourService?
        var reference: DNSServiceRef?
        var hostName = ""
        var port = 0
        var txt = Data()
        var addresses: Set<Address> = []

        func close() {
            if let reference {
                self.reference = nil
                DNSServiceRefDeallocate(reference)
            }
        }
    }

    /// Every interface index that observed this service. A resolution is asked
    /// on each: a peer answering on one interface must not wait for another.
    @objc public var interfaceIndexes: [NSNumber] = []

    private let lock = NSLock()
    private var snapshot: Snapshot?
    private var lookups: [Lookup] = []
    private var generation: UInt = 0
    private var timeout: DispatchWorkItem?
    private var completionQueued = false

    /// Consumers read a resolved service from transfer workers while discovery
    /// refreshes it on the main thread, so the snapshot is read under a lock.
    private var currentSnapshot: Snapshot? { lock.lock(); defer { lock.unlock() }; return snapshot }

    @objc public override var addresses: [Data]? { currentSnapshot?.addresses }
    @objc public override var hostName: String? { currentSnapshot?.hostName }
    @objc public override var port: Int { currentSnapshot?.port ?? -1 }
    @objc public override func txtRecordData() -> Data? { currentSnapshot?.txt }
    /// The numeric address this service resolved to, for diagnostics.
    @objc public var resolvedAddress: String? {
        guard let data = currentSnapshot?.addresses.first else { return nil }
        return Self.numericHost(of: data)
    }
    @objc public var isResolved: Bool { currentSnapshot != nil }

    public override var description: String {
        "\(name) \(type) \(domain) \(resolvedAddress ?? "unresolved"):\(port)"
    }

    public override func resolve(withTimeout interval: TimeInterval) {
        precondition(Thread.isMainThread)
        stop()
        let currentGeneration = generation
        let deadline = DispatchWorkItem { [weak self] in
            guard let self, self.generation == currentGeneration else { return }
            self.fail(DNSServiceErrorType(kDNSServiceErr_Timeout))
        }
        timeout = deadline
        DispatchQueue.main.asyncAfter(deadline: .now() + (interval.isFinite && interval > 0 ? interval : 5), execute: deadline)

        let indexes = interfaceIndexes.isEmpty ? [UInt32(0)] : interfaceIndexes.map { $0.uint32Value }.sorted()
        lookups = indexes.map { _ in
            let lookup = Lookup()
            lookup.owner = self
            return lookup
        }
        for (index, lookup) in zip(indexes, lookups) {
            guard generation == currentGeneration else { return }
            var reference: DNSServiceRef?
            let error = DNSServiceResolve(&reference, kDNSServiceFlagsIncludeP2P, index, name, type, domain,
                                          { reference, _, interface, error, _, host, port, length, txt, context in
                guard let context else { return }
                let lookup = Unmanaged<Lookup>.fromOpaque(context).takeUnretainedValue()
                guard let owner = lookup.owner, owner.isCurrent(lookup, reference: reference) else { return }
                guard error == kDNSServiceErr_NoError else {
                    owner.failed(lookup, error: error)
                    return
                }
                guard let host, port != 0, length == 0 || txt != nil else {
                    owner.failed(lookup, error: DNSServiceErrorType(kDNSServiceErr_Invalid))
                    return
                }
                lookup.hostName = String(cString: host)
                lookup.port = Int(UInt16(bigEndian: port))
                lookup.txt = txt.map { Data(bytes: $0, count: Int(length)) } ?? Data()
                lookup.close()
                owner.resolveAddresses(lookup, interface: interface)
            }, Unmanaged.passUnretained(lookup).toOpaque())
            schedule(reference, for: lookup, error: error)
        }
    }

    public override func stop() {
        precondition(Thread.isMainThread)
        generation &+= 1
        timeout?.cancel()
        timeout = nil
        completionQueued = false
        for lookup in lookups { lookup.close() }
        lookups.removeAll()
        // The last complete snapshot stays readable: a refresh that fails must
        // not blank an address the consumers are already using.
    }

    private func isCurrent(_ lookup: Lookup, reference: DNSServiceRef?) -> Bool {
        timeout != nil && lookups.contains { $0 === lookup } && lookup.reference == reference
    }

    private func schedule(_ reference: DNSServiceRef?, for lookup: Lookup, error: DNSServiceErrorType) {
        guard error == kDNSServiceErr_NoError, let reference else {
            failed(lookup, error: error == kDNSServiceErr_NoError ? DNSServiceErrorType(kDNSServiceErr_Unknown) : error)
            return
        }
        lookup.reference = reference
        let scheduling = DNSServiceSetDispatchQueue(reference, .main)
        if scheduling != kDNSServiceErr_NoError { failed(lookup, error: scheduling) }
    }

    private func resolveAddresses(_ lookup: Lookup, interface: UInt32) {
        var reference: DNSServiceRef?
        let protocols = DNSServiceProtocol(kDNSServiceProtocol_IPv4 | kDNSServiceProtocol_IPv6)
        let error = DNSServiceGetAddrInfo(&reference, kDNSServiceFlagsIncludeP2P, interface, protocols, lookup.hostName,
                                          { reference, flags, interface, error, _, address, _, context in
            guard let context else { return }
            let lookup = Unmanaged<Lookup>.fromOpaque(context).takeUnretainedValue()
            guard let owner = lookup.owner, owner.isCurrent(lookup, reference: reference) else { return }
            // A missing A record is not a failed AAAA lookup, and the reverse.
            if error == kDNSServiceErr_NoSuchRecord {
                owner.queueCompletion()
                return
            }
            guard error == kDNSServiceErr_NoError else {
                owner.failed(lookup, error: error)
                return
            }
            if let address, let value = BonjourService.address(from: address, interface: interface) {
                if flags & UInt32(kDNSServiceFlagsAdd) != 0 { lookup.addresses.insert(value) }
                else { lookup.addresses.remove(value) }
            }
            if flags & UInt32(kDNSServiceFlagsMoreComing) == 0 { owner.queueCompletion() }
        }, Unmanaged.passUnretained(lookup).toOpaque())
        schedule(reference, for: lookup, error: error)
    }

    private func queueCompletion() {
        guard !completionQueued else { return }
        completionQueued = true
        let currentGeneration = generation
        DispatchQueue.main.async { [weak self] in
            guard let self, self.generation == currentGeneration, self.timeout != nil else { return }
            self.completionQueued = false
            let candidates = self.lookups.flatMap { lookup in lookup.addresses.map { (lookup, $0) } }
            // IPv4 first within what arrived, without waiting for a family or an
            // interface that may never answer.
            let ordered = candidates.sorted {
                if $0.1.isIPv4 != $1.1.isIPv4 { return $0.1.isIPv4 }
                return $0.1.host < $1.1.host
            }
            guard let first = ordered.first else { return }
            let snapshot = Snapshot(addresses: ordered.map(\.1.socketAddress), hostName: first.0.hostName,
                                    port: first.0.port, txt: first.0.txt)
            self.stop()
            self.lock.lock(); self.snapshot = snapshot; self.lock.unlock()
            self.delegate?.netServiceDidResolveAddress?(self)
        }
    }

    private func failed(_ lookup: Lookup, error: DNSServiceErrorType) {
        lookup.close()
        lookups.removeAll { $0 === lookup }
        if lookups.isEmpty { fail(error) }
    }

    private func fail(_ error: DNSServiceErrorType) {
        stop()
        // The shape NSNetService's delegates already read: an error domain and a code.
        delegate?.netService?(self, didNotResolve: [
            NetService.errorDomain: NSNumber(value: Int(NetService.ErrorCode.unknownError.rawValue)),
            NetService.errorCode: NSNumber(value: Int(error))])
    }

    /// A sockaddr as the host's consumers expect it, with an IPv6 link-local
    /// address carrying the scope that makes it usable.
    public static func address(from address: UnsafePointer<sockaddr>, interface: UInt32) -> Address? {
        let family = Int32(address.pointee.sa_family)
        let size: Int
        switch family {
        case AF_INET: size = MemoryLayout<sockaddr_in>.size
        case AF_INET6: size = MemoryLayout<sockaddr_in6>.size
        default: return nil
        }
        guard Int(address.pointee.sa_len) >= size else { return nil }
        var storage = sockaddr_storage()
        withUnsafeMutablePointer(to: &storage) { UnsafeMutableRawPointer($0).copyMemory(from: address, byteCount: size) }
        if family == AF_INET6 {
            withUnsafeMutablePointer(to: &storage) {
                $0.withMemoryRebound(to: sockaddr_in6.self, capacity: 1) { value in
                    let bytes = withUnsafeBytes(of: value.pointee.sin6_addr) { Array($0) }
                    if bytes[0] == 0xfe && bytes[1] & 0xc0 == 0x80 && value.pointee.sin6_scope_id == 0 {
                        value.pointee.sin6_scope_id = interface
                    }
                }
            }
        }
        let data = withUnsafeBytes(of: storage) { Data($0.prefix(size)) }
        guard let host = numericHost(of: data) else { return nil }
        return Address(host: host, isIPv4: family == AF_INET, socketAddress: data)
    }

    /// The numeric form of a sockaddr, never a name lookup.
    @objc(numericHostOfSocketAddress:)
    public static func numericHost(of data: Data) -> String? {
        guard data.count >= MemoryLayout<sockaddr>.size else { return nil }
        var host = [CChar](repeating: 0, count: Int(NI_MAXHOST))
        let result: Int32 = data.withUnsafeBytes { bytes in
            guard let base = bytes.baseAddress?.assumingMemoryBound(to: sockaddr.self) else { return -1 }
            return getnameinfo(base, socklen_t(data.count), &host, socklen_t(host.count), nil, 0, NI_NUMERICHOST)
        }
        guard result == 0 else { return nil }
        return String(cString: host)
    }

    /// TXT record parsing that keeps binary and empty values, for callers that
    /// want it without `NSNetService`'s dictionary conversion.
    @objc(txtDictionaryFromTXTRecordData:)
    public static func txtDictionary(fromTXTRecord data: Data?) -> [String: Data] {
        guard let data, !data.isEmpty, let length = UInt16(exactly: data.count) else { return [:] }
        return data.withUnsafeBytes { bytes in
            var result: [String: Data] = [:]
            for index in 0..<TXTRecordGetCount(length, bytes.baseAddress) {
                var key = [CChar](repeating: 0, count: 256)
                var valueLength: UInt8 = 0
                var value: UnsafeRawPointer?
                let error = TXTRecordGetItemAtIndex(length, bytes.baseAddress, index, UInt16(key.count), &key, &valueLength, &value)
                guard error == kDNSServiceErr_NoError else { return [:] }
                result[String(cString: key)] = value.map { Data(bytes: $0, count: Int(valueLength)) } ?? Data()
            }
            return result
        }
    }

    deinit {
        timeout?.cancel()
        for lookup in lookups { lookup.close() }
    }
}

// MARK: - Discovery

@objc public protocol HorosBonjourBrowserDelegate: AnyObject {
    @objc optional func horosBonjourBrowserWillSearch(_ browser: BonjourBrowser)
    @objc optional func horosBonjourBrowserDidStopSearch(_ browser: BonjourBrowser)
    @objc(horosBonjourBrowser:didFindService:)
    optional func horosBonjourBrowser(_ browser: BonjourBrowser, didFind service: BonjourService)
    @objc(horosBonjourBrowser:didRemoveService:)
    optional func horosBonjourBrowser(_ browser: BonjourBrowser, didRemove service: BonjourService)
    /// The same peer, with different interfaces or a different TXT record. The
    /// row it belongs to is refreshed, never removed and added again.
    @objc(horosBonjourBrowser:didUpdateService:)
    optional func horosBonjourBrowser(_ browser: BonjourBrowser, didUpdate service: BonjourService)
    @objc(horosBonjourBrowser:didNotSearch:)
    optional func horosBonjourBrowser(_ browser: BonjourBrowser, didNotSearch error: [String: Any])
}

@objc(HorosBonjourBrowser)
public final class BonjourBrowser: NSObject {
    /// One entry per name/type/domain, whatever the interface. Bonjour compares
    /// names without case, so the key is folded — but the service keeps the name
    /// exactly as advertised: it is what the user sees and what DNSServiceResolve
    /// is given.
    struct Identity: Hashable {
        let name: String
        let type: String
        let domain: String
        init(name: String, type: String, domain: String) {
            self.name = name.lowercased(); self.type = type.lowercased(); self.domain = domain.lowercased()
        }
    }

    @objc public weak var delegate: HorosBonjourBrowserDelegate?
    private var browser: NWBrowser?
    private var generation: UInt = 0
    private var announcedSearch = false
    /// The whole browse result per identity, not just its interfaces: a TXT
    /// record that changed with the same interfaces is still a change the
    /// consumers have to see.
    private var discovered: [Identity: (service: BonjourService, results: Set<NWBrowser.Result>)] = [:]

    @objc public override init() { super.init() }

    @objc public var discoveredServices: [BonjourService] { discovered.values.map(\.service) }
    @objc public var isSearching: Bool { browser != nil }

    @objc(searchForServicesOfType:inDomain:)
    public func searchForServices(ofType type: String, inDomain domain: String) {
        precondition(Thread.isMainThread)
        stop()
        let currentGeneration = generation
        let parameters = NWParameters.tcp
        parameters.includePeerToPeer = true
        let browser = NWBrowser(for: .bonjourWithTXTRecord(type: type, domain: domain.isEmpty ? nil : domain), using: parameters)
        self.browser = browser
        browser.stateUpdateHandler = { [weak self] state in
            guard let self, self.generation == currentGeneration, self.browser != nil else { return }
            switch state {
            case .ready:
                self.announceSearchIfNeeded()
            case .waiting(let error):
                // An interface that went away can come back on this browser.
                // Keep what was found; the Sources liveness policy decides.
                NSLog("Horos Bonjour waiting for %@: %@", type, String(describing: error))
            case .failed(let error):
                self.fail(error)
            default:
                break
            }
        }
        browser.browseResultsChangedHandler = { [weak self] results, _ in
            guard let self, self.generation == currentGeneration, self.browser != nil else { return }
            self.announceSearchIfNeeded()
            self.apply(results, generation: currentGeneration)
        }
        browser.start(queue: .main)
    }

    @objc public func stop() {
        precondition(Thread.isMainThread)
        let wasSearching = browser != nil
        generation &+= 1
        browser?.stateUpdateHandler = nil
        browser?.browseResultsChangedHandler = nil
        browser?.cancel()
        browser = nil
        announcedSearch = false
        let previous = discovered
        discovered.removeAll()
        for entry in previous.values {
            entry.service.delegate = nil
            entry.service.stop()
        }
        if wasSearching { delegate?.horosBonjourBrowserDidStopSearch?(self) }
    }

    private func announceSearchIfNeeded() {
        guard !announcedSearch else { return }
        announcedSearch = true
        delegate?.horosBonjourBrowserWillSearch?(self)
    }

    /// The whole snapshot decides, never a single interface's removal event:
    /// losing Wi-Fi must not remove a peer still answering on Ethernet.
    private func apply(_ results: Set<NWBrowser.Result>, generation currentGeneration: UInt) {
        var grouped: [Identity: Set<NWBrowser.Result>] = [:]
        var advertised: [Identity: (name: String, type: String, domain: String)] = [:]
        for result in results {
            guard case let .service(name, type, domain, _) = result.endpoint else { continue }
            let identity = Identity(name: name, type: type, domain: domain)
            grouped[identity, default: []].insert(result)
            advertised[identity] = (name, type, domain)
        }

        for identity in Array(discovered.keys) where grouped[identity] == nil {
            guard generation == currentGeneration else { return }
            guard let removed = discovered.removeValue(forKey: identity) else { continue }
            removed.service.stop()
            delegate?.horosBonjourBrowser?(self, didRemove: removed.service)
            removed.service.delegate = nil
        }
        for (identity, observations) in grouped {
            guard generation == currentGeneration else { return }
            if let existing = discovered[identity] {
                guard existing.results != observations else { continue }
                existing.service.interfaceIndexes = Self.interfaceIndexes(in: observations)
                discovered[identity] = (existing.service, observations)
                delegate?.horosBonjourBrowser?(self, didUpdate: existing.service)
            } else {
                let names = advertised[identity] ?? (identity.name, identity.type, identity.domain)
                let service = BonjourService(domain: names.domain, type: names.type, name: names.name)
                service.interfaceIndexes = Self.interfaceIndexes(in: observations)
                discovered[identity] = (service, observations)
                delegate?.horosBonjourBrowser?(self, didFind: service)
            }
        }
    }

    /// Every interface that observed this service, including the one named in
    /// the endpoint itself.
    static func interfaceIndexes(in results: Set<NWBrowser.Result>) -> [NSNumber] {
        var indexes = Set<UInt32>()
        for result in results {
            indexes.formUnion(result.interfaces.compactMap { UInt32(exactly: $0.index) })
            if case let .service(_, _, _, interface) = result.endpoint, let interface,
               let index = UInt32(exactly: interface.index) {
                indexes.insert(index)
            }
        }
        return indexes.sorted().map { NSNumber(value: $0) }
    }

    private func fail(_ error: NWError) {
        let nsError = error as NSError
        let currentGeneration = generation
        apply([], generation: currentGeneration)
        guard generation == currentGeneration else { return }
        delegate?.horosBonjourBrowser?(self, didNotSearch: [
            "domain": nsError.domain, "code": nsError.code,
            NSLocalizedDescriptionKey: nsError.localizedDescription])
    }

    deinit {
        browser?.stateUpdateHandler = nil
        browser?.browseResultsChangedHandler = nil
        browser?.cancel()
        let services = discovered.values.map(\.service)
        let cleanup = { for service in services { service.delegate = nil; service.stop() } }
        if Thread.isMainThread { cleanup() } else { DispatchQueue.main.async(execute: cleanup) }
    }
}

// MARK: - Publication

@objc(HorosBonjourAdvertisement)
public final class BonjourAdvertisement: NSObject {
    private final class Registration {
        weak var owner: BonjourAdvertisement?
        var reference: DNSServiceRef?
        func close() {
            if let reference { self.reference = nil; DNSServiceRefDeallocate(reference) }
        }
    }

    private let requestedName: String
    /// The name the daemon gave the service: it renames on a collision, and the
    /// self-filter compares against what was actually published.
    @objc public private(set) var name: String
    @objc public let type: String
    @objc public let port: Int
    @objc public private(set) var txtRecord: [String: String] = [:]
    @objc public private(set) var isPublished = false

    private var txtData = Data()
    private var registration: Registration?
    private var active = false
    private var generation: UInt = 0
    private var retry: DispatchWorkItem?
    private var retryDelay: TimeInterval = 1

    @objc(initWithName:type:port:)
    public init(name: String, type: String, port: Int) {
        requestedName = name
        self.name = name
        self.type = type
        self.port = port
        super.init()
    }

    /// Whether a port may be advertised at all: only a real, non-privileged
    /// listener port. A service created while sharing was off used to keep
    /// port zero forever.
    @objc(isPublishablePort:)
    public static func isPublishable(port: Int) -> Bool { port > 0 && port <= 65535 }

    @objc(publishWithTXTRecord:)
    public func publish(txtRecord values: [String: String]) {
        precondition(Thread.isMainThread)
        guard Self.isPublishable(port: port) else {
            NSLog("Horos Bonjour refuses to publish %@ %@ on port %ld", name, type, port)
            return
        }
        let data: Data
        do { data = try Self.encodeTXTRecord(values) }
        catch {
            NSLog("Horos Bonjour invalid TXT record for %@ %@:%ld: %@", name, type, port, error as NSError)
            return
        }
        let changed = txtData != data
        txtRecord = values
        txtData = data
        active = true
        if let reference = registration?.reference {
            guard changed else { return }
            let error = data.withUnsafeBytes { DNSServiceUpdateRecord(reference, nil, 0, UInt16(data.count), $0.baseAddress, 0) }
            if error != kDNSServiceErr_NoError { failed(error) }
        } else if retry == nil {
            register()
        }
    }

    @objc public func stop() {
        precondition(Thread.isMainThread)
        active = false
        isPublished = false
        generation &+= 1
        retry?.cancel(); retry = nil
        registration?.close(); registration = nil
        retryDelay = 1
    }

    private func register() {
        guard active, registration == nil else { return }
        guard let wirePort = UInt16(exactly: port), wirePort > 0 else {
            failed(DNSServiceErrorType(kDNSServiceErr_BadParam))
            return
        }
        let pending = Registration()
        pending.owner = self
        var reference: DNSServiceRef?
        let error = txtData.withUnsafeBytes { bytes in
            DNSServiceRegister(&reference, 0, 0, requestedName, type, nil, nil, wirePort.bigEndian,
                               UInt16(txtData.count), bytes.baseAddress,
                               { reference, flags, error, name, _, _, context in
                guard let context else { return }
                let pending = Unmanaged<Registration>.fromOpaque(context).takeUnretainedValue()
                guard let owner = pending.owner, owner.registration === pending, pending.reference == reference else { return }
                if error != kDNSServiceErr_NoError {
                    owner.failed(error)
                } else if flags & UInt32(kDNSServiceFlagsAdd) != 0, let name {
                    owner.name = String(cString: name)
                    owner.isPublished = true
                    owner.retryDelay = 1
                    NSLog("Horos Bonjour service published: %@ %@:%ld", owner.name, owner.type, owner.port)
                }
            }, Unmanaged.passUnretained(pending).toOpaque())
        }
        guard error == kDNSServiceErr_NoError, let reference else {
            failed(error == kDNSServiceErr_NoError ? DNSServiceErrorType(kDNSServiceErr_Unknown) : error)
            return
        }
        pending.reference = reference
        registration = pending
        let scheduling = DNSServiceSetDispatchQueue(reference, .main)
        if scheduling != kDNSServiceErr_NoError { failed(scheduling) }
    }

    private func failed(_ error: DNSServiceErrorType) {
        registration?.close(); registration = nil
        isPublished = false
        NSLog("Warning: Horos Bonjour service did not publish: %@ %@:%ld DNS-SD error=%d", name, type, port, error)
        // Reconnect to the same API after a daemon failure; never a helper process,
        // and never a retry loop for a configuration or permission error.
        guard active, retry == nil, Self.isTransient(error) else { return }
        let currentGeneration = generation
        let work = DispatchWorkItem { [weak self] in
            guard let self, self.active, self.generation == currentGeneration else { return }
            self.retry = nil
            self.register()
        }
        retry = work
        DispatchQueue.main.asyncAfter(deadline: .now() + retryDelay, execute: work)
        retryDelay = min(retryDelay * 2, 10)
    }

    /// Exposed as Int32: the generated header is imported by sources that do
    /// not import dnssd, and DNSServiceErrorType would not be a type there.
    @objc(isTransientDNSServiceError:)
    public static func isTransient(_ error: Int32) -> Bool {
        switch Int(error) {
        case kDNSServiceErr_ServiceNotRunning, kDNSServiceErr_DefunctConnection, kDNSServiceErr_Transient,
             kDNSServiceErr_NotInitialized, kDNSServiceErr_Timeout, kDNSServiceErr_NoMemory:
            return true
        default:
            return false
        }
    }

    /// DNS-SD TXT encoding with the key/length rules the daemon enforces, so an
    /// invalid record is refused here instead of failing the registration.
    @objc(encodeTXTRecord:error:)
    public static func encodeTXTRecordObjC(_ values: [String: String]) throws -> Data {
        try encodeTXTRecord(values)
    }

    static func encodeTXTRecord(_ values: [String: String]) throws -> Data {
        var record = TXTRecordRef()
        TXTRecordCreate(&record, 0, nil)
        defer { TXTRecordDeallocate(&record) }
        for key in values.keys.sorted() {
            let value = values[key, default: ""]
            guard !key.isEmpty, key.utf8.allSatisfy({ $0 >= 0x20 && $0 <= 0x7e && $0 != 0x3d }),
                  let length = UInt8(exactly: value.utf8.count), key.utf8.count + 1 + value.utf8.count <= 255 else {
                throw NSError(domain: "DNSServiceErrorDomain", code: Int(kDNSServiceErr_BadParam), userInfo: [
                    NSLocalizedDescriptionKey: "TXT record key \(key) or its value cannot be advertised."])
            }
            let error = value.withCString { TXTRecordSetValue(&record, key, length, $0) }
            guard error == kDNSServiceErr_NoError else {
                throw NSError(domain: "DNSServiceErrorDomain", code: Int(error))
            }
        }
        let count = Int(TXTRecordGetLength(&record))
        guard count > 0, let bytes = TXTRecordGetBytesPtr(&record) else { return Data() }
        return Data(bytes: bytes, count: count)
    }

    deinit {
        retry?.cancel()
        if let registration {
            if Thread.isMainThread { registration.close() }
            else { DispatchQueue.main.async { registration.close() } }
        }
    }
}
