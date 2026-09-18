#!/usr/bin/env python3
"""The mean projection is a mode of each ray cast mapper, not of the process (#665).

VTK's mean in Horos was a static flag in the MIP helper, `vtkMeanIPMode`, that
MPRController and CPRController wrote when their own window changed mode and
every mapper of the process read: a 3D viewer in MIP drew a mean once any MPR
or CPR had switched to mean, two MPR windows decided each other's projection,
and a 3D viewer's own mode 3 was a MinIP unless another window had turned the
flag on. Checked here:

* the helper keeps no mode of its own and reads the mode of the mapper that
  draws; the mapper declares it, off by default;
* the 3D view turns it on for mode 3 and off for 0-2, on its own mapper and on
  a fused series' mapper;
* the MPR and CPR controllers set the mode through the view, and nothing in
  the sources or tools writes a process-wide flag any more;
* a ray without a sample no longer divides by zero.

`<git revision>` as an optional argument reads the sources from that revision,
the negative control.
"""
from pathlib import Path
import re
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
revision = sys.argv[1] if len(sys.argv) > 1 else None


def read(path):
    if revision:
        return subprocess.check_output(['git', '-C', str(root), 'show', revision + ':' + path]).decode('latin1')
    return (root / path).read_bytes().decode('latin1')


def files(pattern):
    if revision:
        listing = subprocess.check_output(['git', '-C', str(root), 'ls-tree', '-r', '--name-only', revision]).decode()
        return [name for name in listing.splitlines() if re.fullmatch(pattern, name)]
    return [str(path.relative_to(root)) for path in root.glob('**/*') if re.fullmatch(pattern, str(path.relative_to(root)))]


failures = []
helper = read('Horos/Sources/vtkHorosFixedPointVolumeRayCastMIPHelper.cxx')
mapper = read('Horos/Sources/vtkHorosFixedPointVolumeRayCastMapper.h')
view = read('Horos/Sources/VRView.mm')

if re.search(r'static\s+int\s+vtkMeanIPMode', helper) or 'setvtkMeanIPMode' in helper:
    failures.append('the MIP helper still keeps a process-wide mean flag')
if 'int meanIP = HorosMeanIntensity(mapper);' not in helper:
    failures.append('the MIP helper does not read the mean mode of the mapper that draws')
if not re.search(r'dynamic_cast<vtkHorosFixedPointVolumeRayCastMapper \*>\(mapper\);\s*return horos && horos->GetMeanIntensity\(\);', helper):
    failures.append('the mean mode is not read from the Horos mapper')
if 'maxValue = hits ? total / hits : 0;' not in helper:
    failures.append('a ray without a sample still divides by zero')
for needle in ('void SetMeanIntensity(bool on) { this->MeanIntensity = on; }', 'bool GetMeanIntensity() const { return this->MeanIntensity; }',
               'bool MeanIntensity = false;'):
    if needle not in mapper:
        failures.append('the mapper does not keep its own mean mode, off by default: ' + needle)

def method(source, signature):
    start = source.find(signature)
    if start < 0: return ''
    depth, index = 0, source.index('{', start)
    while True:
        if source[index] == '{': depth += 1
        elif source[index] == '}':
            depth -= 1
            if depth == 0: return source[start:index + 1]
        index += 1

if 'volumeMapper->SetMeanIntensity( modeID == 3);' not in method(view, '- (void) setMode: (long) modeID'):
    failures.append('the 3D view does not set its mapper\'s mean for mode 3 only')
if 'blendingVolumeMapper->SetMeanIntensity( modeID == 3);' not in method(view, '- (void) setBlendingMode: (long) modeID'):
    failures.append('the 3D view does not set a fused series\' mean for mode 3 only')
for name in ('Horos/Sources/MPRController.m', 'Horos/Sources/CPRController.m'):
    controller = read(name)
    if '[mprView1.vrView setMode: clippingRangeMode];' not in controller:
        failures.append(name + ' no longer sets its view\'s mode')
writers = [name for name in files(r'(Horos/Sources|tools)/.*\.(m|mm|h|cxx|cpp|c|py|swift)') if 'setvtkMeanIPMode' in read(name)]
if writers:
    failures.append('the process-wide mean flag is still written by: ' + ', '.join(sorted(writers)))

if failures:
    for failure in failures:
        print('FAIL: ' + failure)
    sys.exit(1)
print('ok: the mean projection is a mode of each mapper, set by its own view (#665)')
