import Foundation

/// Why a DICOM association could not be made.
///
/// Every failure to reach a node reported the same sentence. Until this change
/// it was `0000:0001 Illegal parameter` — the association thread's real
/// condition was overwritten one line after it was read — and with that
/// corrected it is `0006:031b Failed to establish association`, which is the
/// same for a closed port, an unknown host name, a firewall dropping the
/// packets, and macOS refusing the application access to the local network.
///
/// The last of those is the one people cannot guess. Since macOS Sequoia an
/// application must be granted **Local Network** access before it can open a
/// connection to another machine on the LAN, and when it is not, the connection
/// fails as if the host were unreachable. Nothing in the DICOM condition says
/// so.
///
/// Prefer an explicit protocol condition. When it does not identify the cause,
/// a separate TCP probe supplies reachability evidence only. This runs after
/// an association has already failed.
@objc(HorosNetworkDiagnosis)
public final class NetworkDiagnosis: NSObject {
    /// Whether an address is one the Local Network privacy gate covers: the
    /// private ranges, link-local, and mDNS names.
    @objc(isLocalNetworkAddress:)
    public static func isLocalNetworkAddress(_ address: String) -> Bool {
        let host = address.lowercased()
        if host.hasSuffix(".local") || host.hasSuffix(".local.") {
            return true
        }
        let parts = host.split(separator: ".").compactMap { Int($0) }
        guard parts.count == 4, parts.allSatisfy({ (0...255).contains($0) }) else {
            // A name we have not resolved. Assume the wider internet, so the
            // local-network advice is not given where it does not apply.
            return false
        }
        switch (parts[0], parts[1]) {
        case (10, _), (192, 168), (169, 254):
            return true
        case (172, 16...31):
            return true
        default:
            return false
        }
    }

    /// The sentence for one `connect()` outcome. `code` is `errno`, or 0 when
    /// the connection succeeded, or -1 when it timed out.
    @objc(explanationForErrno:host:port:isLocalNetwork:)
    public static func explanation(forErrno code: Int32, host: String, port: Int,
                                   isLocalNetwork: Bool) -> String {
        let where_ = "\(host):\(port)"
        let localNetworkAdvice = isLocalNetwork
            ? " On macOS Sequoia and later an application must be granted Local Network access"
                + " before it can reach another machine on the LAN; if it has been denied, the"
                + " connection fails exactly like this. System Settings ▸ Privacy & Security ▸"
                + " Local Network."
            : ""

        switch code {
        case 0:
            return "The port at \(where_) accepted a diagnostic TCP connection. "
                + "This confirms TCP reachability only; it does not establish why the DICOM operation failed."
        case ECONNREFUSED:
            return "Nothing is listening on port \(port) at \(host). The host answered - it "
                + "refused the connection - so this is the port or the node being down, not a "
                + "network permission."
        case EHOSTUNREACH, ENETUNREACH, EHOSTDOWN, ENETDOWN:
            return "There is no route to \(host)." + localNetworkAdvice
        case -1, ETIMEDOUT:
            return "No answer from \(where_) within the time allowed. Something is dropping the "
                + "packets - a firewall, or a host that is not there." + localNetworkAdvice
        case EACCES, EPERM:
            return "The system refused to let this application connect to \(where_)."
                + (isLocalNetwork ? localNetworkAdvice : "")
        case EAI_NONAME_CODE:
            return "The name \(host) could not be resolved. Check the spelling, or use the "
                + "address."
        default:
            return "The connection to \(where_) failed: \(String(cString: strerror(code)))."
                + localNetworkAdvice
        }
    }

    /// A value outside errno's range, used to mean "the name did not resolve".
    static let EAI_NONAME_CODE: Int32 = -2

    /// Try to open a TCP connection, and report why it did not work. Returns 0
    /// on success, `EAI_NONAME_CODE` when the name does not resolve, -1 on
    /// timeout, and otherwise `errno`.
    @objc(probeHost:port:timeout:)
    public static func probe(host: String, port: Int, timeout: TimeInterval) -> Int32 {
        var hints = addrinfo(ai_flags: 0, ai_family: AF_UNSPEC, ai_socktype: SOCK_STREAM,
                             ai_protocol: 0, ai_addrlen: 0, ai_canonname: nil, ai_addr: nil,
                             ai_next: nil)
        var result: UnsafeMutablePointer<addrinfo>?
        guard getaddrinfo(host, String(port), &hints, &result) == 0, let list = result else {
            return EAI_NONAME_CODE
        }
        defer { freeaddrinfo(list) }

        var last: Int32 = EAI_NONAME_CODE
        var candidate: UnsafeMutablePointer<addrinfo>? = list
        while let entry = candidate {
            let descriptor = socket(entry.pointee.ai_family, entry.pointee.ai_socktype,
                                    entry.pointee.ai_protocol)
            if descriptor >= 0 {
                var flags = fcntl(descriptor, F_GETFL, 0)
                flags |= O_NONBLOCK
                _ = fcntl(descriptor, F_SETFL, flags)

                let started = connect(descriptor, entry.pointee.ai_addr,
                                      entry.pointee.ai_addrlen)
                if started == 0 {
                    close(descriptor)
                    return 0
                }
                if errno == EINPROGRESS {
                    var poller = pollfd(fd: descriptor, events: Int16(POLLOUT), revents: 0)
                    let milliseconds = Int32(max(timeout, 0) * 1000)
                    let ready = poll(&poller, 1, milliseconds)
                    if ready > 0 {
                        var error: Int32 = 0
                        var length = socklen_t(MemoryLayout<Int32>.size)
                        getsockopt(descriptor, SOL_SOCKET, SO_ERROR, &error, &length)
                        close(descriptor)
                        if error == 0 {
                            return 0
                        }
                        last = error
                    } else if ready == 0 {
                        close(descriptor)
                        last = -1
                    } else {
                        last = errno
                        close(descriptor)
                    }
                } else {
                    last = errno
                    close(descriptor)
                }
            } else {
                last = errno
            }
            candidate = entry.pointee.ai_next
        }
        return last
    }

    /// The address a name resolves to, so the local-network question is asked
    /// about where the connection actually goes.
    @objc(firstAddressOfHost:port:)
    public static func firstAddress(ofHost host: String, port: Int) -> String? {
        var hints = addrinfo(ai_flags: 0, ai_family: AF_UNSPEC, ai_socktype: SOCK_STREAM,
                             ai_protocol: 0, ai_addrlen: 0, ai_canonname: nil, ai_addr: nil,
                             ai_next: nil)
        var result: UnsafeMutablePointer<addrinfo>?
        guard getaddrinfo(host, String(port), &hints, &result) == 0, let list = result else {
            return nil
        }
        defer { freeaddrinfo(list) }
        var name = [CChar](repeating: 0, count: Int(NI_MAXHOST))
        guard getnameinfo(list.pointee.ai_addr, list.pointee.ai_addrlen,
                          &name, socklen_t(name.count), nil, 0, NI_NUMERICHOST) == 0 else {
            return nil
        }
        return String(cString: name)
    }

    /// Classify only evidence in the original protocol condition. A later TCP
    /// probe cannot establish certificate validity or an A-ASSOCIATE-RJ.
    static func protocolExplanation(_ condition: String) -> String? {
        let text = condition.lowercased()
        if text.contains("certificate verify failed") {
            return "TLS certificate verification failed. Check the peer certificate, its validity and the configured trust policy."
        }
        if text.contains("secure transport layer") || text.contains("tls handshake") {
            return "The TLS connection failed. Check the configured TLS protocol, cipher suites and certificate settings."
        }
        // In the vendored DUL state machine, state 5 waits for association
        // response and event 17 is ARTIM_TIMER_EXPIRED (dulfsm.h).
        let associationTimer = text.contains("0006:0303") && text.contains("state 5 event 17")
        if associationTimer || text.contains("network read timeout") || text.contains("timeout in non-blocking mode") {
            return "The peer did not complete the DICOM exchange before the timeout. Check the peer service and the configured DICOM timeout; no association rejection was confirmed."
        }
        if text.contains("association rejected") {
            return "The peer rejected the DICOM association. Check the called and calling AE titles and the peer's association policy."
        }
        return nil
    }

    /// Preserve the original condition. Probe only when it does not already
    /// identify a protocol failure, and avoid replacing it with a later result.
    @objc(explainFailureToHost:port:condition:)
    public static func explainFailure(toHost host: String, port: Int, condition: String?) -> String {
        let flattened = (condition ?? "")
            .split(whereSeparator: { $0.isNewline })
            .map { $0.trimmingCharacters(in: .whitespaces) }
            .filter { !$0.isEmpty }
            .joined(separator: "; ")
        let sentence: String
        if let protocolReason = protocolExplanation(flattened) {
            sentence = protocolReason
        } else {
            let code = probe(host: host, port: port, timeout: 2)
            let local = isLocalNetworkAddress(firstAddress(ofHost: host, port: port) ?? host)
            sentence = explanation(forErrno: code, host: host, port: port, isLocalNetwork: local)
        }
        return flattened.isEmpty ? sentence : sentence + " (\(flattened))"
    }
}
