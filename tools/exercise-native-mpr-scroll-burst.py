#!/usr/bin/env python3
"""Bursts of scroll events on the 3D MPR, and what the screen shows after them (#611).

A synthetic CT phantom (tools/measure-native-sr-surfaces.py's: a body cylinder of 40 HU in air with a
sphere of 800 HU; 192 x 192 x 100, or --size and --slices) is imported into a fresh private database, and
tools/probe-mpr-scroll-burst.m, injected, opens its 3D MPR: MIP of 1 mm, the three views at 100 %,
WL 40 / WW 400, with Use Metal in MPR off (VTK) or on (Metal), one launch each.

Per batch, on the first view, as in the report: --events scroll events alternating up and down (so the
plane ends where it started), each handled in its own main-queue block. Around it, without any other
event, the view is captured before, during, and 0, 0.3, 1 and 3 s after the last event, in two ways
that do not share a tool call:

  window   screencapture -l <window>: the window server's image of the MPR window alone
  display  screencapture -R <view>: the composited display, cut to the view's rectangle

and at the same moments the probe reports each view's reconstructed plane (DCMPix: size and the mean of
its central quarter), how many times the view drew and how long ago it last did. Both captures share
the window server (ScreenCaptureKit) and neither proves the signal on the monitor; the draw count and
the plane are the app's side of it.

The anatomy is measured in the central fifth of the view: its mean luminance, against the same capture
before the burst. A capture holds the anatomy when that mean is at least half the reference.

    local-validation/venv/bin/python tools/exercise-native-mpr-scroll-burst.py \\
        --app build/Variants/candidate/HorosDevelopment.app --out local-validation/611-app

Needs a Python with pydicom, numpy and Pillow, and screen recording allowed for the process that runs it.
Captures show only the synthetic phantom and stay under --out.
"""
import argparse
import importlib.util
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

SCREENCAPTURE = "/usr/sbin/screencapture"


def phantom(folder: Path, size: int, slices: int) -> str:
    """The SR tool's phantom, at `size` x `size` x `slices`; the main series' SeriesInstanceUID."""
    spec = importlib.util.spec_from_file_location("sr_surfaces", ROOT / "tools/measure-native-sr-surfaces.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.SIZE, module.SLICES = size, slices
    uids = module.generate(folder)
    for path in folder.glob("fusion-*.dcm"):
        path.unlink()
    return uids["main"]


def prepare(app: Path, out: Path) -> Path:
    entitlements = plistlib.loads((ROOT / "build/Development/entitlements.plist").read_bytes())
    entitlements["com.apple.security.cs.allow-dyld-environment-variables"] = True
    path = out / "probe-entitlements.plist"
    path.write_bytes(plistlib.dumps(entitlements))
    subprocess.run(["/usr/bin/codesign", "--force", "--sign", "-", "--options", "runtime", "--entitlements", str(path),
                    str(app)], check=True, capture_output=True)
    dylib = out / "probe-mpr-scroll-burst.dylib"
    subprocess.run(["xcrun", "clang", "-dynamiclib", "-fobjc-arc", "-framework", "Cocoa",
                    str(ROOT / "tools/probe-mpr-scroll-burst.m"), "-o", str(dylib)], check=True)
    return dylib


class Session:
    def __init__(self, app: Path, root: Path, dylib: Path, log: Path):
        self.commands = Path(tempfile.mkdtemp(prefix="mpr-commands-", dir=str(root.parent)))
        self.number = 0
        native_app.stop_all(app)
        self.process = native_app.launch(root, log, ["-ApplePersistenceIgnoreState", "YES"], app=app,
                                         environment={"DYLD_INSERT_LIBRARIES": str(dylib),
                                                      "HOROS_MPR_COMMANDS": str(self.commands)})

    def send(self, payload: dict) -> Path:
        self.number += 1
        staging = self.commands / f".{self.number}.json"
        staging.write_text(json.dumps(payload))
        os.rename(staging, self.commands / f"{self.number}.json")
        return self.commands / f"{self.number}.out.json"

    def command(self, payload: dict, timeout: float = 300):
        answer = self.send(payload)
        native_app.wait_for(lambda: answer.exists() or self.process.poll() is not None, timeout, interval=0.05,
                            description=f"the answer to {payload['action']}")
        return json.loads(answer.read_text()) if answer.exists() else None

    def stop(self):
        native_app.stop(self.process)
        shutil.rmtree(self.commands, ignore_errors=True)


def window_bounds(number: int):
    """The window's bounds in screen points, top-left origin, from the window list."""
    script = ("import CoreGraphics\nlet list = CGWindowListCopyWindowInfo([.optionIncludingWindow], CGWindowID(%d)) as? [[String: Any]] ?? []\n"
              "if let b = list.first?[kCGWindowBounds as String] as? [String: Any] { print(b[\"X\"]!, b[\"Y\"]!, b[\"Width\"]!, b[\"Height\"]!) }\n"
              % number)
    with tempfile.NamedTemporaryFile("w", suffix=".swift", delete=False) as handle:
        handle.write(script)
    try:
        output = subprocess.run(["swift", handle.name], capture_output=True, text=True, timeout=120).stdout.split()
    finally:
        os.unlink(handle.name)
    return [float(v) for v in output] if len(output) == 4 else None


def central_mean(image_path: Path, box):
    """Mean luminance (0-255) of the central fifth of `box` (x, y, width, height in the image's pixels)."""
    import numpy
    from PIL import Image
    with Image.open(image_path) as image:
        gray = numpy.asarray(image.convert("L"), dtype=numpy.float64)
    x, y, width, height = box
    cx, cy = x + width / 2, y + height / 2
    x0, x1 = int(round(cx - width / 10)), int(round(cx + width / 10))
    y0, y1 = int(round(cy - height / 10)), int(round(cy + height / 10))
    region = gray[max(0, y0):max(0, y1), max(0, x0):max(0, x1)]
    return float(region.mean()) if region.size else None


def capture(folder: Path, label: str, window: int, window_origin, frame, scale: float):
    """Both captures of the view at one moment: the time each was taken and the anatomy measure."""
    result = {}
    path = folder / f"{label}-window.png"
    taken = time.monotonic()
    code = subprocess.run([SCREENCAPTURE, "-x", "-o", "-l", str(window), str(path)], capture_output=True).returncode
    if code == 0 and path.exists() and window_origin:
        box = ((frame["x"] - window_origin[0]) * scale, (frame["y"] - window_origin[1]) * scale,
               frame["width"] * scale, frame["height"] * scale)
        result["window"] = {"at": taken, "mean": central_mean(path, box)}
    else:
        result["window"] = {"at": taken, "error": f"screencapture -l exited {code}"}
    path = folder / f"{label}-display.png"
    taken = time.monotonic()
    rect = ",".join(str(int(round(frame[key]))) for key in ("x", "y", "width", "height"))
    code = subprocess.run([SCREENCAPTURE, "-x", "-R", rect, str(path)], capture_output=True).returncode
    if code == 0 and path.exists():
        from PIL import Image
        with Image.open(path) as image:
            size = image.size
        result["display"] = {"at": taken, "mean": central_mean(path, (0, 0, size[0], size[1]))}
    else:
        result["display"] = {"at": taken, "error": f"screencapture -R exited {code}"}
    return result


def run_control(control: str, app: Path, out: Path, fixture: Path, series: str, dylib: Path, arguments) -> dict:
    folder = out / control
    if folder.exists():
        shutil.rmtree(folder)
    folder.mkdir(parents=True)
    root = folder / "database"
    session = Session(app, root, dylib, folder / "horos.log")
    record = {"control": control, "batches": []}
    try:
        data = native_app.database_folder(root)
        native_app.wait_for(lambda: (data / "INCOMING.noindex").is_dir(), 90, description="the database to open")
        if not (session.command({"action": "ping"}, 90) or {}).get("ok"):
            raise RuntimeError("the probe did not answer")
        for path in sorted(fixture.glob("*.dcm")):
            staging = data / "INCOMING.noindex" / f".{path.name}.part"
            shutil.copyfile(path, staging)
            os.rename(staging, data / "INCOMING.noindex" / path.name)
        native_app.wait_for(lambda: (native_app.image_count(root) or 0) >= arguments.slices, 600, interval=0.5,
                            description="the import")
        time.sleep(2)
        opened = session.command({"action": "open", "series": series, "mode": 1, "thickness_mm": 1.0, "wl": 40, "ww": 400,
                                  "metal": control == "metal", "fill_screen": arguments.fill_screen})
        record["open"] = opened
        if not opened or not opened.get("ok"):
            raise RuntimeError(f"could not open the 3D MPR: {opened}")
        time.sleep(3)
        window = opened["window"]
        scale = opened["backing_scale"]
        frame = opened["frames"][arguments.view - 1]
        origin = window_bounds(window)
        record["window_bounds"] = origin
        for batch in range(arguments.batches):
            entry = {"batch": batch + 1, "first": 1 if batch % 2 == 0 else -1, "captures": []}
            entry["captures"].append({"moment": "before", "state": session.command({"action": "state"}),
                                      **capture(folder, f"b{batch + 1}-before", window, origin, frame, scale)})
            answer_path = session.send({"action": "burst", "view": arguments.view, "events": arguments.events,
                                        "delta": arguments.delta, "first": entry["first"],
                                        "interval_ms": arguments.interval_ms})
            during = 0
            while not answer_path.exists() and session.process.poll() is None:
                entry["captures"].append({"moment": f"during-{during}",
                                          **capture(folder, f"b{batch + 1}-during-{during}", window, origin, frame, scale)})
                during += 1
            ended = time.monotonic()
            entry["burst"] = json.loads(answer_path.read_text()) if answer_path.exists() else None
            for delay in arguments.after_ms:
                wait = ended + delay / 1000 - time.monotonic()
                if wait > 0:
                    time.sleep(wait)
                label = f"after-{delay}ms"
                entry["captures"].append({"moment": label, "since_end_s": time.monotonic() - ended,
                                          **capture(folder, f"b{batch + 1}-{label}", window, origin, frame, scale),
                                          "state": session.command({"action": "state"})})
            record["batches"].append(entry)
            time.sleep(2)
    finally:
        session.stop()
    return record


def verdicts(record: dict, view: int) -> list:
    """Per capture after a burst: whether each capture holds the anatomy, and the app's side of it."""
    lines = []
    for entry in record["batches"]:
        before = next(c for c in entry["captures"] if c["moment"] == "before")
        reference = {kind: before[kind].get("mean") for kind in ("window", "display")}
        for moment in entry["captures"]:
            row = {"batch": entry["batch"], "moment": moment["moment"]}
            for kind in ("window", "display"):
                mean, ref = moment[kind].get("mean"), reference[kind]
                row[kind] = None if mean is None or not ref else round(mean / ref, 3)
            state = (moment.get("state") or {}).get("views")
            if state:
                row["plane_mean"] = state[view - 1]["central_mean"]
                row["draws"] = state[view - 1]["draws"]
                row["since_last_draw_ms"] = state[view - 1]["since_last_draw_ms"]
            lines.append(row)
    return lines


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--app", type=Path, default=native_app.DEVELOPMENT_APP)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--control", action="append", choices=["vtk", "metal"])
    parser.add_argument("--batches", type=int, default=2)
    parser.add_argument("--events", type=int, default=120)
    parser.add_argument("--delta", type=float, default=1.5)
    parser.add_argument("--interval-ms", type=float, default=0)
    parser.add_argument("--view", type=int, choices=(1, 2, 3), default=1)
    parser.add_argument("--after-ms", type=float, action="append")
    parser.add_argument("--size", type=int, default=192, help="columns and rows of the phantom")
    parser.add_argument("--slices", type=int, default=100)
    parser.add_argument("--fill-screen", action="store_true", help="the MPR window takes the screen's visible frame")
    arguments = parser.parse_args()
    arguments.after_ms = arguments.after_ms or [0, 300, 1000, 3000]
    out = arguments.out.resolve()
    if "local-validation" not in out.parts:
        parser.error("--out must be under local-validation")
    out.mkdir(parents=True, exist_ok=True)
    fixture = out / "fixture"
    if fixture.exists():
        shutil.rmtree(fixture)
    series = phantom(fixture, arguments.size, arguments.slices)
    app = arguments.app.resolve()
    dylib = prepare(app, out)
    summary = {"app": str(app), "arguments": {k: v for k, v in vars(arguments).items() if k not in ("app", "out")},
               "controls": {}}
    for control in arguments.control or ["vtk", "metal"]:
        record = run_control(control, app, out, fixture, series, dylib, arguments)
        (out / f"{control}.json").write_text(json.dumps(record, indent=1) + "\n")
        rows = verdicts(record, arguments.view)
        summary["controls"][control] = rows
        print(f"{control}:")
        for row in rows:
            if row["moment"].startswith("during"):
                continue
            print("  batch {batch} {moment:>12}: window {window}, display {display}, plane {plane_mean}, draws {draws}, "
                  "last draw {since_last_draw_ms} ms ago".format(**{k: row.get(k) for k in
                  ("batch", "moment", "window", "display", "plane_mean", "draws", "since_last_draw_ms")}))
        lows = [r for r in rows if r["moment"].startswith("during") and any((r.get(k) or 1) < 0.5 for k in ("window", "display"))]
        print(f"  during the bursts: {len(lows)} of {sum(r['moment'].startswith('during') for r in rows)} captures without the anatomy")
    (out / "summary.json").write_text(json.dumps(summary, indent=1) + "\n")
    shutil.rmtree(fixture, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
