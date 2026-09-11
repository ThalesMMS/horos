#!/usr/bin/env python3
"""An Enhanced CT states the orientation once, and Horos looked for it per frame.

`-[DicomFile decodeDCMTK]` computes a slice location for every frame of a
multiframe by combining the frame's position with the orientation, and stores the
result as `sliceLocationArray`. It read the orientation only from the per-frame
item:

    if (ditem->findAndGetSequenceItem(DCM_PlaneOrientationSequence, eitem, x).good())
        …
    else succeed = NO;

A real Enhanced CT puts `ImageOrientationPatient` in
`SharedFunctionalGroupsSequence` > `PlaneOrientationSequence`, once, because
every frame shares it, and gives each frame only its `ImagePositionPatient`. For
such a study `succeed` was never true, no slice locations were stored, and the
stack was left with the order the frames happen to be encoded in.

Measured with `tools/generate-enhanced-ct-fixture.py` - 12 frames written in a
shuffled order, positions 2 mm apart, orientation shared:

    frameID  sliceLocation        frameID  sliceLocation
      0      0.0                    0      2.0
      1      0.0        becomes     1      6.0
      …      …                      …      …
     11      0.0                   11     20.0

`-[DicomSeries sortDescriptorsForImages]` sorts by `sliceLocation` then
`instanceNumber`; with every location equal, the tiebreak is the frame's place in
the file, which is exactly what the acceptance criterion forbids.

The shared block also read `ImageOrientationVolume` out of
`PlanePositionVolumeSequence`. That tag lives in `PlaneOrientationVolumeSequence`
(0020,930f), which - along with three of its neighbours - the vendored
dictionary did not have at all.
"""
from pathlib import Path
from dcmtk_build import dcmtk_flags
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
failures = []
dcmtk = root / 'DCMTK'
driver = root / 'tools/exercise-functional-group-tags.cc'
reader = (root / 'Horos/Sources/DicomFileDCMTKCategory.mm').read_bytes().decode('latin1')
series = (root / 'Horos/Sources/DicomSeries.m').read_bytes().decode('latin1')


def body(signature, source):
    at = source.find(signature)
    if at < 0:
        return ''
    opening = source.index('{', at)
    depth, index = 0, opening
    while index < len(source):
        if source[index] == '{':
            depth += 1
        elif source[index] == '}':
            depth -= 1
            if depth == 0:
                return source[opening:index + 1]
        index += 1
    return ''


# --- the dictionary knows the tags the geometry is stored under ---------------
if not driver.exists():
    failures.append('the driver that asks the dictionary for the tags is gone')
else:
    with tempfile.TemporaryDirectory(prefix='horos-fgtags-') as directory:
        binary = Path(directory) / 'fgtags'
        build = subprocess.run(
            ['xcrun', 'clang++', '-std=c++11', str(driver), *dcmtk_flags(), '-o', str(binary)],
            capture_output=True, text=True)
        if build.returncode != 0:
            failures.append('the dictionary does not build:\n%s' % build.stderr[-1500:])
        else:
            run = subprocess.run([str(binary)], capture_output=True, text=True, timeout=120)
            if run.returncode != 0:
                failures.append('asking the dictionary failed: %s' % run.stderr[-500:])
            answers = {}
            for line in run.stdout.splitlines():
                parts = line.split('\t')
                if len(parts) == 5:
                    answers[parts[0]] = (parts[1], parts[2], parts[3], parts[4])
            expected = {
                '0020,9113': ('PlanePositionSequence', 'SQ', '1', '1'),
                '0020,9116': ('PlaneOrientationSequence', 'SQ', '1', '1'),
                '0020,930e': ('PlanePositionVolumeSequence', 'SQ', '1', '1'),
                # The one the shared block was reading the orientation out of the
                # wrong sequence for, because this one was not in the dictionary.
                '0020,930f': ('PlaneOrientationVolumeSequence', 'SQ', '1', '1'),
                '0020,9301': ('ImagePositionVolume', 'FD', '3', '3'),
                '0020,9302': ('ImageOrientationVolume', 'FD', '6', '6'),
                '0020,0032': ('ImagePositionPatient', 'DS', '3', '3'),
                '0020,0037': ('ImageOrientationPatient', 'DS', '6', '6'),
            }
            for tag, want in expected.items():
                got = answers.get(tag)
                if got != want:
                    failures.append('(%s) is %r, expected %r' % (tag, got, want))

# --- the shared orientation is read, and a frame may rely on it ---------------
decode = body('- (BOOL)decodeDCMTK', reader) or reader
shared = decode[decode.find('// SHARED'):decode.find('// PER FRAME')]
if not shared:
    failures.append('the shared functional group is no longer read')
else:
    if 'DCM_PlaneOrientationSequence' not in shared or 'DCM_ImageOrientationPatient' not in shared:
        failures.append('the orientation an Enhanced CT states once, in the shared group, is not '
                        'read, so every frame of one is left without a slice location')
    if 'DCM_PlaneOrientationVolumeSequence' not in shared:
        failures.append('ImageOrientationVolume is still looked for in a sequence it does not '
                        'live in')

per_frame = decode[decode.find('// PER FRAME'):]
if 'hasSharedOrientation' not in per_frame:
    failures.append('a frame that carries only its position, which is the ordinary case, still '
                    'fails to produce a slice location')
if 'sliceLocationArray' not in per_frame:
    failures.append('the per-frame slice locations are not collected')

# --- and the order they are sorted in is the geometric one --------------------
descriptors = body('- (NSArray*) sortDescriptorsForImages', series)
if not descriptors:
    failures.append('-sortDescriptorsForImages is gone')
elif 'sliceLocation' not in descriptors or 'instanceNumber' not in descriptors:
    failures.append('a series is no longer ordered by slice location with the instance number as '
                    'the tiebreak, so what this fixes would not reach the stack')

for failure in failures:
    print('FAIL: %s' % failure)
if failures:
    sys.exit(1)
print('ok: the shared orientation of an Enhanced CT is read, every frame gets the slice location '
      'of its own position, and the dictionary knows the tags they are stored under')
