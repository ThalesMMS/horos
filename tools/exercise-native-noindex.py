#!/usr/bin/env python3
"""Run the database flows that resolve `.noindex` folders in the built app (#612).

Each scenario starts the isolated development bundle on a database folder of
its own, prepared beforehand, and checks the folders afterwards by content hash:

  fresh       a new database creates DATABASE/INCOMING/TEMP .noindex folders
  import      uncompressed and JPEG-LS files dropped into INCOMING are indexed;
              with ListenerCompressionSettings=1 the compressed ones pass through
              DECOMPRESSION.noindex and the Decompress helper
  legacy      a legacy DECOMPRESSION folder is renamed on first use, contents intact
  both        legacy DATABASE and DECOMPRESSION folders beside their .noindex
              counterparts: nothing merged, replaced or removed. (Files placed
              in DECOMPRESSION.noindex itself are not a fixture: at launch the
              app moves that working folder's contents to INCOMING by design.)
  conflict    a regular file named DECOMPRESSION.noindex is kept byte for byte,
              the error is logged and the app keeps running

    python3 tools/exercise-native-noindex.py --fixture local-validation/delta4/fixtures/jpegls \
        --out local-validation/delta4/612-app

The fixture is tools/generate-jpegls-fixture.py output (synthetic). Results go
to <out>/results.json; app logs to <out>/<scenario>/horos.log.
"""
import argparse
import hashlib
import json
import os
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import native_app  # noqa: E402

parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument("--fixture", type=Path, required=True)
parser.add_argument("--out", type=Path, required=True)
parser.add_argument("--app", type=Path, default=native_app.DEVELOPMENT_APP)
parser.add_argument("--only", action="append")
arguments = parser.parse_args()

COMPRESSED = ["mono-lossless.dcm", "mono-nearlossless.dcm", "rgb-sample.dcm", "rgb-line.dcm", "rgb-none.dcm"]
UNCOMPRESSED = ["uncompressed.dcm"]


def manifest(folder: Path):
    entries = {}
    for current, directories, files in os.walk(folder):
        for name in directories:
            entries[str((Path(current) / name).relative_to(folder)) + "/"] = "dir"
        for name in files:
            path = Path(current) / name
            entries[str(path.relative_to(folder))] = hashlib.sha256(path.read_bytes()).hexdigest()
    return entries


def populate(folder: Path, label: str):
    (folder / "series" / "déjà").mkdir(parents=True)
    (folder / "sentinel.txt").write_text(label)
    (folder / "series" / "déjà" / "payload.bin").write_bytes(os.urandom(8192))
    return manifest(folder)


def drop(names, incoming: Path):
    for name in names:
        # Copy under a dot name, then rename: the importer skips dot files, so
        # it never reads a half-written file.
        staging = incoming / f".{name}.part"
        shutil.copyfile(arguments.fixture / name, staging)
        os.rename(staging, incoming / name)


def run(name, prepare, extra, act, verify):
    root = (arguments.out / name / "database").resolve()
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)
    data = native_app.database_folder(root)
    data.mkdir()
    context = prepare(data) or {}
    log = arguments.out / name / "horos.log"
    native_app.stop_all(arguments.app)
    started = time.monotonic()
    process = native_app.launch(root, log, extra, app=arguments.app)
    result = {"scenario": name}
    try:
        native_app.wait_for(lambda: (data / "Database.sql").is_file() and (data / "INCOMING.noindex").is_dir(),
                            90, description="the database to open")
        result["database_open_s"] = round(time.monotonic() - started, 2)
        act(root, data, context, result)
        result["alive"] = process.poll() is None
    finally:
        native_app.stop(process)
    text = log.read_text(errors="replace")
    verify(root, data, context, result, text)
    return result


def top(data: Path):
    return sorted(p.name + ("/" if p.is_dir() else "") for p in data.iterdir())


results = []
failures = []


def check(result, condition, message):
    result.setdefault("checks", []).append({"check": message, "ok": bool(condition)})
    if not condition:
        failures.append(f"{result['scenario']}: {message}")
        print("FAIL:", result["scenario"], message)


def wait_imported(root, expected, timeout=120):
    return native_app.wait_for(lambda: (native_app.image_count(root) or 0) >= expected and native_app.image_count(root),
                               timeout, interval=0.5, description=f"{expected} indexed images")


def nothing(data):
    return {}


def act_fresh(root, data, context, result):
    time.sleep(3)
    result["folders"] = top(data)


def verify_fresh(root, data, context, result, log):
    for folder in ("DATABASE.noindex/", "INCOMING.noindex/", "TEMP.noindex/"):
        check(result, folder in result["folders"], f"{folder} created")
    check(result, not any(".noindex.noindex" in f for f in result["folders"]), "no doubled suffix")
    check(result, all(f.endswith(".noindex/") or not f.startswith(("DATABASE", "INCOMING", "DECOM", "TEMP")) for f in result["folders"]),
          "no truncated or unsuffixed working folders")
    check(result, result["alive"], "app running")


def act_import(root, data, context, result):
    incoming = data / "INCOMING.noindex"
    started = time.monotonic()
    drop(UNCOMPRESSED + COMPRESSED, incoming)
    count = wait_imported(root, len(UNCOMPRESSED + COMPRESSED))
    result["import_s"] = round(time.monotonic() - started, 2)
    result["images"] = count
    native_app.wait_for(lambda: not any((data / "DECOMPRESSION.noindex").iterdir()), 30,
                        description="the decompression folder to empty")
    result["folders"] = top(data)
    result["incoming_left"] = sorted(p.name for p in incoming.iterdir())
    stored = sorted((data / "DATABASE.noindex").rglob("*.dcm"))
    syntaxes = []
    import subprocess
    probe = ("import sys, json, pydicom\n"
             "print(json.dumps([str(pydicom.dcmread(p, stop_before_pixels=True).file_meta.TransferSyntaxUID) for p in sys.argv[1:]]))")
    venv = ROOT / "local-validation/venv/bin/python"
    if venv.is_file() and stored:
        syntaxes = json.loads(subprocess.run([str(venv), "-c", probe] + [str(p) for p in stored],
                                             capture_output=True, text=True, check=True).stdout)
    result["stored_transfer_syntaxes"] = sorted(set(syntaxes))
    result["stored_files"] = len(stored)


def verify_import(root, data, context, result, log):
    check(result, result["images"] == 6, "six images indexed")
    check(result, "DECOMPRESSION.noindex/" in result["folders"], "DECOMPRESSION.noindex created on first import")
    check(result, not any(".noindex.noindex" in f for f in result["folders"]), "no doubled suffix")
    check(result, result["incoming_left"] == [], "incoming emptied")
    check(result, result["stored_files"] == 6, "six files stored in DATABASE.noindex")
    check(result, result["stored_transfer_syntaxes"] and all(s in ("1.2.840.10008.1.2.1", "1.2.840.10008.1.2") for s in result["stored_transfer_syntaxes"]),
          f"stored files decompressed ({result['stored_transfer_syntaxes']})")
    check(result, result["alive"], "app running")


def prepare_legacy(data):
    return {"legacy": populate(data / "DECOMPRESSION", "legacy")}


def act_single_import(root, data, context, result):
    drop(UNCOMPRESSED, data / "INCOMING.noindex")
    result["images"] = wait_imported(root, 1)
    time.sleep(2)
    result["folders"] = top(data)


def verify_legacy(root, data, context, result, log):
    check(result, result["images"] == 1, "the import still happens")
    check(result, not (data / "DECOMPRESSION").exists(), "legacy folder renamed")
    moved = data / "DECOMPRESSION.noindex"
    check(result, moved.is_dir() and manifest(moved) == context["legacy"], "renamed folder keeps every file and hash")
    check(result, result["alive"], "app running")


def prepare_both(data):
    (data / "DECOMPRESSION.noindex").mkdir()
    return {"legacy_database": populate(data / "DATABASE", "legacy database"),
            "legacy_decompression": populate(data / "DECOMPRESSION", "legacy decompression")}


def verify_both(root, data, context, result, log):
    check(result, result["images"] == 1, "the import still happens")
    check(result, manifest(data / "DATABASE") == context["legacy_database"], "legacy DATABASE folder untouched")
    check(result, manifest(data / "DECOMPRESSION") == context["legacy_decompression"],
          "legacy DECOMPRESSION folder untouched")
    stored = manifest(data / "DATABASE.noindex")
    check(result, not any(name.endswith(("sentinel.txt", "payload.bin")) for name in stored),
          "nothing from the legacy folder merged into DATABASE.noindex")
    check(result, any(name.endswith(".dcm") for name in stored), "the imported file is in DATABASE.noindex")
    check(result, (data / "DECOMPRESSION.noindex").is_dir(), "DECOMPRESSION.noindex still a folder")
    check(result, result["alive"], "app running")


def prepare_conflict(data):
    conflict = data / "DECOMPRESSION.noindex"
    conflict.write_bytes(b"not a folder: must survive " + os.urandom(128))
    return {"digest": hashlib.sha256(conflict.read_bytes()).hexdigest()}


def act_conflict(root, data, context, result):
    drop(UNCOMPRESSED, data / "INCOMING.noindex")
    # Several listener scans (every 3 s by default) must pass over the conflict.
    time.sleep(15)
    result["images"] = native_app.image_count(root)
    result["folders"] = top(data)


def verify_conflict(root, data, context, result, log):
    conflict = data / "DECOMPRESSION.noindex"
    check(result, conflict.is_file() and hashlib.sha256(conflict.read_bytes()).hexdigest() == context["digest"],
          "the conflicting file is kept byte for byte")
    check(result, "a file already exists there and is left untouched" in log, "the error is logged explicitly")
    check(result, result["alive"], "app still running after repeated scans")
    result["import_blocked_while_conflict"] = result["images"] == 0


SCENARIOS = {
    "fresh": (nothing, [], act_fresh, verify_fresh),
    "import": (nothing, ["-ListenerCompressionSettings", "1"], act_import, verify_import),
    "legacy": (prepare_legacy, [], act_single_import, verify_legacy),
    "both": (prepare_both, [], act_single_import, verify_both),
    "conflict": (prepare_conflict, [], act_conflict, verify_conflict),
}

arguments.out.mkdir(parents=True, exist_ok=True)
for name, (prepare, extra, act, verify) in SCENARIOS.items():
    if arguments.only and name not in arguments.only:
        continue
    print(f"scenario {name}…", flush=True)
    try:
        results.append(run(name, prepare, extra, act, verify))
    except Exception as error:  # a timeout is a failed scenario, reported as such
        failures.append(f"{name}: {error}")
        results.append({"scenario": name, "error": str(error)})
        print("FAIL:", name, error)

(arguments.out / "results.json").write_text(json.dumps({"app": str(arguments.app), "results": results,
                                                         "failures": failures}, indent=1, ensure_ascii=False) + "\n")
print(json.dumps(results, indent=1, ensure_ascii=False))
raise SystemExit(1 if failures else 0)
