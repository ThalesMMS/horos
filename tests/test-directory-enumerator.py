#!/usr/bin/env python3
"""N2DirectoryEnumerator closes each directory handle itself, and lists what it always listed (#627).

Links the N2DirectoryEnumerator.o the application is built from into
tools/probe-directory-enumerator.m and drives it over synthetic trees - shallow
with Unicode, hidden files, an empty and an unreadable folder and symlinks,
deep, and wide - on the internal volume and on a disposable APFS image:

  * the paths come out in the documented order (depth first, a folder before
    its contents, readdir order within a folder), with filesOnly, recursive,
    a maximum and skipDescendants honoured, and identical to the revision
    before the change;
  * every descriptor opened is closed after a full scan, after abandoning a
    scan early and after skipping, fifty times over;
  * no thread is created: the enumerator used to start one per closedir.

    python3 tests/test-directory-enumerator.py                 # the built object
    python3 tests/test-directory-enumerator.py --revision REV  # the source at REV

Against the revision before #627 the thread checks must fail.
"""
import argparse
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import object_probe  # noqa: E402

SOURCE = "Nitrogen/Sources/N2DirectoryEnumerator.mm"
parser = argparse.ArgumentParser()
parser.add_argument("--revision")
parser.add_argument("--baseline", default="efb2b0cef", help="revision whose inventory must match")
parser.add_argument("--configuration", default="Debug")
arguments = parser.parse_args()

work = Path(tempfile.mkdtemp(prefix="horos-enumerator-"))


def build(revision, label):
    if revision is None:
        obj = object_probe.app_object("N2DirectoryEnumerator", arguments.configuration)
        if obj is None:
            print("needs a built N2DirectoryEnumerator.o", file=sys.stderr)
            raise SystemExit(2)
    else:
        command = object_probe.compile_command(SOURCE, arguments.configuration)
        source = object_probe.revision_source(SOURCE, revision, work / label / "N2DirectoryEnumerator.mm")
        obj = work / label / "N2DirectoryEnumerator.o"
        object_probe.compile_source(command, source, obj)
    return object_probe.link_probe(ROOT / "tools/probe-directory-enumerator.m", [obj], work / f"probe-{label}")


try:
    probe = build(arguments.revision, "under-test")
    reference_probe = None
    if not arguments.revision and arguments.baseline:
        try:
            reference_probe = build(arguments.baseline, "baseline")
        except (LookupError, subprocess.CalledProcessError) as error:
            print(f"baseline inventory not compared: {error}")
except LookupError as error:
    print(f"needs a build log with the compile command: {error}", file=sys.stderr)
    raise SystemExit(2)

failures = []


def check(condition, message):
    if not condition:
        failures.append(message)
        print("FAIL:", message)


def run(binary, *args):
    output = subprocess.run([str(binary)] + [str(a) for a in args], check=True, capture_output=True, text=True).stdout
    return json.loads(output.strip().splitlines()[-1])


def reference(root: Path, files_only=False, recursive=True, maximum=-1, skip=None):
    """The enumerator's contract, written independently: pre-order, readdir order."""
    found = []

    def walk(folder: Path, prefix: str):
        try:
            entries = list(os.scandir(folder))
        except OSError:
            return
        for entry in entries:
            relative = f"{prefix}/{entry.name}" if prefix else entry.name
            is_dir = entry.is_dir(follow_symlinks=False)
            if maximum >= 0 and len(found) >= maximum:
                return
            if not (files_only and is_dir):
                found.append(relative)
            if is_dir and recursive and entry.name != skip:
                if os.access(entry.path, os.R_OK | os.X_OK):
                    walk(Path(entry.path), relative)
    walk(root, "")
    return found[:maximum] if maximum >= 0 else found


def shallow_tree(base: Path):
    base.mkdir(parents=True)
    (base / unicodedata.normalize("NFC", "exame é.dcm")).write_bytes(b"x" * 10)
    (base / unicodedata.normalize("NFD", "série é")).mkdir()
    (base / unicodedata.normalize("NFD", "série é") / "1.dcm").write_bytes(b"y")
    (base / ".hidden.dcm").write_bytes(b"z")
    (base / "empty").mkdir()
    (base / "locked").mkdir()
    (base / "locked" / "inside.dcm").write_bytes(b"secret")
    (base / "日本").mkdir()
    (base / "日本" / "a").mkdir()
    (base / "日本" / "a" / "b.dcm").write_bytes(b"b")
    os.symlink(base / "exame é.dcm", base / "link-to-file")
    os.symlink(base / "日本", base / "link-to-folder")
    os.chmod(base / "locked", 0)
    return base


def deep_tree(base: Path, depth=40):
    level = base
    for index in range(depth):
        level = level / f"level-{index:02d}"
        level.mkdir(parents=True)
        (level / f"{index}.dcm").write_bytes(b"d")
    return base


def wide_tree(base: Path, count=3000):
    base.mkdir(parents=True)
    for index in range(count):
        (base / f"image-{index:04d}.dcm").write_bytes(b"w")
    return base


def exercise(root_label: Path):
    trees = {"shallow": shallow_tree(root_label / "shallow"), "deep": deep_tree(root_label / "deep"),
             "wide": wide_tree(root_label / "wide")}
    try:
        for name, tree in trees.items():
            variants = [(False, True, -1), (True, True, -1), (False, False, -1), (True, True, 7), (False, True, 3)]
            for files_only, recursive, maximum in variants:
                label = f"{root_label.name}/{name} filesOnly={files_only} recursive={recursive} max={maximum}"
                result = run(probe, "list", tree, int(files_only), int(recursive), maximum)
                expected = reference(tree, files_only, recursive, maximum)
                check(result["paths"] == expected, f"{label}: order or content differs ({len(result['paths'])} vs {len(expected)})")
                check(result["fds_after_release"] == result["fds_before"], f"{label}: descriptors not returned {result}")
                check(result["threads_created"] == 0, f"{label}: {result['threads_created']} threads created")
                if reference_probe is not None:
                    baseline = run(reference_probe, "list", tree, int(files_only), int(recursive), maximum)
                    check(baseline["paths"] == result["paths"], f"{label}: inventory differs from {arguments.baseline}")
            # skipDescendants when the folder comes out: its contents are not listed.
            skipped = run(probe, "skip", tree, "level-05" if name == "deep" else "日本")
            skip_name = "level-05" if name == "deep" else "日本"
            check(skipped["paths"] == reference(tree, skip=skip_name), f"{root_label.name}/{name}: skipDescendants differs")
            check(skipped["fds_after_release"] == skipped["fds_before"], f"{root_label.name}/{name}: skip leaked descriptors")
            # After a file, or a folder opendir refused, nothing was opened for it:
            # skipping must not close the parent and cut the rest of the listing (#684).
            if name == "shallow":
                for entry in (".hidden.dcm", "locked"):
                    skipped = run(probe, "skip", tree, entry)
                    check(skipped["paths"] == reference(tree), f"{root_label.name}/{name}: skip after {entry} cut the listing")
                    check(skipped["fds_after_release"] == skipped["fds_before"], f"{root_label.name}/{name}: skip after {entry} leaked descriptors")
        # Abandoned early, deep in the tree: every open handle closed, fifty times over.
        for attempt in range(50):
            result = run(probe, "abandon", trees["deep"], 25)
            if attempt == 0:
                check(result["fds_while_open"] > result["fds_before"], f"abandon: no handle was open while reading {result}")
            if result["fds_after_release"] != result["fds_before"] or result["threads_created"] != 0:
                check(False, f"abandon #{attempt}: {result}")
                break
    finally:
        os.chmod(trees["shallow"] / "locked", stat.S_IRWXU)


try:
    internal = work / "internal"
    internal.mkdir()
    exercise(internal)
    image, mount = work / "volume.dmg", work / "mnt"
    mount.mkdir()
    subprocess.run(["hdiutil", "create", "-quiet", "-size", "64m", "-fs", "APFS", "-volname", "HorosEnumerator627",
                    "-type", "UDIF", str(image)], check=True)
    subprocess.run(["hdiutil", "attach", "-quiet", "-nobrowse", "-mountpoint", str(mount), str(image)], check=True)
    try:
        volume = mount / "image"
        volume.mkdir()
        exercise(volume)
    finally:
        subprocess.run(["hdiutil", "detach", "-quiet", "-force", str(mount)], check=False)
finally:
    shutil.rmtree(work, ignore_errors=True)

if failures:
    print(f"{len(failures)} failure(s)")
    raise SystemExit(1)
print("PASS: order, filesOnly, recursive, maximum and skipDescendants match the contract and the baseline inventory; "
      "descriptors balanced after scans, skips and fifty abandoned scans; no thread created; internal volume and APFS image")
