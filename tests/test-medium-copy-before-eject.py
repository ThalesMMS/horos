#!/usr/bin/env python3
"""A disc was ejected on a one-second timer, read only as far as its index, and
every file taken off it was declared unreadable.

Three things stood between a mounted CD and the database.

`-[DicomFile getDicomFile]` chose a parser. Papyrus was taken out of the project
and `-getDicomFilePapyrus:` was left as a stub returning -1, which `-init:` reads
as "I cannot read this file". `PREFERPAPYRUSFORCD` was registered as 1, so every
file read from a mounted CD or DVD took that route:

    if( PREFERPAPYRUSFORCD) isCD = filesAreFromCDMedia;
    if( TOOLKITPARSER == 1 || isCD == YES) return [self getDicomFilePapyrus: NO];

Nobody could turn it off: the checkbox bound to it lived in the General
preference pane's hidden "DICOM Toolkits" box.

`-[DicomDatabase scanAtPath:isVolume:]` then took a DICOMDIR that named part of
the medium as naming all of it, so what the index omitted was never looked for.

And it waited for the copy like this:

    while (copyFilesThread.progress < 1.0)
    {
        if(!copyFilesThread.isExecuting) { threadHung += sleepInterval; }
        else { threadHung = 0.0f; }
        if(threadHung > 1.0f) { break; }   // ten passes stuck... break

A thread that has not started yet is not a thread that is stuck, and the comment
directly above the loop said so: "sometimes the while() below is reached before
copyFilesThread.isExecuting gets true". One second later the loop gave up, and
what follows it ejects the disc.

Measured on a 40 MB image holding twelve instances in three series, with an index
naming four: before, one series and four images; after,

    HOROSCD: 17 file(s) on the medium, 4 named by the index,
             8 more found by reading it, 12 instance(s) to take

and three series, twelve images, nothing missing.
"""
from pathlib import Path
import re
import sys

root = Path(__file__).resolve().parents[1]
failures = []
scan = (root / 'Horos/Sources/DicomDatabase+Scan.mm').read_bytes().decode('latin1')
defaults = (root / 'Horos/Sources/DefaultsOsiriX.m').read_bytes().decode('latin1')
dicomfile = (root / 'Horos/Sources/DicomFile.mm').read_bytes().decode('latin1')
code = re.sub(r'//[^\n]*', '', scan)

# --- a disc is read by the parser that is still here --------------------------
at = dicomfile.find('-(short) getDicomFile\n')
if at < 0:
    failures.append('-[DicomFile getDicomFile] is gone')
else:
    body = re.sub(r'//[^\n]*', '', dicomfile[at:at + 1200])
    body = body[:body.find('\n}') + 2]
    if 'getDicomFilePapyrus' in body:
        failures.append('a file can still be handed to the Papyrus stub, which answers -1 for '
                        'every file it is given')
    if 'getDicomFileDCMTK' not in body:
        failures.append('DCMTK no longer reads the file')
live = re.sub(r'//[^\n]*', '', dicomfile)
if 'getDicomFilePapyrus' in live:
    failures.append('the stub that stands in for the removed toolkit is still here')
if 'PREFERPAPYRUSFORCD' in live:
    failures.append('the preference that routed discs to the stub is still read')
if 'PREFERPAPYRUSFORCD' in defaults:
    failures.append('the preference that routed discs to the stub is still registered')
for pane in root.glob('Preference Panes/OSIGeneralPreferencePane/*.lproj/'
                      'OSIGeneralPreferencePanePref.xib'):
    if 'PREFERPAPYRUSFORCD' in pane.read_text(encoding='utf-8'):
        failures.append('%s still offers a checkbox bound to it' % pane.parent.name)

# --- the wait -----------------------------------------------------------------
at = code.find('copyFilesThread')
if at < 0:
    failures.append('the copy no longer runs on its own thread')
else:
    if 'threadHung' in code:
        failures.append('the wait still gives up one second after finding the thread not yet '
                        'executing, and the disc is ejected after it')
    if 'copyFilesThread.isFinished == NO' not in code:
        failures.append('the wait no longer waits for the copy to finish')
    if 'waitedForStart' not in code:
        failures.append('nothing bounds how long the copy may take to start')
    eject = code.find('CDDVDEjectAfterAutoCopy')
    if eject < 0:
        failures.append('the eject is gone')
    elif eject < at:
        failures.append('the medium is ejected before the copy is started')
    else:
        condition = code[eject - 200:eject + 300]
        if 'isFinished' not in condition:
            failures.append('the medium is ejected without checking that the copy finished')
        if 'isCancelled' not in condition:
            failures.append('a cancelled copy would still eject the medium')

# --- reading past the index ---------------------------------------------------
if 'ScanDiskBeyondDICOMDIR' not in code:
    failures.append('a DICOMDIR that names part of the medium is still taken as naming all of it')
else:
    at = code.find('BOOL doScan')
    window = code[at:at + 600] if at >= 0 else ''
    if 'usedDicomdir' not in window or 'scanBeyondDicomdir' not in window:
        failures.append('the decision to read the medium does not consider the index being '
                        'incomplete')
    if 'ScanDiskIfDICOMDIRZero' not in window:
        failures.append('the case of an index that names nothing is no longer handled')
    if 'indexedPaths' not in code:
        failures.append('the files the index already named are not skipped, so they would be '
                        'read twice')

if 'ScanDiskBeyondDICOMDIR' not in defaults:
    failures.append('the preference is not registered, so it has no documented default')

# --- and the numbers are on the record ----------------------------------------
if 'named by the index' not in scan or 'instance(s) to take' not in scan:
    failures.append('nothing says how much of the medium was taken before it is ejected')

for failure in failures:
    print('FAIL: %s' % failure)
if failures:
    sys.exit(1)
print('ok: a disc is read by DCMTK, past its index, what was taken is on the record, and it is '
      'ejected only after the copy has finished')
