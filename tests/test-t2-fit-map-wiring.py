#!/usr/bin/env python3
"""Built-in T2 Fit Map is registered and Intel load failures keep a T2 diagnosis."""
from pathlib import Path
import sys

root = Path(__file__).resolve().parents[1]
manager = (root / 'Horos/Sources/PluginManager.m').read_text(encoding='latin1')
viewer = root / 'Horos/Sources/ViewerController+T2FitMap.m'
header = root / 'Horos/Sources/ViewerController+T2FitMap.h'
pbx = (root / 'Horos.xcodeproj/project.pbxproj').read_text(encoding='utf-8')
xib = (root / 'Horos/Resources/en.lproj/Viewer.xib').read_text(encoding='latin1', errors='replace')

if 'T2FitMapFilter registerIn:plugins' not in manager:
    print('FAIL: discoverPlugins does not register the built-in T2 Fit Map', file=sys.stderr)
    sys.exit(1)
if 'T2FitMapCompatibility diagnosticForBundleAtPath' not in manager and \
   'T2FitMapCompatibility diagnostic:forBundleAtPath' not in manager:
    print('FAIL: plugin load failures do not ask T2FitMapCompatibility for a diagnosis', file=sys.stderr)
    sys.exit(1)
if not viewer.is_file() or not header.is_file():
    print('FAIL: ViewerController+T2FitMap is missing', file=sys.stderr)
    sys.exit(1)
host = viewer.read_text(encoding='latin1')
if 't2FitMapProcessCurrentSeries' not in host:
    print('FAIL: viewer category does not process the current multi-echo series', file=sys.stderr)
    sys.exit(1)
if 'T2FitMapEngine' not in host:
    print('FAIL: viewer category must fit through T2FitMapEngine', file=sys.stderr)
    sys.exit(1)
if 'newWindow' not in host:
    print('FAIL: a successful fit must open the T2 map in a new 2D viewer', file=sys.stderr)
    sys.exit(1)
if 'T2FitMap.swift' not in pbx:
    print('FAIL: T2FitMap.swift is not in the app target', file=sys.stderr)
    sys.exit(1)
if 'ViewerController+T2FitMap.m' not in pbx:
    print('FAIL: ViewerController+T2FitMap.m is not in the app target', file=sys.stderr)
    sys.exit(1)
if 'T2 Fit Map' in xib or 't2FitMap' in xib:
    print('FAIL: Viewer.xib must stay untouched', file=sys.stderr)
    sys.exit(1)
print('PASS: built-in T2 Fit Map is registered, diagnoses Intel ABI, and fits from the viewer')
