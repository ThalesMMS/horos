#!/usr/bin/env python3
"""WADO renderings of an object the portal already holds, against first renderings (#635).

The portal keeps each object's DCMPix (wadoCache, per object and frame) and
renders every later request for that object from it. This launches the isolated
development bundle with the web portal and WADO on (loopback, no password), imports
synthetic objects through INCOMING and compares, request by request:

  reference   each combination of parameters asked of an identical copy nothing
              has asked for anything yet - what a first request returns
  shared      every combination asked of one object in a shuffled order, then
              again in the reverse order (so each rendering but the very first
              comes from the cached DCMPix)

Objects: grey CT with a window in the file, grey CT without one, RGB US, and a
three-frame grey object without a window. Combinations: PNG and JPEG; natural size
and 160 x 120; no window and an explicit window; frames 0 and 2 of the multiframe.
Each shared response must decode to the reference's size and pixels (PNG exactly,
JPEG within 2 levels). The client-side latency of each request is recorded
(first_ms: an object's first rendering; repeat_valid_ms and repeat_corrected_ms:
a new combination from the cached DCMPix - valid when its window was applied
correctly before #635 too, corrected otherwise; cached_ms: a combination asked
before, served from the response cache).

With --baseline-app and --candidate-app it runs the A/A and A/B of those
latencies instead (one launch per invocation, --rounds alternated rounds).

    local-validation/venv/bin/python tools/exercise-native-wado-cache.py \\
        --app build/Variants/candidate/HorosDevelopment.app --out local-validation/delta4/635-app/candidate

Needs a Python with pydicom, numpy and Pillow. Exit 0 when every shared response
matches its reference.
"""
import argparse
import io
import itertools
import json
import os
import random
import shutil
import socket
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import numpy
from PIL import Image
from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.uid import (CTImageStorage, ExplicitVRLittleEndian, UltrasoundImageStorage,
                         UltrasoundMultiFrameImageStorage, generate_uid)

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import native_app  # noqa: E402

FORMATS = ("image/png", "image/jpeg")
SIZES = (None, (120, 160))
WINDOWS = (None, (1500, 3000))


def base(sop_class, study, series, number, modality, description):
    ds = Dataset()
    ds.file_meta = FileMetaDataset()
    ds.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
    ds.SOPClassUID, ds.SOPInstanceUID = sop_class, generate_uid()
    ds.StudyInstanceUID, ds.SeriesInstanceUID = study, series
    ds.PatientName, ds.PatientID = "SYNTHETIC^WADO", "SYN-635"
    ds.StudyDate, ds.StudyTime, ds.StudyID = "20260916", "120000", "635"
    ds.StudyDescription, ds.SeriesDescription = "Synthetic WADO cache", description
    ds.Modality, ds.InstanceNumber, ds.SeriesNumber = modality, number, 1
    return ds


def grey(rows, columns, frame=0):
    y, x = numpy.mgrid[0:rows, 0:columns]
    return ((x * 7 + y * 3 + frame * 900) % 4000).astype(numpy.uint16)


def generate(folder: Path, copies: int):
    folder.mkdir(parents=True)
    study = generate_uid()
    kinds = {}

    def add(kind, make):
        uid = generate_uid()
        kinds[kind] = {"series": uid, "objects": []}
        for number in range(1, copies + 2):
            sop_class, modality = make.header
            ds = make(base(sop_class, study, uid, number, modality, kind))
            ds.save_as(folder / f"{kind}-{number}.dcm", enforce_file_format=True)
            kinds[kind]["objects"].append(str(ds.SOPInstanceUID))

    def ct(window):
        def make(ds):
            ds.Rows, ds.Columns = 256, 320
            ds.SamplesPerPixel, ds.PhotometricInterpretation = 1, "MONOCHROME2"
            ds.BitsAllocated, ds.BitsStored, ds.HighBit, ds.PixelRepresentation = 16, 12, 11, 0
            if window:
                ds.WindowCenter, ds.WindowWidth = 2000, 4000
            ds.RescaleIntercept, ds.RescaleSlope = 0, 1
            ds.PixelSpacing = [0.5, 0.5]
            ds.PixelData = grey(256, 320).tobytes()
            return ds
        make.header = (CTImageStorage, "CT")
        return make

    def us(ds):
        ds.Rows, ds.Columns = 240, 320
        ds.SamplesPerPixel, ds.PhotometricInterpretation, ds.PlanarConfiguration = 3, "RGB", 0
        ds.BitsAllocated, ds.BitsStored, ds.HighBit, ds.PixelRepresentation = 8, 8, 7, 0
        y, x = numpy.mgrid[0:240, 0:320]
        rgb = numpy.stack([(x * 255 // 319), (y * 255 // 239), ((x + y) * 255 // 558)], axis=-1).astype(numpy.uint8)
        ds.PixelData = rgb.tobytes()
        return ds
    us.header = (UltrasoundImageStorage, "US")

    def multiframe(ds):
        ds.Rows, ds.Columns, ds.NumberOfFrames = 128, 160, 3
        ds.SamplesPerPixel, ds.PhotometricInterpretation = 1, "MONOCHROME2"
        ds.BitsAllocated, ds.BitsStored, ds.HighBit, ds.PixelRepresentation = 16, 12, 11, 0
        ds.PixelData = b"".join(grey(128, 160, f).tobytes() for f in range(3))
        return ds
    multiframe.header = (UltrasoundMultiFrameImageStorage, "US")

    add("ct-window", ct(True))
    add("ct-no-window", ct(False))
    add("us-rgb", us)
    add("multiframe", multiframe)
    return study, kinds


def combinations(kind):
    frames = (0, 2) if kind == "multiframe" else (0,)
    return list(itertools.product(FORMATS, SIZES, WINDOWS, frames))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--app", type=Path, default=native_app.DEVELOPMENT_APP)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=635)
    parser.add_argument("--baseline-app", type=Path)
    parser.add_argument("--candidate-app", type=Path)
    parser.add_argument("--rounds", type=int, default=10)
    parser.add_argument("--limit", action="append", default=[])
    parser.add_argument("--metrics", action="store_true", help=argparse.SUPPRESS)
    arguments = parser.parse_args()
    if arguments.baseline_app:
        return compare(arguments)
    out = arguments.out.resolve()
    if "local-validation" not in out.parts:
        parser.error("--out must be under local-validation")
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    copies = max(len(combinations(k)) for k in ("ct-window", "multiframe"))
    study, kinds = generate(out / "fixture", copies)
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    root = out / "database"
    data = native_app.database_folder(root)
    app = arguments.app.resolve()
    native_app.stop_all(app)
    process = native_app.launch(root, out / "horos.log",
                                ["-httpWebServer", "YES", "-httpWebServerPort", str(port), "-wadoServer", "YES",
                                 "-encryptedWebServer", "NO", "-passwordWebServer", "NO",
                                 "-wadoRequestRequireValidToken", "NO", "-webServerAddress", "127.0.0.1"], app=app)
    results = {"app": str(app), "port": port, "seed": arguments.seed, "cases": [], "latency": {}}
    failures = []
    try:
        native_app.wait_for(lambda: (data / "INCOMING.noindex").is_dir(), 90, description="the database to open")
        files = sorted((out / "fixture").glob("*.dcm"))
        for path in files:
            staging = data / "INCOMING.noindex" / f".{path.name}.part"
            shutil.copyfile(path, staging)
            os.rename(staging, data / "INCOMING.noindex" / path.name)
        native_app.wait_for(lambda: (native_app.image_count(root) or 0) >= sum(
            len(k["objects"]) * (3 if name == "multiframe" else 1) for name, k in kinds.items()), 180, description="the import")
        native_app.wait_for(lambda: socket.socket().connect_ex(("127.0.0.1", port)) == 0, 60, description="the web portal")
        time.sleep(2)

        def request(kind, index, combination):
            content, size, window, frame = combination
            query = (f"/wado?requestType=WADO&studyUID={study}&seriesUID={kinds[kind]['series']}"
                     f"&objectUID={kinds[kind]['objects'][index]}&contentType={content}&frameNumber={frame}")
            if size:
                query += f"&rows={size[0]}&columns={size[1]}"
            if window:
                query += f"&windowCenter={window[0]}&windowWidth={window[1]}"
            start = time.perf_counter()
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}{query}", timeout=60) as response:
                    body = response.read()
                    status = response.status
            except urllib.error.HTTPError as error:
                body, status = error.read(), error.code
            return status, body, (time.perf_counter() - start) * 1000

        def decode(body):
            image = Image.open(io.BytesIO(body))
            return numpy.asarray(image.convert("RGB")).astype(numpy.int16)

        # A repeat is "valid" when the window it asks for was applied correctly by the
        # code before #635 as well: an explicit window, or an object whose file has one.
        latency = {"first_ms": [], "repeat_valid_ms": [], "repeat_corrected_ms": [], "cached_ms": []}
        for kind in kinds:
            combos = combinations(kind)
            references = {}
            for index, combination in enumerate(combos, start=1):
                status, body, elapsed = request(kind, index, combination)
                latency["first_ms"].append(elapsed)
                references[combination] = (status, body)
            order = combos[:]
            random.Random(arguments.seed).shuffle(order)
            for position, combination in enumerate(order + order[::-1]):
                status, body, elapsed = request(kind, 0, combination)
                if position == 0:
                    latency["first_ms"].append(elapsed)
                elif position < len(order):
                    valid = combination[2] is not None or kind == "ct-window"
                    latency["repeat_valid_ms" if valid else "repeat_corrected_ms"].append(elapsed)
                else:
                    latency["cached_ms"].append(elapsed)
                ref_status, ref_body = references[combination]
                case = {"kind": kind, "combination": list(map(str, combination)), "pass": "first" if position < len(order) else "second",
                        "status": status, "bytes": len(body)}
                ok = status == ref_status == 200 and body and ref_body
                if ok:
                    got, expected = decode(body), decode(ref_body)
                    ok = got.shape == expected.shape
                    difference = int(numpy.abs(got - expected).max()) if ok else None
                    tolerance = 0 if combination[0] == "image/png" else 2
                    ok = ok and difference <= tolerance
                    case.update(shape=list(got.shape), reference_shape=list(expected.shape), max_difference=difference)
                    if not ok:
                        name = f"{kind}-{'-'.join(str(c).replace('/', '_').replace(' ', '') for c in combination)}-{case['pass']}"
                        (out / "mismatches").mkdir(exist_ok=True)
                        (out / "mismatches" / f"{name}.shared").write_bytes(body)
                        (out / "mismatches" / f"{name}.reference").write_bytes(ref_body)
                case["ok"] = bool(ok)
                results["cases"].append(case)
                if not ok:
                    failures.append(case)
        results["latency"] = latency
        results["app_running"] = process.poll() is None
    finally:
        native_app.stop(process)
    (out / "result.json").write_text(json.dumps(results, indent=1) + "\n")
    for case in failures:
        print(f"FAIL {case['kind']} {case['combination']} ({case['pass']} pass): {case.get('max_difference')} "
              f"{case.get('shape')} vs {case.get('reference_shape')}")
    for name, values in results["latency"].items():
        if values:
            print(f"{name}: n={len(values)} median={sorted(values)[len(values) // 2]:.2f} ms")
    print(f"{len(results['cases']) - len(failures)} of {len(results['cases'])} shared responses match their reference")
    if arguments.metrics:
        metrics = dict(results["latency"])
        metrics["mismatch_count"] = [len(failures)]
        print(json.dumps(metrics))
        shutil.rmtree(out / "fixture", ignore_errors=True)
        shutil.rmtree(out / "database", ignore_errors=True)
        return 0
    return 0 if not failures and results.get("app_running") else 1


def compare(arguments):
    """A/A and A/B of the latencies: one launch per invocation, alternated by round."""
    import ab_protocol
    out = arguments.out.resolve()
    if "local-validation" not in out.parts:
        raise SystemExit("--out must be under local-validation")
    out.mkdir(parents=True, exist_ok=True)
    apps = {"baseline": arguments.baseline_app.resolve(), "candidate": arguments.candidate_app.resolve()}

    def command(label, slot):
        return [sys.executable, str(Path(__file__).resolve()), "--app", str(apps[label]),
                "--out", str(out / f"run-{slot}"), "--seed", str(arguments.seed), "--metrics"]

    plan = {"apps": {k: str(v) for k, v in apps.items()}, "rounds": arguments.rounds, "limits": arguments.limit,
            "protocol_version": ab_protocol.PROTOCOL_VERSION,
            "design": "one launch per invocation, alternated by round; client-side latency of each WADO request"}
    (out / "plan.json").write_text(json.dumps(plan, indent=1) + "\n")
    limits = ab_protocol._parse_limits(arguments.limit)
    aa = ab_protocol.run_protocol({"A": command("baseline", "a"), "A'": command("baseline", "b")}, arguments.rounds, 1)
    (out / "aa.json").write_text(json.dumps(aa) + "\n")
    tolerance = ab_protocol.calibrate(aa, limits, set(), ab_protocol.DEFAULT_SEED, ab_protocol.DEFAULT_RESAMPLES)
    (out / "tolerance.json").write_text(json.dumps(tolerance, indent=1) + "\n")
    ab = ab_protocol.run_protocol({"baseline": command("baseline", "a"), "candidate": command("candidate", "b")},
                                  arguments.rounds, 1)
    (out / "ab.json").write_text(json.dumps(ab) + "\n")
    analysis = ab_protocol.analyze(ab, tolerance, set(), ab_protocol.DEFAULT_SEED, ab_protocol.DEFAULT_RESAMPLES)
    (out / "analysis.json").write_text(json.dumps(analysis, indent=1) + "\n")
    table = ab_protocol.markdown(analysis, ("baseline", "candidate"))
    (out / "table.md").write_text(table)
    print(table)
    return 0 if analysis["overall"] == "non-inferior" else 1


if __name__ == "__main__":
    raise SystemExit(main())
