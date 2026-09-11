#!/usr/bin/env python3
"""Execute custom folder policy with hostile/missing fields and real disk output."""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
code = r'''
import Foundation
@main struct Test {
 static func main() throws {
    let policy = ExportFolderNaming(options: ["patient": 1, "study": 1, "series": 1])
    let identity = "1.2.840.12345.1"
    let patient = policy.patientFolder(name: "OriginalName", patientID: "QA-123", identity: identity)
    precondition(patient.hasPrefix("QA-123-"))
    precondition(!patient.contains("OriginalName"))
    let root = URL(fileURLWithPath: CommandLine.arguments[1])
    let fm = FileManager.default
    var components = Set<String>()
    for uid in ["1.2.3.4", "1.2.3.5"] {
        let component = policy.seriesFolder(name: "Same:Series", number: 1, uid: uid, identity: uid)
        precondition(components.insert(component).inserted)
        let folder = root.appendingPathComponent(component, isDirectory: true)
        try fm.createDirectory(at: folder, withIntermediateDirectories: false)
        try Data(uid.utf8).write(to: folder.appendingPathComponent("image.dcm"), options: .withoutOverwriting)
        let bytes = try Data(contentsOf: folder.appendingPathComponent("image.dcm"))
        precondition(bytes == Data(uid.utf8))
    }
    for value: String? in [nil, "", " ", ".", "..", "/../", "\\..\\", ":*?", "a\n/b", String(repeating: "日本語", count: 200)] {
        let name = policy.seriesFolder(name: value, number: nil, uid: identity, identity: "ignored")
        precondition(!name.contains("/") && !name.contains("\\") && !name.contains(":"))
        precondition(name != "." && name != ".." && name.utf8.count < 255)
        precondition(root.appendingPathComponent(name).deletingLastPathComponent() == root)
        precondition(name == policy.seriesFolder(name: value, number: nil, uid: identity, identity: "ignored"))
    }
    let fallback = policy.studyFolder(name: nil, studyID: nil, uid: nil, identity: "x-coredata://synthetic/study/1")
    precondition(fallback.hasPrefix("Study-"))
    precondition(fallback != policy.studyFolder(name: nil, studyID: nil, uid: nil, identity: "x-coredata://synthetic/study/2"))
    let fields = ExportFolderNaming(options: ["patient": 0, "study": 2, "series": 2])
    precondition(fields.patientFolder(name: "QA", patientID: "SECRET", identity: identity).hasPrefix("QA-"))
    precondition(fields.studyFolder(name: "SECRET", studyID: "SECRET", uid: identity, identity: "ignored").hasPrefix(identity + "-"))
    precondition(fields.seriesFolder(name: "SECRET", number: 7, uid: identity, identity: "ignored").hasPrefix("7-"))
    let batch = NSUUID()
    let anonymous = ExportFolderNaming.anonymousPath(batch: batch, studyIndex: 1, seriesIndex: 1)
    precondition(anonymous.hasPrefix("Anonymized-"))
    precondition(anonymous.hasSuffix("Study-0001/Series-0001"))
    precondition(anonymous != ExportFolderNaming.anonymousPath(batch: batch, studyIndex: 1, seriesIndex: 2))
    precondition(anonymous != ExportFolderNaming.anonymousPath(batch: NSUUID(), studyIndex: 1, seriesIndex: 1))
    let invalid = ExportFolderNaming(options: ["patient": 99, "study": -1, "series": "../../"])
    precondition(invalid.patientFolder(name: "QA", patientID: "SECRET", identity: identity).hasPrefix("QA-"))
    print("PASS: allowed fields, deterministic UID/object fallback, bounded child paths, distinct homonymous series and preserved bytes")
 }
}
'''
source = (root / 'Horos/Sources/BrowserController.m').read_bytes().decode('latin1')
assert source.count('[d setObject:folderOptions forKey:@"folderNaming"]') == 1
assert '!addDICOMDIR && folderOptions' in source
assert source.count('configuredPatientFolderForImage:curImage naming:customFolderNaming') == 3
anonymous_source = (root / 'Horos/Sources/Anonymization.mm').read_bytes().decode('latin1')
a = anonymous_source.index('NSString *relativePath = [HorosExportFolderNaming anonymousPathForBatch:')
b = anonymous_source.index('                    @try', a)
assert 'patientID' not in anonymous_source[a:b] and 'studyName' not in anonymous_source[a:b] and 'series.name' not in anonymous_source[a:b]
with tempfile.TemporaryDirectory(prefix='horos-folder-naming-') as d:
    p = Path(d)
    (p / 'test.swift').write_text(code)
    (p / 'exports').mkdir()
    subprocess.run(['xcrun', 'swiftc', '-sanitize=address', str(root / 'Horos/Sources/ExportFolderNaming.swift'), str(p / 'test.swift'), '-o', str(p / 'test')], check=True)
    subprocess.run([str(p / 'test'), str(p / 'exports')], check=True)
