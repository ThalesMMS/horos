#!/usr/bin/env python3
"""#384 A File > Print spools database pages without opening a viewer."""
from pathlib import Path
import sys

root = Path(__file__).resolve().parents[1]
source = (root / 'Horos/Sources/PrintSelection.swift').read_text(encoding='utf-8')
browser = (root / 'Horos/Sources/BrowserController.m').read_bytes().decode('latin1')
header = (root / 'Horos/Sources/BrowserController.h').read_bytes().decode('latin1')

start = browser.find('- (void)printDatabaseSelection:(id)sender')
if start < 0:
    print('FAIL: printDatabaseSelection is missing')
    sys.exit(1)
brace = browser.find('{', start)
depth, index = 0, brace
while index < len(browser):
    if browser[index] == '{':
        depth += 1
    elif browser[index] == '}':
        depth -= 1
        if depth == 0:
            body = browser[brace:index + 1]
            break
    index += 1
else:
    print('FAIL: printDatabaseSelection has no body')
    sys.exit(1)

if 'requiresViewerToSpool' not in source or 'return true' in source.split('requiresViewerToSpool')[1][:80]:
    print('FAIL: database print must not require a viewer')
    sys.exit(1)
if 'Open a viewer to spool' in body:
    print('FAIL: printDatabaseSelection still asks the user to open a viewer')
    sys.exit(1)
if 'spool:prepared' not in body and 'spool:' not in body:
    print('FAIL: printDatabaseSelection must call the Swift spooler')
    sys.exit(1)
if 'DCMPix' not in body:
    print('FAIL: database images must be rasterized with DCMPix, not a viewer')
    sys.exit(1)
if 'printOperationWithView' not in body and 'printDatabaseSpool' not in body:
    print('FAIL: spooled pages must reach NSPrintOperation')
    sys.exit(1)
if 'printDatabaseSpool' in body and 'printDatabaseSpool' not in header:
    print('FAIL: printDatabaseSpool must be declared')
    sys.exit(1)
if 'implementsRegisteredGIF' in source and 'return true' in source.split('implementsRegisteredGIF')[1][:80]:
    print('FAIL: GIF package B must not be claimed here')
    sys.exit(1)
print('PASS: #384 A database print spools raster/PDF pages without a viewer')
