#!/usr/bin/env python3
"""The #631 NIfTI/Analyze matrix through the development app: detection, import, viewer, metadata.

tools/generate-nifti-matrix.py writes the files and their expectations;
tools/probe-nifti-import.m, injected, drives the app. For each import path, in a
fresh private database:

  incoming   each case's folder dropped into INCOMING.noindex
  copy       File > Import with "copy files into the database" (COPYDATABASE YES, always)
  link       File > Import without copying (COPYDATABASE NO): the database points at the files

then every series the database made is opened in a 2D viewer the way the browser
opens it, and every frame the viewer holds is read back: size, spacing,
thickness, interval, origin, orientation, readability and the values at the
generator's sample points. Separately, for every case, +[DicomFile isNIfTIFile:]
and -[DicomFile init:] (detection and registration) and +[DicomFile getNIfTIXML:]
(the metadata window) on the original files.

A database row is matched to its case by the file it points at: a file linked in
place by its folder, a copy by its SHA-256, so a renamed copy is still recognised.
Each case's files carry the case's name (the app names a NIfTI series after its
file, #641). The app dying is recorded against the step that killed it, and the app
is relaunched on the same database for the rest.

Checks against the generator (valid cases, wherever a series was made): one
frame per slice of the first volume, the columns and rows, the in-plane spacing
and the slice thickness, and every sampled value as stored (Horos does not apply
scl_slope/scl_inter). Bad cases: not indexed, or indexed and shown as unreadable;
never a crash.

    local-validation/venv/bin/python tools/exercise-native-nifti-import.py \\
        --app build/Variants/candidate/HorosDevelopment.app --out local-validation/delta4/631-app/candidate
    local-validation/venv/bin/python tools/exercise-native-nifti-import.py \\
        --compare local-validation/delta4/631-app/baseline local-validation/delta4/631-app/candidate

--compare writes compare.json and compare.md next to the second result: where the
two apps differ, case by case. Needs numpy. Everything stays under --out.
"""
import argparse
import hashlib
import json
import plistlib
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import native_app  # noqa: E402

MODES = {"incoming": [], "copy": ["-COPYDATABASE", "YES", "-COPYDATABASEMODE", "0"], "link": ["-COPYDATABASE", "NO"]}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class App:
    """One launch of the app with the probe, answering numbered commands."""

    def __init__(self, app: Path, root: Path, folder: Path, dylib: Path, extra: list[str]):
        self.app, self.root, self.folder, self.dylib, self.extra = app, root, folder, dylib, extra
        self.launches = 0
        self.start()

    def start(self):
        self.launches += 1
        self.commands = self.folder / f"commands-{self.launches}"
        self.commands.mkdir(parents=True)
        self.number = 0
        native_app.stop_all(self.app)
        # A relaunch after a crash must not stop at the system's offer to reopen the windows.
        self.process = native_app.launch(self.root, self.folder / f"horos-{self.launches}.log",
                                         ["-LISTENERCHECKINTERVAL", "1", "-ApplePersistenceIgnoreState", "YES"]
                                         + self.extra, app=self.app,
                                         environment={"DYLD_INSERT_LIBRARIES": str(self.dylib),
                                                      "HOROS_NIFTI_COMMANDS": str(self.commands)})
        data = native_app.database_folder(self.root)
        native_app.wait_for(lambda: (data / "INCOMING.noindex").is_dir(), 90, description="the database to open")
        self.ask({"action": "ping"}, timeout=60)

    def alive(self):
        return self.process.poll() is None

    def ask(self, command, timeout=120):
        self.number += 1
        (self.commands / f".{self.number}.json").write_text(json.dumps(command))
        (self.commands / f".{self.number}.json").rename(self.commands / f"{self.number}.json")
        answer = self.commands / f"{self.number}.out.json"
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if answer.exists():
                return json.loads(answer.read_text())
            if not self.alive():
                return {"crashed": True, "exit": self.process.returncode}
            time.sleep(0.1)
        return {"timeout": True}

    def stop(self):
        native_app.stop(self.process)


def prepare(app: Path, out: Path) -> Path:
    entitlements = plistlib.loads((ROOT / "build/Development/entitlements.plist").read_bytes())
    entitlements["com.apple.security.cs.allow-dyld-environment-variables"] = True
    (out / "probe-entitlements.plist").write_bytes(plistlib.dumps(entitlements))
    subprocess.run(["/usr/bin/codesign", "--force", "--sign", "-", "--options", "runtime", "--entitlements",
                    str(out / "probe-entitlements.plist"), str(app)], check=True, capture_output=True)
    dylib = out / "probe-nifti-import.dylib"
    subprocess.run(["xcrun", "clang", "-dynamiclib", "-fobjc-arc", "-framework", "Cocoa",
                    str(ROOT / "tools/probe-nifti-import.m"), "-o", str(dylib)], check=True)
    return dylib


def settle_images(app: App, timeout=180):
    """The image rows once their number has stopped changing for five seconds."""
    last, stable_since, deadline = None, time.monotonic(), time.monotonic() + timeout
    rows = []
    while time.monotonic() < deadline:
        answer = app.ask({"action": "images"})
        if answer.get("crashed") or answer.get("timeout"):
            return answer, rows
        rows = answer["images"]
        if len(rows) != last:
            last, stable_since = len(rows), time.monotonic()
        elif time.monotonic() - stable_since >= 5:
            return None, rows
        time.sleep(1)
    return {"timeout": True}, rows


def run_mode(mode: str, app_path: Path, out: Path, matrix: Path, expected: dict, dylib: Path) -> dict:
    folder = out / mode
    if folder.exists():
        shutil.rmtree(folder)
    folder.mkdir(parents=True)
    root = folder / "database"
    cases = expected["cases"]
    by_hash = {}
    for name, case in cases.items():
        for filename in case["files"]:
            by_hash.setdefault(sha256(matrix / name / filename), []).append((name, filename))
    result = {"mode": mode, "app": str(app_path), "events": [], "cases": {n: {"series": {}} for n in cases}}
    app = App(app_path, root, folder, dylib, MODES[mode])
    try:
        # the import
        if mode == "incoming":
            incoming = native_app.database_folder(root) / "INCOMING.noindex"
            for name in sorted(cases):
                staging = incoming / f".{name}"
                shutil.copytree(matrix / name, staging)
                staging.rename(incoming / name)
        else:
            answer = app.ask({"action": "import", "paths": [str(matrix / name) for name in sorted(cases)]})
            result["events"].append({"import": answer})
        problem, rows = settle_images(app)
        if problem:
            result["events"].append({"import_wait": problem})
        # rows to cases, by content
        for row in rows:
            path = Path(row["path"])
            # A file linked in place is its case's own; a copy is known by its content. The
            # header of a pair whose image is cut short is byte for byte the good pair's.
            if path.parent.parent == matrix and path.parent.name in cases:
                owners = [(path.parent.name, path.name)]
            else:
                owners = by_hash.get(sha256(path), []) if path.is_file() else []
                # Such a header is two cases' by content; the image stored beside it says which (#642).
                image = path.with_suffix(".img")
                if len(owners) > 1 and image.is_file():
                    image_hash = sha256(image)
                    owners = [(name, filename) for name, filename in owners
                              if any(other.lower().endswith(".img") and sha256(matrix / name / other) == image_hash
                                     for other in cases[name]["files"])]
            if not owners:
                result["events"].append({"unmatched_row": row})
                continue
            for name, filename in owners:
                series = result["cases"][name]["series"].setdefault(row["series_uri"], {"rows": []})
                series["rows"].append(dict(row, case_file=filename))
        # every series in a viewer
        for name in sorted(cases):
            case = cases[name]
            points = sorted({(i, j) for _, i, j, _ in case.get("samples", [])}) or [(0, 0)]
            for uri, series in result["cases"][name]["series"].items():
                if not app.alive():
                    app.start()
                answer = app.ask({"action": "open", "series": uri, "points": [list(p) for p in points]}, timeout=180)
                series["points"] = [list(p) for p in points]
                series["viewer"] = answer
                if answer.get("crashed"):
                    result["events"].append({"crash": f"opening {name}", "exit": answer.get("exit")})
        # detection, registration and metadata on the original files
        for name in sorted(cases):
            header = str(matrix / name / cases[name]["header_file"])
            for action in ("detect", "xml"):
                if not app.alive():
                    app.start()
                answer = app.ask({"action": action, "path": header})
                result["cases"][name][action] = answer
                if answer.get("crashed"):
                    result["events"].append({"crash": f"{action} {name}", "exit": answer.get("exit")})
        result["launches"] = app.launches
    finally:
        app.stop()
    result["checks"] = check(result, expected)
    (folder / "result.json").write_text(json.dumps(result, indent=1) + "\n")
    return result


def check(result: dict, expected: dict) -> list:
    checks = []

    def record(name, ok, message):
        checks.append({"case": name, "ok": bool(ok), "check": message})

    for name, case in expected["cases"].items():
        outcome = result["cases"][name]
        crashed = [e for e in result["events"] if name in str(e.get("crash", ""))]
        record(name, not crashed, "the app survives every step")
        if not case["valid"]:
            for uri, series in outcome["series"].items():
                frames = (series.get("viewer") or {}).get("frames") or []
                readable = [f for f in frames if not f["unreadable"]]
                record(name, not readable, f"a bad file is not shown as an image ({len(readable)} readable frame(s))")
            continue
        nx, ny, nz = case["dims"]
        record(name, len(outcome["series"]) == 1, f"imported as one series ({len(outcome['series'])})")
        for uri, series in outcome["series"].items():
            viewer = series.get("viewer") or {}
            frames = viewer.get("frames") or []
            record(name, len(frames) == nz, f"{len(frames)} frames in the viewer, {nz} slices")
            by_frame = {}
            for index, frame in enumerate(frames):
                ok = (frame["width"], frame["height"]) == (nx, ny) and not frame["unreadable"]
                if not ok:
                    record(name, False, f"frame {index}: {frame['width']} x {frame['height']}, unreadable {frame['unreadable']}")
                by_frame[frame["frame"]] = frame
            if not frames:
                continue
            first = frames[0]
            spacing_ok = all(a is not None and abs(a - b) < 1e-4 for a, b in zip(first["spacing"], case["spacing"][:2]))
            record(name, spacing_ok, f"in-plane spacing {first['spacing']}")
            record(name, first["thickness"] is not None and abs(first["thickness"] - case["spacing"][2]) < 1e-4,
                   f"thickness {first['thickness']}")
            wrong = []
            for k, i, j, value in case["samples"]:
                frame = by_frame.get(k)
                if frame is None:
                    wrong.append(f"no frame {k}")
                    continue
                got = frame["values"][series["points"].index([i, j])]
                if got is None or abs(got - value) > 1e-3 * max(1.0, abs(value)):
                    wrong.append(f"({i}, {j}, {k}) = {got}, expected {value}")
            record(name, not wrong, f"sampled values as stored{': ' + '; '.join(wrong[:3]) if wrong else ''}")
    return checks


def compare(first: Path, second: Path) -> int:
    differences = []
    lines = [f"# {first.name} → {second.name}", "", "| mode | case | what differs |", "|---|---|---|"]
    for mode in MODES:
        a_path, b_path = first / mode / "result.json", second / mode / "result.json"
        if not (a_path.exists() and b_path.exists()):
            continue
        a, b = json.loads(a_path.read_text()), json.loads(b_path.read_text())
        for name in sorted(a["cases"]):
            left, right = a["cases"][name], b["cases"][name]
            found = []

            def series_summary(outcome):
                summary = []
                for series in outcome["series"].values():
                    frames = (series.get("viewer") or {}).get("frames") or []
                    summary.append({"rows": len(series["rows"]),
                                    "modality": series["rows"][0]["modality"], "file_type": series["rows"][0]["file_type"],
                                    "frames": [{k: f[k] for k in ("width", "height", "spacing", "thickness", "interval",
                                                                  "origin", "orientation", "unreadable", "values", "sum",
                                                                  "min", "max")} for f in frames]})
                return sorted(summary, key=json.dumps)

            if series_summary(left) != series_summary(right):
                found.append("series or frames")
            for action in ("detect", "xml"):
                if left.get(action) != right.get(action):
                    found.append(action)
            crash_a = [e for e in a["events"] if name in str(e.get("crash", ""))]
            crash_b = [e for e in b["events"] if name in str(e.get("crash", ""))]
            if bool(crash_a) != bool(crash_b):
                found.append(f"crash {bool(crash_a)} → {bool(crash_b)}")
            if found:
                differences.append({"mode": mode, "case": name, "differs": found})
                lines.append(f"| {mode} | {name} | {', '.join(found)} |")
    if not differences:
        lines.append("| — | — | nothing |")
    (second / "compare.json").write_text(json.dumps(differences, indent=1) + "\n")
    (second / "compare.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    return 0


def run_memory(names: list, app_path: Path, out: Path, matrix: Path, expected: dict, dylib: Path) -> dict:
    """Every frame of each case read in one pass, held like a viewer's and released (#643)."""
    folder = out / "memory"
    if folder.exists():
        shutil.rmtree(folder)
    folder.mkdir(parents=True)
    volumes = []
    for name in names:
        case = expected["cases"][name]
        volumes.append({"label": name, "path": str(matrix / name / case["header_file"]), "frames": case["frames"]})
    app = App(app_path, folder / "database", folder, dylib, MODES["link"])
    try:
        answer = app.ask({"action": "measure", "volumes": volumes, "detect": [], "iterations": 0}, timeout=1800)
    finally:
        app.stop()
    result = {"volumes": volumes, "metrics": answer}
    (folder / "result.json").write_text(json.dumps(result, indent=1) + "\n")
    for volume in volumes:
        label, frames = volume["label"], volume["frames"]
        metric = lambda key: ((answer or {}).get(f"{label}_{key}") or [None])[0]
        retained = metric("retained_kib_count")
        per_frame = f"{retained / frames:.1f}" if retained is not None else "?"
        print(f"memory {label}: {frames} frames, first {metric('first_us')} µs, series {metric('series_ms')} ms, "
              f"peak {metric('peak_kib_count')} KiB, retained {retained} KiB ({per_frame} KiB a frame), "
              f"failures {(answer or {}).get('failures_count', [0])}")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--app", type=Path, default=native_app.DEVELOPMENT_APP)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--mode", action="append", choices=list(MODES))
    parser.add_argument("--compare", nargs=2, type=Path)
    parser.add_argument("--same-names", action="store_true",
                        help="the matrix with every case's files named volume.* (#641)")
    parser.add_argument("--size", help="columns,rows,slices of the matrix's volumes (the generator's default otherwise)")
    parser.add_argument("--memory", action="append", metavar="CASE",
                        help="read every frame of CASE one after the other in the app (the probe's measure action): "
                             "time, and the footprint at its highest and once the frames are released (#643); "
                             "without --mode, only this")
    arguments = parser.parse_args()
    if arguments.compare:
        return compare(*arguments.compare)
    if not arguments.out:
        parser.error("--out is needed")
    out = arguments.out.resolve()
    if "local-validation" not in out.parts:
        parser.error("--out must be under local-validation")
    out.mkdir(parents=True, exist_ok=True)
    matrix = out / "matrix"
    if matrix.exists():
        shutil.rmtree(matrix)
    subprocess.run([sys.executable, str(ROOT / "tools/generate-nifti-matrix.py"), str(matrix)]
                   + (["--same-names"] if arguments.same_names else [])
                   + (["--size", arguments.size] if arguments.size else []), check=True)
    expected = json.loads((matrix / "expected.json").read_text())
    app = arguments.app.resolve()
    dylib = prepare(app, out)
    summary = {"app": str(app), "modes": {}}
    if arguments.memory:
        summary["memory"] = run_memory(arguments.memory, app, out, matrix, expected, dylib)
    for mode in arguments.mode or ([] if arguments.memory else list(MODES)):
        result = run_mode(mode, app, out, matrix, expected, dylib)
        failed = [c for c in result["checks"] if not c["ok"]]
        summary["modes"][mode] = {"checks": len(result["checks"]), "failed": failed, "events": result["events"],
                                  "launches": result.get("launches")}
        print(f"{mode}: {len(result['checks']) - len(failed)} of {len(result['checks'])} checks passed, "
              f"{result.get('launches')} launch(es)")
        for failure in failed:
            print(f"  FAIL {failure['case']}: {failure['check']}")
    (out / "summary.json").write_text(json.dumps(summary, indent=1) + "\n")
    return 0 if all(not m["failed"] for m in summary["modes"].values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
