#!/usr/bin/env python3
"""Metal is the default renderer in the 2D viewer, the MPR and volume rendering.

Source level, with `<git revision>` as an optional argument for the negative
control:

* the 2D viewer and the MPR read an absent per-window flag as on, so a window
  renders with Metal without a visit to the contextual menu;
* a fresh profile registers the Metal engine for volume rendering, and the
  graphics board probe no longer writes an engine over it;
* the preference pane and the 3D window can both show that engine: their
  matrices carry a cell tagged 2 and have the room to draw it;
* the planar Metal 4 pilot stays opt-in, as #609 measured and decided.
"""
from pathlib import Path
from xml.etree import ElementTree
import re
import subprocess
import sys

root = Path(__file__).resolve().parents[1]


def read(path):
    if len(sys.argv) > 1:
        return subprocess.check_output(['git', '-C', str(root), 'show', sys.argv[1] + ':' + path]).decode('latin1')
    return (root / path).read_bytes().decode('latin1')


def body(source, signature):
    """The method body that follows `signature`, up to its closing brace."""
    start = source.find(signature)
    if start < 0:
        return ''
    start = source.find('{', start)
    return source[start:source.find('\n}', start)]


failures = []

# --- an absent per-window flag means Metal ----------------------------------
for path, signature, name in [
        ('Horos/Sources/PlanarHostBridge.m', '- (BOOL)horosPlanarMetalEnabled', 'the 2D viewer'),
        ('Horos/Sources/MPRHostBridge.m', '- (BOOL)horosMPRMetalEnabled', 'the MPR')]:
    getter = body(read(path), signature)
    if not getter:
        failures.append('%s has no enabled flag to read' % name)
    elif not re.search(r'boolValue\s*:\s*YES', getter):
        failures.append('%s treats an absent flag as off, so Metal is not the default' % name)

# --- a fresh profile gets the Metal engine ----------------------------------
defaults = read('Horos/Sources/DefaultsOsiriX.m')
registered = re.search(r'setObject:\s*@"(\d)"\s*forKey:\s*@"MAPPERMODEVR"', defaults)
if not registered:
    failures.append('no engine is registered for volume rendering')
elif registered.group(1) != '2':
    failures.append('volume rendering registers engine %s, not Metal' % registered.group(1))
if 'HorosPlanarMetal4Pilot' in defaults:
    failures.append('the Metal 4 pilot is registered as a default; #609 decided it stays opt-in')

# --- the board probe picks a view size, not an engine -----------------------
probe = body(read('Horos/Sources/VRView.mm'), '+ (void) testGraphicBoard')
if not probe:
    failures.append('the graphics board probe is gone')
for written in re.findall(r'setInteger:\s*(\d)\s*forKey:\s*@"MAPPERMODEVR"', probe):
    if written != '2':
        failures.append('the board probe writes engine %s over the Metal default' % written)

# --- the blended volume still has a mapper under the default engine ---------
blending = body(read('Horos/Sources/VRView.mm'), '- (void) setBlendingEngine: (long) engineID showWait:')
if not blending:
    failures.append('the blending engine setter is gone')
elif 'case 2' not in blending:
    failures.append('engine 2 leaves the blended volume without a mapper, so fusion volume rendering cannot draw')

# --- both radio matrices can show engine 2 ----------------------------------
for path, keypath in [
        ('Preference Panes/OSI3DPreferencePane/Base.lproj/OSI3DPreferencePanePref.xib', 'values.MAPPERMODEVR'),
        ('Preference Panes/OSI3DPreferencePane/ja-JP.lproj/OSI3DPreferencePanePref.xib', 'values.MAPPERMODEVR'),
        ('Horos/Resources/en.lproj/VR.xib', 'selection.engine'),
        ('Horos/Resources/ja-JP.lproj/VR.xib', 'selection.engine')]:
    tree = ElementTree.fromstring(read(path).encode('latin1'))
    matrices = [m for m in tree.iter('matrix')
                if any(b.get('keyPath') == keypath for b in m.iter('binding'))]
    if len(matrices) != 1:
        failures.append('%s: %d matrices bound to %s' % (path, len(matrices), keypath))
        continue
    matrix = matrices[0]
    cells = [c for c in matrix.iter('buttonCell') if c.get('key') != 'prototype']
    tags = [c.get('tag', '0') for c in cells]
    if '2' not in tags:
        failures.append('%s: the engine list has no Metal cell, so the default cannot be shown' % path)
    if len(set(tags)) != len(tags):
        failures.append('%s: two engine cells share a tag' % path)
    # A cell the matrix has no room to draw is a cell the user cannot pick.
    def size(key, axis):
        found = [s for s in matrix.iter('size') if s.get('key') == key]
        return float(found[0].get(axis)) if found else 0.0
    frame = [r for r in matrix.iter('rect') if r.get('key') == 'frame']
    needed = len(cells) * size('cellSize', 'height') + (len(cells) - 1) * size('intercellSpacing', 'height')
    if frame and size('cellSize', 'height') and float(frame[0].get('height')) + 0.5 < needed:
        failures.append('%s: the matrix is %s tall and its %d cells need %g'
                        % (path, frame[0].get('height'), len(cells), needed))

# --- the pilot is still chosen by hand --------------------------------------
if 'UserDefaults.standard.bool(forKey: PlanarBackend.pilotDefaultsKey)' not in read('Horos/Sources/PlanarHostRenderer.swift'):
    failures.append('the planar backend no longer reads the pilot preference as an opt-in')

if failures:
    for failure in failures:
        print('FAIL:', failure)
    raise SystemExit(1)
print('ok: Metal is the default in the viewer, the MPR and volume rendering, and the pilot stays opt-in')
