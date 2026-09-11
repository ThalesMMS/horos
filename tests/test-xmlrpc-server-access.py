#!/usr/bin/env python3
"""The XML-RPC interface answers loopback by default and authenticates otherwise."""
from pathlib import Path
import subprocess, tempfile
root = Path(__file__).resolve().parents[1]
main = r'''import AppKit

// Loopback recognition covers the whole 127/8 block and the forms a dual-stack
// accept produces, since that is what N2ConnectionListener reports as the peer.
for address in ["127.0.0.1", "127.1.2.3", "127.255.255.255", "::1", "0:0:0:0:0:0:0:1",
                "::ffff:127.0.0.1", "::FFFF:127.0.0.1", "::1%lo0"] {
    assert(XMLRPCServerAccess.isLoopbackAddress(address), "expected loopback: \(address)")
}
for address in ["128.0.0.1", "10.0.0.4", "100.89.33.90", "::ffff:10.0.0.4", "2001:db8::1",
                "", "127.0.0", "127.0.0.256", "localhost"] {
    assert(!XMLRPCServerAccess.isLoopbackAddress(address), "expected remote: \(address)")
}
assert(!XMLRPCServerAccess.isLoopbackAddress(nil))

// The preference alone never opens the port: a credential is a precondition.
assert(!XMLRPCServerAccess.bindsBeyondLoopback(allowRemote: false, hasCredential: false))
assert(!XMLRPCServerAccess.bindsBeyondLoopback(allowRemote: false, hasCredential: true))
assert(!XMLRPCServerAccess.bindsBeyondLoopback(allowRemote: true, hasCredential: false))
assert(XMLRPCServerAccess.bindsBeyondLoopback(allowRemote: true, hasCredential: true))

let credential = XMLRPCServerAccess.basicHeader(username: "ris", password: "s3cret")!
assert(credential == "Basic cmlzOnMzY3JldA==")
assert(XMLRPCServerAccess.basicHeader(username: "ris:2", password: "x") == nil)
assert(XMLRPCServerAccess.basicHeader(username: "ris", password: "") == nil)
assert(XMLRPCServerAccess.basicHeader(username: "", password: "x") == nil)
assert(XMLRPCServerAccess.basicHeader(username: "ris", password: "a\nb") == nil)

// Bound to loopback: local callers keep working with no credential at all, and
// a peer that reached the socket some other way is refused outright.
func decide(_ peer: String?, _ authorization: String?, _ credential: String?, _ beyond: Bool) -> XMLRPCAccessDecision {
    return XMLRPCServerAccess.decision(peerAddress: peer, authorization: authorization,
                                       credential: credential, listensBeyondLoopback: beyond)
}
assert(decide("127.0.0.1", nil, nil, false) == .allow)
assert(decide("::1", nil, credential, false) == .allow)
assert(decide("100.89.33.90", nil, nil, false) == .refuse)
assert(decide("100.89.33.90", credential, credential, false) == .refuse)
assert(decide(nil, nil, nil, false) == .refuse)

// Serving other interfaces: every request is authenticated, loopback included.
assert(decide("100.89.33.90", nil, credential, true) == .challenge)
assert(decide("100.89.33.90", "", credential, true) == .challenge)
assert(decide("100.89.33.90", "Basic cmlzOndyb25n", credential, true) == .challenge)
assert(decide("100.89.33.90", credential.lowercased(), credential, true) == .challenge)
assert(decide("100.89.33.90", credential + " ", credential, true) == .challenge)
assert(decide("100.89.33.90", credential, credential, true) == .allow)
assert(decide("127.0.0.1", nil, credential, true) == .challenge)
assert(decide("127.0.0.1", credential, credential, true) == .allow)
// A listener that lost its credential refuses rather than falling open.
assert(decide("100.89.33.90", credential, nil, true) == .refuse)
assert(decide("100.89.33.90", credential, "", true) == .refuse)

assert(XMLRPCServerAccess.challengeHeaderValue.contains("Basic realm=\"Horos XML-RPC\""))
assert(XMLRPCServerAccess.exposureWarning.contains("patient names"))

// The sheet refuses to enable remote access without a usable credential, and
// never asks for one to turn it off.
typealias Settings = XMLRPCRemoteAccessPanel.Settings
assert(Settings(allowRemote: false, username: "", password: "").refusal == nil)
assert(Settings(allowRemote: false, username: "ris", password: "").refusal == nil)
assert(Settings(allowRemote: true, username: "ris", password: "").refusal != nil)
assert(Settings(allowRemote: true, username: "", password: "s3cret").refusal != nil)
assert(Settings(allowRemote: true, username: "ris:2", password: "s3cret").refusal != nil)
assert(Settings(allowRemote: true, username: "ris", password: "s3cret").refusal == nil)

// The button goes in the empty space beside the port field, found through the
// binding rather than through a nib outlet, and never over another control.
let parent = NSView(frame: NSRect(x: 0, y: 0, width: 587, height: 213))
let port = NSTextField(frame: NSRect(x: 361, y: 53, width: 96, height: 19))
port.bind(.value, to: NSUserDefaultsController.shared, withKeyPath: "values.httpXMLRPCServerPort", options: nil)
let other = NSTextField(frame: NSRect(x: 15, y: 53, width: 200, height: 19))
parent.addSubview(other)
parent.addSubview(port)

let button = XMLRPCRemoteAccessPanel.install(in: parent)!
assert(button.frame.minX > port.frame.maxX)
assert(button.frame.maxX <= parent.bounds.width)
assert(!button.frame.intersects(port.frame) && !button.frame.intersects(other.frame))
assert(button.superview === parent)
// Installing twice keeps one button.
assert(XMLRPCRemoteAccessPanel.install(in: parent) === button)
assert(parent.subviews.filter { $0 is NSButton }.count == 1)

// A pane without the field, or without room, gets no button drawn over it.
assert(XMLRPCRemoteAccessPanel.install(in: NSView(frame: NSRect(x: 0, y: 0, width: 587, height: 213))) == nil)
let narrow = NSView(frame: NSRect(x: 0, y: 0, width: 470, height: 213))
let narrowPort = NSTextField(frame: NSRect(x: 361, y: 53, width: 96, height: 19))
narrowPort.bind(.value, to: NSUserDefaultsController.shared, withKeyPath: "values.httpXMLRPCServerPort", options: nil)
narrow.addSubview(narrowPort)
assert(XMLRPCRemoteAccessPanel.install(in: narrow) == nil)

// The sheet shows the stored user name and the exposure warning, never a
// password read back from the keychain.
let sheet = XMLRPCRemoteAccessPanel.shared.makeSheet(
    settings: Settings(allowRemote: true, username: "ris", password: ""))
let fields = sheet.contentView!.subviews.compactMap { $0 as? NSTextField }
assert(fields.contains { $0.stringValue == "ris" })
assert(fields.contains { $0.stringValue.contains("patient names") })
assert(sheet.contentView!.subviews.contains { ($0 as? NSSecureTextField)?.stringValue == "" })
assert(XMLRPCRemoteAccessPanel.shared.settings == Settings(allowRemote: true, username: "ris", password: ""))

print("PASS: loopback default, authenticated remote access, refusal before dispatch, pane button")
'''
with tempfile.TemporaryDirectory(prefix="horos-xmlrpc-access-") as tmp:
    p = Path(tmp)
    (p / "main.swift").write_text(main)
    subprocess.run(["swiftc", "-suppress-warnings",
                    str(root / "Horos/Sources/XMLRPCServerAccess.swift"),
                    str(root / "Horos/Sources/XMLRPCRemoteAccessPanel.swift"),
                    str(p / "main.swift"), "-o", str(p / "test")], check=True)
    subprocess.run([str(p / "test")], check=True)
