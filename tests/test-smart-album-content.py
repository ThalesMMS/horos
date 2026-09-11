#!/usr/bin/env python3
"""Smart albums can ask for studies that carry ROIs or segmentations (#380 B).

Object level: the shared clause matches a study whose series include the legacy
`OsiriX ROI SR` (series 5002) or a SEG series, and no other study; adding and
removing it leaves the rest of the predicate alone.

Source level: the editor toggles that one clause, the album still stores a
predicate string and nothing else, and the album count thread skips an album
deleted while it runs instead of faulting on it.
"""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
driver = r'''
import Foundation
func expect(_ ok: Bool, _ reason: String) { if !ok { fatalError(reason) } }

// Studies as the predicate sees them: a study is a name and its series.
func study(_ name: String, _ series: [[String: Any]]) -> NSDictionary {
    ["name": name, "series": series] as NSDictionary
}
let plain = study("plain", [["id": 1, "name": "CT axial", "modality": "CT"]])
let legacy = study("legacy", [["id": 1, "name": "CT axial", "modality": "CT"],
                              ["id": 5002, "name": "OsiriX ROI SR", "modality": "SR"]])
let segmented = study("segmented", [["id": 1, "name": "CT axial", "modality": "CT"],
                                    ["id": 7, "name": "Surfaces", "modality": "SEG"]])
let lowercase = study("lowercase", [["id": 7, "name": "Surfaces", "modality": "seg"]])
let impostor = study("impostor", [["id": 5002, "name": "Some other report", "modality": "SR"],
                                  ["id": 3, "name": "CT", "modality": "CT"]])
let all = [plain, legacy, segmented, lowercase, impostor]

func matches(_ format: String) -> [String] {
    let predicate = NSPredicate(format: format)
    return all.filter { predicate.evaluate(with: $0) }.map { $0["name"] as! String }
}
expect(matches(StudyContentPredicates.roiOrSegmentationFormat) == ["legacy", "segmented", "lowercase"],
       "ROI or segmentation: \(matches(StudyContentPredicates.roiOrSegmentationFormat))")
expect(matches(StudyContentPredicates.legacyROIFormat) == ["legacy"], "legacy ROI only")
expect(matches(StudyContentPredicates.segmentationFormat) == ["segmented", "lowercase"], "segmentation, case-insensitive")
expect(!matches(StudyContentPredicates.roiOrSegmentationFormat).contains("impostor"),
       "a series numbered 5002 with another name is not a ROI series")
expect(!matches(StudyContentPredicates.roiOrSegmentationFormat).contains("plain"), "a plain study does not match")

// Adding and removing the clause leaves the rest of the predicate intact.
let clause = StudyContentPredicates.roiOrSegmentationFormat
expect(StudyContentPredicates.adding(clause, to: nil) == clause, "an empty album becomes the clause")
expect(StudyContentPredicates.adding(clause, to: "") == clause, "an empty string too")
expect(StudyContentPredicates.adding(clause, to: "TRUEPREDICATE") == clause, "TRUEPREDICATE is replaced, not conjoined")
let user = "modality ==[cd] \"CT\" AND name CONTAINS[cd] \"phantom\""
let both = StudyContentPredicates.adding(clause, to: user)
expect(both.contains(user) && both.contains(clause), "the user's predicate survives: \(both)")
expect(StudyContentPredicates.adding(clause, to: both) == both, "adding twice changes nothing")
expect(StudyContentPredicates.contains(clause, in: both), "the clause is recognised")
expect(!StudyContentPredicates.contains(clause, in: user), "and not seen where it is absent")
let removed = StudyContentPredicates.removing(clause, from: both)
expect(NSPredicate(format: removed).predicateFormat == NSPredicate(format: user).predicateFormat,
       "removing gives back the user's predicate: \(removed)")
expect(StudyContentPredicates.removing(clause, from: clause) == "", "removing the only clause empties the album")
expect(StudyContentPredicates.removing(clause, from: user) == user, "removing what is not there changes nothing")
expect(NSPredicate(format: both).evaluate(with: study("phantom", [["id": 5002, "name": "OsiriX ROI SR", "modality": "SR"]])) == false,
       "the conjunction still needs the user's own clause")

print("PASS: the ROI/segmentation clause matches legacy ROI SR and SEG series only, and adding or removing it preserves the rest of the album's predicate")
'''
with tempfile.TemporaryDirectory(prefix='horos-album-content-') as folder:
    tmp = Path(folder)
    (tmp / 'main.swift').write_text(driver)
    subprocess.run(['xcrun', 'swiftc', str(root / 'Horos/Sources/StudyContentPredicates.swift'), str(tmp / 'main.swift'),
                    '-o', str(tmp / 'test')], check=True)
    subprocess.run([str(tmp / 'test')], check=True)

editor = (root / 'Horos/Sources/SmartWindowController.m').read_bytes().decode('latin1')
browser = (root / 'Horos/Sources/BrowserController.m').read_bytes().decode('latin1')
project = (root / 'Horos.xcodeproj/project.pbxproj').read_text()
assert 'HorosStudyContentPredicates.roiOrSegmentationFormat' in editor, 'the editor uses the shared clause'
assert 'toggleContentCriterion:' in editor and 'installContentCriterionCheckbox' in editor
assert 'setAccessibilityLabel' in editor, 'the checkbox carries its label'
for forbidden in ('NSEntityDescription', 'insertNewObjectForEntityForName', 'ROIStore', 'roiDatabase'):
    assert forbidden not in editor, 'the editor must not build a second ROI store: ' + forbidden
assert 'album.predicateString = ' in browser or 'setPredicateString' in browser or 'predicateString' in browser, \
    'albums still keep one predicate string'
assert 'existingObjectWithID:albumObjectID error:nil' in browser, 'the count thread must not fault on a deleted album'
assert 'if( ialbum == nil || ialbum.isDeleted)' in browser, 'a deleted album is skipped'
assert '[[NSThread currentThread] isCancelled]' in browser, 'the count thread stays cancellable'
assert sum('StudyContentPredicates.swift' in line for line in project.splitlines()) == 4, \
    'StudyContentPredicates.swift is not fully registered in the Xcode project'
print('smart album wiring: one shared clause in the editor, no second ROI store, deletion-safe and cancellable indexing')
