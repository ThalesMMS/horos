#!/usr/bin/env python3
"""In-app A/B of importing a folder tree through INCOMING (Δ4 protocol, #627).

Two development bundles built from the same checkout, differing only in the
change under test (tools/build-variant-app.py), import the same synthetic trees
through INCOMING.noindex, alternated by round, each run on a fresh private
database, with tools/probe-app-resources.m injected. Per batch (a tree of
--folders folders of --files images, renamed into INCOMING in one step):

  import_ms              the app's own time in its INCOMING scans from the rename
                         until every image is indexed and INCOMING is empty
                         (enumeration, moves and indexing; the timer's wait
                         between scans is not the app's work and is left out)
  threads_created_count  threads the process created meanwhile
  threads_peak_count     most threads alive meanwhile, above the count before
  fds_peak_count         most descriptors open meanwhile, above the count before
  footprint_peak_mib     largest memory footprint meanwhile, above the one before

Every run also checks what was indexed: the image count, and the SOP instance
UIDs of the files the database stored against the generated ones.

    local-validation/venv/bin/python tools/measure-native-incoming-import.py \\
        --baseline-app build/Variants/627-baseline/HorosDevelopment.app \\
        --candidate-app build/Variants/627-candidate/HorosDevelopment.app \\
        --rounds 20 --out local-validation/delta4/627-app-c1 --limit import_ms:median=0.05 ...

Needs a Python with pydicom (the trees and the check).
"""
import argparse
import json
import os
import plistlib
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import native_app  # noqa: E402

HIGHER = []


def generate(fixture: Path, batches: int, folders: int, files: int):
    """Unique studies, one per folder, so a batch imports folders x files images."""
    import numpy
    from pydicom.dataset import Dataset, FileMetaDataset
    from pydicom.uid import CTImageStorage, ExplicitVRLittleEndian, generate_uid
    manifest = {}
    pixels = numpy.arange(32 * 32, dtype=numpy.uint16).reshape(32, 32).tobytes()
    for batch in range(batches):
        uids = []
        for folder in range(folders):
            directory = fixture / f"batch-{batch}" / f"study-{folder:03d}"
            directory.mkdir(parents=True)
            study, series = generate_uid(), generate_uid()
            for number in range(1, files + 1):
                ds = Dataset()
                ds.file_meta = FileMetaDataset()
                ds.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
                ds.SOPClassUID = CTImageStorage
                ds.SOPInstanceUID = generate_uid()
                ds.StudyInstanceUID, ds.SeriesInstanceUID = study, series
                ds.PatientName, ds.PatientID = f"SYNTHETIC^IMPORT{batch}", f"SYN-627-{batch}-{folder:03d}"
                ds.StudyDate, ds.StudyTime, ds.StudyID = "20260916", "120000", "627"
                ds.Modality, ds.SeriesNumber, ds.InstanceNumber = "CT", 1, number
                ds.Rows = ds.Columns = 32
                ds.SamplesPerPixel, ds.PhotometricInterpretation = 1, "MONOCHROME2"
                ds.BitsAllocated = ds.BitsStored = 16
                ds.HighBit, ds.PixelRepresentation = 15, 0
                ds.PixelData = pixels
                ds.save_as(directory / f"{number}.dcm", enforce_file_format=True)
                uids.append(str(ds.SOPInstanceUID))
        manifest[f"batch-{batch}"] = uids
    (fixture / "manifest.json").write_text(json.dumps(manifest) + "\n")


def prepare_bundle(app: Path, work: Path):
    entitlements = plistlib.loads((ROOT / "build/Development/entitlements.plist").read_bytes())
    entitlements["com.apple.security.cs.allow-dyld-environment-variables"] = True
    path = work / "probe-entitlements.plist"
    path.write_bytes(plistlib.dumps(entitlements))
    subprocess.run(["/usr/bin/codesign", "--force", "--sign", "-", "--options", "runtime", "--entitlements", str(path),
                    str(app)], check=True, capture_output=True)


def samples(path: Path):
    lines = []
    if path.exists():
        for line in path.read_text(errors="replace").splitlines():
            try:
                lines.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return lines


def entries(folder: Path):
    try:
        return any(os.scandir(folder))
    except FileNotFoundError:
        return False


def run_once(app: Path, fixture: Path, dylib: Path, batches: int):
    """One launch of one bundle: every batch imported in turn; prints the observations."""
    import pydicom
    manifest = json.loads((fixture / "manifest.json").read_text())
    work = Path(tempfile.mkdtemp(prefix="incoming-import-", dir=str(fixture.parent)))
    root = work / "database"
    recording = work / "resources.jsonl"
    result = {name: [] for name in ("import_ms", "threads_created_count", "threads_peak_count", "fds_peak_count",
                                    "footprint_peak_mib")}
    native_app.stop_all(app)
    process = native_app.launch(root, work / "horos.log", ["-LISTENERCHECKINTERVAL", "1"], app=app,
                                environment={"DYLD_INSERT_LIBRARIES": str(dylib), "HOROS_RESOURCE_RECORDER": str(recording),
                                             "HOROS_RESOURCE_INTERVAL_MS": "20"})
    try:
        data = native_app.database_folder(root)
        incoming = data / "INCOMING.noindex"
        native_app.wait_for(lambda: incoming.is_dir(), 90, description="the database to open")
        native_app.wait_for(lambda: any(s.get("recorder") == "loaded" and s.get("incoming_scans_timed")
                                        for s in samples(recording)), 30, description="the recorder")
        time.sleep(3)
        expected = 0
        for batch in range(batches):
            name = f"batch-{batch}"
            staging = work / "staging" / name
            shutil.copytree(fixture / name, staging)
            before = samples(recording)
            last = [s for s in before if "t" in s][-1]
            time.sleep(0.3)
            os.rename(staging, incoming / name)
            expected += len(manifest[name])
            native_app.wait_for(lambda: (native_app.image_count(root) or 0) >= expected and not entries(incoming), 300,
                                interval=0.05, description=f"{name} to be imported")
            time.sleep(0.3)
            after = samples(recording)[len(before):]
            scans = [s for s in after if "scan_start" in s and s["scan_start"] >= last["t"]]
            during = [s for s in after if "t" in s]
            result["import_ms"].append(sum(s["scan_end"] - s["scan_start"] for s in scans) * 1000)
            result["threads_created_count"].append(during[-1]["created"] - last["created"])
            result["threads_peak_count"].append(max(s["alive"] for s in during) - last["alive"])
            result["fds_peak_count"].append(max(s["fds"] for s in during) - last["fds"])
            result["footprint_peak_mib"].append((max(s["footprint"] for s in during) - last["footprint"]) / (1 << 20))
            time.sleep(1.5)
        stored = set()
        for path in (data / "DATABASE.noindex").rglob("*.dcm"):
            stored.add(str(pydicom.dcmread(path, stop_before_pixels=True).SOPInstanceUID))
        generated = {uid for name in list(manifest)[:batches] for uid in manifest[name]}
        if stored != generated or native_app.image_count(root) != len(generated):
            raise SystemExit(f"indexed {native_app.image_count(root)}, stored {len(stored)}, generated {len(generated)}, "
                             f"missing {len(generated - stored)}, unexpected {len(stored - generated)}")
    finally:
        native_app.stop(process)
    shutil.rmtree(work, ignore_errors=True)
    print(json.dumps(result))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--run", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--fixture", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--dylib", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--baseline-app", type=Path)
    parser.add_argument("--candidate-app", type=Path)
    parser.add_argument("--rounds", type=int, default=20)
    parser.add_argument("--batches", type=int, default=3)
    parser.add_argument("--folders", type=int, default=200)
    parser.add_argument("--files", type=int, default=3)
    parser.add_argument("--limit", action="append", default=[])
    parser.add_argument("--out", type=Path)
    arguments = parser.parse_args()
    if arguments.run:
        run_once(arguments.run, arguments.fixture, arguments.dylib, arguments.batches)
        return 0

    import ab_protocol
    out = arguments.out.resolve()
    if "local-validation" not in out.parts:
        parser.error("--out must be under local-validation")
    out.mkdir(parents=True, exist_ok=True)
    fixture = out / "fixture"
    if fixture.exists():
        shutil.rmtree(fixture)
    generate(fixture, arguments.batches, arguments.folders, arguments.files)
    dylib = out / "probe-app-resources.dylib"
    subprocess.run(["xcrun", "clang", "-dynamiclib", "-O2", "-fno-objc-arc", "-framework", "Foundation",
                    str(ROOT / "tools/probe-app-resources.m"), "-o", str(dylib)], check=True)
    apps = {"baseline": arguments.baseline_app.resolve(), "candidate": arguments.candidate_app.resolve()}
    variants = {}
    for label, app in apps.items():
        prepare_bundle(app, out)
        described = app.parent / "variant.json"
        variants[label] = {"app": str(app), "variant": json.loads(described.read_text()) if described.exists() else None}

    def command(label):
        return [sys.executable, str(Path(__file__).resolve()), "--run", str(apps[label]), "--fixture", str(fixture),
                "--dylib", str(dylib), "--batches", str(arguments.batches)]

    plan = {"variants": variants, "rounds": arguments.rounds, "batches": arguments.batches, "folders": arguments.folders,
            "files": arguments.files, "limits": arguments.limit, "protocol_version": ab_protocol.PROTOCOL_VERSION,
            "design": "separate launches alternated by round, fresh database per launch, in-app scan timing"}
    (out / "plan.json").write_text(json.dumps(plan, indent=1) + "\n")
    limits = ab_protocol._parse_limits(arguments.limit)
    aa = ab_protocol.run_protocol({"A": command("baseline"), "A'": command("baseline")}, arguments.rounds, 1)
    (out / "aa.json").write_text(json.dumps(aa) + "\n")
    tolerance = ab_protocol.calibrate(aa, limits, set(HIGHER), ab_protocol.DEFAULT_SEED, ab_protocol.DEFAULT_RESAMPLES)
    (out / "tolerance.json").write_text(json.dumps(tolerance, indent=1) + "\n")
    for key, value in tolerance["tolerances"].items():
        print(f"A/A {key}: tolerance {value['tolerance']:.4g} (limit {value['relevance_limit']}) "
              f"{'capable' if value['capable'] else 'INCAPABLE'}")
    ab = ab_protocol.run_protocol({"baseline": command("baseline"), "candidate": command("candidate")}, arguments.rounds, 1)
    (out / "ab.json").write_text(json.dumps(ab) + "\n")
    analysis = ab_protocol.analyze(ab, tolerance, set(HIGHER), ab_protocol.DEFAULT_SEED, ab_protocol.DEFAULT_RESAMPLES)
    (out / "analysis.json").write_text(json.dumps(analysis, indent=1) + "\n")
    table = ab_protocol.markdown(analysis, ("baseline", "candidate"))
    (out / "table.md").write_text(table)
    print(table)
    shutil.rmtree(fixture, ignore_errors=True)
    return 0 if analysis["overall"] == "non-inferior" else 1


if __name__ == "__main__":
    raise SystemExit(main())
