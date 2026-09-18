#!/usr/bin/env python3
"""NSImage (N2) scales exports to the pixels asked for, with the picture intact (#625).

Links the NSImage+N2.o the application is built from into
tools/probe-image-scaling.m and scales synthetic sources made the way DCMPix
makes its images (one 8-bit grey or RGB bitmap, points equal to pixels), plus
RGBA, Retina (two pixels per point) and Display P3 sources, each with a
quadrant pattern and an orientation mark. For every source and target:

  * the result is an image of exactly the requested points and ceil(points)
    pixels, whatever the screen's backing scale;
  * the picture fits without distortion, centred, the rest transparent;
  * orientation, grey and colour values, alpha and the colour space survive
    (within the Lanczos filter's reach at quadrant centres);
  * the same size gives the same pixels; upscaling and fractional sizes work;
  * invalid sizes and an empty image give nil; the result outlives its pool;
    64 concurrent calls agree with the serial result pixel for pixel.

    python3 tests/test-image-scaling.py                 # the built object
    python3 tests/test-image-scaling.py --revision REV  # the source at REV
    python3 tests/test-image-scaling.py --source-file F # any source (the benchmark reference)
"""
import argparse
import json
import math
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import object_probe  # noqa: E402

SOURCE = "Nitrogen/Sources/NSImage+N2.mm"
parser = argparse.ArgumentParser()
parser.add_argument("--revision")
parser.add_argument("--source-file", type=Path, help="a source file to compile instead (the benchmark reference)")
parser.add_argument("--configuration", default="Debug")
arguments = parser.parse_args()

work = Path(tempfile.mkdtemp(prefix="horos-image-scaling-"))
support = []
for name in ("N2Debug", "NSException+N2", "NSColor+N2", "N2Operators"):
    obj = object_probe.app_object(name, arguments.configuration)
    if obj is not None:
        support.append(obj)
if arguments.revision or arguments.source_file:
    try:
        command = object_probe.compile_command(SOURCE, arguments.configuration)
    except LookupError as error:
        print(f"needs a build log with the compile command: {error}", file=sys.stderr)
        raise SystemExit(2)
    if arguments.source_file:
        source = work / "NSImage+N2.mm"
        source.write_bytes(arguments.source_file.read_bytes())
    else:
        source = object_probe.revision_source(SOURCE, arguments.revision, work / "NSImage+N2.mm")
    obj = work / "NSImage+N2.o"
    object_probe.compile_source(command, source, obj)
else:
    obj = object_probe.app_object("NSImage+N2", arguments.configuration)
    if obj is None:
        print("needs a built NSImage+N2.o", file=sys.stderr)
        raise SystemExit(2)
probe = object_probe.link_probe(ROOT / "tools/probe-image-scaling.m", [obj] + support, work / "probe",
                                frameworks=("Cocoa", "CoreImage", "QuartzCore", "Accelerate"))
run = subprocess.run([str(probe), "contract"], capture_output=True, text=True, timeout=300)
if run.returncode != 0:
    print(run.stdout[-2000:], run.stderr[-4000:])
    raise SystemExit(1)
result = json.loads(run.stdout.strip().splitlines()[-1])
print(f"object under test: {obj}")
failures = []


def check(condition, message):
    if not condition:
        failures.append(message)
        print("FAIL:", message)


def close(a, b, tolerance):
    return abs(a - b) <= tolerance


for case in result["cases"]:
    label = f"{case['source']} {case['source_pixels']} -> {case['target']}"
    output, source_description = case["output"], case["input"]
    if output.get("nil", True):
        check(False, f"{label}: no image")
        continue
    target_w, target_h = case["target"]
    check(close(output["points"][0], target_w, 1e-6) and close(output["points"][1], target_h, 1e-6),
          f"{label}: {output['points']} points")
    check(output["pixels"] == [math.ceil(target_w), math.ceil(target_h)], f"{label}: {output['pixels']} pixels")
    check(output["bits"] == 8, f"{label}: {output['bits']} bits")
    expected_model = 0 if case["source"] == "grey" else 1
    check(output["model"] == expected_model, f"{label}: colour model {output['model']}")
    if case["source"] == "p3":
        check("P3" in output["colour_space"], f"{label}: colour space {output['colour_space']}")
    # The picture fits without distortion, centred.
    points_w, points_h = case["source_points"]
    pixels_w, pixels_h = output["pixels"]
    fit = min(pixels_w / points_w, pixels_h / points_h)
    content_w, content_h = points_w * fit, points_h * fit
    expected = {"x": (pixels_w - content_w) / 2, "y": (pixels_h - content_h) / 2, "width": content_w, "height": content_h}
    box = output["opaque"]
    check(all(abs(box[key] - expected[key]) <= 1.5 for key in expected), f"{label}: content {box}, expected {expected}")
    # Values at the quadrant centres and the orientation mark match the source.
    colours = 1 if case["source"] == "grey" else 3
    for key, values in output["values"].items():
        reference = source_description["values"][key]
        ok = all(close(values[c], reference[c], 3) for c in range(colours))
        check(ok, f"{label}: {key} {values[:colours]} vs source {reference[:colours]}")
    if case["target"] == case["source_points"] and case["source"] != "retina":
        check(case["identical_colours"], f"{label}: the same size changed pixels")

check(all(value is True for value in result["invalid_returns_nil"].values()),
      f"invalid inputs: {result['invalid_returns_nil']}")
check(not result["after_pool"].get("nil", True) and result["after_pool"]["pixels"] == [150, 100],
      f"after the pool: {result['after_pool']}")
check(result["concurrent"] == {"calls": 64, "failures": 0, "mismatches": 0}, f"concurrent: {result['concurrent']}")

if failures:
    print(f"{len(failures)} failure(s)")
    raise SystemExit(1)
print(f"PASS: {len(result['cases'])} source/target pairs keep exact size, fit, centring, orientation, values and "
      "colour space; same size identical; invalid inputs nil; result outlives its pool; 64 concurrent calls identical")
