#!/usr/bin/env python3
"""NSThread (N2): a block thread keeps its contract, and progress details notify when they change (#626).

Links the NSThread+N2.o the application is built from into
tools/probe-thread-block.m and checks what the callers rely on:
+performBlockInBackground: starts at once and returns the NSThread the block
runs on, off the calling thread; the block has its own autorelease pool; an
exception it raises is contained; captures are released once it has run, even
while the caller still holds the thread; it runs to the end when nobody keeps
the thread; cancellation is cooperative and the thread dictionary is shared.
-setProgressDetails: notifies exactly when the details read change - including
a detail that reads like the status, nil inside a nested operation and leaving
one - with every will paired with a did, on a background thread and on the
calling one; the other keys the category notifies by hand notify once per
change and not for a repeat (no automatic KVO notification on top).

    python3 tests/test-thread-block.py                 # the built object
    python3 tests/test-thread-block.py --revision REV  # the source at REV

Against the revision before #626 the notification checks must fail.
"""
import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import object_probe  # noqa: E402

SOURCE = "Nitrogen/Sources/NSThread+N2.mm"
parser = argparse.ArgumentParser()
parser.add_argument("--revision")
parser.add_argument("--configuration", default="Debug")
arguments = parser.parse_args()

work = Path(tempfile.mkdtemp(prefix="horos-thread-block-"))
support = [object_probe.app_object(name, arguments.configuration) for name in ("N2Debug", "NSException+N2")]
if any(o is None for o in support):
    print("needs built N2Debug.o and NSException+N2.o", file=sys.stderr)
    raise SystemExit(2)
if arguments.revision:
    try:
        command = object_probe.compile_command(SOURCE, arguments.configuration)
    except LookupError as error:
        print(f"needs a build log with the compile command: {error}", file=sys.stderr)
        raise SystemExit(2)
    source = object_probe.revision_source(SOURCE, arguments.revision, work / "NSThread+N2.mm")
    obj = work / "NSThread+N2.o"
    object_probe.compile_source(command, source, obj)
else:
    obj = object_probe.app_object("NSThread+N2", arguments.configuration)
    if obj is None:
        print("needs a built NSThread+N2.o", file=sys.stderr)
        raise SystemExit(2)
probe = object_probe.link_probe(ROOT / "tools/probe-thread-block.m", [obj] + support, work / "probe",
                                frameworks=("Cocoa",))
result = json.loads(subprocess.run([str(probe), "contract"], check=True, capture_output=True, text=True,
                                   timeout=120).stdout.strip().splitlines()[-1])
print(f"object under test: {obj}")
failures = []


def check(condition, message):
    if not condition:
        failures.append(message)
        print("FAIL:", message)


for key in ("returned_class_is_thread", "ran", "same_thread_object", "ran_off_main", "finished",
            "autoreleased_inside_block_released", "captures_released_while_thread_is_held",
            "captures_released_after_thread_release", "runs_to_end_unheld", "exception_contained",
            "thread_dictionary_shared", "cancel_observed", "cancelled_finishes"):
    check(result.get(key) is True, f"{key}: {result.get(key)}")

EXPECTED = [("same text as the status", 1, "Loading"), ("same content, another object", 0, "Loading"),
            ("new text", 1, "Step 2"), ("same text again", 0, "Step 2"), ("nil", 1, None), ("nil again", 0, None),
            ("text equal to a later status", 1, "Step 3"),
            ("enter a nested operation", 0, "Step 3"), ("nested: the details around it", 0, "Step 3"),
            ("nested: new text", 1, "Nested"), ("nested: nil shows the details around it", 1, "Step 3"),
            ("nested: nil again", 0, "Step 3"), ("nested: text before leaving", 1, "Leaving"),
            ("leave the nested operation", 1, "Step 3"), ("enter and leave without details", 0, "Step 3")]
for where in ("details_background", "details_current"):
    sequence = result.get(where) or {}
    steps = sequence.get("steps", [])
    observed = [(s["step"], s["notified"], s["value"]) for s in steps]
    for expected, seen in zip(EXPECTED, observed + [None] * (len(EXPECTED) - len(observed))):
        check(expected == seen, f"{where}: expected {expected}, observed {seen}")
    check(sequence.get("will") == sequence.get("did"), f"{where}: will {sequence.get('will')} vs did {sequence.get('did')}")

# Every key the category notifies by hand: one notification for a change, none for the same value again.
keys = result.get("key_notifications") or {}
for key in ("status", "progress", "supportsCancel", "supportsBackgrounding", "uniqueId", "isCancelled"):
    check(keys.get(key) == [1, 0], f"{key}: notifications for a change and for a repeat {keys.get(key)}, expected [1, 0]")

# Recorded, not judged here: a thread may not report isExecuting yet right after
# -start. DCMTKQueryNode's retrieve loop polls isExecuting (see the issue it has).
print(f"not executing yet right after start: {result['not_yet_executing_right_after_start_of_300']} of 300")

if failures:
    print(f"{len(failures)} failure(s)")
    raise SystemExit(1)
print("PASS: immediate start off the calling thread, same NSThread object, pool drained, exception contained, "
      "captures released after running, runs unheld, cooperative cancel, shared dictionary, "
      "progress details notify exactly when the value read changes (nested operations included) with paired "
      "will/did, and every hand-notified key notifies once per change")
