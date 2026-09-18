#!/usr/bin/env python3
"""The functional reference #625's benchmark compares against.

At efb2b0cef, -imageByScalingProportionallyToSize: leaves the Lanczos scale at
zero when the size asked for is the image's own, and returns an empty picture:
a timing of that is not a timing of scaling. The reference is efb2b0cef's
Nitrogen/Sources/NSImage+N2.mm with that branch taken for every size - the
scale is then computed (1 for the same size) - and nothing else changed.

    python3 tools/make-scaling-reference.py out/NSImage+N2.mm
"""
import argparse
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASELINE = "efb2b0cef"
SOURCE = "Nitrogen/Sources/NSImage+N2.mm"
GUARD = b"if( NSEqualSizes( imageSize, targetSize) == NO)"

parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument("output", type=Path)
arguments = parser.parse_args()
text = subprocess.run(["git", "-C", str(ROOT), "show", f"{BASELINE}:{SOURCE}"], capture_output=True, check=True).stdout
method = text.index(b"- (NSImage*)imageByScalingProportionallyToSize:(NSSize)targetSize\n")
guard = text.index(GUARD, method)
if text.find(GUARD, guard + 1) != -1:
    raise SystemExit("the guard appears more than once in the method: the reference would be ambiguous")
reference = text[:guard] + b"if( YES) // functional reference (#625): the scale is computed for the same size too" + \
    text[guard + len(GUARD):]
arguments.output.parent.mkdir(parents=True, exist_ok=True)
arguments.output.write_bytes(reference)
print(f"{arguments.output}: {BASELINE} with the same-size scale fixed")
