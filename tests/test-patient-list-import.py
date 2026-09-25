#!/usr/bin/env python3
"""A list of patients read from an image becomes the right entries and the right studies (#703).

The parser and the matching decision are Swift with no AppKit, Vision or
database; they are compiled and run here on lines as text recognition returns
them. The window, the recognition and the database calls are checked in source:
recognition stays on the machine, and no name or identifier reaches the log.
"""
from pathlib import Path
import json
import re
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
failures = []
core = root / 'Horos/Sources/PatientListImport.swift'

DRIVER = r'''
import Foundation

func show(_ entries: [PatientListEntry]) -> [[String: Any]] {
    entries.map { ["name": $0.name, "id": $0.identifier ?? "", "age": $0.age, "sex": $0.sex ?? "", "confidence": $0.confidence] }
}
let format = PatientListFormat(identifierPattern: nil, ignoredLines: nil)
var out: [String: Any] = [:]

out["numbered"] = show(PatientListParser.entries(lines: [
    "Agenda", "Pacientes", "Agenda - Ambulatório",
    "1. João da Silva — Prontuário: 12345 — 46 anos / M",
    "2) Maria Aparecida dos Santos",
    "ID: AB-778",
    "3. SOUZA, ANA",
    "MRN 55012, 7 yrs, F",
    "4. Sala 3 - 14:30",
    "5. Carlos Eduardo Lima Sexo: M",
    "Pedro Álvares Cabral ULI: 987654321 12 y.o. / F",
], confidences: [1, 1, 1, 0.97, 0.8, 1, 1, 1, 1, 1, 1], format: format))

// A site whose identifiers carry no label: a pattern in the preferences.
let bare = PatientListFormat(identifierPattern: #"\b([A-Z]{2}\d{6})\b"#, ignoredLines: ["hoje"])
out["configured"] = show(PatientListParser.entries(lines: ["Hoje", "Ana Beatriz Rocha XY123456", "Luís Gomes"],
                                                    confidences: [], format: bare))
let broken = PatientListFormat(identifierPattern: "(unclosed", ignoredLines: nil)
out["brokenPatternProblem"] = broken.problem ?? ""
out["brokenPatternStillParses"] = show(PatientListParser.entries(lines: ["Ana Rocha ID: 77"], confidences: [], format: broken))

out["key"] = PatientListMatching.key("João  D'Ávila^Müller, Jr.")
out["searchWords"] = PatientListMatching.searchWords("João da Silva e Souza")

func decide(_ name: String, _ id: String?, age: Int = -1, sex: String? = nil, confidence: Double = 1,
            _ candidates: [[String: Any]]) -> [String: Any] {
    let entry = PatientListEntry(name: name, identifier: id)
    entry.age = age; entry.sex = sex; entry.confidence = confidence
    let now = ISO8601DateFormatter().date(from: "2026-09-25T12:00:00Z")!
    let d = PatientListMatching.decide(entry: entry, candidates: candidates, now: now)
    return ["studies": d.studies.map { $0.intValue }, "byID": d.matchedByIdentifier, "include": d.include, "warnings": d.warnings]
}
let born1980 = ISO8601DateFormatter().date(from: "1980-03-01T00:00:00Z")!
let db: [[String: Any]] = [
    ["patientUID": "SILVA JOAO-12345-", "patientID": "12345", "name": "SILVA^JOAO", "dateOfBirth": born1980, "sex": "M"],
    ["patientUID": "SILVA JOAO-12345-", "patientID": "12345", "name": "SILVA^JOAO", "dateOfBirth": born1980, "sex": "M"],
    ["patientUID": "SILVA JOAO-999-", "patientID": "999", "name": "DA SILVA^JOAO", "sex": "M"],
    ["patientUID": "SANTOS MARIA-AB-778-", "patientID": "AB-778", "name": "DOS SANTOS^MARIA APARECIDA", "sex": "F"],
    ["patientUID": "SOUZA ANA-1-", "patientID": "1", "name": "SOUZA^ANA", "sex": "F"],
    ["patientUID": "SOUZA ANA-2-", "patientID": "2", "name": "SOUZA^ANA", "sex": "F"],
]
out["idMatch"] = decide("João Silva", "12345", age: 46, sex: "M", db)
out["idMatchOtherName"] = decide("Pedro Pereira", "12345", db)
out["idUnknown"] = decide("João Silva", "00000", db)
out["nameOnly"] = decide("Maria Aparecida dos Santos", nil, db)
out["homonyms"] = decide("Ana Souza", nil, db)
out["ageMismatch"] = decide("João Silva", "12345", age: 30, db)
out["sexMismatch"] = decide("João Silva", "12345", sex: "F", db)
out["noBirthDate"] = decide("João da Silva", "999", age: 40, db)
out["unsure"] = decide("João Silva", "12345", confidence: 0.6, db)
out["nothing"] = decide("Ninguém Daqui", nil, db)
out["particles"] = decide("João da Silva", "12345", db)

let data = try! JSONSerialization.data(withJSONObject: out, options: [.sortedKeys])
FileHandle.standardOutput.write(data)
'''

results = None
with tempfile.TemporaryDirectory(prefix='horos-patient-list-') as folder:
    work = Path(folder)
    (work / 'main.swift').write_text(DRIVER)
    built = subprocess.run(['xcrun', '--sdk', 'macosx', 'swiftc', '-o', str(work / 'check'), str(core), str(work / 'main.swift')],
                           capture_output=True, text=True)
    if built.returncode != 0:
        failures.append('the parser does not compile:\n' + built.stderr[-2500:])
    else:
        run = subprocess.run([str(work / 'check')], capture_output=True, text=True)
        if run.returncode != 0:
            failures.append('the driver failed: ' + run.stderr[-1500:])
        else:
            results = json.loads(run.stdout)


def expect(label, got, wanted):
    if got != wanted:
        failures.append('%s: %r, expected %r' % (label, got, wanted))


if results:
    rows = [(e['name'], e['id'], e['age'], e['sex']) for e in results['numbered']]
    expect('numbered list', rows, [
        ('João da Silva', '12345', 46, 'M'),
        ('Maria Aparecida dos Santos', 'AB-778', -1, ''),
        ('SOUZA, ANA', '55012', 7, 'F'),
        ('Carlos Eduardo Lima', '', -1, 'M'),
        ('Pedro Álvares Cabral', '987654321', 12, 'F'),
    ])
    expect('confidence of an entry is its lowest line', results['numbered'][1]['confidence'], 0.8)
    expect('configured pattern and headings',
           [(e['name'], e['id']) for e in results['configured']], [('Ana Beatriz Rocha', 'XY123456'), ('Luís Gomes', '')])
    if 'not a regular expression' not in results['brokenPatternProblem']:
        failures.append('a broken pattern in the preferences is not reported')
    expect('a broken pattern falls back to the default',
           [(e['name'], e['id']) for e in results['brokenPatternStillParses']], [('Ana Rocha', '77')])
    expect('name key', results['key'], 'JOAO D AVILA MULLER JR')
    expect('search words leave particles out', results['searchWords'], ['JOAO', 'SILVA', 'SOUZA'])

    d = results
    expect('identifier decides', (d['idMatch']['studies'], d['idMatch']['byID'], d['idMatch']['include'], d['idMatch']['warnings']),
           ([0, 1], True, True, []))
    expect('identifier with another name is flagged and needs confirmation',
           (d['idMatchOtherName']['studies'], len(d['idMatchOtherName']['warnings']), d['idMatchOtherName']['include']), ([0, 1], 1, False))
    expect('an unknown identifier is not replaced by the name',
           (d['idUnknown']['include'], d['idUnknown']['byID']), (False, False))
    if not any('identifier' in w for w in d['idUnknown']['warnings']):
        failures.append('an unknown identifier is not reported')
    expect('name only needs confirmation', (d['nameOnly']['studies'], d['nameOnly']['include']), ([3], False))
    if not any('name only' in w for w in d['nameOnly']['warnings']):
        failures.append('a match by name only is not reported')
    expect('homonyms are never joined', (d['homonyms']['studies'], d['homonyms']['include']), ([], False))
    if not any('Several patients' in w for w in d['homonyms']['warnings']):
        failures.append('homonyms are not reported')
    if not any('age' in w for w in d['ageMismatch']['warnings']):
        failures.append('an age that differs from the birth date is not reported')
    if not any('sex' in w for w in d['sexMismatch']['warnings']):
        failures.append('a sex that differs is not reported')
    if not any('birth date' in w for w in d['noBirthDate']['warnings']):
        failures.append('an age with no stored birth date is not reported')
    if not any('unsure' in w for w in d['unsure']['warnings']):
        failures.append('a low recognition confidence is not reported')
    expect('a patient not in the database', (d['nothing']['studies'], d['nothing']['include']), ([], False))
    expect('a particle does not make a name differ', d['particles']['warnings'], [])

# --- the rest, in source -------------------------------------------------------
window = (root / 'Horos/Sources/PatientListAlbumWindow.swift')
host = (root / 'Horos/Sources/BrowserController.m').read_bytes().decode('latin1')
query = (root / 'Horos/Sources/QueryController.mm').read_bytes().decode('latin1')
if not window.exists():
    failures.append('the window and the recognition are missing')
else:
    ui = window.read_text()
    for forbidden in ('URLSession', 'NSURLConnection', 'NSLog(', 'print(', 'os_log', 'Logger('):
        if forbidden in ui or forbidden in core.read_text():
            failures.append('the new code uses %s: recognition and its results must not leave the machine or reach a log' % forbidden)
    for required in ('VNRecognizeTextRequest', '.accurate', 'recognitionLanguages'):
        if required not in ui:
            failures.append('the recognition does not use %s' % required)
at = host.find('#pragma mark Patient list album (#703)')
section = host[at:host.find('#pragma mark', at + 10)] if at >= 0 else ''
if not section:
    failures.append('BrowserController has no patient list album section')
else:
    for required, why in (('refreshObject:', 'studies are not re-read before the album is saved'),
                          ('patientsnamePredicate:', 'the name search is not the browser\'s'),
                          ('patientUID', 'the other studies of a found patient are not added'),
                          ('queryPatientID:', 'the Query/Retrieve by identifier is not the existing one'),
                          ('queryPatientName:', 'there is no Query/Retrieve by name'),
                          (' #%d', 'an album name already used is not made unique')):
        if required not in section:
            failures.append(why)
    for line in section.splitlines():
        if 'NSLog' in line and re.search(r'name|identifier|patientID', line.split('NSLog', 1)[1]):
            failures.append('the patient list section logs patient data: ' + line.strip())
at = query.find('- (NSArray*) queryPatientName:')
body = query[at:query.find('\n}\n', at)] if at >= 0 else ''
if 'savePresetInDictionaryWithDICOMNodes' not in body or 'applyPresetDictionary: savedSettings' not in body:
    failures.append('the Query/Retrieve by name does not restore the user\'s filters')

for failure in failures:
    print('FAIL: %s' % failure)
if failures:
    sys.exit(1)
print('ok: patient lists parse with the default and configured formats, identifiers decide, names only '
      'propose, homonyms stay apart, and recognition stays local and out of the log')
