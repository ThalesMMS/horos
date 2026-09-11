#!/usr/bin/env python3
"""Federated search keeps origin, permissions and distinct homonyms.

The production Swift object is compiled and asked the acceptance questions
from #55: an optional query aggregates only the chosen local databases; each
hit still names its origin and the caller's permission; two patients who
share a name stay two rows.
"""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
code = r'''
import Foundation

var failures = 0
func check(_ condition: Bool, _ what: String) {
    if !condition { print("FAIL \(what)"); failures += 1 }
}

let search = FederatedSearch.self
let defaultPath = "/tmp/horos-fed/Documents/Horos Data"
let chest = "/tmp/horos-fed/Section Databases/Chest"
let msk = "/tmp/horos-fed/Section Databases/MSK"
let paths: [[String: Any]] = [
    ["Path": chest, "Description": "Chest", "FederatedSearch": true],
    ["Path": msk, "Description": "MSK", "FederatedSearch": false],
]

let sources = search.sources(fromLocalDatabasePaths: paths, defaultPath: defaultPath,
                             defaultName: "Documents DB", defaultIncluded: true)
check(sources.count == 3, "default plus two section databases")
check((sources[0]["name"] as? String) == "Documents DB", "default keeps its name")
check((sources[0]["included"] as? Bool) == true, "default is included when asked")
check((sources[1]["included"] as? Bool) == true, "Chest was opted in")
check((sources[2]["included"] as? Bool) == false, "MSK was left out")

let included = search.includedPaths(fromLocalDatabasePaths: paths, defaultPath: defaultPath,
                                    defaultIncluded: true)
check(included.count == 2, "only the chosen databases are queried")
check(search.isPath(chest, includedIn: paths, defaultPath: defaultPath, defaultIncluded: true),
      "Chest is a chosen source")
check(!search.isPath(msk, includedIn: paths, defaultPath: defaultPath, defaultIncluded: true),
      "MSK is not queried until it is chosen")
check(search.isPath(defaultPath, includedIn: paths, defaultPath: defaultPath, defaultIncluded: true),
      "the documents database is chosen when its flag is on")
check(!search.isPath(defaultPath, includedIn: paths, defaultPath: defaultPath, defaultIncluded: false),
      "the documents database can be left out")

let updated = search.updatingLocalDatabasePaths(paths, path: msk, included: true)
check(search.isPath(msk, includedIn: updated, defaultPath: defaultPath, defaultIncluded: true),
      "opting MSK in is persisted on that source")

check(search.pathsEqual(chest, chest + "/Horos Data"),
      "a folder and its Horos Data directory are the same source")
check(!search.pathsEqual(chest, msk), "two section folders stay distinct")

let aliceChest: [String: Any] = [
    "name": "Pneumonia", "patientUID": "alice-1", "patientID": "TF-001",
    "studyInstanceUID": "1.2.1", "accessionNumber": "A1", "studyName": "CT",
    "originPath": chest, "originName": "Chest",
]
let bobChest: [String: Any] = [
    "name": "Pneumonia", "patientUID": "bob-2", "patientID": "TF-002",
    "studyInstanceUID": "1.2.2", "accessionNumber": "A2", "studyName": "CT",
    "originPath": chest, "originName": "Chest",
]
let aliceCopy: [String: Any] = [
    "name": "Pneumonia", "patientUID": "alice-1", "patientID": "TF-001",
    "studyInstanceUID": "1.2.1", "accessionNumber": "A1", "studyName": "CT",
    "originPath": chest, "originName": "Chest",
]
let aliceDocs: [String: Any] = [
    "name": "Pneumonia", "patientUID": "alice-1", "patientID": "TF-001",
    "studyInstanceUID": "1.2.1", "accessionNumber": "A1", "studyName": "CT",
    "originPath": defaultPath, "originName": "Documents DB",
]

check(search.areHomonyms(name: "Pneumonia", patientUID: "alice-1",
                         otherName: "Pneumonia", otherPatientUID: "bob-2"),
      "the same diagnosis name on two patient UIDs is a homonym")
check(!search.areHomonyms(name: "Pneumonia", patientUID: "alice-1",
                          otherName: "Pneumonia", otherPatientUID: "alice-1"),
      "the same patient is not a homonym of itself")

let merged = search.mergingHits([aliceChest, bobChest, aliceCopy, aliceDocs])
check(merged.count == 3, "homonyms and a second origin stay distinct; a duplicate is dropped")
let identities = merged.map {
    search.identityKey(patientUID: $0["patientUID"] as? String,
                       studyUID: $0["studyInstanceUID"] as? String,
                       originPath: $0["originPath"] as? String)
}
check(Set(identities).count == 3, "identity is patient, study and origin, not the displayed name")

check(search.hit(aliceChest, matchesQuery: "pneu", field: "name"), "name query matches")
check(!search.hit(aliceChest, matchesQuery: "pneu", field: "patientID"), "name is not an ID")
check(search.hit(aliceChest, matchesQuery: "TF-001", field: "searchID"), "ID query matches")
check(search.hit(aliceChest, matchesQuery: "A1", field: "searchAccessionNumber"), "accession query matches")
check(!search.hit(aliceChest, matchesQuery: "", field: "name"), "an empty query does not aggregate")

check(search.isUnrestrictedPermission(nil), "no predicate is unrestricted")
check(search.isUnrestrictedPermission(""), "an empty predicate is unrestricted")
check(search.isUnrestrictedPermission("YES == YES"), "the portal's open filter is unrestricted")
check(search.permissionLabel(forPredicate: "") == "unrestricted", "open access is labelled")
check(search.permissionLabel(forPredicate: "comment CONTAINS 'Chest'") == "comment CONTAINS 'Chest'",
      "a restriction is shown as written")
check(search.studyAllowed(byPredicate: "comment CONTAINS 'Chest'", comment: "Chest teaching",
                          name: "Pneumonia", patientID: "TF-001"),
      "the Chest comment is allowed")
check(!search.studyAllowed(byPredicate: "comment CONTAINS 'Chest'", comment: "MSK teaching",
                           name: "Pneumonia", patientID: "TF-001"),
      "MSK is hidden from a Chest-only user")

let xid = search.federatedXID(studyXID: "ABCD/Study/p1", originPath: chest)
check(search.isFederatedXID(xid), "a federated XID is marked")
check(!search.isFederatedXID("ABCD/Study/p1"), "a local Core Data XID is not federated")
check(search.originPath(fromFederatedXID: xid) == chest, "the XID still names the origin")
check(search.studyXID(fromFederatedXID: xid) == "ABCD/Study/p1", "the XID still names the study")

check(search.displayName("Pneumonia", origin: "Chest", currentOrigin: "Documents DB")
        == "Pneumonia — Chest", "origin is visible next to a homonym")
check(search.displayName("Pneumonia", origin: "Documents DB", currentOrigin: "Documents DB")
        == "Pneumonia", "the current database is not repeated")

if failures == 0 {
    print("ok: optional chosen sources, visible origin and permission, distinct homonyms")
} else {
    print("FAIL \(failures) checks")
    exit(1)
}
'''
with tempfile.TemporaryDirectory(prefix='horos-federated-') as temp:
    folder = Path(temp)
    (folder / 'main.swift').write_text(code)
    binary = folder / 'probe'
    build = subprocess.run(
        ['xcrun', 'swiftc',
         str(root / 'Horos/Sources/DatabaseLocation.swift'),
         str(root / 'Horos/Sources/FederatedSearch.swift'),
         str(folder / 'main.swift'),
         '-o', str(binary)],
        capture_output=True, text=True)
    assert build.returncode == 0, build.stderr
    result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr
    print(result.stdout, end='')
