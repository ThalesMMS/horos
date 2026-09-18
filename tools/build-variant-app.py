#!/usr/bin/env python3
"""Build a development bundle that differs from HEAD only in named files.

For an in-app A/B of one change, both bundles come from the same checkout and
the same incremental Debug build; the baseline bundle has the changed files as
they were at the baseline revision. The files are put back and the checkout is
rebuilt afterwards, so the build folder again holds HEAD's objects (the
object-level tests link them).

    python3 tools/build-variant-app.py --name 627-baseline \\
        --file Nitrogen/Sources/N2DirectoryEnumerator.mm=efb2b0cef
    python3 tools/build-variant-app.py --name 627-candidate

Each bundle lands in build/Variants/<name>/HorosDevelopment.app with a
variant.json naming HEAD, the swapped files and their revisions.
"""
import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import native_app  # noqa: E402

parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument("--name", required=True)
parser.add_argument("--file", action="append", default=[], help="path=revision")
arguments = parser.parse_args()


def git(*args, **kwargs):
    return subprocess.run(["git", "-C", str(ROOT)] + list(args), check=True, capture_output=True, **kwargs)


swaps = []
for item in arguments.file:
    path, _, revision = item.partition("=")
    if not revision:
        parser.error(f"--file needs path=revision: {item}")
    if git("status", "--porcelain", "--", path, text=True).stdout.strip():
        raise SystemExit(f"{path} has uncommitted changes; commit or stash them first")
    swaps.append((path, revision))

head = git("rev-parse", "HEAD", text=True).stdout.strip()


def build():
    native_app.stop_all()
    result = subprocess.run([str(ROOT / "script/build_and_run.sh"), "--verify"], capture_output=True, text=True)
    native_app.stop_all()
    log = (ROOT / "build/logs/build-and-run.log").read_text(errors="replace")
    if result.returncode != 0 or "** BUILD SUCCEEDED **" not in log:
        raise SystemExit(f"build failed:\n{result.stdout[-2000:]}\n{result.stderr[-2000:]}")


destination = ROOT / "build/Variants" / arguments.name / "HorosDevelopment.app"
try:
    for path, revision in swaps:
        (ROOT / path).write_bytes(git("show", f"{revision}:{path}").stdout)
    build()
    if destination.parent.exists():
        shutil.rmtree(destination.parent)
    destination.parent.mkdir(parents=True)
    subprocess.run(["/usr/bin/ditto", str(ROOT / "build/Development/HorosDevelopment.app"), str(destination)], check=True)
    (destination.parent / "variant.json").write_text(json.dumps(
        {"head": head, "swapped": [{"path": p, "revision": r} for p, r in swaps]}, indent=1) + "\n")
finally:
    if swaps:
        git("checkout", "--", *[path for path, _ in swaps])
if swaps:
    build()
print(destination)
