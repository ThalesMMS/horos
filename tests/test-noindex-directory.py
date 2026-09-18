#!/usr/bin/env python3
"""`confirmNoIndexDirectoryAtPath:` resolves the right folder and deletes nothing (#612).

Links the NSFileManager+N2.o the application is built from and drives it on
real temporary folders: names with and without the suffix, empty and nil
requests, a legacy folder with nested content, both folders at once, a file in
the way, a rename that the file system refuses, and names that are short,
nested or Unicode. Every folder that should survive is compared by content
hash before and after.

    python3 tests/test-noindex-directory.py                 # the built object
    python3 tests/test-noindex-directory.py --revision REV  # a source revision

The second form recompiles the file as it was at REV with the app's own flags;
run against the revision before the fix, it must fail.
"""
import argparse
import hashlib
import json
import os
import stat
import subprocess
import sys
import tempfile
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import object_probe  # noqa: E402

SOURCE = "Nitrogen/Sources/NSFileManager+N2.mm"

parser = argparse.ArgumentParser()
parser.add_argument("--revision")
parser.add_argument("--configuration", default=None)
arguments = parser.parse_args()

scratch = Path(tempfile.mkdtemp(prefix="horos-noindex-"))
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

probe = object_probe.link_probe(ROOT / "tools/probe-noindex-directory.m", [obj], scratch / "probe")
print(f"object under test: {obj}")


def confirm(path):
    output = subprocess.run([str(probe), "confirm", "<nil>" if path is None else str(path)],
                            check=True, capture_output=True, text=True).stdout
    return json.loads(output.strip().splitlines()[-1])


def manifest(folder: Path):
    """Relative path → (kind, sha256) for everything under a folder, the folder included."""
    entries = {".": ("dir", "")}
    for current, directories, files in os.walk(folder):
        for name in directories:
            entries[str((Path(current) / name).relative_to(folder))] = ("dir", "")
        for name in files:
            path = Path(current) / name
            entries[str(path.relative_to(folder))] = ("file", hashlib.sha256(path.read_bytes()).hexdigest())
    return entries


def populate(folder: Path, label: str):
    folder.mkdir(parents=True)
    (folder / "sentinel").write_text(label)
    (folder / "sub" / "déjà vu").mkdir(parents=True)
    (folder / "sub" / "déjà vu" / "image.dcm").write_bytes(os.urandom(4096))
    (folder / "empty").mkdir()
    return manifest(folder)


def fresh(name):
    folder = scratch / "cases" / name
    folder.mkdir(parents=True)
    return folder


def listing(folder: Path):
    return sorted(str(p.relative_to(folder)) for p in folder.rglob("*"))


failures = []


def check(condition, message):
    if not condition:
        failures.append(message)
        print("FAIL:", message)


# 1. A name without the suffix gains it; short, nested and Unicode names alike.
for label, name in [("short", "x"), ("nested", "a/b/c/Incoming"), ("nfc", unicodedata.normalize("NFC", "Imagens é")),
                    ("nfd", unicodedata.normalize("NFD", "Imagens é")), ("cjk", "日本語"), ("space", "Horos Data")]:
    root = fresh(f"unsuffixed-{label}")
    requested = root / name
    expected = requested.parent / (requested.name + ".noindex")
    answer = confirm(requested)
    check(answer == {"result": str(expected)}, f"{label}: {answer} != {expected}")
    check(expected.is_dir(), f"{label}: {expected} was not created")
    check(not requested.exists(), f"{label}: the unsuffixed name was created too")
    check(not list(root.rglob("*.noindex.noindex")), f"{label}: a doubled suffix appeared")

# 2. A name with the suffix keeps it, including a trailing slash.
for label, name in [("database", "DATABASE.noindex"), ("minimal", "a.noindex"), ("slash", "INCOMING.noindex/")]:
    root = fresh(f"suffixed-{label}")
    expected = root / name.rstrip("/")
    answer = confirm(str(root / name))
    check(answer == {"result": str(expected)}, f"{label}: {answer} != {expected}")
    check(expected.is_dir(), f"{label}: {expected} missing")
    check(listing(root) == [expected.name], f"{label}: unexpected entries {listing(root)}")

# 3. Empty and nil requests answer nil and touch nothing.
for label, value in [("empty", ""), ("nil", None)]:
    root = fresh(f"request-{label}")
    before = sorted(os.listdir(scratch))
    answer = confirm(value)
    check(answer == {"result": None}, f"{label}: {answer}")
    check(listing(root) == [], f"{label}: created {listing(root)}")
    check(sorted(os.listdir(scratch)) == before, f"{label}: changed the scratch folder")

# 4. A legacy folder is renamed when the new name is free, contents intact.
for requested_name in ("Incoming", "Incoming.noindex"):
    root = fresh(f"legacy-{requested_name}")
    legacy = root / "deep" / "Incoming"
    original = populate(legacy, "legacy")
    destination = legacy.with_name("Incoming.noindex")
    answer = confirm(root / "deep" / requested_name)
    check(answer == {"result": str(destination)}, f"legacy {requested_name}: {answer}")
    check(not legacy.exists(), f"legacy {requested_name}: the old folder is still there")
    check(destination.is_dir() and manifest(destination) == original,
          f"legacy {requested_name}: contents changed in the move")

# 5. Both folders present: neither is merged, replaced or removed.
root = fresh("both")
manifests = {name: populate(root / name, name) for name in ("DATABASE", "DATABASE.noindex", "DATABASE.noindex.noindex")}
for requested_name in ("DATABASE", "DATABASE.noindex"):
    answer = confirm(root / requested_name)
    check(answer == {"result": str(root / "DATABASE.noindex")}, f"both {requested_name}: {answer}")
    for name, expected in manifests.items():
        check((root / name).is_dir() and manifest(root / name) == expected, f"both {requested_name}: {name} changed")

# 6. A regular file at the destination is an error, and the file stays byte for byte.
for with_legacy in (False, True):
    for requested_name in ("DECOMPRESSION", "DECOMPRESSION.noindex"):
        root = fresh(f"file-{with_legacy}-{requested_name}")
        conflict = root / "DECOMPRESSION.noindex"
        conflict.write_bytes(b"do not delete " + os.urandom(64))
        digest = hashlib.sha256(conflict.read_bytes()).hexdigest()
        legacy_manifest = populate(root / "DECOMPRESSION", "legacy") if with_legacy else None
        answer = confirm(root / requested_name)
        check("exception" in answer, f"file conflict {requested_name}: no error reported ({answer})")
        check(conflict.is_file() and hashlib.sha256(conflict.read_bytes()).hexdigest() == digest,
              f"file conflict {requested_name}: the file was altered or removed")
        if with_legacy:
            check(manifest(root / "DECOMPRESSION") == legacy_manifest, f"file conflict {requested_name}: legacy changed")
        expected_entries = {"DECOMPRESSION.noindex"} | ({"DECOMPRESSION"} if with_legacy else set())
        check({p.name for p in root.iterdir()} == expected_entries, f"file conflict {requested_name}: {listing(root)}")

# 7. A rename the file system refuses is an error, not a success, and loses nothing.
root = fresh("rename-refused")
locked = root / "locked"
legacy_manifest = populate(locked / "TEMP", "legacy")
os.chmod(locked, stat.S_IRUSR | stat.S_IXUSR)
try:
    answer = confirm(locked / "TEMP.noindex")
finally:
    os.chmod(locked, stat.S_IRWXU)
check("exception" in answer and "rename" in answer.get("reason", ""), f"refused rename: {answer}")
check(manifest(locked / "TEMP") == legacy_manifest, "refused rename: legacy folder changed")
check(not (locked / "TEMP.noindex").exists(), "refused rename: destination appeared")

# 8. A component that is only ".noindex" has no legacy name to move: its parent stays put.
root = fresh("bare-suffix")
parent_manifest = populate(root / "sub", "parent")
answer = confirm(root / "sub" / ".noindex")
check(answer == {"result": str(root / "sub" / ".noindex")}, f"bare suffix: {answer}")
current = manifest(root / "sub")
current.pop(".noindex", None)
check(current == parent_manifest, "bare suffix: the parent folder was moved or changed")

# 9. A legacy name that is a file, not a folder, is left alone.
root = fresh("legacy-file")
(root / "INCOMING").write_bytes(b"not a folder")
answer = confirm(root / "INCOMING.noindex")
check(answer == {"result": str(root / "INCOMING.noindex")}, f"legacy file: {answer}")
check((root / "INCOMING").read_bytes() == b"not a folder" and (root / "INCOMING.noindex").is_dir(),
      "legacy file: the file changed or the folder was not created")

# 10. The callers all ask for paths that already carry the suffix, so the value
#     they keep and the folder confirmed are the same one.
database = (ROOT / "Horos/Sources/DicomDatabase.mm").read_bytes().decode("latin1")
for accessor, name in [("dataDirPath", "DATABASE.noindex"), ("incomingDirPath", "INCOMING.noindex"),
                       ("decompressionDirPath", "DECOMPRESSION.noindex")]:
    body = database.split(f"-(NSString*){accessor} {{", 1)[-1].split("}", 1)[0]
    check(f'@"{name}"' in body, f"{accessor} no longer returns a {name} path")
calls = []
for relative in ("Horos/Sources/DicomDatabase.mm", "Horos/Sources/BrowserController.m", "Horos/Sources/AppController.m"):
    text = (ROOT / relative).read_bytes().decode("latin1")
    for line in text.splitlines():
        if "confirmNoIndexDirectoryAtPath:" in line and "createNoIndexDirectoryIfNecessary" not in line:
            calls.append((relative, line.strip()))
for relative, line in calls:
    argument = line.split("confirmNoIndexDirectoryAtPath:", 1)[1]
    check(any(token in argument for token in ("dataDirPath", "incomingDirPath", "decompressionDirPath", "OUTpath", "path]")),
          f"{relative}: unexpected argument in {line}")

if failures:
    print(f"{len(failures)} failure(s)")
    raise SystemExit(1)
print("PASS: suffix resolution, empty/nil, legacy rename with hashes, both folders kept, file conflict kept, "
      "refused rename reported, bare suffix, legacy file kept, callers keep .noindex paths")
