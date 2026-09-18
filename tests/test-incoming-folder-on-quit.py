#!/usr/bin/env python3
"""Quitting sends a non-empty INCOMING folder to the Trash, and touches nothing in TEMP (#629).

The cleanup listed INCOMING.noindex and then deleted and trashed each name
inside TEMP.noindex. Compiles Horos/Sources/IncomingFolderOnQuit.swift with a
driver and runs it on a disposable APFS volume, so the Trash involved is that
volume's own: an empty folder and one holding only .DS_Store stay put; a folder
with received files goes to the Trash whole, contents intact. Then checks that
AppController's quit cleanup asks it, and composes no TEMP.noindex path from the
INCOMING listing any more.

    python3 tests/test-incoming-folder-on-quit.py [REV]
"""
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
revision = sys.argv[1] if len(sys.argv) > 1 else None


def read(relative):
    if revision:
        result = subprocess.run(["git", "-C", str(ROOT), "show", f"{revision}:{relative}"], capture_output=True)
        return result.stdout.decode("latin1") if result.returncode == 0 else None
    path = ROOT / relative
    return path.read_bytes().decode("latin1") if path.exists() else None


failures = []


def check(condition, message):
    if not condition:
        failures.append(message)
        print("FAIL:", message)


swift = read("Horos/Sources/IncomingFolderOnQuit.swift")
controller = read("Horos/Sources/AppController.m")
check(swift is not None, "there is no IncomingFolderOnQuit.swift")

block = controller.split("// EMPTY THE INCOMING.noindex DIRECTORY", 1)[1].split("confirmDirectoryAtPath: incomingDirectoryPath", 1)[0]
check("tempDirectory" not in block, "the INCOMING cleanup still composes paths in TEMP.noindex")
check("HorosIncomingFolderOnQuit sendToTrashIfPending: incomingDirectoryPath" in block,
      "the INCOMING cleanup does not ask HorosIncomingFolderOnQuit")
check("removeItemAtPath" not in block, "the INCOMING cleanup deletes received files instead of trashing them")

DRIVER = r'''
import Foundation
let root = CommandLine.arguments[1]
func report(_ label: String, _ path: String) {
    do {
        var resulting: NSString?
        try IncomingFolderOnQuit.sendToTrashIfPending(path, resultingPath: &resulting)
        print("\(label)\t\(resulting ?? "-")")
    } catch {
        print("\(label)\terror:\(error.localizedDescription)")
    }
}
report("empty", root + "/empty/INCOMING.noindex")
report("dsstore", root + "/dsstore/INCOMING.noindex")
report("received", root + "/received/INCOMING.noindex")
report("missing", root + "/missing/INCOMING.noindex")
print("pending\t" + IncomingFolderOnQuit.pendingEntries(inFolder: root + "/dsstore/INCOMING.noindex").joined(separator: ","))
'''

if swift is not None and not revision:
    work = Path(tempfile.mkdtemp(prefix="horos-incoming-quit-"))
    image, mount = work / "volume.dmg", work / "mnt"
    mount.mkdir()
    try:
        (work / "IncomingFolderOnQuit.swift").write_text(swift)
        (work / "main.swift").write_text(DRIVER)
        subprocess.run(["xcrun", "swiftc", "-O", str(work / "IncomingFolderOnQuit.swift"), str(work / "main.swift"),
                        "-o", str(work / "driver")], check=True, capture_output=True)
        subprocess.run(["hdiutil", "create", "-quiet", "-size", "32m", "-fs", "APFS", "-volname", "HorosIncoming629",
                        "-type", "UDIF", str(image)], check=True)
        subprocess.run(["hdiutil", "attach", "-quiet", "-nobrowse", "-mountpoint", str(mount), str(image)], check=True)
        (mount / "empty/INCOMING.noindex").mkdir(parents=True)
        (mount / "dsstore/INCOMING.noindex").mkdir(parents=True)
        (mount / "dsstore/INCOMING.noindex/.DS_Store").write_bytes(b"\0" * 64)
        received = mount / "received/INCOMING.noindex"
        (received / "study é").mkdir(parents=True)
        (received / ".transfer.dcm").write_bytes(os.urandom(2048))
        (received / "study é" / "image.dcm").write_bytes(os.urandom(4096))
        digests = {p.relative_to(received): hashlib.sha256(p.read_bytes()).hexdigest()
                   for p in received.rglob("*") if p.is_file()}
        output = subprocess.run([str(work / "driver"), str(mount)], check=True, capture_output=True, text=True).stdout
        answers = dict(line.split("\t", 1) for line in output.rstrip("\n").split("\n"))
        check(answers["empty"] == "-" and (mount / "empty/INCOMING.noindex").is_dir(), f"empty folder: {answers['empty']}")
        check(answers["dsstore"] == "-" and (mount / "dsstore/INCOMING.noindex/.DS_Store").exists(),
              f".DS_Store only: {answers['dsstore']}")
        check(answers["pending"] == "", f".DS_Store counted as pending: {answers['pending']!r}")
        check(answers["missing"] == "-", f"missing folder: {answers['missing']}")
        trashed = Path(answers["received"])
        check(not received.exists(), "received folder still in place")
        check(os.path.realpath(trashed).startswith(os.path.realpath(mount) + "/.Trashes/"),
              f"received folder went to {trashed}, not the volume's Trash")
        check(trashed.is_dir() and {p.relative_to(trashed): hashlib.sha256(p.read_bytes()).hexdigest()
                                    for p in trashed.rglob("*") if p.is_file()} == digests,
              "received files changed on the way to the Trash")
    finally:
        subprocess.run(["hdiutil", "detach", "-quiet", "-force", str(mount)], check=False)
        shutil.rmtree(work, ignore_errors=True)

if failures:
    print(f"{len(failures)} failure(s)")
    raise SystemExit(1)
print("PASS: empty and .DS_Store-only folders stay, a folder with received files goes whole to its volume's Trash, "
      "and the quit cleanup no longer composes TEMP.noindex paths")
