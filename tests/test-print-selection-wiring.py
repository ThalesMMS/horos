#!/usr/bin/env python3
"""#384 A print helper is in the app target; File > Print is not the outline view."""
from pathlib import Path
import sys

root = Path(__file__).resolve().parents[1]
pbx = (root / 'Horos.xcodeproj/project.pbxproj').read_text(encoding='utf-8')
source = root / 'Horos/Sources/PrintSelection.swift'
browser = (root / 'Horos/Sources/BrowserController.m').read_bytes().decode('latin1')
header = (root / 'Horos/Sources/BrowserController.h').read_bytes().decode('latin1')
policy = source.read_text(encoding='utf-8')

if 'PrintSelection.swift' not in pbx:
    print('FAIL: PrintSelection.swift is not in the app target')
    sys.exit(1)
if 'PrintSelection.swift in Sources' not in pbx:
    print('FAIL: PrintSelection.swift is not in a Sources build phase')
    sys.exit(1)
if 'printDatabaseSelection' not in header:
    print('FAIL: BrowserController.h does not declare printDatabaseSelection')
    sys.exit(1)
if 'printDatabaseSelection' not in browser:
    print('FAIL: BrowserController.m does not implement printDatabaseSelection')
    sys.exit(1)
if 'HorosPrintSelection jobFromItems' not in browser:
    print('FAIL: BrowserController must ask the Swift helper for the print job')
    sys.exit(1)
if 'mayPrintOutlineView' not in browser:
    print('FAIL: print: must refuse to print the outline view')
    sys.exit(1)
if 'implementsRegisteredGIF' in policy and 'return true' in policy.split('implementsRegisteredGIF')[1][:80]:
    print('FAIL: GIF package B must not be claimed here')
    sys.exit(1)
if '#378' not in policy:
    print('FAIL: GIF dependency on #378 must stay explicit')
    sys.exit(1)
print('PASS: #384 A helper is compiled in; browser print uses the selection, not the table')
