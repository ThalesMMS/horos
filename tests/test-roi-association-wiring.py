#!/usr/bin/env python3
"""Viewer imports .roi / .rois_series / JSON through the Swift identity service."""
from pathlib import Path
import sys

root = Path(__file__).resolve().parents[1]
controller = (root / 'Horos/Sources/ViewerController.m').read_text(encoding='latin1')
header = (root / 'Horos/Sources/ViewerController+ROIInterchange.h').read_text(encoding='utf-8')
impl = (root / 'Horos/Sources/ViewerController+ROIInterchange.m').read_text(encoding='utf-8')
pbx = (root / 'Horos.xcodeproj/project.pbxproj').read_text(encoding='utf-8')
xib = (root / 'Horos/Resources/en.lproj/Viewer.xib').read_text(encoding='latin1', errors='replace')
dcm = (root / 'Horos/Sources/DCMView.m').read_text(encoding='latin1')


def fail(message):
    print('FAIL:', message, file=sys.stderr)
    sys.exit(1)

for name in ('ROIAssociation.swift', 'ROIArchiveFormat.swift'):
    if name not in pbx:
        fail(f'{name} is not in the app target')

if 'importROIArchiveFromPath:' not in header or 'importROIFiles:' not in header:
    fail('archive import is not declared on the ROI interchange category')

load = controller[controller.index('- (void) roiLoadFromSeries: (NSString*) filename'):
                  controller.index('- (IBAction) roiLoadFromFiles:')]
if 'importROIArchiveFromPath:' not in load:
    fail('roiLoadFromSeries does not call the Swift-backed archive importer')
if 'roisSeries count] > x' in load or 'for( int x = 0; x < [pixList[y] count]' in load:
    fail('roiLoadFromSeries still assigns ROIs by slice index')

files = controller[controller.index('- (IBAction) roiLoadFromFiles: (id) sender'):
                   controller.index('- (IBAction) roiSaveSeries:')]
if 'roiLoadFromFilesArray:' in files:
    fail('Import ROI(s) still dumps .roi files onto the current slice')
if 'importROIFiles:' not in files:
    fail('Import ROI(s) does not batch .roi files through identity matching')

drag = controller[controller.index('if( found == NO)'):
                  controller.index('- (NSDragOperation)draggingEntered:')]
if 'roiLoadFromFilesArray:' in drag:
    fail('drag-and-drop still dumps .roi files onto the current slice')
if 'importROIFiles:' not in drag:
    fail('drag-and-drop does not batch .roi files through identity matching')

apply = impl[impl.index('- (BOOL) applyAssociationItems:'):
             impl.index('- (BOOL) importROIInterchangeFromPath:')]
if 'plan.canApply == NO' not in apply:
    fail('applyAssociationItems does not require a complete identity plan')
if apply.find('addToUndoQueue') < apply.find('plan.canApply == NO'):
    fail('undo is queued before the association plan is accepted')
if 'HorosROILabelPresentation' in apply or 'stringTex' in apply:
    fail('association import must not touch the #227/#245 label matrix')

json_import = impl[impl.index('- (BOOL) importROIInterchangeFromPath:'):
                   impl.index('- (BOOL) importROIArchiveFromPath:')]
if 'planWithDocument:' not in json_import:
    fail('JSON import does not use ROIAssociation')
if json_import.find('addToUndoQueue') < json_import.find('plan.canApply == NO'):
    fail('JSON import queues undo before the association plan is accepted')

archive = impl[impl.index('- (BOOL) importROIArchiveFromPath:'):
               impl.index('- (BOOL) importROIFiles:')]
needed = ['HorosROIArchiveKindKeyedArchive', 'inspectUnarchived:', 'The archive decoded but contains no ROIs']
missing = [item for item in needed if item not in archive]
if missing:
    fail('archive importer is missing ' + ', '.join(missing))

if 'roiLoadFromFilesArray:' not in dcm:
    fail('DCMView still owns the current-slice loader for other callers; do not delete it here')

if 'ROIAssociation' in xib or 'importROIArchiveFromPath' in xib:
    fail('Viewer.xib must stay untouched')

print('PASS: viewer imports ROI archives through Swift identity matching, not slice index or current-slice dump')
