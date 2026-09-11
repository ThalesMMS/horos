#!/usr/bin/env python3
"""Surgical procedure CSV/SR import is wired into the host without a sidecar table."""
from pathlib import Path
import re
import sys

root = Path(__file__).resolve().parents[1]
failures = []


def read(path):
    return path.read_bytes().decode('latin1')


def stripped(path):
    return re.sub(r'//[^\n]*', '', read(path))


source = read(root / 'Horos/Sources/SurgicalProcedureImport.swift')
for token in ('1.2.840.10008.5.1.4.1.1.88.11', 'Horos Surgical Procedure SR',
              'parseCSV', 'preview', 'encodeBasicTextSR', 'isSurgicalProcedureSR',
              'isStructuredReport', 'confirming'):
    if token not in source:
        failures.append('SurgicalProcedureImport.swift no longer names %r' % token)
if 'not a sidecar table' not in source:
    failures.append('the importer no longer says procedures are DICOM SR, not a sidecar table')
if 'name similarity is not a merge key' not in source:
    failures.append('identity matching no longer refuses name-similarity merges')

if 'timelineEventsFromSRPaths' not in source:
    failures.append('the surgical timeline is no longer indexed from SR files')
if 'numbersReaderScript' not in source:
    failures.append('the Numbers JXA reader is missing')
if 'table(fromNumbersJSON' not in source:
    failures.append('Numbers JSON can no longer become a surgical log table')
if 'displayModality' not in source or 'SURG' not in source:
    failures.append('the timeline no longer distinguishes SURG from image modalities')
if 'appleEventsDeniedErrorNumber' not in source or '-1743' not in source or '-10814' not in source:
    failures.append('Numbers/Apple Events diagnosis no longer reports host error numbers')
if 'detailsHTML' not in source:
    failures.append('timeline events no longer have a display HTML')

browser = stripped(root / 'Horos/Sources/BrowserController.m')
if 'installSurgicalProcedureImportMenu' not in browser:
    failures.append('the File menu no longer installs Import Surgical Procedure Log')
if 'importSurgicalProcedureLog:' not in browser:
    failures.append('the database window no longer has importSurgicalProcedureLog:')
if 'HorosSurgicalProcedureImportSession' not in browser:
    failures.append('the action no longer uses the Swift import session')
if 'addFilesAtPaths' not in browser or 'dicomOnly:YES' not in browser:
    failures.append('committed SR files are no longer imported through the existing DICOM path')
if 'surgicalProcedureTimelineEvents' not in browser:
    failures.append('the database window no longer indexes the surgical timeline from SR files')
if 'HorosSurgicalProcedureOutline' not in browser:
    failures.append('the database outline no longer inserts SURG timeline rows')
if 'arrayByInsertingEvents' not in browser:
    failures.append('the outline refresh no longer merges SURG rows into the study list')
if 'HorosSurgicalProcedureOutlineRow' not in browser:
    failures.append('timeline rows are no longer distinct from DicomStudy in the outline')
if 'showSurgicalProcedureTimeline:' not in browser:
    failures.append('the database window no longer displays the surgical timeline')
if 'HorosNumbersAutomationStatus' not in browser:
    failures.append('Numbers/Apple Events are no longer probed with a host error status')

app = stripped(root / 'Horos/Sources/AppController.m')
if 'installSurgicalProcedureImportMenu' not in app:
    failures.append('startup no longer installs the surgical log menu')

header = stripped(root / 'Horos/Sources/BrowserController.h')
if 'installSurgicalProcedureImportMenu' not in header or 'importSurgicalProcedureLog:' not in header:
    failures.append('BrowserController.h no longer declares the surgical import selectors')
if 'surgicalProcedureTimelineEvents' not in header:
    failures.append('BrowserController.h no longer declares the surgical timeline')
if 'showSurgicalProcedureTimeline:' not in header:
    failures.append('BrowserController.h no longer declares showSurgicalProcedureTimeline:')

project = read(root / 'Horos.xcodeproj/project.pbxproj')
if 'SurgicalProcedureImport.swift' not in project:
    failures.append('SurgicalProcedureImport.swift is not in the Xcode project')
if 'SurgicalProcedureOutline.swift' not in project:
    failures.append('SurgicalProcedureOutline.swift is not in the Xcode project')

if not (root / 'docs/surgical-procedure-sr-import.md').is_file():
    failures.append('the validation record is missing')

for failure in failures:
    print('FAIL:', failure)
if failures:
    sys.exit(1)
print('ok: surgical CSV/SR import is compiled, menu-wired and imports via DICOM SR files')
