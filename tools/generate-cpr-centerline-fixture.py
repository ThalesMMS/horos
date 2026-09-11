#!/usr/bin/env python3
"""Write patient-space CPR centerlines for the volume-geometry fixture.

The regular stack from tools/generate-volume-geometry-fixture.py starts at
patient (0, 0, 0), 0.5 mm in-plane, 2 mm slices, 64 × 64. Patient X/Y stay
in [0, 32) mm and Z in [0, 30] mm. These files are millimetres in the DICOM
patient frame, not voxel indices. They are not DICOM.

    python3 tools/generate-cpr-centerline-fixture.py <empty dir>
"""
import argparse
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument('destination', type=Path)
arguments = parser.parse_args()

arguments.destination.mkdir(parents=True, exist_ok=True)
if any(arguments.destination.iterdir()):
    raise SystemExit('%s is not empty' % arguments.destination)

# Same three patient-space nodes the interactive Curved MPR session completes.
(arguments.destination / 'interactive-equivalent.txt').write_text(
    '# space=patient\n'
    '# units=mm\n'
    '0 0 0\n'
    '10 0 0\n'
    '10 8 4\n'
)

# A longer centreline that stays inside the regular / isotropic stacks.
(arguments.destination / 'volume-geometry.txt').write_text(
    '# space=patient\n'
    '# units=mm\n'
    '4 16 0\n'
    '8 16 6\n'
    '12 16 12\n'
    '18 14 18\n'
    '24 12 24\n'
    '28 12 30\n'
)

(arguments.destination / 'pixel-labeled.txt').write_text(
    '# space=pixel\n'
    '0 0 0\n'
    '10 0 0\n'
    '10 8 4\n'
)

print('interactive-equivalent.txt  3 patient-mm nodes')
print('volume-geometry.txt         6 patient-mm nodes inside VOL-102')
print('pixel-labeled.txt           refused: not patient space')
