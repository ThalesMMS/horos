#!/usr/bin/env python3
"""Trashing an item never deletes another one, and a failure leaves it in place (#613).

Links the NSFileManager+N2.o the application is built from and drives both
forms of -moveItemAtPathToTrash: on synthetic items:

  * a Unicode file and a nested Unicode folder go to the Trash with every byte;
  * two items with the same name both survive in the Trash;
  * empty, nil and missing paths, a refused move (read-only parent) and a
    read-only volume report failure and leave the source untouched;
  * on a second, disposable APFS volume the system chooses that volume's own
    Trash, and two same-named items trashed there both survive.

Only items this test creates are touched. Each is identified by a random name;
the ones the system put in the home Trash are moved back out by the path it
returned and removed from the scratch folder; the disk images are detached.

    python3 tests/test-trash-disposal.py                  # the built object
    python3 tests/test-trash-disposal.py --revision REV   # a source revision

Against the revision before the fix only the void form exists, so only the
same-name scenario on the disposable volume runs - and it must fail.
"""
import argparse
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unicodedata
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import object_probe  # noqa: E402

SOURCE = "Nitrogen/Sources/NSFileManager+N2.mm"
HOME_TRASH = Path.home() / ".Trash"

parser = argparse.ArgumentParser()
parser.add_argument("--revision")
parser.add_argument("--configuration")
arguments = parser.parse_args()

scratch = Path(tempfile.mkdtemp(prefix="horos-trash-test-"))
if arguments.revision:
    configuration = arguments.configuration or "Debug"
    try:
        command = object_probe.compile_command(SOURCE, configuration)
    except (LookupError, FileNotFoundError) as error:
        print(f"needs a {configuration} build log with the compile command: {error}", file=sys.stderr)
        raise SystemExit(2)
    source = object_probe.revision_source(SOURCE, arguments.revision, scratch / "NSFileManager+N2.mm")
    obj = scratch / "NSFileManager+N2.o"
    object_probe.compile_source(command, source, obj)
else:
    obj = (object_probe.app_object("NSFileManager+N2", arguments.configuration)
           if arguments.configuration else object_probe.first_app_object("NSFileManager+N2"))
    if obj is None:
        print("needs a built NSFileManager+N2.o under build/Build/Intermediates.noindex", file=sys.stderr)
        raise SystemExit(2)
probe = object_probe.link_probe(ROOT / "tools/probe-trash.m", [obj], scratch / "probe")
print(f"object under test: {obj}")

failures = []
to_restore = []   # (path the system returned, expected digest) - moved back out at the end
home_leftovers = []  # exact home-Trash paths the old revision used, removed after checking their digest
images = []


def check(condition, message):
    if not condition:
        failures.append(message)
        print("FAIL:", message)


def digest(path: Path):
    if path.is_dir():
        entries = []
        for current, directories, files in os.walk(path):
            directories.sort()
            for name in sorted(files):
                item = Path(current) / name
                entries.append((str(item.relative_to(path)), hashlib.sha256(item.read_bytes()).hexdigest()))
        return hashlib.sha256(json.dumps(entries).encode()).hexdigest()
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(mode, path):
    output = subprocess.run([str(probe), mode, "<nil>" if path is None else str(path)],
                            check=True, capture_output=True, text=True).stdout
    return json.loads(output.strip().splitlines()[-1])


def unique(label):
    return f"horos-trash-test-{uuid.uuid4().hex[:12]}-{label}"


def make_file(folder: Path, name: str, size=4096):
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / name
    path.write_bytes(os.urandom(size))
    return path


def make_folder(folder: Path, name: str):
    path = folder / name
    (path / "série" / "日本").mkdir(parents=True)
    (path / "série" / "日本" / "image.dcm").write_bytes(os.urandom(2048))
    (path / "notes.txt").write_text("synthetic")
    return path


def attach(label, readonly_with=None):
    image = scratch / f"{label}.dmg"
    mount = scratch / f"mnt-{label}"
    mount.mkdir()
    subprocess.run(["hdiutil", "create", "-quiet", "-size", "64m", "-fs", "APFS", "-volname", f"HorosTrash{label}",
                    "-type", "UDIF", str(image)], check=True)
    if readonly_with:
        subprocess.run(["hdiutil", "attach", "-quiet", "-nobrowse", "-mountpoint", str(mount), str(image)], check=True)
        for name, data in readonly_with.items():
            (mount / name).write_bytes(data)
        subprocess.run(["hdiutil", "detach", "-quiet", str(mount)], check=True)
        mount.mkdir(exist_ok=True)
        subprocess.run(["hdiutil", "attach", "-quiet", "-readonly", "-nobrowse", "-mountpoint", str(mount), str(image)],
                       check=True)
    else:
        subprocess.run(["hdiutil", "attach", "-quiet", "-nobrowse", "-mountpoint", str(mount), str(image)], check=True)
    images.append(mount)
    return mount


def volume_trash_items(mount: Path, prefix: str):
    """Items under this user's folder of a disposable volume's Trash.

    `.Trashes` itself is write-and-search only (1333), so it cannot be listed;
    the per-user folder inside it can.
    """
    folder = mount / ".Trashes" / str(os.getuid())
    return [folder / name for name in os.listdir(folder) if name.startswith(prefix)] if folder.is_dir() else []


try:
    if not arguments.revision:
        home = scratch / "home"
        # 1-2. A Unicode file and a nested Unicode folder keep every byte.
        for label, item in [("file", make_file(home, unique(unicodedata.normalize("NFC", "exame é.dcm")))),
                            ("nfd-folder", make_folder(home, unique(unicodedata.normalize("NFD", "série é"))))]:
            before = digest(item)
            answer = run("trash", item)
            check(answer["ok"] and answer["error"] is None, f"{label}: {answer}")
            if answer["ok"]:
                resulting = Path(answer["resulting"])
                to_restore.append((resulting, before))
                check(not item.exists(), f"{label}: the source is still there")
                check(resulting.parent == HOME_TRASH, f"{label}: went to {resulting.parent}, not the home Trash")
                check(resulting.exists() and digest(resulting) == before, f"{label}: contents changed in the Trash")

        # 3. Two items with the same name both survive, with their own contents.
        name = unique("same.dcm")
        first, second = make_file(home / "a", name), make_file(home / "b", name)
        digests = [digest(first), digest(second)]
        answers = [run("trash", first), run("trash", second)]
        check(all(a["ok"] for a in answers), f"same name: {answers}")
        if all(a["ok"] for a in answers):
            paths = [Path(a["resulting"]) for a in answers]
            to_restore.extend(zip(paths, digests))
            check(paths[0] != paths[1], f"same name: both ended at {paths[0]}")
            check(all(p.exists() and digest(p) == d for p, d in zip(paths, digests)),
                  "same name: an earlier item was replaced or changed")

        # 4-5. Empty, nil and missing paths fail without effects.
        for label, value in [("empty", ""), ("nil", None), ("missing", str(home / unique("absent")))]:
            answer = run("trash", value)
            check(not answer["ok"] and answer["resulting"] is None and answer["error"], f"{label}: {answer}")
            check(run("trash-void", value) == {"exists_after": False}, f"{label}: void form misbehaved")

        # 6. A move the file system refuses leaves the item where it was.
        locked = home / "locked"
        item = make_file(locked, unique("kept.dcm"))
        before = digest(item)
        os.chmod(locked, stat.S_IRUSR | stat.S_IXUSR)
        try:
            answer = run("trash", item)
            void = run("trash-void", item)
        finally:
            os.chmod(locked, stat.S_IRWXU)
        check(not answer["ok"] and answer["error"], f"refused: reported success {answer}")
        check(item.exists() and digest(item) == before, "refused: the item was altered or removed")
        check(void == {"exists_after": True}, f"refused: void form lost the item {void}")

        # 7. A second volume: the system uses that volume's Trash.
        volume = attach("rw")
        item = make_file(volume, unique("volume é.dcm"))
        folder = make_folder(volume, unique("volume-folder"))
        for label, source in [("volume file", item), ("volume folder", folder)]:
            before = digest(source)
            answer = run("trash", source)
            check(answer["ok"], f"{label}: {answer}")
            if answer["ok"]:
                resulting = Path(answer["resulting"])
                check(os.path.realpath(resulting).startswith(os.path.realpath(volume) + "/"),
                      f"{label}: went to {resulting}, off its volume")
                check(resulting.exists() and digest(resulting) == before, f"{label}: contents changed")
                check(not source.exists(), f"{label}: source still there")

        # 8. A read-only volume: failure, source untouched.
        name = unique("readonly.dcm")
        payload = os.urandom(1024)
        readonly = attach("ro", readonly_with={name: payload})
        answer = run("trash", readonly / name)
        check(not answer["ok"] and answer["error"], f"read-only: {answer}")
        check((readonly / name).read_bytes() == payload, "read-only: the item changed")

    # 9. Same name twice through the void form, on a disposable volume: both
    #    items must still exist somewhere in a Trash. The revision before the
    #    fix deleted the first one to make room for the second.
    shared = attach("void")
    name = unique("void-same.dcm")
    first, second = make_file(shared / "one", name), make_file(shared / "two", name)
    digests = {digest(first), digest(second)}
    for item in (first, second):
        answer = run("trash-void", item)
        check(answer == {"exists_after": False}, f"void same name: {item} was not trashed ({answer})")
    survivors = volume_trash_items(shared, name.rsplit(".", 1)[0])
    home_copy = HOME_TRASH / name
    if home_copy.exists():
        home_leftovers.append(home_copy)
        survivors.append(home_copy)
    found = {digest(path) for path in survivors if path.is_file()}
    check(found == digests, f"void same name: {len(digests - found)} of 2 items no longer exist anywhere")
finally:
    for resulting, expected in to_restore:
        if resulting.exists() and digest(resulting) == expected:
            back = scratch / "restored" / resulting.name
            back.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(resulting), str(back))
    for leftover in home_leftovers:
        # Created by this test under a random name and checked by content above.
        if leftover.name.startswith("horos-trash-test-") and leftover.is_file():
            leftover.unlink()
    for mount in images:
        subprocess.run(["hdiutil", "detach", "-quiet", "-force", str(mount)], check=False)
    shutil.rmtree(scratch, ignore_errors=True)

if failures:
    print(f"{len(failures)} failure(s)")
    raise SystemExit(1)
print("PASS: Unicode file and folder, same name twice, empty/nil/missing, refused move, second volume, "
      "read-only volume, void form keeps both same-named items")
