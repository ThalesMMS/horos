#!/usr/bin/env python3
"""Host contract for Word report merge — mock/compilation, not native Word.

Issue #157's remaining acceptance is a real merge in Microsoft Word. This file
does not launch Word, send mail, or write a .doc. It checks that the already-
shipped host still: resolves .doc/.docx by exact name, prepares on a private
copy, publishes only a regular non-empty file, and on AppleScript failure closes
only the merge documents it opened.
"""
from pathlib import Path
import sys

root = Path(__file__).resolve().parents[1]
failures = []

reports = (root / 'Horos/Sources/Reports.m').read_bytes().decode('latin1')
replacement = (root / 'Horos/Sources/HorosReportFileReplacement.h').read_text()
placement = (root / 'Horos/Sources/ReportImagePlacement.swift').read_text()
conversion = (root / 'Horos/Sources/PagesPDFConversion.swift').read_text()

source = reports
if 'createNewWordReportForStudy:' not in source:
    failures.append('createNewWordReportForStudy: is missing')
    print('FAIL:\n- ' + '\n- '.join(failures))
    sys.exit(1)

for needle, reason in (
    ('HorosCreateReportFromTemplate', 'the merge still prepares a private copy before publishing'),
    (r'tell application \"Microsoft Word\"', 'the merge still talks to Word'),
    ('on error errorMessage number errorNumber', 'a refused merge must keep the AppleScript number'),
    # Both documents are closed through the helper now: Word rejects a command
    # sent to a stored `active document`, and the variables the old handler
    # tested were undefined whenever `open` was the statement that failed.
    ('my closeReportDocument(mergedName)', 'a failed merge must close the merged document'),
    ('my closeReportDocument(templateName)', 'a failed merge must close the template window'),
    ('on closeReportDocument(theName)', 'the handler that closes the documents is missing'),
    ('The merge did not create a new document.', 'a merge that edited the template in place is a failure'),
    ('hasPrefix: @"doc"', 'exact .doc/.docx names must still resolve'),
):
    if needle not in source:
        failures.append(reason)

templates = reports[reports.find('+(NSString*)databaseWordTemplatesDirPath'):]
templates = templates[:templates.find('+(NSString*)resolvedDatabaseWordTemplatesDirPath')]
if 'must never be removed' not in templates and 'never be removed' not in templates:
    failures.append('creating WORD TEMPLATES must not delete a colliding file')
if 'createDirectoryAtPath:folder' not in templates:
    failures.append('WORD TEMPLATES is no longer created without deleting a collision')

if 'HorosCreateReportFromTemplate' not in replacement:
    failures.append('HorosCreateReportFromTemplate is missing')

# Image insertion (#153) and Pages→PDF (#129) stay on their own types.
if 'PagesPDFConversion' in placement:
    failures.append('image insertion was mixed into the Pages PDF converter')
if 'insertSelectedImagesIntoReport' in conversion or 'HorosReportImageInsertion' in conversion:
    failures.append('Pages PDF conversion now inserts report images')
if 'createNewWordReportForStudy' in placement:
    failures.append('image insertion absorbed the Word merge')

if failures:
    print('FAIL:\n- ' + '\n- '.join(failures))
    sys.exit(1)
print('PASS: Word merge host still prepares privately, closes only its windows on error, '
      'and stays off the Pages PDF and image-insertion types')
