#!/usr/bin/env python3
"""Horos-Horos direct transfer negotiates capability, then falls back to DICOM."""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
main = r'''import Foundation

func check(_ condition: @autoclosure () -> Bool, _ message: String) {
    precondition(condition(), message)
}

func server(_ fields: [String: Any]) -> [String: Any] { fields }

// Compatible Horos peer, chosen and authorized: use the direct path.
let capable: [String: Any] = [
    "Address": "192.0.2.10",
    "AETitle": "PEER",
    "Port": "11112",
    "HorosDirectTransferVersion": 4,
    "HorosDirectTransferPort": 49152,
    "HorosDirectTransferToken": "token-one",
    "Description": "peer"
]
check(DirectTransferPolicy.route(server: capable, destinationChosen: true, authorized: true) == DirectTransferPolicy.routeDirect,
      "authorized capable peer uses direct transfer")
check(DirectTransferPolicy.fallbackReason(for: capable) == nil, "capable peer has no DIMSE fallback reason")

// Bonjour can discover the port, but advertisement is not authorization.
check(DirectTransferPolicy.route(server: capable, destinationChosen: true, authorized: false) == DirectTransferPolicy.routeRefuse,
      "Bonjour advertisement does not authorize the transfer")
check(DirectTransferPolicy.route(server: capable, destinationChosen: false, authorized: true) == DirectTransferPolicy.routeRefuse,
      "an implicit destination is not a send")
check(DirectTransferPolicy.bonjourTXTFields()["HorosDirectTransferToken"] == nil,
      "Bonjour TXT must not publish the token")
check(DirectTransferPolicy.bonjourTXTFields()["HorosDirectTransferVersion"] != nil,
      "Bonjour may advertise the protocol version")

// Older or incomplete peers keep DIMSE explicitly. DICOMweb is untouched.
let oldPeer = server(["Address": "192.0.2.11", "AETitle": "OLD", "Port": "104",
                      "HorosDirectTransferVersion": 1, "HorosDirectTransferPort": 0])
check(DirectTransferPolicy.route(server: oldPeer, destinationChosen: true, authorized: true) == DirectTransferPolicy.routeDIMSE,
      "version 1 without a live port uses DIMSE")
let dimseReason = DirectTransferPolicy.fallbackReason(for: oldPeer)!
check(dimseReason.lowercased().contains("dicom"), dimseReason)
check(!dimseReason.lowercased().contains("success"), dimseReason)

let web = server(["Address": "example.test", "retrieveMode": 3, "DICOMwebURL": "https://pacs.example/dicomweb"])
check(DirectTransferPolicy.route(server: web, destinationChosen: true, authorized: true) == DirectTransferPolicy.routeDIMSE,
      "DICOMweb nodes are not replaced by HOROSFT1")

let ipv6 = server(["Address": "2001:db8::10", "AETitle": "V6", "Port": "11112",
                   "HorosDirectTransferVersion": 4, "HorosDirectTransferPort": 48000,
                   "HorosDirectTransferToken": "v6-token"])
check(DirectTransferPolicy.route(server: ipv6, destinationChosen: true, authorized: true) == DirectTransferPolicy.routeDirect,
      "IPv6 hosts are valid direct endpoints")

// Wire header: magic, version, counts, token. Wrong magic or token is not success.
let header = try DirectTransferPolicy.encodeBulkHeader(fileCount: 2, totalBytes: 32, token: "token-one")
check(header.starts(with: Data("HOROSFT1".utf8)), "bulk magic")
let decoded = try DirectTransferPolicy.decodeBulkHeader(header)
check(decoded.version == 1 && decoded.fileCount == 2 && decoded.totalBytes == 32 && decoded.token == "token-one",
      "round-trip bulk header")
do {
    _ = try DirectTransferPolicy.decodeBulkHeader(Data("XXXXYYYY".utf8) + header.dropFirst(8))
    preconditionFailure("wrong magic must not decode")
} catch { }

let session = try DirectTransferPolicy.encodeSessionHeader(operation: .checkIn, token: "token-one")
check(session.starts(with: Data("HOROSFT2".utf8)), "session magic")
let sessionDecoded = try DirectTransferPolicy.decodeSessionHeader(session)
check(sessionDecoded.version == 4 && sessionDecoded.operation == .checkIn && sessionDecoded.token == "token-one",
      "session header version 4")
check(!DirectTransferPolicy.sessionCompatible(advertisedVersion: 3), "session older than 4 is incompatible")
check(DirectTransferPolicy.sessionCompatible(advertisedVersion: 4), "session 4 is current")

// Inventory: SOPInstanceUID, not file or frame counts. Partial is not success.
let expected = ["1.2.1", "1.2.2"]
check(DirectTransferPolicy.outcome(expectedUIDs: expected, receivedUIDs: expected,
                                     fileCount: 1, frameCount: 10, cancelled: false, ackStatus: 0,
                                     writeError: false) == DirectTransferPolicy.outcomeSuccess,
      "one multiframe file can carry two SOP UIDs")
check(DirectTransferPolicy.outcome(expectedUIDs: expected, receivedUIDs: ["1.2.1"],
                                     fileCount: 2, frameCount: 2, cancelled: false, ackStatus: 0,
                                     writeError: false) == DirectTransferPolicy.outcomePartial,
      "a missing SOP is a partial failure")
check(DirectTransferPolicy.outcome(expectedUIDs: expected, receivedUIDs: expected,
                                     fileCount: 2, frameCount: 2, cancelled: true, ackStatus: 0,
                                     writeError: false) == DirectTransferPolicy.outcomeCancelled,
      "cancel is not success")
check(DirectTransferPolicy.outcome(expectedUIDs: expected, receivedUIDs: expected,
                                     fileCount: 2, frameCount: 2, cancelled: false, ackStatus: 1,
                                     writeError: false) == DirectTransferPolicy.outcomeRejected,
      "nonzero ACK is not success")
check(DirectTransferPolicy.outcome(expectedUIDs: expected, receivedUIDs: expected,
                                     fileCount: 2, frameCount: 2, cancelled: false, ackStatus: 0,
                                     writeError: true) == DirectTransferPolicy.outcomeWriteError,
      "a write error is not success")

// Temporary Bonjour/TCP sources must not erase a saved node. Peer UID replaces a stale session.
let catalog = DirectTransferSourceCatalog()
catalog.addPermanent(identifier: "saved-pacs", aeTitle: "PACS", address: "192.0.2.4")
catalog.addBonjour(identifier: "bonjour-peer", aeTitle: "PEER", address: "192.0.2.10")
catalog.addSession(identifier: "sess-1", peerUID: "UID-A", aeTitle: "PEER", address: "192.0.2.10")
catalog.dropBonjour(identifier: "bonjour-peer")
catalog.dropSession(identifier: "sess-1")
check(catalog.permanentIdentifiers == ["saved-pacs"], "permanent PACS remains after Bonjour/TCP drop")
check(!catalog.identifiers.contains("bonjour-peer"), "stale Bonjour source is gone")
catalog.addSession(identifier: "sess-2", peerUID: "UID-A", aeTitle: "PEER", address: "192.0.2.11")
catalog.addSession(identifier: "sess-3", peerUID: "UID-A", aeTitle: "PEER", address: "192.0.2.12")
check(catalog.sessionIdentifiers == ["sess-3"], "the same peer UID replaces the previous check-in")

let status = DirectTransferPolicy.status(fileCount: 3, patientName: "DOE^JOHN")
check(!status.contains("DOE"), status)
check(!status.contains("JOHN"), status)
check(status.contains("3"), status)

do {
    _ = try DirectTransferPolicy.encodeFileFrame(name: "../escape.dcm", bytes: Data([1]))
    preconditionFailure("path traversal in the file name must be refused")
} catch { }

// Two in-process peers: real TCP, compressed-looking payload, checksum and SOP inventory.
let tmp = URL(fileURLWithPath: CommandLine.arguments[1], isDirectory: true)
let payloadA = Data((0..<64).map { UInt8($0) }) // stand-in for a compressed DICOM object
let payloadB = Data((0..<32).map { UInt8(255 - $0) })
let sendDir = tmp.appendingPathComponent("send", isDirectory: true)
let recvDir = tmp.appendingPathComponent("recv", isDirectory: true)
try FileManager.default.createDirectory(at: sendDir, withIntermediateDirectories: true)
try FileManager.default.createDirectory(at: recvDir, withIntermediateDirectories: true)
let fileA = sendDir.appendingPathComponent("1.2.840.10008.1.dcm")
let fileB = sendDir.appendingPathComponent("1.2.840.10008.2.dcm")
try payloadA.write(to: fileA)
try payloadB.write(to: fileB)

let token = "loopback-token"
let listener = DirectTransferListener(token: token)
try listener.start(interface: .loopbackIPv4)
defer { listener.stop() }
check(listener.port > 0, "ephemeral listen port")

let result = try DirectTransferClient.send(
    files: [fileA.path, fileB.path],
    host: "127.0.0.1",
    port: Int(listener.port),
    token: token,
    expectedUIDs: ["1.2.840.10008.1", "1.2.840.10008.2"],
    cancelled: false
)
check(result.outcome == DirectTransferPolicy.outcomeSuccess, "loopback ACK")
let received = try listener.takeReceivedFiles(into: recvDir)
check(received.map(\.name).sorted() == ["1.2.840.10008.1.dcm", "1.2.840.10008.2.dcm"], "names")
let gotA = try Data(contentsOf: recvDir.appendingPathComponent("1.2.840.10008.1.dcm"))
let gotB = try Data(contentsOf: recvDir.appendingPathComponent("1.2.840.10008.2.dcm"))
check(gotA == payloadA, "pixels A")
check(gotB == payloadB, "pixels B")

do {
    _ = try DirectTransferClient.send(
        files: [fileA.path],
        host: "127.0.0.1",
        port: Int(listener.port),
        token: "wrong-token",
        expectedUIDs: ["1.2.840.10008.1"],
        cancelled: false
    )
    preconditionFailure("wrong token must not succeed")
} catch { }

do {
    _ = try DirectTransferClient.send(
        files: [fileA.path],
        host: "127.0.0.1",
        port: Int(listener.port),
        token: token,
        expectedUIDs: ["1.2.840.10008.1"],
        cancelled: true
    )
    preconditionFailure("cancelled send must not return success")
} catch { }

listener.stop()
try listener.start(interface: .loopbackIPv6)
let v6 = try DirectTransferClient.send(
    files: [fileB.path],
    host: "::1",
    port: Int(listener.port),
    token: token,
    expectedUIDs: ["1.2.840.10008.2"],
    cancelled: false
)
check(v6.outcome == DirectTransferPolicy.outcomeSuccess, "IPv6 loopback")

print("PASS: capability, DIMSE fallback, Bonjour is not trust, inventory, loopback IPv4/IPv6")
'''

with tempfile.TemporaryDirectory(prefix='horos-direct-') as tmp:
    p = Path(tmp)
    (p / 'main.swift').write_text(main)
    subprocess.run([
        'xcrun', 'swiftc',
        str(root / 'Horos/Sources/HorosDirectTransfer.swift'),
        str(p / 'main.swift'), '-o', str(p / 'test')
    ], check=True)
    subprocess.run([str(p / 'test'), tmp], check=True)


def objc_body(source, signature):
    at = 0
    while True:
        at = source.find(signature, at)
        if at < 0:
            return ''
        brace = source.find('{', at)
        semi = source.find(';', at)
        if brace >= 0 and (semi < 0 or brace < semi):
            break
        at += len(signature)
    depth, index = 0, brace
    while index < len(source):
        if source[index] == '{':
            depth += 1
        elif source[index] == '}':
            depth -= 1
            if depth == 0:
                return source[brace:index + 1]
        index += 1
    return ''


send = (root / 'Horos/Sources/SendController.m').read_bytes().decode('latin1')
bonjour = (root / 'Horos/Sources/BonjourPublisher.m').read_bytes().decode('latin1')
delegate = (root / 'DCM Framework/DCMNetServiceDelegate.m').read_bytes().decode('latin1')
pbx = (root / 'Horos.xcodeproj/project.pbxproj').read_text(encoding='utf-8')
swift = (root / 'Horos/Sources/HorosDirectTransfer.swift').read_text(encoding='utf-8')

assert 'HorosDirectTransfer.swift in Sources' in pbx, 'the helper must be in the Horos target'
assert 'Horos-Swift.h' in send, 'SendController must see the Swift policy'
offis = objc_body(send, '- (void) sendDICOMFilesOffis:(NSDictionary *) dict')
assert 'HorosDirectTransferPolicy' in offis or 'DirectTransferPolicy' in offis, (
    'sendDICOMFilesOffis must ask the Swift policy before C-STORE')
assert 'Using DICOM transfer' in offis or 'falling back to DICOM' in offis.lower() or 'DICOM C-STORE' in offis, (
    'DIMSE fallback must be named, not a silent success')
assert 'HorosDirectTransferService' in offis or 'DirectTransferClient' in offis, (
    'an authorized direct peer must use the Horos-Horos sender')

assert 'NSClassFromString(@"HorosDirectTransfer' in bonjour, (
    'BonjourPublisher must not hard-fail isolated sharing tests if Swift is absent')
assert 'HorosDirectTransferVersion' in bonjour, 'sharing TXT advertises the protocol version'
assert 'HorosDirectTransferToken' not in bonjour.split('setObject')[0] or 'HorosDirectTransferToken' not in bonjour, (
    'sharing TXT must not publish the token')
# Token string may appear in comments; the TXT dictionary builder must not set it.
update = objc_body(bonjour, '- (void)updateBonjour')
assert 'HorosDirectTransferToken' not in update, 'updateBonjour must not put the token in TXT'

assert 'HorosDirectTransferVersion' in delegate, 'Bonjour DICOM list must read the advertised version'
assert 'HorosDirectTransferPort' in delegate, 'Bonjour DICOM list must read the advertised port'
# Token from Bonjour TXT would turn discovery into a secret. Saved nodes keep their own token.
bonjour_block = delegate[delegate.find('searchDICOMBonjour'):delegate.find('if( send)')]
assert 'HorosDirectTransferToken' not in bonjour_block, (
    'Bonjour discovery must not copy a token out of the TXT record')

assert 'QIDO' not in swift or 'does not replace' in swift.lower() or 'DICOMweb' in swift, (
    'the Swift helper must leave the local DICOMweb client alone')
assert 'retrieveMode' in swift and '3' in swift, 'DICOMweb retrieve mode 3 stays on DIMSE/HTTP'

print('PASS: SendController, Bonjour TXT and DCMNetServiceDelegate stay wired without publishing the token')
