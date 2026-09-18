#!/usr/bin/env python3
"""Images read by the app's own DCMPix, in the app (#630).

The development app imports synthetic series through INCOMING - CT 512 x 512,
384 x 256 and 128 x 128, and a 6-frame ultrasound multiframe - into a fresh
private database; tools/probe-dcmpix-load.m, injected, then loads every image
with DCMPix inside the app: cold, warm (the parsed-file cache shared with a live
DCMPix), 8 threads at once, three load/release/purge cycles, a file replaced under
a live DCMPix (#603) and broken files (truncated pixels, header only, not DICOM).
Every load's size and sampled pixel values are checked against the generator; a
broken file must fail without producing the expected pixels and without a crash.

--compression jpeg2000 or jpegls writes the same pixels losslessly encoded (JPEG
2000 reversible, JPEG-LS lossless; each frame its own fragment), so the same
checks read the app's OpenJPEG and JPEG-LS decoders (#617). Needs imagecodecs.

    local-validation/venv/bin/python tools/exercise-native-dcmpix-load.py \\
        --app build/Development/HorosDevelopment.app --out local-validation/delta4/630-app-check

Needs a Python with pydicom and numpy. Everything stays under --out.
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


def value_at(series, number, x, y):
    return (series * 1000 + number * 7 + x * 3 + y * 5) % 4000


def encapsulate_frames(ds, frames, compression: str):
    """Replace native pixel data by the frames losslessly encoded, one fragment each."""
    if compression == "none":
        return
    import imagecodecs
    from pydicom.encaps import encapsulate
    from pydicom.uid import JPEG2000Lossless, JPEGLSLossless
    if compression == "jpeg2000":
        encoded = [imagecodecs.jpeg2k_encode(frame, level=0, codecformat="J2K", reversible=True) for frame in frames]
        ds.file_meta.TransferSyntaxUID = JPEG2000Lossless
    else:
        encoded = [imagecodecs.jpegls_encode(frame, level=0) for frame in frames]
        ds.file_meta.TransferSyntaxUID = JPEGLSLossless
    ds.PixelData = encapsulate(encoded)
    ds["PixelData"].is_undefined_length = True


def generate(folder: Path, compression: str = "none"):
    """CT series of different sizes and a multiframe; stored values are a known function."""
    import numpy
    from pydicom.dataset import Dataset, FileMetaDataset
    from pydicom.uid import CTImageStorage, ExplicitVRLittleEndian, generate_uid
    folder.mkdir(parents=True)
    study = generate_uid()
    manifest = []
    for series, (rows, columns, count) in enumerate(((512, 512, 24), (384, 256, 12), (128, 128, 24)), start=1):
        uid = generate_uid()
        for number in range(1, count + 1):
            ds = Dataset()
            ds.file_meta = FileMetaDataset()
            ds.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
            ds.SOPClassUID, ds.SOPInstanceUID = CTImageStorage, generate_uid()
            ds.StudyInstanceUID, ds.SeriesInstanceUID = study, uid
            ds.PatientName, ds.PatientID = "SYNTHETIC^DCMPIX", "SYN-630"
            ds.StudyDate, ds.StudyTime, ds.StudyID = "20260916", "120000", "630"
            ds.Modality, ds.SeriesNumber, ds.InstanceNumber = "CT", series, number
            ds.Rows, ds.Columns = rows, columns
            ds.SamplesPerPixel, ds.PhotometricInterpretation = 1, "MONOCHROME2"
            ds.BitsAllocated, ds.BitsStored, ds.HighBit, ds.PixelRepresentation = 16, 12, 11, 0
            ds.RescaleIntercept, ds.RescaleSlope = 0, 1
            ds.PixelSpacing, ds.SliceThickness = [0.7, 0.7], 1
            ds.ImageOrientationPatient, ds.ImagePositionPatient = [1, 0, 0, 0, 1, 0], [0, 0, number]
            y, x = numpy.mgrid[0:rows, 0:columns]
            pixels = ((series * 1000 + number * 7 + x * 3 + y * 5) % 4000).astype(numpy.uint16)
            ds.PixelData = pixels.tobytes()
            encapsulate_frames(ds, [pixels], compression)
            path = folder / f"s{series}-{number:03d}.dcm"
            ds.save_as(path, enforce_file_format=True)
            samples = [[sx, sy, value_at(series, number, sx, sy)] for sx, sy in ((0, 0), (columns - 1, 0), (0, rows - 1),
                                                                                (columns // 2, rows // 3))]
            manifest.append({"sop": str(ds.SOPInstanceUID), "width": columns, "height": rows, "samples": samples, "frame": 0})
    # A multiframe ultrasound: every frame is its own image in the database.
    from pydicom.uid import UltrasoundMultiFrameImageStorage
    frames, rows, columns = 6, 96, 128
    ds = Dataset()
    ds.file_meta = FileMetaDataset()
    ds.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
    ds.SOPClassUID, ds.SOPInstanceUID = UltrasoundMultiFrameImageStorage, generate_uid()
    ds.StudyInstanceUID, ds.SeriesInstanceUID = study, generate_uid()
    ds.PatientName, ds.PatientID = "SYNTHETIC^DCMPIX", "SYN-630"
    ds.StudyDate, ds.StudyTime, ds.StudyID = "20260916", "120000", "630"
    ds.Modality, ds.SeriesNumber, ds.InstanceNumber = "US", 9, 1
    ds.Rows, ds.Columns, ds.NumberOfFrames = rows, columns, frames
    ds.SamplesPerPixel, ds.PhotometricInterpretation = 1, "MONOCHROME2"
    ds.BitsAllocated, ds.BitsStored, ds.HighBit, ds.PixelRepresentation = 8, 8, 7, 0
    ds.FrameTime = 40
    y, x = numpy.mgrid[0:rows, 0:columns]
    pixels = [((frame * 37 + x * 2 + y) % 256).astype(numpy.uint8) for frame in range(frames)]
    ds.PixelData = b"".join(frame.tobytes() for frame in pixels)
    encapsulate_frames(ds, pixels, compression)
    ds.save_as(folder / "multiframe.dcm", enforce_file_format=True)
    for frame in range(frames):
        samples = [[sx, sy, (frame * 37 + sx * 2 + sy) % 256] for sx, sy in ((0, 0), (columns - 1, 0), (5, rows - 1), (70, 40))]
        manifest.append({"sop": str(ds.SOPInstanceUID), "width": columns, "height": rows, "samples": samples, "frame": frame})
    return manifest


def prepare_bundle(app: Path, work: Path):
    entitlements = plistlib.loads((ROOT / "build/Development/entitlements.plist").read_bytes())
    entitlements["com.apple.security.cs.allow-dyld-environment-variables"] = True
    path = work / "probe-entitlements.plist"
    path.write_bytes(plistlib.dumps(entitlements))
    subprocess.run(["/usr/bin/codesign", "--force", "--sign", "-", "--options", "runtime", "--entitlements", str(path),
                    str(app)], check=True, capture_output=True)


def records(path: Path):
    lines = []
    if path.exists():
        for line in path.read_text(errors="replace").splitlines():
            try:
                lines.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return lines


def run_once(app: Path, fixture: Path, dylib: Path, keep: Path | None = None):
    import pydicom
    manifest = json.loads((fixture / "manifest.json").read_text())
    work = Path(tempfile.mkdtemp(prefix="dcmpix-load-", dir=str(fixture.parent)))
    root, log, trigger, plan_path = work / "database", work / "load.jsonl", work / "go", work / "plan.json"
    native_app.stop_all(app)
    process = native_app.launch(root, work / "horos.log", [], app=app,
                                environment={"DYLD_INSERT_LIBRARIES": str(dylib), "HOROS_DCMPIX_PLAN": str(plan_path),
                                             "HOROS_DCMPIX_TRIGGER": str(trigger), "HOROS_DCMPIX_LOG": str(log)})
    try:
        data = native_app.database_folder(root)
        native_app.wait_for(lambda: (data / "INCOMING.noindex").is_dir(), 90, description="the database to open")
        native_app.wait_for(lambda: any(r.get("probe") == "loaded" for r in records(log)), 30, description="the probe")
        for path in sorted((fixture / "series").glob("*.dcm")):
            staging = data / "INCOMING.noindex" / f".{path.name}.part"
            shutil.copyfile(path, staging)
            os.rename(staging, data / "INCOMING.noindex" / path.name)
        native_app.wait_for(lambda: len(list((data / "DATABASE.noindex").rglob("*.dcm"))) >= len({e["sop"] for e in manifest})
                            and (native_app.image_count(root) or 0) >= len(manifest), 180, interval=0.5,
                            description="the import")
        time.sleep(2)
        by_sop = {}
        for entry in manifest:
            by_sop.setdefault(entry["sop"], []).append(entry)
        images = []
        for path in sorted((data / "DATABASE.noindex").rglob("*.dcm")):
            for entry in by_sop[str(pydicom.dcmread(path, stop_before_pixels=True).SOPInstanceUID)]:
                images.append(dict(entry, path=str(path)))
        images.sort(key=lambda e: (e["path"], e["frame"]))
        single = [e for e in images if e["frame"] == 0 and e["width"] != 128]
        target = single[0]
        replacement = next(e for e in single if (e["width"], e["height"]) != (target["width"], target["height"]))
        plan = {"images": images,
                "replace": {"path": target["path"], "with": str(fixture / "replacement.dcm"), "width": replacement["width"],
                            "height": replacement["height"], "samples": replacement["samples"],
                            "width_before": target["width"], "height_before": target["height"],
                            "samples_before": target["samples"]},
                "broken": [str(p) for p in sorted((fixture / "broken").glob("*.dcm"))]}
        # The replacement is the other image's file content under the target's path.
        shutil.copyfile(replacement["path"], fixture / "replacement.dcm")
        plan_path.write_text(json.dumps(plan))
        trigger.write_text("go\n")
        native_app.wait_for(lambda: any("summary" in r for r in records(log)), 300, interval=0.5,
                            description="the probe's loads")
        running = process.poll() is None
    finally:
        native_app.stop(process)
    lines = records(log)
    summary = next(r["summary"] for r in lines if "summary" in r)
    loads = [r for r in lines if "phase" in r]
    failures = []
    for line in loads:
        if line["phase"] in ("cold", "warm", "concurrent", "purge-cycle", "replace-before", "replace-after"):
            if not (line["pixels"] and line["size_ok"] and line["samples_ok"]):
                failures.append(line)
        elif line["phase"] == "broken" and line["pixels"] and line["samples_ok"]:
            failures.append(line)
    if "exception" in summary or not running:
        failures.append({"summary": summary, "running": running})

    def times(phase):
        return [line["us"] for line in loads if line["phase"] == phase]

    result = {"cold_us": times("cold"), "warm_us": times("warm"), "concurrent_us": times("concurrent"),
              "concurrent_wall_ms": [summary.get("concurrent_wall_ms", -1)], "purge_us": summary.get("purge_us", []),
              "broken_us": times("broken"), "failures_count": [len(failures)]}
    if keep:
        keep.mkdir(parents=True, exist_ok=True)
        (keep / "load.jsonl").write_text(log.read_text())
        (keep / "failures.json").write_text(json.dumps(failures, indent=1) + "\n")
        (keep / "result.json").write_text(json.dumps(result, indent=1) + "\n")
    shutil.rmtree(work, ignore_errors=True)
    return result


def build_fixture(out: Path, compression: str = "none"):
    fixture = out / "fixture"
    if fixture.exists():
        shutil.rmtree(fixture)
    manifest = generate(fixture / "series", compression)
    (fixture / "manifest.json").write_text(json.dumps(manifest))
    broken = fixture / "broken"
    broken.mkdir()
    sources = sorted((fixture / "series").glob("s1-*.dcm"))
    data = sources[0].read_bytes()
    (broken / "truncated-pixels.dcm").write_bytes(data[: len(data) // 2])
    (broken / "header-only.dcm").write_bytes(data[:600])
    (broken / "not-dicom.dcm").write_bytes(os.urandom(4096))
    return fixture


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--app", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--compression", choices=("none", "jpeg2000", "jpegls"), default="none")
    arguments = parser.parse_args()
    out = arguments.out.resolve()
    if "local-validation" not in out.parts:
        parser.error("--out must be under local-validation")
    out.mkdir(parents=True, exist_ok=True)
    fixture = build_fixture(out, arguments.compression)
    dylib = out / "probe-dcmpix-load.dylib"
    subprocess.run(["xcrun", "clang", "-dynamiclib", "-fobjc-arc", "-framework", "Cocoa",
                    str(ROOT / "tools/probe-dcmpix-load.m"), "-o", str(dylib)], check=True)
    app = arguments.app.resolve()
    prepare_bundle(app, out)
    run_once(app, fixture, dylib, keep=out / "check")
    failures = json.loads((out / "check/failures.json").read_text())
    loads = [json.loads(line) for line in (out / "check/load.jsonl").read_text().splitlines() if '"phase"' in line]
    phases = {}
    for line in loads:
        phases.setdefault(line["phase"], []).append(line)
    for phase, lines in phases.items():
        ok = sum(1 for l in lines if l["pixels"] and l["size_ok"] and l["samples_ok"])
        print(f"{phase}: {len(lines)} loads, {ok} with the right size and pixels")
    print(f"failures: {len(failures)}")
    shutil.rmtree(fixture, ignore_errors=True)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
