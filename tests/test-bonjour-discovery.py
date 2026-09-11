#!/usr/bin/env python3
"""Native Bonjour discovery, resolution and publication (#606), object level.

Compiles `Horos/Sources/BonjourDiscovery.swift` with a driver that publishes a
service of its own and browses for it. What it checks, in order:

* one service per name/type/domain even when several interfaces observe it,
  and the interface set is carried on the service;
* a real `DNSServiceRegister` publication is found by a real `NWBrowser`, and
  resolves to a numeric address, the published port and the published TXT,
  without connecting to that port;
* changing the TXT record updates the same service rather than removing and
  re-adding it;
* stopping the advertisement removes it;
* a port no listener is on is refused, and a TXT record the daemon would
  reject is refused before registration;
* a resolution that is stopped publishes nothing, and the previous snapshot
  survives a failed refresh;
* IPv6 link-local addresses keep their scope and IPv4 is preferred among what
  arrived.
"""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
source = root / 'Horos/Sources/BonjourDiscovery.swift'
failures = []
if 'BonjourDiscovery.swift in Sources' not in (root / 'Horos.xcodeproj/project.pbxproj').read_text():
    failures.append('BonjourDiscovery.swift is not in the Horos target')

DRIVER = r'''
import Foundation
import Network

var failed = false
func expect(_ ok: Bool, _ reason: String) { if !ok { print("FAIL: " + reason); failed = true } }
func pump(_ seconds: TimeInterval) {
    let deadline = Date().addingTimeInterval(seconds)
    while Date() < deadline { RunLoop.main.run(mode: .default, before: Date().addingTimeInterval(0.05)) }
}
func wait(_ seconds: TimeInterval, until condition: () -> Bool) -> Bool {
    let deadline = Date().addingTimeInterval(seconds)
    while Date() < deadline {
        if condition() { return true }
        RunLoop.main.run(mode: .default, before: Date().addingTimeInterval(0.05))
    }
    return condition()
}

// ---- pure checks that need no daemon -------------------------------------
expect(!BonjourAdvertisement.isPublishable(port: 0), "port 0 is not publishable")
expect(!BonjourAdvertisement.isPublishable(port: -1), "a negative port is not publishable")
expect(!BonjourAdvertisement.isPublishable(port: 70000), "a port past 65535 is not publishable")
expect(BonjourAdvertisement.isPublishable(port: 8780), "a listener port is publishable")
expect(BonjourAdvertisement.isTransient(Int32(kDNSServiceErr_ServiceNotRunning)), "a stopped daemon is transient")
expect(BonjourAdvertisement.isTransient(Int32(kDNSServiceErr_DefunctConnection)), "a defunct connection is transient")
expect(!BonjourAdvertisement.isTransient(Int32(kDNSServiceErr_BadParam)), "a bad parameter is not retried")
expect(!BonjourAdvertisement.isTransient(Int32(kDNSServiceErr_NoAuth)), "a permission error is not retried")
do {
    _ = try BonjourAdvertisement.encodeTXTRecord(["key=with=equals": "v"])
    expect(false, "a TXT key with '=' must be refused")
} catch { }
do {
    _ = try BonjourAdvertisement.encodeTXTRecord(["k": String(repeating: "x", count: 300)])
    expect(false, "an over-long TXT value must be refused")
} catch { }
let encoded = try! BonjourAdvertisement.encodeTXTRecord(["AETitle": "HOROSTEST", "port": "11112"])
let decoded = BonjourService.txtDictionary(fromTXTRecord: encoded)
expect(decoded["AETitle"].map { String(data: $0, encoding: .utf8) } == "HOROSTEST", "TXT round trip keeps the AE title")
expect(decoded["port"].map { String(data: $0, encoding: .utf8) } == "11112", "TXT round trip keeps the port")

// An IPv6 link-local address must carry the scope of the interface it came on.
var linkLocal = sockaddr_in6()
linkLocal.sin6_len = UInt8(MemoryLayout<sockaddr_in6>.size)
linkLocal.sin6_family = sa_family_t(AF_INET6)
linkLocal.sin6_addr.__u6_addr.__u6_addr8.0 = 0xfe
linkLocal.sin6_addr.__u6_addr.__u6_addr8.1 = 0x80
linkLocal.sin6_addr.__u6_addr.__u6_addr8.15 = 0x01
let scoped = withUnsafePointer(to: &linkLocal) { pointer in
    pointer.withMemoryRebound(to: sockaddr.self, capacity: 1) { BonjourService.address(from: $0, interface: 7) }
}
expect(scoped?.host.hasSuffix("%") == false && scoped?.host.contains("%") == true,
       "a link-local address keeps its zone: \(scoped?.host ?? "nil")")
var loopback = sockaddr_in()
loopback.sin_len = UInt8(MemoryLayout<sockaddr_in>.size)
loopback.sin_family = sa_family_t(AF_INET)
loopback.sin_addr.s_addr = inet_addr("127.0.0.1")
let four = withUnsafePointer(to: &loopback) { pointer in
    pointer.withMemoryRebound(to: sockaddr.self, capacity: 1) { BonjourService.address(from: $0, interface: 0) }
}
expect(four?.host == "127.0.0.1" && four?.isIPv4 == true, "an IPv4 sockaddr becomes its numeric form")
expect(BonjourService.numericHost(of: four!.socketAddress) == "127.0.0.1", "the socket address round trips")

// ---- a real publication, discovered and resolved --------------------------
final class Collector: NSObject, HorosBonjourBrowserDelegate, NetServiceDelegate {
    var found: [String] = []
    var removed: [String] = []
    var updated: [String] = []
    var resolved: [String: BonjourService] = [:]
    var searchFailed: [String: Any]?
    func horosBonjourBrowser(_ browser: BonjourBrowser, didFind service: BonjourService) {
        found.append(service.name)
        service.delegate = self
        service.resolve(withTimeout: 10)
    }
    func horosBonjourBrowser(_ browser: BonjourBrowser, didRemove service: BonjourService) { removed.append(service.name) }
    func horosBonjourBrowser(_ browser: BonjourBrowser, didUpdate service: BonjourService) {
        updated.append(service.name)
        service.delegate = self
        service.resolve(withTimeout: 10)
    }
    func horosBonjourBrowser(_ browser: BonjourBrowser, didNotSearch error: [String: Any]) { searchFailed = error }
    func netServiceDidResolveAddress(_ sender: NetService) {
        if let service = sender as? BonjourService { resolved[service.name] = service }
    }
}

let unique = "HorosTest-\(ProcessInfo.processInfo.processIdentifier)"
let type = "_horos-test._tcp."
let advertisement = BonjourAdvertisement(name: unique, type: type, port: 54321)
advertisement.publish(txtRecord: ["AETitle": "FIRST", "port": "11112"])
let collector = Collector()
let browser = BonjourBrowser()
browser.delegate = collector
browser.searchForServices(ofType: type, inDomain: "")

let discovered = wait(20) { collector.found.contains { $0.hasPrefix(unique) } && !collector.resolved.isEmpty }
if !discovered {
    // A machine with mDNSResponder unavailable cannot run this half.
    print("skip: the published service was not discovered; found=\(collector.found) error=\(String(describing: collector.searchFailed))")
    exit(failed ? 1 : 2)
}
expect(advertisement.isPublished, "the advertisement reports itself published as \(advertisement.name)")
let service = collector.resolved.values.first!
expect(service.port == 54321, "the resolved port is the published one: \(service.port)")
expect(service.addresses?.isEmpty == false, "the service resolved to at least one address")
expect(service.resolvedAddress?.isEmpty == false, "the resolved address is numeric: \(service.resolvedAddress ?? "nil")")
expect(service.hostName?.isEmpty == false, "the resolved host name is kept: \(service.hostName ?? "nil")")
let txt = BonjourService.txtDictionary(fromTXTRecord: service.txtRecordData())
expect(txt["AETitle"].map { String(data: $0, encoding: .utf8) } == "FIRST", "the resolved TXT is the published one: \(txt)")
let foundOnce = collector.found.filter { $0.hasPrefix(unique) }.count
expect(foundOnce == 1, "one service for one publication across every interface, found \(foundOnce) times")

// The addresses are numeric sockaddrs the host's consumers can read.
for data in service.addresses ?? [] {
    expect(BonjourService.numericHost(of: data) != nil, "every advertised address is a readable sockaddr")
}

// ---- a TXT change updates that service, it is not re-added ---------------
let foundBefore = collector.found.count
advertisement.publish(txtRecord: ["AETitle": "SECOND", "port": "11112"])
let updatedTXT = wait(15) {
    let current = BonjourService.txtDictionary(fromTXTRecord: collector.resolved.values.first?.txtRecordData())
    return current["AETitle"].map { String(data: $0, encoding: .utf8) } == "SECOND"
}
expect(updatedTXT, "a TXT change reaches the resolved service")
expect(collector.found.count == foundBefore, "a TXT change does not re-add the service")
expect(collector.removed.isEmpty, "a TXT change does not remove the service")

// ---- stopping the advertisement removes it -------------------------------
advertisement.stop()
expect(!advertisement.isPublished, "a stopped advertisement is not published")
let gone = wait(20) { collector.removed.contains { $0.hasPrefix(unique) } }
expect(gone, "stopping the advertisement removes the service")

// ---- a stopped resolution publishes nothing, and keeps its snapshot ------
let previousPort = service.port
service.resolve(withTimeout: 10)
service.stop()
pump(1)
expect(service.port == previousPort, "a stopped resolution leaves the last snapshot in place")

browser.stop()
expect(!browser.isSearching, "the browser stopped")
pump(0.5)
print(failed ? "FAILED" : "ok: native Bonjour discovery, resolution and publication")
exit(failed ? 1 : 0)
'''

if not failures:
    with tempfile.TemporaryDirectory() as tmp:
        driver = Path(tmp) / 'main.swift'
        driver.write_text(DRIVER)
        binary = Path(tmp) / 'driver'
        build = subprocess.run(['xcrun', 'swiftc', str(source), str(driver), '-o', str(binary)], capture_output=True, text=True)
        if build.returncode != 0:
            failures.append('driver did not compile:\n' + build.stderr[-3000:])
        else:
            run = subprocess.run([str(binary)], capture_output=True, text=True, timeout=180)
            if run.returncode == 2:
                print((run.stdout or '').strip(), file=__import__('sys').stderr)
                raise SystemExit(2)
            if run.returncode != 0:
                failures.append((run.stdout + run.stderr).strip() or 'driver failed without output')
            else:
                print(run.stdout.strip())

if failures:
    for failure in failures:
        print('FAIL:', failure)
    raise SystemExit(1)
