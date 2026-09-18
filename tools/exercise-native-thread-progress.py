#!/usr/bin/env python3
"""Progress, cancellation and notifications of the app's own threads, in the app (#626).

Runs one development bundle with tools/probe-thread-progress.m injected, on a
fresh private database per scenario, and records every thread the activity
window receives (ThreadsManager): the notifications each key sent, the
redundant ones, the distinct changes, and the details the thread reads when
it exits. Three flows, all local and synthetic:

  import     120 synthetic CT images copied into INCOMING
  remote     the app shares its database (no password) and opens it as a remote
             database on 127.0.0.1, then updates it: the index download
  retrieve   C-GET of a synthetic study from tools/serve-cget-fixture.py, run the
             way the query window runs it; `retrieve-cancel` cancels it midway the
             way the activity window's cancel button does

    local-validation/venv/bin/python tools/exercise-native-thread-progress.py \\
        --app build/Development/HorosDevelopment.app --out local-validation/delta4/626-app/candidate

Needs a Python with pydicom, pynetdicom and numpy (the fixture and the peer).
The bundle is re-signed with the entitlement that lets DYLD_INSERT_LIBRARIES
through; nothing else about it changes. Everything stays under --out.
"""
import argparse
import json
import os
import plistlib
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import native_app  # noqa: E402

parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument("--app", type=Path, default=native_app.DEVELOPMENT_APP)
parser.add_argument("--out", type=Path, required=True)
parser.add_argument("--scenario", action="append", choices=["import", "remote", "retrieve", "retrieve-cancel"])
arguments = parser.parse_args()
scenarios = arguments.scenario or ["import", "remote", "retrieve", "retrieve-cancel"]

out = arguments.out.resolve()
if "local-validation" not in out.parts:
    parser.error("--out must be under local-validation")
# Only the scenarios asked for are replaced, so one can be run again on its own.
out.mkdir(parents=True, exist_ok=True)
for name in scenarios:
    for leftover in (out / name, out / f"fixture-{name}"):
        if leftover.exists():
            shutil.rmtree(leftover)
app = arguments.app.resolve()


def prepare_bundle():
    """Allow the injected probe, as tools/probe-native-retrieval.py does."""
    entitlements = plistlib.loads((ROOT / "build/Development/entitlements.plist").read_bytes())
    entitlements["com.apple.security.cs.allow-dyld-environment-variables"] = True
    path = out / "probe-entitlements.plist"
    path.write_bytes(plistlib.dumps(entitlements))
    subprocess.run(["/usr/bin/codesign", "--force", "--sign", "-", "--options", "runtime", "--entitlements", str(path),
                    str(app)], check=True, capture_output=True)
    dylib = out / "probe-thread-progress.dylib"
    subprocess.run(["xcrun", "clang", "-dynamiclib", "-fobjc-arc", "-framework", "Cocoa",
                    str(ROOT / "tools/probe-thread-progress.m"), "-o", str(dylib)], check=True)
    return dylib


def generate_series(folder: Path, count: int):
    import numpy
    from pydicom.dataset import Dataset, FileMetaDataset
    from pydicom.uid import CTImageStorage, ExplicitVRLittleEndian, generate_uid
    folder.mkdir(parents=True)
    study, series = generate_uid(), generate_uid()
    for number in range(1, count + 1):
        ds = Dataset()
        ds.file_meta = FileMetaDataset()
        ds.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
        ds.SOPClassUID = CTImageStorage
        ds.SOPInstanceUID = generate_uid()
        ds.StudyInstanceUID, ds.SeriesInstanceUID = study, series
        ds.PatientName, ds.PatientID = "SYNTHETIC^PROGRESS", "SYN-626"
        ds.StudyDate, ds.StudyTime, ds.StudyID = "20260916", "120000", "626"
        ds.StudyDescription, ds.SeriesDescription = "Synthetic progress", "Synthetic CT"
        ds.Modality, ds.SeriesNumber, ds.InstanceNumber = "CT", 1, number
        ds.Rows = ds.Columns = 64
        ds.SamplesPerPixel, ds.PhotometricInterpretation = 1, "MONOCHROME2"
        ds.BitsAllocated = ds.BitsStored = 16
        ds.HighBit, ds.PixelRepresentation = 15, 0
        ds.PixelSpacing, ds.SliceThickness = [1, 1], 1
        ds.ImageOrientationPatient, ds.ImagePositionPatient = [1, 0, 0, 0, 1, 0], [0, 0, number]
        ds.PixelData = (numpy.arange(64 * 64, dtype=numpy.uint16).reshape(64, 64) + number).tobytes()
        ds.save_as(folder / f"ct-{number:03d}.dcm", enforce_file_format=True)


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def records(path: Path):
    if not path.exists():
        return []
    lines = []
    for line in path.read_text(errors="replace").splitlines():
        try:
            lines.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return lines


def run(name, extra_arguments, environment, before_trigger=None, peer=None):
    folder = out / name
    root = folder / "database"
    log = folder / "thread-progress.jsonl"
    trigger = folder / "go"
    env = {"DYLD_INSERT_LIBRARIES": str(dylib), "HOROS_THREAD_PROGRESS_LOG": str(log),
           "HOROS_THREAD_PROGRESS_TRIGGER": str(trigger)}
    env.update(environment)
    native_app.stop_all(app)
    process = native_app.launch(root, folder / "horos.log", extra_arguments, app=app, environment=env)
    result = {"scenario": name}
    try:
        data = native_app.database_folder(root)
        native_app.wait_for(lambda: (data / "INCOMING.noindex").is_dir(), 90, description="the database to open")
        native_app.wait_for(lambda: any(r.get("probe") == "loaded" for r in records(log)), 30,
                            description="the probe to load")
        if before_trigger:
            before_trigger(data, root, result)
        trigger.write_text("go\n")
        if environment:
            native_app.wait_for(lambda: any(r.get("driving") == "done" for r in records(log)), 240, interval=0.5,
                                description="the probe to finish driving")
        time.sleep(4)  # the last threads exit and report
        result["images_in_database"] = native_app.image_count(root)
        result["app_running"] = process.poll() is None
    finally:
        native_app.stop(process)
        if peer:
            peer.terminate()
            try:
                peer.wait(timeout=10)
            except subprocess.TimeoutExpired:
                peer.kill()
    lines = records(log)
    result["probe"] = [r for r in lines if "probe" in r]
    result["threads"] = [r["thread_exit"] for r in lines if "thread_exit" in r]
    for key in ("remote_update", "retrieve"):
        found = [r[key] for r in lines if key in r]
        if found:
            result[key] = found[-1]
    (folder / "result.json").write_text(json.dumps(result, indent=1, ensure_ascii=False) + "\n")
    return result


dylib = prepare_bundle()
summary = {"app": str(app), "scenarios": {}}

if "import" in scenarios:
    fixture = out / "fixture-import"
    generate_series(fixture, 120)

    def copy_into_incoming(data, root, result):
        started = time.monotonic()
        incoming = data / "INCOMING.noindex"
        for path in sorted(fixture.glob("*.dcm")):
            staging = incoming / f".{path.name}.part"
            shutil.copyfile(path, staging)
            os.rename(staging, incoming / path.name)
        native_app.wait_for(lambda: (native_app.image_count(root) or 0) >= 120, 180, interval=0.25,
                            description="the import")
        result["import_seconds"] = time.monotonic() - started

    summary["scenarios"]["import"] = run("import", [], {}, before_trigger=copy_into_incoming)

if "remote" in scenarios:
    fixture = out / "fixture-remote"
    generate_series(fixture, 60)

    def import_for_sharing(data, root, result):
        incoming = data / "INCOMING.noindex"
        for path in sorted(fixture.glob("*.dcm")):
            staging = incoming / f".{path.name}.part"
            shutil.copyfile(path, staging)
            os.rename(staging, incoming / path.name)
        native_app.wait_for(lambda: (native_app.image_count(root) or 0) >= 60, 180, interval=0.25,
                            description="the import")
        native_app.wait_for(lambda: socket.socket().connect_ex(("127.0.0.1", 8780)) == 0, 60,
                            description="the shared-database listener")
        time.sleep(4)  # the import thread exits before the update starts

    summary["scenarios"]["remote"] = run("remote", ["-bonjourSharing", "YES", "-bonjourPasswordProtected", "NO"],
                                         {"HOROS_THREAD_PROGRESS_REMOTE": "8780"}, before_trigger=import_for_sharing)

for name in ("retrieve", "retrieve-cancel"):
    if name not in scenarios:
        continue
    folder = out / name
    folder.mkdir(parents=True, exist_ok=True)
    port = free_port()
    peer_command = [sys.executable, str(ROOT / "tools/serve-cget-fixture.py"), str(folder / "peer"), "--port", str(port),
                    "--instances", "30", "--instance-delay", "0.05" if name == "retrieve" else "0.4"]
    peer = subprocess.Popen(peer_command, stdout=open(folder / "peer.log", "w"), stderr=subprocess.STDOUT)
    # The peer writes its evidence on DICOM events only: wait for its port.
    native_app.wait_for(lambda: socket.socket().connect_ex(("127.0.0.1", port)) == 0, 60, description="the C-GET peer")
    servers = folder / "servers.json"
    servers.write_text(json.dumps([{"Address": "127.0.0.1", "Port": port, "AETitle": "CGETFIX", "TransferSyntax": 0,
                                    "retrieveMode": 1, "Description": "synthetic C-GET peer"}]))
    environment = {"HOROS_THREAD_PROGRESS_RETRIEVE": str(servers)}
    if name == "retrieve-cancel":
        environment["HOROS_THREAD_PROGRESS_CANCEL_AFTER"] = "4"
    # The listener stays off: C-GET brings the images back on its own association.
    arguments_for_retrieve = ["-STORESCP", "NO", "-USESTORESCP", "NO", "-TLSStoreSCP", "NO", "-hideListenerError", "YES",
                              "-SingleProcessMultiThreadedListener", "YES", "-syncDICOMNodes", "NO",
                              "-publishDICOMBonjour", "NO", "-searchDICOMBonjour", "NO", "-AETITLE", "HOROSDEV",
                              "-AEPORT", str(free_port()), "-DICOMTimeout", "8", "-DICOMConnectionTimeout", "5"]
    summary["scenarios"][name] = run(name, arguments_for_retrieve, environment, peer=peer)

previous = json.loads((out / "summary.json").read_text()) if (out / "summary.json").exists() else {"scenarios": {}}
previous["scenarios"].update(summary["scenarios"])
summary["scenarios"] = previous["scenarios"]
(out / "summary.json").write_text(json.dumps(summary, indent=1, ensure_ascii=False) + "\n")
for name, result in summary["scenarios"].items():
    print(f"== {name}: images {result.get('images_in_database')}, running {result.get('app_running')}, "
          f"remote {result.get('remote_update')}, retrieve {result.get('retrieve')}")
    for thread in result["threads"]:
        counts = {key: value for key, value in thread["counts"].items() if value[0]}
        print(f"   {thread['thread']!r}: {counts} last details {thread['last_announced_details']!r} "
              f"read at exit {thread['details_read_at_exit']!r} cancelled {thread['cancelled']}")
