#!/usr/bin/env python3
"""A 3D preset group that empties out does not take the panel with it.

The preset panel has a fixed number of preview slots and a group has any number
of presets, so every refresh decides three things. The arithmetic was inline and
got two of them wrong the moment a group turned out to be empty - the last preset
of a group deleted while the panel is open, then any refresh (Revert Series calls
one):

  - the loop that blanks the unused slots compared `int i` against
    `[presetPreviewArray count]`, an NSUInteger. With i == -1 the comparison
    promotes to a huge unsigned number, `-1 < 9` is false, and the slots keep the
    previous group's thumbnails;
  - slot 0 was selected regardless, -[VRController updatePresetInfoPanel] asked
    the empty list for its first preset, and NSRangeException unwound out of
    whatever had asked for the refresh.

Reproduced against the running application, with the backtrace ending in
updatePresetInfoPanel. The arithmetic is now one Swift type, exercised here for
the cases the inline loop could not state.
"""
from pathlib import Path
import re
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
failures = []
vr = (root / 'Horos/Sources/VRController.mm').read_bytes().decode('latin1')

at = vr.find('- (void)displayPresetsForSelectedGroup;\n{')
body = vr[at:vr.index('\n}', at) + 2] if at >= 0 else ''
if not body:
    failures.append('displayPresetsForSelectedGroup is gone')
else:
    for wanted in ('HorosPresetPageLayout clampPage:', 'HorosPresetPageLayout presetIndicesForPage:',
                   'HorosPresetPageLayout selectableSlotForPage:'):
        if wanted not in body:
            failures.append('the refresh no longer asks for %s' % wanted)
    # The shapes that went wrong: a signed index walked against an unsigned count,
    # and slot 0 selected whatever was there.
    if 'i--' in body or 'int i, n;' in body:
        failures.append('the signed index walk is back in displayPresetsForSelectedGroup')
    if re.search(r'objectAtIndex:\s*0\]\s*setSelected', body):
        failures.append('slot 0 is selected again without asking whether it holds a preset')
    # And a page with nothing on it has nothing selected: the ring has to go too,
    # or Apply still looks like it would do something.
    if 'setSelectedPresetPreview: nil' not in body or 'hideSelectionFrame' not in body:
        failures.append('a page with no preset on it keeps the previous selection ring')
preview = (root / 'Horos/Sources/VRPresetPreview.mm').read_bytes().decode('latin1')
if '- (void)hideSelectionFrame;' not in preview or 'setSelectedState:NO]' not in preview:
    failures.append('VRPresetPreview cannot put its selection frame away')

# The number of pages comes from the same place, so an empty group cannot reach a
# division that is only accidentally safe.
if re.search(r'presetPageMax\s*=\s*\(\(long\)', vr):
    failures.append('presetPageMax is computed by hand again')
if 'HorosPresetPageLayout pageCountForPresetCount:' not in vr:
    failures.append('the page count no longer comes from the layout')

# Both places that turn a selection into a preset have to survive a stale one.
for name, marker in (('updatePresetInfoPanel', '- (void)updatePresetInfoPanel;'),
                     ('load3DSettings:', '- (IBAction)load3DSettings:(id)sender;')):
    at = vr.find(marker)
    section = vr[at:at + 2600] if at >= 0 else ''
    if not section:
        failures.append('%s is gone' % name)
        continue
    if re.search(r'objectAtIndex:\s*\[selectedPresetPreview index\]', section):
        failures.append('%s still indexes the settings list with the raw selection' % name)
    if 'selected >= (NSInteger) [settingsList count]' not in section:
        failures.append('%s does not check the selection against the list it is about to index'
                        % name)

for failure in failures:
    print('FAIL: %s' % failure)
reported = len(failures)

main = r'''import Foundation

let slots = 9

// An empty group still has a page, that page holds nothing, and nothing on it
// can be selected. That is the case the inline loop could not say.
precondition(PresetPageLayout.pageCount(presetCount: 0, slots: slots) == 1)
precondition(PresetPageLayout.presetIndices(page: 0, presetCount: 0, slots: slots)
             == Array(repeating: NSNotFound, count: slots))
precondition(PresetPageLayout.selectableSlot(page: 0, presetCount: 0, slots: slots) == -1)

// A full page, a partial page, and the slots after the last preset.
precondition(PresetPageLayout.pageCount(presetCount: 9, slots: slots) == 1)
precondition(PresetPageLayout.pageCount(presetCount: 10, slots: slots) == 2)
precondition(PresetPageLayout.pageCount(presetCount: 15, slots: slots) == 2)
precondition(PresetPageLayout.presetIndices(page: 0, presetCount: 15, slots: slots)
             == Array(0 ..< 9))
precondition(PresetPageLayout.presetIndices(page: 1, presetCount: 15, slots: slots)
             == Array(9 ..< 15) + Array(repeating: NSNotFound, count: 3))
precondition(PresetPageLayout.selectableSlot(page: 1, presetCount: 15, slots: slots) == 0)

// A page left over from a longer group comes back into range instead of running
// off the end of a shorter one.
precondition(PresetPageLayout.clamp(page: 5, presetCount: 4, slots: slots) == 0)
precondition(PresetPageLayout.clamp(page: -3, presetCount: 40, slots: slots) == 0)
precondition(PresetPageLayout.clamp(page: 3, presetCount: 40, slots: slots) == 3)
precondition(PresetPageLayout.presetIndices(page: 99, presetCount: 4, slots: slots)
             == Array(0 ..< 4) + Array(repeating: NSNotFound, count: 5))

// Every slot is accounted for, on every page, for a range of group sizes: no
// preset is shown twice and none is left out.
for count in 0 ... 40 {
    var seen: [Int] = []
    for page in 0 ..< PresetPageLayout.pageCount(presetCount: count, slots: slots) {
        let indices = PresetPageLayout.presetIndices(page: page, presetCount: count, slots: slots)
        precondition(indices.count == slots)
        seen += indices.filter { $0 != NSNotFound }
        let selectable = PresetPageLayout.selectableSlot(page: page, presetCount: count, slots: slots)
        if indices.contains(where: { $0 != NSNotFound }) {
            precondition(selectable >= 0 && indices[selectable] != NSNotFound)
        } else {
            precondition(selectable == -1)
        }
    }
    precondition(seen == Array(0 ..< count), "group of \(count) laid out as \(seen)")
}

// A panel with no slots at all asks for nothing rather than dividing by zero.
precondition(PresetPageLayout.pageCount(presetCount: 12, slots: 0) == 1)
precondition(PresetPageLayout.presetIndices(page: 0, presetCount: 12, slots: 0).isEmpty)
precondition(PresetPageLayout.selectableSlot(page: 0, presetCount: 12, slots: 0) == -1)

print("PASS: every preset lands in exactly one slot, and an empty page selects nothing")
'''

with tempfile.TemporaryDirectory(prefix='horos-preset-layout-') as tmp:
    p = Path(tmp)
    (p / 'main.swift').write_text(main)
    build = subprocess.run(['swiftc', str(root / 'Horos/Sources/PresetPageLayout.swift'),
                            str(p / 'main.swift'), '-o', str(p / 'test')],
                           capture_output=True, text=True)
    if build.returncode:
        print(build.stderr.strip()[-2000:])
        sys.exit('the layout did not compile')
    checks = subprocess.run([str(p / 'test')], capture_output=True, text=True)
    print((checks.stdout + checks.stderr).strip())
    if checks.returncode:
        failures.append('the page layout does not hold for every group size')

for failure in failures[reported:]:
    print('FAIL: %s' % failure)
if failures:
    sys.exit(1)
print('ok: the preset panel lays out its slots without walking off either end')
