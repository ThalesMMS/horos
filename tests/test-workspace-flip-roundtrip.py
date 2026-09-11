#!/usr/bin/env python3
"""Workspace state keeps each flip axis apart and restores both (#598).

`+[ViewerController saveWindowsStateWithDICOMSR:name:]` used to write
`[view xFlipped]` under both keys, so a vertical flip never reached the saved
workspace, and the loader in `-[BrowserController databaseOpenStudy:]` never
read either key back. The DICOM SR envelope archives the same property list
(`-[DicomStudy archiveWindowsStateAsDICOMSR]` reads `self.windowsState`), so
the producer is checked once and the archive path is checked to reuse it.
"""
import re
from pathlib import Path

root = Path(__file__).resolve().parents[1]
viewer = (root / 'Horos/Sources/ViewerController.m').read_bytes().decode('latin1')
browser = (root / 'Horos/Sources/BrowserController.m').read_bytes().decode('latin1')
study = (root / 'Horos/Sources/DicomStudy.m').read_bytes().decode('latin1')

# Producer: one dictionary entry per axis, each read from its own property.
start = viewer.index('+ (void) saveWindowsStateWithDICOMSR: (BOOL) DICOMSR name: (NSString*) name')
producer = viewer[start:viewer.index('\n- (void) executeUndo:', start)]
writes = dict(re.findall(r'\[dict setObject: @\(\[view ([xy]Flipped)\]\) forKey:@"([xy]Flipped)"\];', producer))
assert writes == {'xFlipped': 'xFlipped', 'yFlipped': 'yFlipped'}, writes
assert 'forKey:@"windowsState"]' in producer and 'archiveWindowsStateAsDICOMSR' in producer

# Archive: the SR envelope wraps the very blob the producer stored.
archive = study[study.index('- (void) archiveWindowsStateAsDICOMSR'):]
archive = archive[:archive.index('\n}\n')]
assert 'NSData *windowsState = self.windowsState;' in archive
assert 'initWithWindowsState: windowsState' in archive

# Loader: each axis is applied from its own key, after the geometry, and an
# absent key (older workspaces) leaves the flip untouched.
start = browser.index('float rotation = [[dict valueForKey:@"rotation"] floatValue];')
loader = browser[start:browser.index('checkAllWindowsAreVisibleIsOff = NO', start)]
for axis in 'xy':
    guard = 'if( [dict valueForKey: @"%sFlipped"])' % axis
    apply = '[v set%sFlipped: [[dict valueForKey: @"%sFlipped"] boolValue]];' % (axis.upper(), axis)
    assert guard in loader, 'loader must guard the %s axis for older workspaces' % axis
    assert apply in loader, 'loader must restore the %s axis' % axis
    assert loader.index(guard) < loader.index(apply)
    assert loader.index('[v setRotation: rotation];') < loader.index(apply)
print('workspace flip round trip: producer, archive and loader consistent')
