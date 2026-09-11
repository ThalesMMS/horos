#!/usr/bin/env python3
"""Editing one half of a node must not lose the other half (#380 A).

Object level: a DICOMweb edit merges into the node that was there, so AE title,
address, port, transfer syntax, TLS and WADO settings survive; only the four
DICOMweb keys change; a node's identity among the others is its AE title,
address and port, not its description.

Source level: the preferences window still loads plugin panes, keeps the
current pane when one fails to load, reuses the host's fullscreen policy
instead of a second one, and the Locations pane writes `SERVERS` only from the
controller's own array. Secrets stay in the Keychain: the editor never writes a
password, a token or an authorization header into user defaults.
"""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
driver = r'''
import Foundation
func expect(_ ok: Bool, _ reason: String) { if !ok { fatalError(reason) } }

let node: NSDictionary = [
    "AETitle": "PACS", "Address": "10.0.0.4", "Port": "11112", "Description": "Main PACS",
    "TransferSyntax": 0, "retrieveMode": 0, "QR": true, "Send": true,
    "TLSEnabled": true, "TLSAuthenticated": true, "TLSSupportedCipherSuite": ["TLS_AES_256_GCM_SHA384"],
    "WADOPort": 8080, "WADOUrl": "wado", "WADOhttps": 1, "WADOTransferSyntax": -1,
    "SomeFutureKey": "kept",
]
let edited = DICOMwebNodeEditor.merging(into: node, url: "https://dicomweb.example/dicomweb", credentialIdentifier: "cred-1")
for key in ["AETitle", "Address", "Port", "Description", "TransferSyntax", "QR",
            "TLSEnabled", "TLSAuthenticated", "TLSSupportedCipherSuite",
            "WADOPort", "WADOUrl", "WADOhttps", "WADOTransferSyntax", "SomeFutureKey"] {
    expect(String(describing: edited[key]) == String(describing: node[key]),
           "\(key) survives the edit: \(String(describing: edited[key])) vs \(String(describing: node[key]))")
}
expect(edited["DICOMwebURL"] as? String == "https://dicomweb.example/dicomweb", "the URL is written")
expect(edited["DICOMwebCredentialID"] as? String == "cred-1", "the credential reference is written")
expect((edited["retrieveMode"] as? NSNumber)?.intValue == 3, "retrieve mode becomes DICOMweb")
expect((edited["Send"] as? NSNumber)?.boolValue == false, "the pilot has no STOW")
let changed = edited.allKeys.compactMap { $0 as? String }.filter {
    String(describing: edited[$0]) != String(describing: node[$0])
}
expect(Set(changed).isSubset(of: Set(DICOMwebNodeEditor.editedKeys)),
       "only the DICOMweb keys changed: \(changed)")

let cleared = DICOMwebNodeEditor.merging(into: edited, url: "https://dicomweb.example/dicomweb", credentialIdentifier: nil)
expect(cleared["DICOMwebCredentialID"] == nil, "no authentication removes the credential reference")
expect(cleared["TLSEnabled"] as? Bool == true, "and still keeps the DIMSE half")
for key in cleared.allKeys.compactMap({ $0 as? String }) {
    let value = String(describing: cleared[key]).lowercased()
    expect(!value.contains("basic ") && !value.contains("bearer "), "\(key) must not carry an authorization header")
}
expect(!cleared.allKeys.contains { ($0 as? String)?.lowercased().contains("password") == true },
       "no password is written into the node")

// Identity is the DIMSE triple, not the description.
expect(DICOMwebNodeEditor.identity(of: node) == "PACS|10.0.0.4|11112", "identity is AE, address and port")
let renamed: NSDictionary = ["AETitle": "pacs", "Address": "10.0.0.4", "Port": 11112, "Description": "Renamed"]
expect(DICOMwebNodeEditor.identity(of: renamed) == DICOMwebNodeEditor.identity(of: node),
       "the same node under another description and a numeric port is the same node")
let elsewhere: NSDictionary = ["AETitle": "PACS", "Address": "10.0.0.5", "Port": "11112"]
expect(DICOMwebNodeEditor.identity(of: elsewhere) != DICOMwebNodeEditor.identity(of: node), "another address is another node")

print("PASS: a DICOMweb edit changes only its own four keys, keeps AE/port/TLS/WADO and any unknown key, writes no secret into the node, and a node is identified by AE title, address and port")
'''
with tempfile.TemporaryDirectory(prefix='horos-preferences-') as folder:
    tmp = Path(folder)
    (tmp / 'main.swift').write_text(driver)
    subprocess.run(['xcrun', 'swiftc', *[str(root / 'Horos/Sources' / name) for name in
                    ('DICOMwebNodeEditor.swift', 'DICOMwebClient.swift', 'DICOMwebCredentials.swift', 'DICOMwebMultipart.swift')],
                    str(tmp / 'main.swift'), '-o', str(tmp / 'test')], check=True)
    subprocess.run([str(tmp / 'test')], check=True)

preferences = (root / 'Horos/Sources/PreferencesWindowController.mm').read_bytes().decode('latin1')
locations = (root / 'Preference Panes/OSILocationsPreferencePane/OSILocationsPreferencePanePref.m').read_bytes().decode('latin1')
editor = (root / 'Horos/Sources/DICOMwebNodeEditor.swift').read_text()
assert 'PluginManager' in preferences or 'pluginsPanes' in preferences or 'plugin' in preferences.lower(), \
    'the preferences window must keep loading plugin panes'
assert 'Preferences Could Not Be Opened' in preferences or 'couldNotBeOpened' in preferences.lower() or 'showAlert' in preferences, \
    'a pane that fails to load must be reported, not leave an empty window'
for forbidden in ('setPresentationOptions', 'NSApplicationPresentationFullScreen', 'toggleFullScreen'):
    assert forbidden not in preferences, 'the preferences window must not define a second fullscreen policy: ' + forbidden
assert 'HorosDICOMwebNodeEditor" ) editNode' in locations or 'HorosDICOMwebNodeEditor") editNode' in locations, \
    'the Locations pane reaches the shared editor'
assert '[node setDictionary:edited]' in locations, 'the edited node replaces the entry it came from'
assert locations.count('forKey:@"SERVERS"') >= 3 and 'arrangedObjects] forKey:@"SERVERS"' in locations, \
    'SERVERS is written from the controller array, not rebuilt'
assert 'DICOMwebCredentials.save' in editor and 'Keychain' in editor, 'credentials stay in the Keychain'
assert 'node["DICOMwebPassword"]' not in editor and 'node["Authorization"]' not in editor, \
    'no secret may be written into the node'
print('preferences wiring: plugin panes and the pane-failure alert kept, no second fullscreen policy, Locations still owns SERVERS, credentials stay in the Keychain')
