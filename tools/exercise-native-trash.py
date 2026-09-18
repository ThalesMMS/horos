#!/usr/bin/env python3
"""Quit the built app so its cleanup has to use the Trash, on a disposable volume (#613).

At termination Horos deletes its DUMP working folder and, when the delete
fails, hands the folder to -[NSFileManager moveItemAtPathToTrash:]. This puts
the isolated database on a fresh APFS disk image, drops a file with the
immutable flag into DUMP (so the delete fails), and first sends an unrelated
synthetic folder *also named DUMP* to that volume's Trash. (DUMP rather than
TEMP.noindex: at launch the app moves TEMP.noindex's contents to INCOMING, and
the INCOMING cleanup has its own defect, #629.)
It then quits the app through XML-RPC `KillOsiriX` - the real termination path -
and checks:

  * the working folder left the database for the Trash of its own volume, with
    the immutable file byte for byte;
  * the earlier, same-named item in that Trash is untouched;
  * nothing about the home Trash changed for that name;
  * the app did not log a cleanup failure.

The image is detached at the end; the home Trash is only checked with
`exists` for the one name, never listed.

    python3 tools/exercise-native-trash.py --out local-validation/delta4/613-app
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
import xmlrpc.client
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import native_app  # noqa: E402

parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument("--out", type=Path, required=True)
parser.add_argument("--app", type=Path, default=native_app.DEVELOPMENT_APP)
parser.add_argument("--port", type=int, default=18613)
parser.add_argument("--scenario", choices=("dump", "incoming"), default="dump",
                    help="dump: #613 as described above; incoming: #629 - a file still in "
                         "INCOMING.noindex at quit sends that folder, whole, to its volume's Trash")
arguments = parser.parse_args()

out = arguments.out.resolve()
out.mkdir(parents=True, exist_ok=True)
image = out / "volume.dmg"
mount = out / "mnt"
for stale in (image,):
    if stale.exists():
        stale.unlink()
mount.mkdir(exist_ok=True)
subprocess.run(["hdiutil", "create", "-quiet", "-size", "256m", "-fs", "APFS", "-volname", "HorosTrash613",
                "-type", "UDIF", str(image)], check=True)
subprocess.run(["hdiutil", "attach", "-quiet", "-nobrowse", "-mountpoint", str(mount), str(image)], check=True)

failures = []
result = {"volume": str(mount)}


def check(condition, message):
    result.setdefault("checks", []).append({"check": message, "ok": bool(condition)})
    if not condition:
        failures.append(message)
        print("FAIL:", message)


def manifest(folder: Path):
    entries = {}
    for current, directories, files in os.walk(folder):
        for name in files:
            path = Path(current) / name
            entries[str(path.relative_to(folder))] = hashlib.sha256(path.read_bytes()).hexdigest()
    return entries


def _xmlrpc_ready(port: int) -> bool:
    import socket
    with socket.socket() as probe:
        probe.settimeout(0.5)
        return probe.connect_ex(("127.0.0.1", port)) == 0


STAGER = r"""
#import <Foundation/Foundation.h>
int main(int argc, char **argv) { @autoreleasepool {
    NSURL *resulting = nil; NSError *error = nil;
    if (![NSFileManager.defaultManager trashItemAtURL:[NSURL fileURLWithPath:@(argv[1])] resultingItemURL:&resulting error:&error]) {
        fprintf(stderr, "%s\n", error.description.UTF8String); return 1;
    }
    printf("%s\n", resulting.path.fileSystemRepresentation);
}}
"""


def system_trash(path: Path) -> str:
    """Stage an item with the system API directly, independent of the code under test."""
    source, binary = out / "stage-trash.m", out / "stage-trash"
    if not binary.exists():
        source.write_text(STAGER)
        subprocess.run(["xcrun", "clang", "-fobjc-arc", str(source), "-framework", "Foundation", "-o", str(binary)],
                       check=True)
    return subprocess.run([str(binary), str(path)], capture_output=True, text=True, check=True).stdout.strip()


home_same_name = Path.home() / ".Trash" / "DUMP"
result["home_trash_had_DUMP_before"] = home_same_name.exists()
process = None
volume_trash = mount / ".Trashes" / str(os.getuid())
try:
    # An unrelated item with the same name, already discarded on this volume.
    earlier = mount / "earlier" / "DUMP"
    (earlier / "notes").mkdir(parents=True)
    (earlier / "notes" / "keep me.txt").write_text("discarded earlier; must survive")
    (earlier / "payload.bin").write_bytes(os.urandom(16384))
    earlier_manifest = manifest(earlier)
    earlier_trashed = Path(system_trash(earlier))
    check(earlier_trashed.is_dir() and manifest(earlier_trashed) == earlier_manifest, "earlier item staged in the volume Trash")
    result["earlier_item"] = str(earlier_trashed)

    database = mount / "db"
    log = out / "horos.log"
    native_app.stop_all(arguments.app)
    process = native_app.launch(database, log, ["-httpXMLRPCServer", "1", "-httpXMLRPCServerPort", str(arguments.port),
                                                "-DoNotEmptyIncomingDir", "NO"], app=arguments.app)
    data = native_app.database_folder(database)
    native_app.wait_for(lambda: (data / "Database.sql").is_file() and (data / "DUMP").is_dir(), 90,
                        description="the database to open on the disposable volume")
    temp = data / "DUMP"
    (temp / "locked").mkdir(exist_ok=True)
    locked = temp / "locked" / "series é.dcm"
    locked.write_bytes(os.urandom(32768))
    subprocess.run(["/usr/bin/chflags", "uchg", str(locked)], check=True)
    locked_digest = hashlib.sha256(locked.read_bytes()).hexdigest()
    if arguments.scenario == "incoming":
        # A dot name is a transfer still being written: the importer leaves it
        # alone, so it is still in INCOMING when the app quits.
        incoming = data / "INCOMING.noindex"
        pending = incoming / ".transfer in progress é.dcm"
        pending.write_bytes(os.urandom(8192))
        pending_digest = hashlib.sha256(pending.read_bytes()).hexdigest()
    native_app.wait_for(lambda: _xmlrpc_ready(arguments.port), 60, description="the XML-RPC interface")
    started = time.monotonic()
    try:
        xmlrpc.client.ServerProxy(f"http://127.0.0.1:{arguments.port}/").KillOsiriX({})
    except (xmlrpc.client.Fault, ConnectionError, OSError, xmlrpc.client.ProtocolError):
        pass  # the app may close the connection while quitting
    code = process.wait(timeout=90)
    result["quit_s"] = round(time.monotonic() - started, 2)
    result["exit_code"] = code
    text = log.read_text(errors="replace")

    if arguments.scenario == "incoming":
        trashed = [volume_trash / name for name in os.listdir(volume_trash)] if volume_trash.is_dir() else []
        moved = [p for p in trashed if (p / pending.name).is_file()]
        check(len(moved) == 1, f"INCOMING went whole to its volume's Trash ({[p.name for p in trashed]})")
        if moved:
            result["incoming_trashed_to"] = str(moved[0])
            check(hashlib.sha256((moved[0] / pending.name).read_bytes()).hexdigest() == pending_digest,
                  "the pending file kept every byte")
        check(incoming.is_dir() and not any(incoming.iterdir()), "INCOMING.noindex recreated empty")
        check("FAILED to clean the INCOMING.noindex" not in text, "no INCOMING cleanup failure logged")
    check(not (temp / "locked").exists(), "the DUMP folder with the locked file left the database folder")
    trashed = [volume_trash / name for name in os.listdir(volume_trash)] if volume_trash.is_dir() else []
    moved = [p for p in trashed if p != earlier_trashed and (p / "locked" / "series é.dcm").is_file()]
    check(len(moved) == 1, f"the working folder is in the volume's own Trash ({[p.name for p in trashed]})")
    if moved:
        result["trashed_to"] = str(moved[0])
        check(hashlib.sha256((moved[0] / "locked" / "series é.dcm").read_bytes()).hexdigest() == locked_digest,
              "the immutable file kept every byte")
    check(earlier_trashed.is_dir() and manifest(earlier_trashed) == earlier_manifest,
          "the earlier same-named item in the Trash is untouched")
    check(home_same_name.exists() == result["home_trash_had_DUMP_before"], "the home Trash was not touched for this name")
    check("FAILED to clean the dumpDirectory" not in text, "no cleanup failure logged")
    check("Could not move" not in text, "no Trash failure logged")
finally:
    if process is not None and process.poll() is None:
        native_app.stop(process)
    subprocess.run(["/usr/bin/chflags", "-R", "nouchg", str(mount)], check=False, capture_output=True)
    subprocess.run(["hdiutil", "detach", "-quiet", "-force", str(mount)], check=False)
    if image.exists():
        image.unlink()

(out / "results.json").write_text(json.dumps(result, indent=1, ensure_ascii=False) + "\n")
print(json.dumps(result, indent=1, ensure_ascii=False))
raise SystemExit(1 if failures else 0)
