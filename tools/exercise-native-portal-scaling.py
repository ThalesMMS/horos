#!/usr/bin/env python3
"""The web portal's resized images and movies, from the running app (#625).

Launches the isolated development bundle with the web portal and WADO on
(loopback, no password, no encryption) and a fresh private database; imports
synthetic series through INCOMING; then asks the portal, over HTTP, for what
-[NSImage imageByScalingProportionallyToSize:] produces:

  wado    WADO rendered images (JPEG, PNG, GIF) downscaled square, letterboxed with
          a fractional side, and not resized; grey CT and RGB US
  image   /image.png and /image.jpg previews of a series
  movie   /movie.mp4 of a series (the portal scales every frame, then draws the
          frame counter on it)
  export  the database browser's movie/HTML export of every series (frames scaled
          to the movie size, 400 to 800 pixels a side), run in the app by
          tools/probe-html-export.m

Each response is decoded (Pillow, ffprobe/ffmpeg) and checked: HTTP 200, content
type, exact width and height, the picture centred without distortion, the
orientation mark top-left and the quadrant values of the synthetic pattern after
the series' window. The expected values come from the pattern and the window, not
from a previous run.

    local-validation/venv/bin/python tools/exercise-native-portal-scaling.py \\
        --out local-validation/delta4/625-app

Needs a Python with pydicom, numpy and Pillow, and ffprobe/ffmpeg on the path.
"""
import argparse
import io
import json
import os
import plistlib
import shutil
import socket
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import numpy
from PIL import Image
from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.uid import CTImageStorage, ExplicitVRLittleEndian, UltrasoundImageStorage, generate_uid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import native_app  # noqa: E402

parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument("--app", type=Path, default=native_app.DEVELOPMENT_APP)
parser.add_argument("--out", type=Path, required=True)
arguments = parser.parse_args()
out = arguments.out.resolve()
if "local-validation" not in out.parts:
    parser.error("--out must be under local-validation")
if out.exists():
    shutil.rmtree(out)
out.mkdir(parents=True)

# Grey quadrants after the window (centre 2000, width 4000: value / 4000 * 255).
GREY_STORED = {"topLeft": 800, "topRight": 1600, "bottomLeft": 2400, "bottomRight": 3200, "mark": 0}
GREY_SHOWN = {key: round(value / 4000 * 255) for key, value in GREY_STORED.items()}
RGB = {"topLeft": (220, 30, 40), "topRight": (30, 200, 60), "bottomLeft": (40, 60, 210), "bottomRight": (230, 210, 40),
       "mark": (0, 0, 0)}


def pattern(rows, columns, values, channels):
    shape = (rows, columns, channels) if channels > 1 else (rows, columns)
    array = numpy.zeros(shape, dtype=numpy.uint16 if channels == 1 else numpy.uint8)
    for y in range(rows):
        for x in range(columns):
            key = ("bottom" if y >= rows // 2 else "top") + ("Right" if x >= columns // 2 else "Left")
            if x < columns // 5 and y < rows // 5:
                key = "mark"
            array[y, x] = values[key]
    return array


def dataset(sop_class, study, series, number, modality, description):
    ds = Dataset()
    ds.file_meta = FileMetaDataset()
    ds.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
    ds.SOPClassUID, ds.SOPInstanceUID = sop_class, generate_uid()
    ds.StudyInstanceUID, ds.SeriesInstanceUID = study, series
    ds.PatientName, ds.PatientID = "SYNTHETIC^PORTAL", "SYN-625"
    ds.StudyDate, ds.StudyTime, ds.StudyID = "20260916", "120000", "625"
    ds.StudyDescription, ds.SeriesDescription = "Synthetic portal scaling", description
    ds.Modality, ds.InstanceNumber = modality, number
    return ds


def generate(folder: Path):
    folder.mkdir(parents=True)
    study = generate_uid()
    series = {}
    for label, rows, columns, count in (("ct-square", 512, 512, 6), ("ct-wide", 384, 512, 1), ("ct-small", 256, 256, 6),
                                        ("ct-large", 1024, 1024, 6)):
        uid = generate_uid()
        series[label] = {"series": uid, "rows": rows, "columns": columns, "objects": []}
        pixels = pattern(rows, columns, GREY_STORED, 1)
        for number in range(1, count + 1):
            ds = dataset(CTImageStorage, study, uid, number, "CT", label)
            ds.SeriesNumber = {"ct-square": 1, "ct-wide": 2, "ct-small": 4, "ct-large": 5}[label]
            ds.Rows, ds.Columns = rows, columns
            ds.SamplesPerPixel, ds.PhotometricInterpretation = 1, "MONOCHROME2"
            ds.BitsAllocated, ds.BitsStored, ds.HighBit, ds.PixelRepresentation = 16, 12, 11, 0
            ds.WindowCenter, ds.WindowWidth = 2000, 4000
            ds.RescaleIntercept, ds.RescaleSlope = 0, 1
            ds.PixelSpacing, ds.SliceThickness = [0.5, 0.5], 1
            ds.ImageOrientationPatient, ds.ImagePositionPatient = [1, 0, 0, 0, 1, 0], [0, 0, number]
            ds.PixelData = pixels.tobytes()
            ds.save_as(folder / f"{label}-{number}.dcm", enforce_file_format=True)
            series[label]["objects"].append(str(ds.SOPInstanceUID))
    uid = generate_uid()
    series["us-rgb"] = {"series": uid, "rows": 480, "columns": 640, "objects": []}
    pixels = pattern(480, 640, RGB, 3)
    for number in (1, 2):
        ds = dataset(UltrasoundImageStorage, study, uid, number, "US", "us-rgb")
        ds.SeriesNumber = 3
        ds.Rows, ds.Columns = 480, 640
        ds.SamplesPerPixel, ds.PhotometricInterpretation, ds.PlanarConfiguration = 3, "RGB", 0
        ds.BitsAllocated, ds.BitsStored, ds.HighBit, ds.PixelRepresentation = 8, 8, 7, 0
        ds.PixelData = pixels.tobytes()
        ds.save_as(folder / f"us-rgb-{number}.dcm", enforce_file_format=True)
        series["us-rgb"]["objects"].append(str(ds.SOPInstanceUID))
    return study, series


checks = []
failures = []


def check(condition, message, detail=None):
    checks.append({"check": message, "ok": bool(condition), **({"detail": detail} if detail is not None else {})})
    if not condition:
        failures.append(message)
        print("FAIL:", message, detail if detail is not None else "")


def fetch(port, path):
    url = f"http://127.0.0.1:{port}{path}"
    try:
        with urllib.request.urlopen(url, timeout=60) as response:
            return response.status, response.headers.get("Content-Type", ""), response.read()
    except urllib.error.HTTPError as error:
        return error.code, error.headers.get("Content-Type", ""), error.read()


def box(image):
    """The expected content box when a width x height picture is fitted into the output."""
    return image


def quadrant_values(image: Image.Image, content):
    x0, y0, w, h = content
    grey = image.mode in ("L", "LA", "I;16", "I")
    rgb = image.convert("L" if grey else "RGB")
    points = {"topLeft": (0.35, 0.3), "topRight": (0.75, 0.25), "bottomLeft": (0.25, 0.75), "bottomRight": (0.75, 0.75),
              "mark": (0.06, 0.06)}
    values = {}
    for key, (fx, fy) in points.items():
        x, y = int(x0 + fx * w), int(y0 + fy * h)
        values[key] = rgb.getpixel((x, y))
    return values, grey


def expect_picture(label, data, expected_size, source_size, kind, tolerance):
    try:
        image = Image.open(io.BytesIO(data))
        image.load()
    except Exception as error:  # noqa: BLE001
        check(False, f"{label}: decodes", str(error))
        return
    check(image.size == expected_size, f"{label}: {image.size[0]} x {image.size[1]} pixels, expected "
                                       f"{expected_size[0]} x {expected_size[1]}")
    width, height = image.size
    fit = min(width / source_size[0], height / source_size[1])
    content = ((width - source_size[0] * fit) / 2, (height - source_size[1] * fit) / 2, source_size[0] * fit,
               source_size[1] * fit)
    values, grey = quadrant_values(image, content)
    for key, value in values.items():
        if kind == "grey":
            reference = GREY_SHOWN[key]
            got = value if isinstance(value, int) else value[0]
            ok = abs(got - reference) <= tolerance
        else:
            reference = RGB[key]
            got = value if isinstance(value, tuple) else (value, value, value)
            ok = all(abs(g - r) <= tolerance for g, r in zip(got, reference))
        check(ok, f"{label}: {key} {got} against {reference}")


fixture = out / "fixture"
study_uid, series = generate(fixture)
port = 0
with socket.socket() as s:
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
root = out / "database"
data_folder = native_app.database_folder(root)
native_app.stop_all(arguments.app)
entitlements = plistlib.loads((ROOT / "build/Development/entitlements.plist").read_bytes())
entitlements["com.apple.security.cs.allow-dyld-environment-variables"] = True
(out / "probe-entitlements.plist").write_bytes(plistlib.dumps(entitlements))
subprocess.run(["/usr/bin/codesign", "--force", "--sign", "-", "--options", "runtime", "--entitlements",
                str(out / "probe-entitlements.plist"), str(arguments.app)], check=True, capture_output=True)
export_dylib = out / "probe-html-export.dylib"
subprocess.run(["xcrun", "clang", "-dynamiclib", "-fobjc-arc", "-framework", "Cocoa", str(ROOT / "tools/probe-html-export.m"),
                "-o", str(export_dylib)], check=True)
export_trigger, export_out, export_log = out / "export-go", out / "export", out / "export.jsonl"
process = native_app.launch(root, out / "horos.log",
                            ["-httpWebServer", "YES", "-httpWebServerPort", str(port), "-wadoServer", "YES",
                             "-encryptedWebServer", "NO", "-passwordWebServer", "NO",
                             "-wadoRequestRequireValidToken", "NO", "-webServerAddress", "127.0.0.1",
                             # Previews and movies are scaled to these widths: 512-pixel series
                             # then go through the scaling helper (300 x 300).
                             "-WebServerMaxWidthForMovie", "300", "-WebServerMaxWidthForStillImage", "300",
                             "-WebServerMinWidthForMovie", "64"],
                            app=arguments.app,
                            environment={"DYLD_INSERT_LIBRARIES": str(export_dylib), "HOROS_HTML_EXPORT_TRIGGER": str(export_trigger),
                                         "HOROS_HTML_EXPORT_OUT": str(export_out), "HOROS_HTML_EXPORT_LOG": str(export_log)})
results = {"port": port, "series": series}
try:
    native_app.wait_for(lambda: (data_folder / "INCOMING.noindex").is_dir(), 90, description="the database to open")
    for path in sorted(fixture.glob("*.dcm")):
        staging = data_folder / "INCOMING.noindex" / f".{path.name}.part"
        shutil.copyfile(path, staging)
        os.rename(staging, data_folder / "INCOMING.noindex" / path.name)
    total = sum(len(s["objects"]) for s in series.values())
    native_app.wait_for(lambda: (native_app.image_count(root) or 0) >= total, 120, description="the import")
    native_app.wait_for(lambda: socket.socket().connect_ex(("127.0.0.1", port)) == 0, 60, description="the web portal")
    time.sleep(2)

    # WADO: rendered images at the sizes the request asks for. Each case asks for an
    # object nothing has asked for yet: the portal keeps each object's DCMPix in its
    # WADO cache, and a second request for the same object is a different path (below).
    square, wide, us = series["ct-square"], series["ct-wide"], series["us-rgb"]
    wado_cases = [
        ("WADO grey 512x512 -> 128x128 JPEG", square, 0, "image/jpeg", 128, 128, (128, 128), "grey", 12),
        ("WADO grey 512x512 -> 128x128 PNG", square, 1, "image/png", 128, 128, (128, 128), "grey", 4),
        # GIF carries no colour profile: the encoder converts the grey to its palette's
        # colour space, in both revisions (51 -> 66, 204 -> 214); the tolerance says so.
        ("WADO grey 512x512 -> 128x128 GIF", square, 2, "image/gif", 128, 128, (128, 128), "grey", 20),
        # 512 x 384 into 300 x 200: the height limits, 266.67 x 200, drawn on 267 x 200 pixels.
        ("WADO grey 512x384 -> fractional 266.67x200 PNG", wide, 0, "image/png", 200, 300, (267, 200), "grey", 4),
        ("WADO grey 512x512 not resized PNG", square, 3, "image/png", 1024, 1024, (512, 512), "grey", 4),
        ("WADO RGB 640x480 -> 160x120 PNG", us, 0, "image/png", 120, 160, (160, 120), "rgb", 6),
        ("WADO RGB 640x480 -> 160x120 JPEG", us, 1, "image/jpeg", 120, 160, (160, 120), "rgb", 16),
    ]

    def wado(item, index, content_type, rows, columns):
        query = (f"/wado?requestType=WADO&studyUID={study_uid}&seriesUID={item['series']}&objectUID={item['objects'][index]}"
                 f"&contentType={content_type}&rows={rows}&columns={columns}")
        return fetch(port, query)

    for label, item, index, content_type, rows, columns, size, kind, tolerance in wado_cases:
        status, mime, body = wado(item, index, content_type, rows, columns)
        check(status == 200 and body, f"{label}: HTTP {status}, {len(body)} bytes")
        check(mime.startswith(content_type), f"{label}: content type {mime!r}")
        if body:
            (out / f"{label.replace(' ', '_').replace('>', '')}.{content_type.split('/')[1]}").write_bytes(body)
            expect_picture(label, body, size, (item["columns"], item["rows"]), kind, tolerance)

    # A second rendering of an object the WADO cache already holds, in another format:
    # recorded, not judged here - it does not go through the scaling helper differently,
    # and its result is the same in the revision before #625 (see the validation index).
    status, mime, body = wado(us, 0, "image/jpeg", 120, 160)
    if body:
        (out / "WADO_RGB_second_request_JPEG.jpeg").write_bytes(body)
        image = Image.open(io.BytesIO(body)).convert("RGB")
        results["second_request_rgb_jpeg"] = {"status": status, "size": image.size,
                                              "topLeft": image.getpixel((int(0.35 * 160), int(0.3 * 120))),
                                              "bottomRight": image.getpixel((int(0.75 * 160), int(0.75 * 120)))}

    # Portal previews and movies address objects by XID: <store>/<Entity>/p<pk>.
    sql = data_folder / "Database.sql"
    with sqlite3.connect(f"file:{sql}?mode=ro", uri=True) as db:
        store = db.execute("SELECT Z_UUID FROM Z_METADATA").fetchone()[0]
        series_rows = db.execute("SELECT Z_PK, ZNAME FROM ZSERIES").fetchall()  # the series description
    xids = {description: f"{store}/Series/p{pk}" for pk, description in series_rows}
    results["xids"] = xids
    for extension, mime_type in (("png", "image/png"), ("jpg", "image/jpeg")):
        status, mime, body = fetch(port, f"/image.{extension}?xid={urllib.request.quote(xids.get('ct-square', ''), safe='')}")
        label = f"/image.{extension} of the grey series"
        check(status == 200 and body, f"{label}: HTTP {status}, {len(body)} bytes")
        if body:
            (out / f"image-preview.{extension}").write_bytes(body)
            image = Image.open(io.BytesIO(body))
            results[f"image_{extension}_size"] = image.size
            check(image.size == (300, 300), f"{label}: {image.size[0]} x {image.size[1]} pixels, expected 300 x 300")
            values, _ = quadrant_values(image, (0, 0, image.size[0], image.size[1]))
            # The frame counter is drawn over the top-left corner; the other quadrants are read.
            for key in ("topRight", "bottomLeft", "bottomRight"):
                got = values[key] if isinstance(values[key], int) else values[key][0]
                check(abs(got - GREY_SHOWN[key]) <= 12, f"{label}: {key} {values[key]} against {GREY_SHOWN[key]}")

    status, mime, body = fetch(port, f"/movie.mp4?xid={urllib.request.quote(xids.get('ct-square', ''), safe='')}")
    check(status == 200 and len(body) > 1000, f"/movie.mp4 of the grey series: HTTP {status}, {len(body)} bytes")
    if body:
        movie = out / "series.mp4"
        movie.write_bytes(body)
        probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_frames", "-show_entries",
                                "stream=width,height,nb_read_frames", "-of", "json", str(movie)],
                               capture_output=True, text=True)
        stream = (json.loads(probe.stdout or "{}").get("streams") or [{}])[0]
        results["movie"] = stream
        check(int(stream.get("nb_read_frames", 0)) == len(square["objects"]),
              f"/movie.mp4: {stream.get('nb_read_frames')} frames for {len(square['objects'])} images")
        check(stream.get("width") == 300 and stream.get("height") == 300,
              f"/movie.mp4: frames {stream.get('width')} x {stream.get('height')}, expected 300 x 300")
        frame = out / "movie-frame.png"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(movie), "-vf", "select=eq(n\\,2)", "-frames:v", "1",
                        str(frame)], check=False)
        if frame.exists():
            image = Image.open(frame)
            values, _ = quadrant_values(image, (0, 0, image.size[0], image.size[1]))
            for key in ("topRight", "bottomLeft", "bottomRight"):
                got = values[key] if isinstance(values[key], int) else values[key][0]
                check(abs(got - GREY_SHOWN[key]) <= 20, f"/movie.mp4 frame 3: {key} {values[key]} against {GREY_SHOWN[key]}")
    # The browser's movie/HTML export: frames scaled to the movie size.
    export_trigger.write_text("go\n")
    native_app.wait_for(lambda: export_log.exists() and "export" in export_log.read_text(), 300, interval=0.5,
                        description="the HTML export")
    exported = json.loads(export_log.read_text().splitlines()[-1])["export"]
    results["export"] = exported
    check("exception" not in exported, f"HTML export: {exported}")
    movies = {path.stem: path for path in export_out.rglob("*.mp4")}
    results["export_files"] = sorted(str(path.relative_to(export_out)) for path in export_out.rglob("*") if path.is_file())
    check(any(path.name == "index.html" for path in export_out.rglob("*.html")), "HTML export: an index.html")
    for label, side in (("ct-small", 400), ("ct-large", 800), ("ct-square", 512)):
        # The export names files after the series with punctuation removed: ctsmall_4_4.mp4.
        movie = next((path for stem, path in movies.items() if stem.startswith(label.replace("-", "") + "_")), None)
        check(movie is not None, f"HTML export: a movie for {label} among {sorted(movies)}")
        if movie is None:
            continue
        probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_frames", "-show_entries",
                                "stream=width,height,nb_read_frames", "-of", "json", str(movie)], capture_output=True, text=True)
        stream = (json.loads(probe.stdout or "{}").get("streams") or [{}])[0]
        results[f"export_{label}"] = stream
        check((stream.get("width"), stream.get("height")) == (side, side),
              f"HTML export {label}: frames {stream.get('width')} x {stream.get('height')}, expected {side} x {side}")
        check(int(stream.get("nb_read_frames", 0)) == len(series[label]["objects"]),
              f"HTML export {label}: {stream.get('nb_read_frames')} frames for {len(series[label]['objects'])} images")
        frame = out / f"export-{label}-frame.png"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(movie), "-vf", "select=eq(n\\,2)", "-frames:v", "1",
                        str(frame)], check=False)
        if frame.exists():
            image = Image.open(frame)
            values, _ = quadrant_values(image, (0, 0, image.size[0], image.size[1]))
            for key in ("topLeft", "topRight", "bottomLeft", "bottomRight", "mark"):
                got = values[key] if isinstance(values[key], int) else values[key][0]
                check(abs(got - GREY_SHOWN[key]) <= 20, f"HTML export {label} frame 3: {key} {values[key]} against {GREY_SHOWN[key]}")
    check(process.poll() is None, "the app is still running")
finally:
    native_app.stop(process)

results["checks"] = checks
(out / "results.json").write_text(json.dumps(results, indent=1) + "\n")
print(f"{sum(c['ok'] for c in checks)} of {len(checks)} checks passed")
raise SystemExit(1 if failures else 0)
