#!/usr/bin/env python3
"""A medium prepared by the app, as a disc image: estimate and inventory (#632).

For each scenario, a fresh private database imports a synthetic selection
(small and large images, a Unicode patient name), and tools/probe-burn-media.m,
injected, opens the burn window's controller on every image, times its size
estimate and burns to a disc image (the save panel answered by the probe). The
image is then attached read-only and inventoried.

  full      Weasis on, HTML on, a supplementary folder (Unicode names), and the
            retired launcher preference set to YES as an older version left it
  minimal   Weasis, HTML and the supplementary folder off, no launcher preference
  failure   the disc image asked for in a folder that cannot be written

Checks: the size field shows exactly the files (KiB rounded down each), 17 MiB
for Weasis and `du -sk` of the supplementary folder - never 8 MB for a launcher;
the image holds every DICOM file of the selection byte for byte, a DICOMDIR that
reads back naming each of them, the HTML pages, Weasis and the supplementary files
exactly when asked, and no Horos launcher or application (Weasis's own launcher jar
is part of Weasis); a failure raises the window's alert and leaves no image.

    local-validation/venv/bin/python tools/exercise-native-burn-media.py \\
        --app build/Variants/candidate/HorosDevelopment.app --out local-validation/delta4/632-app/candidate

Needs a Python with pydicom and numpy. Everything stays under --out.
"""
import argparse
import hashlib
import json
import os
import plistlib
import re
import shutil
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
parser.add_argument("--scenario", action="append", choices=["full", "minimal", "failure"])
arguments = parser.parse_args()
scenarios = arguments.scenario or ["full", "minimal", "failure"]
out = arguments.out.resolve()
if "local-validation" not in out.parts:
    parser.error("--out must be under local-validation")
if out.exists():
    shutil.rmtree(out)
out.mkdir(parents=True)
app = arguments.app.resolve()
checks = []


def check(condition, message):
    checks.append({"check": message, "ok": bool(condition)})
    if not condition:
        print("FAIL:", message)


def generate(folder: Path):
    import numpy
    from pydicom.dataset import Dataset, FileMetaDataset
    from pydicom.uid import CTImageStorage, ExplicitVRLittleEndian, generate_uid
    folder.mkdir(parents=True)
    study = generate_uid()
    for series, (size, count) in enumerate(((64, 6), (1024, 2)), start=1):
        uid = generate_uid()
        for number in range(1, count + 1):
            ds = Dataset()
            ds.file_meta = FileMetaDataset()
            ds.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
            ds.SOPClassUID, ds.SOPInstanceUID = CTImageStorage, generate_uid()
            ds.StudyInstanceUID, ds.SeriesInstanceUID = study, uid
            ds.PatientName, ds.PatientID = "SINTÉTICO^Mídia^Ünïcode", "SYN-632"
            ds.StudyDate, ds.StudyTime, ds.StudyID = "20260916", "120000", "632"
            ds.StudyDescription = "Mídia sintética"
            ds.Modality, ds.SeriesNumber, ds.InstanceNumber = "CT", series, number
            ds.Rows = ds.Columns = size
            ds.SamplesPerPixel, ds.PhotometricInterpretation = 1, "MONOCHROME2"
            ds.BitsAllocated, ds.BitsStored, ds.HighBit, ds.PixelRepresentation = 16, 12, 11, 0
            ds.PixelSpacing, ds.SliceThickness = [0.5, 0.5], 1
            ds.ImageOrientationPatient, ds.ImagePositionPatient = [1, 0, 0, 0, 1, 0], [0, 0, number]
            ds.PixelData = (numpy.arange(size * size, dtype=numpy.uint32) % 4000).astype(numpy.uint16).tobytes()
            ds.save_as(folder / f"s{series}-{number}.dcm", enforce_file_format=True)


def records(path: Path):
    lines = []
    if path.exists():
        for line in path.read_text(errors="replace").splitlines():
            try:
                lines.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return lines


entitlements = plistlib.loads((ROOT / "build/Development/entitlements.plist").read_bytes())
entitlements["com.apple.security.cs.allow-dyld-environment-variables"] = True
(out / "probe-entitlements.plist").write_bytes(plistlib.dumps(entitlements))
subprocess.run(["/usr/bin/codesign", "--force", "--sign", "-", "--options", "runtime", "--entitlements",
                str(out / "probe-entitlements.plist"), str(app)], check=True, capture_output=True)
dylib = out / "probe-burn-media.dylib"
subprocess.run(["xcrun", "clang", "-dynamiclib", "-fobjc-arc", "-framework", "Cocoa", str(ROOT / "tools/probe-burn-media.m"),
                "-o", str(dylib)], check=True)
selection = out / "selection"
generate(selection)
supplementary = out / "supplementary-folder"
(supplementary / "Leia-me ção").mkdir(parents=True)
(supplementary / "Leia-me ção" / "instruções.txt").write_text("Material sintético para a mídia.\n")
(supplementary / "viewer-notes.bin").write_bytes(os.urandom(300_000))
supplementary_kib = int(subprocess.run(["/usr/bin/du", "-sk", str(supplementary)], capture_output=True, text=True,
                                       check=True).stdout.split()[0])
summary = {"app": str(app), "scenarios": {}}

for name in scenarios:
    folder = out / name
    root, log, trigger = folder / "database", folder / "burn.jsonl", folder / "go"
    target_dir = folder / "destination"
    target_dir.mkdir(parents=True)
    dmg = target_dir / "Mídia sintética.dmg"
    extra = ["-burnDestination", "2", "-anonymizedBeforeBurning", "NO", "-EncryptCD", "NO",
             "-Compression Mode for Burning", "0"]
    if name == "full":
        extra += ["-BurnWeasis", "YES", "-BurnHtml", "YES", "-BurnSupplementaryFolder", "YES",
                  "-SupplementaryBurnPath", str(supplementary), "-BurnOsirixApplication", "YES"]
    else:
        extra += ["-BurnWeasis", "NO", "-BurnHtml", "NO", "-BurnSupplementaryFolder", "NO"]
    if name == "failure":
        target_dir.chmod(0o555)
    native_app.stop_all(app)
    process = native_app.launch(root, folder / "horos.log", extra, app=app,
                                environment={"DYLD_INSERT_LIBRARIES": str(dylib), "HOROS_BURN_TRIGGER": str(trigger),
                                             "HOROS_BURN_DMG": str(dmg), "HOROS_BURN_LOG": str(log)})
    result = {}
    try:
        data = native_app.database_folder(root)
        native_app.wait_for(lambda: (data / "INCOMING.noindex").is_dir(), 90, description="the database to open")
        native_app.wait_for(lambda: any(r.get("probe") == "loaded" for r in records(log)), 30, description="the probe")
        sources = sorted(selection.glob("*.dcm"))
        for path in sources:
            staging = data / "INCOMING.noindex" / f".{path.name}.part"
            shutil.copyfile(path, staging)
            os.rename(staging, data / "INCOMING.noindex" / path.name)
        native_app.wait_for(lambda: (native_app.image_count(root) or 0) >= len(sources), 120, description="the import")
        time.sleep(2)
        stored = sorted((data / "DATABASE.noindex").rglob("*.dcm"))
        trigger.write_text("go\n")
        # A crash ends the wait too: the estimate is checked all the same.
        native_app.wait_for(lambda: any("burn" in r for r in records(log)) or process.poll() is not None, 600,
                            interval=0.5, description="the burn")
        result["app_running"] = process.poll() is None
    finally:
        native_app.stop(process)
        if name == "failure":
            target_dir.chmod(0o755)
    lines = records(log)
    estimate = next(r["estimate"] for r in lines if "estimate" in r)
    burn = next((r["burn"] for r in lines if "burn" in r), None)
    result.update(estimate=estimate, burn=burn)

    # The estimate: the files, Weasis, the supplementary folder - never a launcher.
    kib = sum(p.stat().st_size // 1024 for p in stored)
    if name == "full":
        kib += 17 * 1024 + supplementary_kib
    match = re.search(r"No of files: (\d+)\s+Files size \(without compression\): ([\d.]+)MB", estimate["text"])
    check(match is not None, f"{name}: the size field reads {estimate['text']!r}")
    if match:
        check(int(match.group(1)) == len(sources), f"{name}: estimate counts {match.group(1)} files of {len(sources)}")
        check(match.group(2) == f"{kib / 1024.0:3.2f}", f"{name}: estimate {match.group(2)} MB, expected {kib / 1024.0:3.2f} MB "
                                                     f"(difference {float(match.group(2)) * 1024 - kib:+.0f} KiB)")
    result["estimate_expected_mb"] = f"{kib / 1024.0:3.2f}"

    if burn is None:
        check(False, f"{name}: the app died during the burn, before it reported (see {folder / 'horos.log'})")
    elif name == "failure":
        check(burn["finished"], "failure: the burn ends")
        check(not burn["dmg_exists"], "failure: no disc image is left")
        check(bool(burn["alert"]) and "not created" in burn["alert"], f"failure: the window says so ({burn['alert']!r})")
    else:
        check(burn["finished"] and burn["dmg_exists"] and not burn["alert"], f"{name}: the disc image is made ({burn})")
        mount = folder / "mounted"
        mount.mkdir()
        attached = subprocess.run(["hdiutil", "attach", "-readonly", "-nobrowse", "-mountpoint", str(mount), str(dmg)],
                                  capture_output=True, text=True)
        check(attached.returncode == 0, f"{name}: the disc image attaches ({attached.stderr.strip()[:200]})")
        try:
            files = [p for p in mount.rglob("*") if p.is_file()]
            names = [str(p.relative_to(mount)) for p in files]
            result["inventory"] = sorted(names)
            stored_hashes = sorted(hashlib.sha256(p.read_bytes()).hexdigest() for p in stored)
            dicoms = [p for p in files if p.name.upper() != "DICOMDIR" and "/DICOM/" in f"/{p.relative_to(mount)}".upper()]
            medium_hashes = sorted(hashlib.sha256(p.read_bytes()).hexdigest() for p in dicoms)
            check(medium_hashes == stored_hashes, f"{name}: the {len(stored)} DICOM files, byte for byte "
                                                 f"(found {len(dicoms)})")
            check(any(p.name.upper() == "DICOMDIR" for p in files), f"{name}: a DICOMDIR")
            # The index read back (#639): one patient, one study, two series, and an IMAGE
            # record naming each DICOM file of the medium.
            index = mount / "DICOMDIR"
            if index.is_file():
                import pydicom
                kinds, named = {}, []
                for record in pydicom.dcmread(index).DirectoryRecordSequence:
                    kinds[record.DirectoryRecordType] = kinds.get(record.DirectoryRecordType, 0) + 1
                    if record.DirectoryRecordType == "IMAGE":
                        parts = record.ReferencedFileID
                        named.append(mount.joinpath(*([parts] if isinstance(parts, str) else parts)))
                result["dicomdir_records"] = kinds
                check(kinds == {"PATIENT": 1, "STUDY": 1, "SERIES": 2, "IMAGE": len(stored)},
                      f"{name}: the DICOMDIR lists 1 patient, 1 study, 2 series, {len(stored)} images ({kinds})")
                check(sorted(named) == sorted(dicoms), f"{name}: each IMAGE record names a DICOM file of the medium, and every one is named")
            html = any(p.suffix.lower() in (".html", ".htm") for p in files)
            weasis = any("weasis" in part.lower() for n in names for part in Path(n).parts)
            extra_files = any(p.name == "instruções.txt" for p in files) and any(p.name == "viewer-notes.bin" for p in files)
            # Weasis brings its own weasis-launcher.jar; the launcher that must not be there is Horos's.
            launcher = [n for n in names if not n.lower().startswith("weasis/")
                        and re.search(r"launcher|horos lite|\.app(/|$)", n, re.IGNORECASE)]
            check(html == (name == "full"), f"{name}: HTML pages {'present' if html else 'absent'}")
            check(weasis == (name == "full"), f"{name}: Weasis {'present' if weasis else 'absent'}")
            check(extra_files == (name == "full"), f"{name}: supplementary files {'present' if extra_files else 'absent'}")
            check(not launcher, f"{name}: no launcher or application on the medium ({launcher[:3]})")
        finally:
            subprocess.run(["hdiutil", "detach", str(mount)], capture_output=True)
    check(result.get("app_running", False), f"{name}: the app is still running")
    summary["scenarios"][name] = result
    (folder / "result.json").write_text(json.dumps(result, indent=1, ensure_ascii=False) + "\n")

summary["checks"] = checks
(out / "summary.json").write_text(json.dumps(summary, indent=1, ensure_ascii=False) + "\n")
print(f"{sum(c['ok'] for c in checks)} of {len(checks)} checks passed")
raise SystemExit(0 if all(c["ok"] for c in checks) else 1)
