#!/usr/bin/env python3
"""The medium size estimate counts what goes on the medium, and nothing else (#632).

Links the BurnerWindowController.o and DefaultsOsiriX.o the application is
built from into tools/probe-burn-size-estimate.m and runs
-estimateFolderSize: over synthetic selections - small and large files, Unicode
names - with the launcher preference absent (the app's registered value),
true and false (a value persisted by an older version), Weasis on and off, and
a supplementary folder on, off, pointing nowhere and at a path longer than 300 bytes
(its size used to be read through a 300-byte buffer). The oracle is computed
from the files themselves with the estimate's own units: each file's size in
KiB rounded down, 17 MiB for Weasis, `du -sk` of the supplementary folder, the
sum shown in MB with two decimals.

No launcher is put on the medium, so no case may count one.

    python3 tests/test-burn-size-estimate.py                 # the built objects
    python3 tests/test-burn-size-estimate.py --revision REV  # the sources at REV

Against the revision before #632 the cases that count the launcher fail by
exactly 8 x 1024 KiB.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import object_probe  # noqa: E402

SOURCES = {"BurnerWindowController": "Horos/Sources/BurnerWindowController.m",
           "DefaultsOsiriX": "Horos/Sources/DefaultsOsiriX.m"}
parser = argparse.ArgumentParser()
parser.add_argument("--revision")
parser.add_argument("--configuration", default="Debug")
arguments = parser.parse_args()

work = Path(tempfile.mkdtemp(prefix="horos-burn-estimate-"))
objects = []
for name, source in SOURCES.items():
    if arguments.revision:
        try:
            command = object_probe.compile_command(source, arguments.configuration)
        except LookupError as error:
            print(f"needs a build log with the compile command: {error}", file=sys.stderr)
            raise SystemExit(2)
        copy = object_probe.revision_source(source, arguments.revision, work / "src" / Path(source).name)
        obj = work / f"{name}.o"
        object_probe.compile_source(command, copy, obj)
    else:
        obj = object_probe.app_object(name, arguments.configuration)
        if obj is None:
            print(f"needs a built {name}.o", file=sys.stderr)
            raise SystemExit(2)
    objects.append(obj)
support = object_probe.app_object("N2Debug", arguments.configuration)
if support is None:
    print("needs a built N2Debug.o", file=sys.stderr)
    raise SystemExit(2)
probe = object_probe.link_probe(ROOT / "tools/probe-burn-size-estimate.m", objects + [support], work / "probe",
                                frameworks=("Cocoa", "DiscRecording", "DiscRecordingUI", "IOKit", "AVFoundation"))

# The selection: small, large and Unicode-named files.
selection = work / "selection"
selection.mkdir()
sizes = {"tiny.dcm": 300, "exactly-one-kib.dcm": 1024, "medium.dcm": 700_123, "large.dcm": 9_500_000,
         "estudo-coração-é.dcm": 2_048_001, "画像-日本語.dcm": 65_536}
files = []
for name, size in sizes.items():
    path = selection / name
    with open(path, "wb") as handle:
        handle.truncate(size)
        handle.seek(0)
        handle.write(b"DICM")
    files.append(str(path))
supplementary = work / "supplementary"
(supplementary / "sub").mkdir(parents=True)
(supplementary / "readme.txt").write_bytes(os.urandom(3000))
(supplementary / "sub" / "viewer.bin").write_bytes(os.urandom(1_200_000))
supplementary_kib = int(subprocess.run(["/usr/bin/du", "-sk", str(supplementary)], capture_output=True, text=True,
                                       check=True).stdout.split()[0])
# du's line for this one does not fit the 300 bytes the size used to be read through.
long_supplementary = work / "supplementary-long"
while len(str(long_supplementary).encode()) <= 400:
    long_supplementary = long_supplementary / "pasta suplementar com um nome bem comprido, ção"
long_supplementary.mkdir(parents=True)
(long_supplementary / "notes.bin").write_bytes(os.urandom(500_000))
long_kib = int(subprocess.run(["/usr/bin/du", "-sk", str(long_supplementary)], capture_output=True, text=True,
                              check=True).stdout.split()[0])

cases = []
for launcher in ("absent", True, False):
    for weasis in (False, True):
        for extra in ("off", "on", "missing", "long"):
            defaults = {"BurnWeasis": weasis}
            if launcher != "absent":
                defaults["BurnOsirixApplication"] = launcher
            if extra == "on":
                defaults.update(BurnSupplementaryFolder=True, SupplementaryBurnPath=str(supplementary))
            elif extra == "long":
                defaults.update(BurnSupplementaryFolder=True, SupplementaryBurnPath=str(long_supplementary))
            elif extra == "missing":
                defaults.update(BurnSupplementaryFolder=True, SupplementaryBurnPath=str(work / "nowhere"))
            else:
                defaults.update(BurnSupplementaryFolder=False)
            cases.append({"name": f"launcher={launcher} weasis={weasis} supplementary={extra}", "files": files,
                          "defaults": defaults, "weasis": weasis, "extra": extra})
cases.append({"name": "empty selection, launcher=True", "files": [], "defaults": {"BurnOsirixApplication": True},
              "weasis": False, "extra": "off"})
(work / "cases.json").write_text(json.dumps(cases))
run = subprocess.run([str(probe), str(work / "cases.json")], capture_output=True, text=True, timeout=120)
if run.returncode != 0:
    print(run.stdout[-2000:], run.stderr[-4000:])
    raise SystemExit(1)
results = {r["name"]: r for r in json.loads(run.stdout.strip().splitlines()[-1])}
print(f"objects under test: {', '.join(str(o) for o in objects)}")

failures = []
PATTERN = re.compile(r"No of files: (\d+)\s+Files size \(without compression\): ([\d.]+)MB")
for case in cases:
    text = results[case["name"]]["text"]
    match = PATTERN.search(text)
    if not match:
        failures.append(f"{case['name']}: unreadable estimate {text!r}")
        continue
    kib = sum(os.path.getsize(f) // 1024 for f in case["files"])
    if case["weasis"]:
        kib += 17 * 1024
    if case["extra"] == "on":
        kib += supplementary_kib
    elif case["extra"] == "long":
        kib += long_kib
    expected = f"{kib / 1024.0:3.2f}"
    count, shown = int(match.group(1)), match.group(2)
    if count != len(case["files"]) or shown != expected:
        shown_kib = float(shown) * 1024
        failures.append(f"{case['name']}: shows {count} files, {shown} MB; expected {len(case['files'])} files, "
                        f"{expected} MB (difference {shown_kib - kib:+.0f} KiB)")
for failure in failures:
    print("FAIL:", failure)
if failures:
    print(f"{len(failures)} failure(s)")
    raise SystemExit(1)
print(f"PASS: {len(cases)} selections (small, large and Unicode files; launcher preference absent, true and false; "
      "Weasis on and off; supplementary folder on, off, missing and at a path over 400 bytes) estimate exactly the "
      "files, Weasis and the "
      "supplementary folder, and never a launcher")
