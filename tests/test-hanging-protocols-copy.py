#!/usr/bin/env python3
"""The Protocols pane edits a native copy of HANGINGPROTOCOLS and keeps nothing behind (#618).

tools/probe-hanging-protocols.m is linked with the app's compiled
OSIHangingPreferencePanePref.o (Debug) and drives willSelect/willUnselect with
preferences held in memory - no preferences domain is read or written:

- a stored value: the copy is not the stored object, every nested dictionary and
  array is mutable, what the pane edits does not reach the stored value until it
  is saved, the value saved is the edited copy, dates, data and numbers keep
  their types;
- only the registered value: the same;
- a stored string or array (a damaged preference): no exception, and the stored
  value is left exactly as it was;
- nothing stored or registered: an empty dictionary to edit, no exception;
- 500 visits to one pane with 400 protocols: less than 1 KiB retained per visit.

Before #618 the damaged values raised (`-deepMutableCopy` sent to a string,
`-objectForKey:` to an array) and each visit leaked its deep copy; the numbers are
in docs/donor-delta4-validation.md (#618).

Exit 2 (skipped) without the Debug objects.
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "tools"))
import object_probe  # noqa: E402

pane = object_probe.app_object("OSIHangingPreferencePanePref", "Debug")
if pane is None:
    print("skipped: needs OSIHangingPreferencePanePref.o from a Debug build")
    raise SystemExit(2)
failures = []
with tempfile.TemporaryDirectory(prefix="horos-hanging-protocols-") as temporary:
    probe = Path(temporary) / "probe"
    built = subprocess.run(["xcrun", "clang", "-fno-objc-arc", "-arch", "arm64", "-mmacosx-version-min=26.0",
                            "-framework", "Cocoa", "-framework", "PreferencePanes",
                            str(root / "tools/probe-hanging-protocols.m"), str(pane),
                            "-Wl,-undefined,dynamic_lookup", "-o", str(probe)], capture_output=True, text=True)
    if built.returncode != 0:
        print(built.stderr[-2000:])
        raise SystemExit(1)
    # A selector is not an undefined symbol, and strings(1) does not list the method
    # names of an object file: look for the bytes.
    if b"deepMutableCopy\0" in pane.read_bytes():
        failures.append("the pane still sends -deepMutableCopy")
    run = subprocess.run([str(probe), "check"], capture_output=True, text=True, timeout=120)
    if run.returncode != 0:
        print(run.stderr[-2000:])
        raise SystemExit(1)
    result = json.loads(run.stdout.strip().splitlines()[-1])

cases = {case["case"]: case for case in result["cases"]}
for name in ("stored", "registered only"):
    case = cases[name]
    if case.get("exception"):
        failures.append(f"{name}: {case['exception']}")
        continue
    for key, wanted in (("copy_is_stored_object", False), ("mutable_throughout", True), ("stored_untouched_before_save", True),
                        ("wrote", True), ("stored_after_equals_copy", True)):
        if bool(case.get(key)) != wanted:
            failures.append(f"{name}: {key} is {case.get(key)} (immutable at {case.get('immutable_paths')})")
    types = case.get("first_protocol_types", {})
    if "Date" not in types.get("Created", "") or "Data" not in types.get("Blob", "") or types.get("Comparative") != "0.5":
        failures.append(f"{name}: the saved protocol lost its types: {types}")
for name in ("stored string", "stored array"):
    case = cases[name]
    if case.get("exception"):
        failures.append(f"{name}: {case['exception']}")
    if not case.get("stored_after_equals_before"):
        failures.append(f"{name}: the damaged value was overwritten")
case = cases["nothing"]
if case.get("exception") or not case.get("mutable_throughout"):
    failures.append(f"nothing stored: {case}")
if result["retained_bytes_per_visit"] > 1024:
    failures.append(f"{result['retained_bytes_per_visit']:.0f} bytes retained per visit")

for failure in failures:
    print("FAIL:", failure)
if failures:
    raise SystemExit(1)
print(f"ok: the pane copies natively, isolates and keeps its edits typed, leaves damaged values alone, "
      f"and retains {result['retained_bytes_per_visit']:.0f} bytes per visit")
