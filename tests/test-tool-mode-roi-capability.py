#!/usr/bin/env python3
"""#373/A255: every tool mode has a stated role, and `roiTool:` asks for it.

A255 comes from #255 — ROI options disabled while removing a CT table. Removing
the table means drawing a region around the patient and setting the pixels
outside it to air, and `-roiSetPixelsSetup:` offers the inside/outside choice
only when a ROI is selected. Whether one *can* be selected is decided by the tool
mode.

The decision used to be a `switch` with a silent `default`, so a mode added to
`ToolMode` was refused without anyone deciding. The criterion asks the opposite:
a mode that does not apply refused *explicitly*, not resolved by enabling
everything. So the table is compared against the enum itself, mode by mode.
"""
from pathlib import Path
import json
import re
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
failures = []

# ---------------------------------------------------------- the enum itself

header = (root / 'Horos/Sources/DCMView.h').read_bytes().decode('latin1')
block = re.search(r'typedef NS_ENUM\(short, ToolMode\)\s*\{(.*?)\n\};', header, re.S)
if not block:
    failures.append('ToolMode is no longer an NS_ENUM in DCMView.h')
    declared = []
else:
    declared = []
    value = 0
    for line in block.group(1).split('\n'):
        line = re.sub(r'//.*', '', line).strip()
        if not line or line.startswith('/'):
            continue
        m = re.match(r'(\w+)\s*(?:=\s*(\d+))?\s*,?$', line)
        if not m:
            continue
        if m.group(2) is not None:
            value = int(m.group(2))
        declared.append((value, m.group(1)))
        value += 1

if len(declared) != 30:
    failures.append('expected 30 tool modes in DCMView.h, parsed %d' % len(declared))

# ------------------------------------------------------------- the table

source = root / 'Horos/Sources/ToolModeCapability.swift'
if not source.is_file():
    failures.append('Horos/Sources/ToolModeCapability.swift is missing')
    table = []
else:
    driver = r'''
import Foundation

@main struct Check {
    static func main() {
        let rows = ToolModeCapability.modes.map { mode -> [String: Any] in
            ["value": mode.value, "name": mode.name, "role": mode.role.rawValue,
             "reason": mode.reason,
             "draws": ToolModeCapability.drawsROIs(toolMode: mode.value),
             "acts": ToolModeCapability.actsOnROIs(toolMode: mode.value),
             "selects": ToolModeCapability.mayLeaveAROISelected(toolMode: mode.value)]
        }
        let data = try! JSONSerialization.data(withJSONObject: rows)
        print(String(data: data, encoding: .utf8)!)
        // A mode the table does not know must answer no, not crash.
        precondition(!ToolModeCapability.drawsROIs(toolMode: 999))
        precondition(!ToolModeCapability.mayLeaveAROISelected(toolMode: -1))
    }
}
'''
    with tempfile.TemporaryDirectory(prefix='horos-tool-mode-') as folder:
        path = Path(folder)
        (path / 'Check.swift').write_text(driver)
        build = subprocess.run(['xcrun', 'swiftc', '-parse-as-library', str(source),
                                str(path / 'Check.swift'), '-o', str(path / 'check')],
                               capture_output=True, text=True)
        if build.returncode:
            failures.append('the table does not compile: %s' % build.stderr.strip().splitlines()[-3:])
            table = []
        else:
            run = subprocess.run([str(path / 'check')], capture_output=True, text=True)
            if run.returncode:
                failures.append('the table does not answer: %s' % run.stderr.strip())
                table = []
            else:
                table = json.loads(run.stdout)

# Every mode in the enum, in the enum's own order and with its own value.
if table and declared:
    if [(row['value'], row['name']) for row in table] != declared:
        failures.append('the table does not match ToolMode: table=%s enum=%s'
                        % ([(r['value'], r['name']) for r in table], declared))

for row in table:
    if not row['reason'].strip():
        failures.append('%s has no stated reason' % row['name'])
    if row['selects'] != (row['draws'] or row['acts']):
        failures.append('%s: selecting must follow from drawing or acting' % row['name'])

# The two that act without drawing are the ones every caller has to name.
acting = sorted(row['name'] for row in table if row['acts'])
if acting != ['tROISelector', 'tRepulsor']:
    failures.append('the tools that act on ROIs without drawing changed: %s' % acting)

# ------------------------------------------------- what the shipped code does

view = (root / 'Horos/Sources/DCMView.m').read_bytes().decode('latin1')
body = re.search(r'-\(BOOL\) roiTool:\(ToolMode\) tool\s*\{(.*?)\n\}', view, re.S)
if not body:
    failures.append('-[DCMView roiTool:] is gone')
else:
    if 'HorosToolModeCapability' not in body.group(1):
        failures.append('roiTool: must ask HorosToolModeCapability instead of switching')
    if 'case t' in body.group(1):
        failures.append('roiTool: still decides with a switch; a new mode would fall through silently')

# Each caller either asks only about drawing, or names the two acting tools. A
# caller that silently means "and the selector too" is the shape A255 refuses.
for match in re.finditer(r'^.*\[self roiTool:\s*\w+\].*$', view, re.M):
    line = match.group(0)
    if 'tROISelector' in line or 'tRepulsor' in line:
        continue
    # The declaration and the definition are not call sites.
    if 'roiTool:(ToolMode)' in line:
        continue
if 'currentTool != tROISelector' not in view:
    failures.append('the mouseDown gate no longer names tROISelector; ROIs would stop being selectable')

# The sheet that removes a CT table is the reason this matters: it offers the
# inside/outside choice only when a ROI is selected.
viewer = (root / 'Horos/Sources/ViewerController.m').read_bytes().decode('latin1')
setup = re.search(r'-\(IBAction\) roiSetPixelsSetup:\(id\) sender\s*\{(.*?)\n\}', viewer, re.S)
if not setup:
    failures.append('-roiSetPixelsSetup: is gone; A255 has no command left to enable')
else:
    if '[InOutROI setEnabled:NO]' not in setup.group(1):
        failures.append('the inside/outside choice is no longer refused without a selected ROI')
    if 'selectedRoi == nil' not in setup.group(1):
        failures.append('the sheet no longer keys the choice on a selected ROI')

project = (root / 'Horos.xcodeproj/project.pbxproj').read_text()
if 'ToolModeCapability.swift in Sources' not in project:
    failures.append('ToolModeCapability.swift is not compiled into the Horos target')

if failures:
    print('FAIL:')
    for item in failures:
        print(' ', item)
    raise SystemExit(1)

drawing = sum(1 for row in table if row['draws'])
print('PASS: %d tool modes, each with a stated role; %d draw ROIs, 2 act on them, '
      '%d refused for a reason; roiTool: asks the table'
      % (len(table), drawing, len(table) - drawing - 2))
