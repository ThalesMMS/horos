#!/usr/bin/env python3
"""The published association and indexing contract (#380 C), used by #383.

Object level: the identity rules (patient key compared whole and
case/diacritic/width insensitively, no merge by name, ambiguity reported rather
than resolved), the indexing notifications, and the related-studies limit with
its default and its "0 means no limit" reading.

Source level: the browser's comparative search and same-patient expansion take
that limit, sort by date descending so a truncated list keeps the most recent
studies, and the surgical import of #383 states the same identity rule.
"""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
driver = r'''
import Foundation
func expect(_ ok: Bool, _ reason: String) { if !ok { fatalError(reason) } }

expect(AssociationContract.version == 1, "the contract carries a version")
expect(!AssociationContract.mayMergeByNameSimilarity, "names are never a merge key")
expect(AssociationContract.indexingIsAsynchronous, "indexing is asynchronous")
expect(AssociationContract.studyKeyDescription == "studyInstanceUID", "a study is its Study Instance UID")
expect(AssociationContract.instanceKeyDescription == "sopInstanceUID", "an instance is its SOP Instance UID")
expect(AssociationContract.didAddNotification == "OsirixAddToDBNotification", "the indexing notification is the host's")
expect(AssociationContract.relatedStudiesCacheSeconds == 180, "the cache interval is the browser's three minutes")

// Patient keys compare whole, and case, diacritics and width do not matter.
expect(AssociationContract.patientKey("DOE^JOHN-12345-19700101", matches: "doe^john-12345-19700101"), "case insensitive")
expect(AssociationContract.patientKey("DOE^JOÃO-12345-19700101", matches: "DOE^JOAO-12345-19700101"), "diacritic insensitive")
expect(!AssociationContract.patientKey("DOE^JOHN-12345-19700101", matches: "DOE^JOHN-99999-19700101"), "a different ID is a different patient")
expect(!AssociationContract.patientKey("DOE^JOHN-12345-19700101", matches: "DOE^JOHN-12345"), "a key without the birth date is not the same key")
expect(!AssociationContract.patientKey(nil, matches: "DOE^JOHN-12345-19700101"), "an absent key matches nothing")
expect(!AssociationContract.patientKey("", matches: ""), "an empty key matches nothing")

// Ambiguity is reported, not resolved.
expect(AssociationContract.ambiguousPatientKeys(among: ["A-1-19700101", "a-1-19700101"]).isEmpty, "one patient written twice is not ambiguous")
let ambiguous = AssociationContract.ambiguousPatientKeys(among: ["DOE^JOHN-1-19700101", "DOE^JOHN-2-19800202", "DOE^JOHN-1-19700101"])
expect(ambiguous.count == 2, "two patients under one name are ambiguous: \(ambiguous)")
expect(AssociationContract.ambiguousPatientKeys(among: []).isEmpty, "nothing matched is not ambiguity")

// The related-studies limit.
let defaults = UserDefaults(suiteName: "org.horos.test.contract.\(UUID().uuidString)")!
expect(AssociationContract.relatedStudiesLimit(in: defaults) == AssociationContract.defaultRelatedStudiesLimit,
       "the default limit applies when nothing is stored")
defaults.set(25, forKey: AssociationContract.relatedStudiesLimitKey)
expect(AssociationContract.relatedStudiesLimit(in: defaults) == 25, "a stored limit is used")
defaults.set(0, forKey: AssociationContract.relatedStudiesLimitKey)
expect(AssociationContract.relatedStudiesLimit(in: defaults) == 0, "zero means no limit")
defaults.set(-5, forKey: AssociationContract.relatedStudiesLimitKey)
expect(AssociationContract.relatedStudiesLimit(in: defaults) == 0, "a negative limit also means no limit")
expect(AssociationContract.truncationKeepsMostRecent, "a truncated list keeps the most recent studies")
expect(AssociationContract.summary.contains("v1") && AssociationContract.summary.contains("studyInstanceUID"),
       "the summary names the version and the keys")

print("PASS: identity compares patient keys whole and reports ambiguity, indexing is announced not assumed, and the related-studies limit defaults, reads and disables as published")
'''
with tempfile.TemporaryDirectory(prefix='horos-contract-') as folder:
    tmp = Path(folder)
    (tmp / 'main.swift').write_text(driver)
    subprocess.run(['xcrun', 'swiftc', str(root / 'Horos/Sources/AssociationContract.swift'), str(tmp / 'main.swift'),
                    '-o', str(tmp / 'test')], check=True)
    subprocess.run([str(tmp / 'test')], check=True)

browser = (root / 'Horos/Sources/BrowserController.m').read_bytes().decode('latin1')
surgical = (root / 'Horos/Sources/SurgicalProcedureImport.swift').read_text()
project = (root / 'Horos.xcodeproj/project.pbxproj').read_text()
assert 'relatedStudiesLimitIn: [NSUserDefaults standardUserDefaults]' in browser, 'the browser takes the published limit'
assert browser.count('relatedStudiesLimitIn') >= 2, 'both the comparative search and the expansion take it'
assert 'request.fetchLimit = comparativeLimit' in browser, 'the comparative search limits the fetch itself'
assert 'sortDescriptorWithKey: @"date" ascending: NO' in browser, 'and sorts by date descending so the newest survive'
assert 'expansionLimit > 0 && expanded >= expansionLimit' in browser, 'the same-patient expansion is bounded'
assert 'lastRefreshComparativeStudies' in browser, 'the existing cache is kept'
assert 'name similarity is not a merge key' in surgical, "#383's import states the same rule"
assert sum('AssociationContract.swift' in line for line in project.splitlines()) == 4, \
    'AssociationContract.swift is not fully registered in the Xcode project'
print('contract wiring: the browser bounds both related-studies paths by the published limit, keeps the newest and keeps its cache')
