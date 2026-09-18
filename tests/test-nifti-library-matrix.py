#!/usr/bin/env python3
"""The vendored NIfTI library reads the #631 matrix as the format says (#631).

tools/generate-nifti-matrix.py writes NIfTI-1 and Analyze 7.5 files field by
field, with the expectations taken from its own numbers (nibabel agrees with all
of them: tools/verify-nifti-matrix.py). tools/check-nifti-library.py compiles
NIfTI_Library as the Horos target does and checks, case by case: dimensions,
spacing, datatype and magic of the header; every sampled voxel in native byte
order for the six datatypes, both byte orders, one- and two-file NIfTI and
Analyze; scaling as written; qform and sform orientation codes; extension codes
(an unknown ecode no longer hides the rest); and a refusal for every truncated,
empty or impossible file.

Exit 2 (skipped) without numpy or clang.
"""
import subprocess
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
run = subprocess.run([sys.executable, str(root / "tools/check-nifti-library.py"), "--revision", "WORKTREE"],
                     capture_output=True, text=True)
output = (run.stdout + run.stderr).strip()
if run.returncode == 2:
    print(output)
    raise SystemExit(2)
if run.returncode != 0:
    print(output[-4000:])
    raise SystemExit(1)
cases = sum(1 for line in run.stdout.splitlines() if line.split() and line.split()[-1] == "ok")
print(f"ok: the vendored NIfTI library meets the expectations of all {cases} matrix cases")
