#!/usr/bin/env python3
"""Study metadata comes out as a CSV a spreadsheet can read back.

The database list already exported, but as tab-separated text with no escaping
at all: a study description holding a tab moved every field after it one column
to the right, and one holding a carriage return split the row in two. It also
only ever exported the columns the table happened to be showing, never a DICOM
tag somebody asked for.

What a metadata export has to get right, and what is checked here: quoting,
UTF-8 so a name in another script survives, absent fields told apart from empty
ones, and one row per study - selecting a study and one of its series must not
write that study twice.
"""
from pathlib import Path
import re
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
failures = []
browser = (root / 'Horos/Sources/BrowserController.m').read_bytes().decode('latin1')

at = browser.find('- (NSString*) metadataCSVForColumns:')
body = browser[at:browser.index('\n}', at)] if at >= 0 else ''
if not body:
    failures.append('metadataCSVForColumns:onlySelected: is gone')
else:
    # A study and one of its series can both be selected; the study is one row.
    if 'containsObject: study.objectID' not in body:
        failures.append('a study selected together with its series would be written twice')
    if 'HorosStudyMetadataExport headerRowForColumns:' not in body:
        failures.append('the file has no header row')
    if 'valuesForDicomFields: columns forFile:' not in body:
        failures.append('the values no longer come from the study\'s own file')

# The tags are read once per file, with the file's own character set.
reader = (root / 'Horos/Sources/DicomFileDCMTKCategory.mm').read_bytes().decode('latin1')
at = reader.find('+ (NSDictionary*) valuesForDicomFields:')
section = reader[at:at + 3000] if at >= 0 else ''
if not section:
    failures.append('valuesForDicomFields:forFile: is gone')
else:
    if 'DCM_SpecificCharacterSet' not in section or 'encodingForDICOMCharacterSet' not in section:
        failures.append('the values are decoded without asking the file what character set it is in')
    if 'findAndGetOFStringArray' not in section:
        failures.append('a multi-valued element would be read as its first value only')
    # The compiled-in dictionary is the 2005 one; HorosResolveDicomKeyword loads
    # the vendored table and tries both 2011 spellings so PatientName is found.
    if 'HorosResolveDicomKeyword' not in section:
        failures.append('a keyword is looked up in one spelling only, so PatientName finds nothing '
                        'against a dictionary that calls it PatientsName')

for failure in failures:
    print('FAIL: %s' % failure)
reported = len(failures)

main = r'''import Foundation

// RFC 4180: a field with a comma, a quote, a CR or an LF is quoted, and a quote
// inside it is doubled. Everything else is left alone.
precondition(StudyMetadataExport.escaped("Thorax") == "Thorax")
precondition(StudyMetadataExport.escaped("Thorax, with contrast") == "\"Thorax, with contrast\"")
precondition(StudyMetadataExport.escaped("he said \"twice\"") == "\"he said \"\"twice\"\"\"")
precondition(StudyMetadataExport.escaped("one\rtwo") == "\"one\rtwo\"")
precondition(StudyMetadataExport.escaped("one\ntwo") == "\"one\ntwo\"")
precondition(StudyMetadataExport.escaped(nil) == "")
// A tab does not have to be quoted in a CSV, and must not be turned into one.
precondition(StudyMetadataExport.escaped("Hospital\tof Tabs") == "Hospital\tof Tabs")

// Rows are CRLF separated and the file ends with one; an empty export is empty.
let csv = StudyMetadataExport.csv(fromRows: [["a", "b"], ["c,d", "e"]])
precondition(csv == "a,b\r\nc\u{2c}d".replacingOccurrences(of: "c\u{2c}d", with: "\"c,d\"") + ",e\r\n", csv)
precondition(StudyMetadataExport.csv(fromRows: []) == "")

// UTF-8 with the byte order mark, or a spreadsheet reads the accents as its own
// locale and the CJK as nothing at all.
let data = StudyMetadataExport.data(forCSV: "Grüße,グリュース\r\n")
precondition(Array(data.prefix(3)) == [0xEF, 0xBB, 0xBF])
precondition(String(data: data.dropFirst(3), encoding: .utf8) == "Grüße,グリュース\r\n")

// An absent field is an empty cell AND a mention in the last column: DICOM lets
// a field be present and empty, and the two are not the same thing.
let columns = ["PatientName", "AccessionNumber", "InstitutionName"]
let row = StudyMetadataExport.row(columns: columns,
                                  values: ["PatientName": "Grüße^Jörg", "AccessionNumber": ""])
precondition(row == ["Grüße^Jörg", "", "", "InstitutionName"], "\(row)")
precondition(StudyMetadataExport.headerRow(columns: columns)
             == columns + [StudyMetadataExport.missingHeader])
// Nothing missing leaves the last cell empty rather than saying so.
precondition(StudyMetadataExport.row(columns: ["PatientID"], values: ["PatientID": "A"]).last == "")

// DICOM pads with spaces and separates values with a backslash. Neither belongs
// in a cell as it stands.
precondition(StudyMetadataExport.cleaned("SMITH^JOHN ") == "SMITH^JOHN")
precondition(StudyMetadataExport.cleaned("CT\\PT") == "CT; PT")

// The column list: one per line, comments and blanks dropped, a repeat kept once.
let specified = StudyMetadataExport.columns(fromText: """
PatientName
  (0010,0020)   # the identifier

PatientName
# a whole line of comment
StudyDescription
""")
precondition(specified == ["PatientName", "(0010,0020)", "StudyDescription"], "\(specified)")
precondition(StudyMetadataExport.columns(fromText: "").isEmpty)
precondition(StudyMetadataExport.suggestedColumns.contains("PatientID"))

print("PASS: quoted, UTF-8, absent told from empty, and one column per line")
'''

main += r'''

// The rename DICOM made in 2011, which is why a keyword is looked up twice. The
// application's own dictionary is on the old side of it: (0010,0010) is called
// PatientsName there, so PatientName alone finds nothing.
for (given, other) in [("PatientName", "PatientsName"), ("PatientsName", "PatientName"),
                       ("PatientBirthDate", "PatientsBirthDate"), ("PatientsSex", "PatientSex"),
                       ("ReferringPhysicianName", "ReferringPhysiciansName"),
                       ("PerformingPhysiciansName", "PerformingPhysicianName")] {
    precondition(DICOMKeyword.otherSpelling(for: given) == other,
                 "\(given) -> \(DICOMKeyword.otherSpelling(for: given) ?? "nil")")
}
// A keyword the rename never touched has one spelling, and neither does a word
// that is not followed by anything.
precondition(DICOMKeyword.otherSpelling(for: "StudyDescription") == nil)
precondition(DICOMKeyword.otherSpelling(for: "Patient") == nil)
precondition(DICOMKeyword.otherSpelling(for: "") == nil)

print("PASS: both spellings of a renamed keyword")
'''

with tempfile.TemporaryDirectory(prefix='horos-metadata-csv-') as tmp:
    p = Path(tmp)
    (p / 'main.swift').write_text(main)
    build = subprocess.run(['swiftc', str(root / 'Horos/Sources/StudyMetadataExport.swift'),
                            str(root / 'Horos/Sources/DICOMKeyword.swift'),
                            str(p / 'main.swift'), '-o', str(p / 'test')],
                           capture_output=True, text=True)
    if build.returncode:
        print(build.stderr.strip()[-2000:])
        sys.exit('the export did not compile')
    checks = subprocess.run([str(p / 'test')], capture_output=True, text=True)
    print((checks.stdout + checks.stderr).strip())
    if checks.returncode:
        failures.append('the CSV is not one a spreadsheet can read back')

for failure in failures[reported:]:
    print('FAIL: %s' % failure)
if failures:
    sys.exit(1)
print('ok: metadata exports as CSV, escaped, in UTF-8, one row per study')
