#!/usr/bin/env python3
"""Database drags reach Finder through file promises, on the real routes (#605).

Source level, with `<git revision>` as an optional argument for the negative
control:

* the outline no longer advertises the legacy `NSFilesPromisePboardType` nor
  spins the main thread waiting for the export thread; it hands AppKit one
  promise per row through `pasteboardWriterForItem:`, skips a series whose
  study is selected, and switches to JPEG with Option;
* the promise captures object identifiers, the database and the export
  settings before the drop; its worker resolves the identifiers on an
  independent database, refuses an encrypted export without a password, writes
  to staging and commits only when something was produced;
* the export core honours the captured settings and stays silent (no modal
  alert) when asked, reporting the error through the parameters instead;
* album and Sources drops read every pasteboard item;
* the thumbnail matrix drags a DICOM promise and, with Option, a JPEG of the
  captured frame or a JPEG/PDF folder; the Carbon promise fulfilment is gone.
"""
from pathlib import Path
import re
import subprocess
import sys

root = Path(__file__).resolve().parents[1]


def read(path):
    if len(sys.argv) > 1:
        return subprocess.check_output(['git', '-C', str(root), 'show', sys.argv[1] + ':' + path]).decode('latin1')
    return (root / path).read_bytes().decode('latin1')


browser = read('Horos/Sources/BrowserController.m')
header = read('Horos/Sources/BrowserController.h')
sources = read('Horos/Sources/BrowserController+Sources.m')
matrix = read('Horos/Sources/BrowserMatrix.m')
failures = []


def method(source, signature, terminator='\n}\n'):
    start = source.find(signature)
    if start < 0:
        return ''
    return source[start:source.find(terminator, start) + len(terminator)]


# --- outline drag source ------------------------------------------------------
if 'namesOfPromisedFilesDroppedAtDestination' in browser:
    failures.append('the outline still fulfils the legacy file promise')
if 'NSFilesPromisePboardType' in browser:
    failures.append('the outline still advertises NSFilesPromisePboardType')
if 'fourSeconds' in browser:
    failures.append('a drop still waits up to four seconds on the main thread')
writer = method(browser, '- (id<NSPasteboardWriting>) outlineView:(NSOutlineView*) outlineView pasteboardWriterForItem:(id) item\n')
if not writer:
    failures.append('the outline has no pasteboardWriterForItem:')
else:
    if '[outlineView isRowSelected:parentRow]' not in writer.replace(' ', '') and 'isRowSelected: parentRow' not in writer:
        failures.append('a series under a selected study is not skipped')
    if 'NSEventModifierFlagOption' not in writer:
        failures.append('Option does not switch the row drag to JPEG')

promise = method(browser, '- (id<NSPasteboardWriting>) filePromiseForDatabaseObjects:(NSArray*) items asJPEG:(BOOL) jpeg\n')
for key in ('@"rootObjectIDs"', '@"database"', '@"folderTreeTag"', '@"compressionTag"', '@"addDICOMDIR"', '@"encrypt"', '@"password"'):
    if key not in promise:
        failures.append('the promise snapshot lacks %s' % key)
if '[HorosBatchExportPlan exportNameForItemNames:' not in promise:
    failures.append('the promised name is not built by the plan')
if 'promise.extraTypes = BrowserController.DatabaseObjectXIDsPasteboardTypes' not in promise:
    failures.append('a DICOM promise does not carry the object identifiers for internal drops')
if 'HorosPromiseCompletionGuard' not in promise or 'watchThread: thread' not in promise:
    failures.append('the promise writer has no completion guard for a thread that never starts')
if 'writeDatabaseFilePromise:' not in promise or 'addThreadAndStart' not in promise:
    failures.append('the promise writer does not run on an activity thread')

worker = method(browser, '- (void) writeDatabaseFilePromise:(NSMutableDictionary*) parameters\n')
for needed in ('independentDatabase]', 'objectsWithIDs:', 'stagingDirectoryForDestination:', 'fireWithError:', 'commitStaging:', 'discardStaging:',
               'stagingHasContent:', 'quietErrors', 'exportError', 'NSUserCancelledError', 'isDeleted', 'set an encryption password'):
    if needed not in worker:
        failures.append('the promise worker lacks %s' % needed)
if worker.find('commitStaging:') < worker.find('writeReportFileExports:'):
    failures.append('reports must be written before the staging is committed')

# --- export core honours the snapshot and can be quiet -----------------------
core = method(browser, '- (NSArray*) exportDICOMFileInt: (NSMutableDictionary*) parameters\n', '\n#pragma mark')
if not core:
    core = browser[browser.find('- (NSArray*) exportDICOMFileInt: (NSMutableDictionary*) parameters\n'):]
    core = core[:core.find('\n- (', 100)]
for needed in ('[parameters objectForKey:@"addDICOMDIR"]', '[parameters objectForKey:@"encrypt"]', '[parameters objectForKey:@"password"]',
               '[parameters objectForKey:@"folderTreeTag"]', '[parameters objectForKey:@"compressionTag"]', 'quietErrors'):
    if needed not in core:
        failures.append('the export core ignores %s' % needed)
if core.count('if( !quietErrors)') < 2:
    failures.append('the export core still shows a modal alert on a quiet export')
if 'forKey: @"exportError"' not in core:
    failures.append('the export core does not report its error through the parameters')

# --- drops read every item ----------------------------------------------------
if '[BrowserController databaseObjectXIDsOnPasteboard:pb]' not in browser:
    failures.append('the album drop reads the first pasteboard item only')
if '[BrowserController databaseObjectXIDsOnPasteboard:pb]' not in sources:
    failures.append('the Sources drop reads the first pasteboard item only')
if 'identifiersOnPasteboard: pasteboard types: BrowserController.DatabaseObjectXIDsPasteboardTypes' not in browser:
    failures.append('the aggregation is not delegated to HorosPasteboardObjectIdentifiers')

# --- thumbnail matrix -----------------------------------------------------------
if 'kPasteboardTypeFileURLPromise' in matrix or 'PasteboardCopyPasteLocation' in matrix:
    failures.append('the matrix still fulfils the Carbon promise')
if 'startDragOriginalFrame' in matrix:
    failures.append('the Option+Shift original-frame drag is still there')
if 'filePromiseForDatabaseObjects: objects]' not in matrix:
    failures.append('the matrix drag is not a database promise')
jpeg = method(matrix, '- (void) startDragJPEG:(NSEvent *) event\n')
if 'filePromiseForJPEGData:jpeg name:name' not in jpeg or 'asJPEG:YES' not in jpeg:
    failures.append('Option-drag of a thumbnail does not promise a JPEG or a JPEG/PDF folder')
if 'previewPix:selectedButtonCell.tag' not in jpeg:
    failures.append('the image thumbnail JPEG is not the displayed frame captured at drag start')
mouse = method(matrix, '- (void) mouseDown:(NSEvent *)event\n')
if 'NSEventModifierFlagOption' not in mouse or '[self startDragJPEG: event]' not in mouse or 'dx * dx + dy * dy < 16.0' not in mouse:
    failures.append('mouseDown does not route Option to JPEG after a four-point drag')
# The one-second click-hold and its periodic pump are A297 behaviour the new
# drag routing must not displace; test-event-capture-pauses.py owns them too.
if 'startPeriodicEventsAfterDelay: 0 withPeriod:0.001' not in mouse or '[start timeIntervalSinceNow] >= -1' not in mouse:
    failures.append('mouseDown lost the one-second click-hold or its periodic pump')
if mouse.count('[NSEvent stopPeriodicEvents]') < 4:
    failures.append('every exit from mouseDown must stop the periodic pump')

for declaration in ('- (id<NSPasteboardWriting>) filePromiseForDatabaseObjects:(NSArray*) items asJPEG:(BOOL) jpeg;',
                    '+ (NSArray*) databaseObjectXIDsOnPasteboard:(NSPasteboard*) pasteboard;',
                    '+ (BOOL) isReportSeriesForFileExport:(DicomSeries*) series;'):
    if declaration not in header:
        failures.append('BrowserController.h lacks %r' % declaration)

if failures:
    for failure in failures:
        print('FAIL:', failure)
    raise SystemExit(1)
print('ok: database drags are file promises with captured selection, staging and quiet errors')
