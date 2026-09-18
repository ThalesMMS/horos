#!/usr/bin/env python3
"""Surface Rendering's Decimate and Smooth options in the app, and the cost of applying them (#636).

A synthetic CT phantom (a body cylinder of 40 HU in air with a sphere of 800 HU)
is imported twice into a fresh private database: the main series and an identical
copy fused onto it. tools/probe-sr-surfaces.m, injected, opens the main viewer's
Surface Rendering window with the fusion and drives it the way the settings sheet
does.

--check-only (one app): for the first and the second surface and for the fusion's
two surfaces, each alone and at the same iso value (300 HU), the four combinations
of Decimate (reduction 0.5) and Smooth (20 iterations) are rendered and exported to
STL through File > Export. A crash is recorded and the app relaunched on the same
database for the next case. Checks, per surface: no crash, geometry exported, the
smoothing changes the vertices but not the number of triangles, the decimation
removes at least a quarter of the triangles; across surfaces: the second surface
and the fusion's surfaces are the first surface's geometry, combination by
combination. At efb2b0cef the second surface smooths when Decimate is on and does
not when only Smooth is, and the fusion crashes with Smooth on and Decimate off.
A second OK on surfaces already rendered with both options (#616), exported after it:
changing only the colours and transparencies keeps the geometry (the same triangles,
in under 5 % of the cold render's time); changing them after a viewer's notification
that the voxels changed, or changing the first surface's iso value by 25, rebuilds it
(the triangles of a cold render with those settings, in at least 15 % of its time: a
rebuild known to be short does not open the wait window a cold render opens).

A/B (--baseline-app, --candidate-app): launches alternated by round, a fresh
database each; per launch every scenario is timed on the main thread after one
warm-up pass (tools/probe-sr-surfaces.m "measure"), both surfaces on (300 and
-500 HU), with the render the sheet's OK button runs (-renderSurfaces,
-renderFusionSurfaces):

  main_<combination>_ms, main_<combination>_cpu_ms       the two surfaces
  fusion_<combination>_ms, fusion_<combination>_cpu_ms   the fusion's two surfaces

for the combinations dson (both options), dsoff (neither), don_soff (Decimate only)
and doff_son (Smooth only). The baseline did the wrong work in main_don_soff and
main_doff_son (the second surface took the Decimate option for smoothing) and
crashed in fusion_doff_son: there, its launches render the functional reference
instead (-[SRView changeActor:...] with the options asked, as the corrected render
calls it), in the A/A as in the A/B.

    local-validation/venv/bin/python tools/measure-native-sr-surfaces.py --check-only \\
        --app build/Variants/candidate/HorosDevelopment.app --out local-validation/delta4/636-app/candidate
    local-validation/venv/bin/python tools/measure-native-sr-surfaces.py \\
        --baseline-app build/Variants/636-baseline/HorosDevelopment.app \\
        --candidate-app build/Variants/candidate/HorosDevelopment.app --rounds 30 --repetitions 7 \\
        --limit main_dson_ms:median=0.05 ... --out local-validation/delta4/636-app-c1

Needs a Python with pydicom and numpy. Everything stays under --out.
"""
import argparse
import collections
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

SIZE, SLICES, SPACING, INTERVAL = 192, 100, 1.0, 1.5
ISO = 300
COMBINATIONS = {"dsoff": (False, False), "don_soff": (True, False), "doff_son": (False, True), "dson": (True, True)}
# Where the baseline's own render was wrong (main) or crashed (fusion): the reference it renders instead.
REFERENCE_PATHS = {("main", "don_soff"): "surfaces", ("main", "doff_son"): "surfaces",
                   ("fusion", "doff_son"): "fusion-surfaces"}


def generate(folder: Path) -> dict:
    """The phantom, twice: identical pixels and geometry, two series of one study."""
    import numpy
    from pydicom.dataset import Dataset, FileMetaDataset
    from pydicom.uid import CTImageStorage, ExplicitVRLittleEndian, generate_uid
    folder.mkdir(parents=True)
    study, frame = generate_uid(), generate_uid()
    centre = (SIZE - 1) / 2 * SPACING
    y, x = numpy.mgrid[0:SIZE, 0:SIZE] * SPACING
    radial = numpy.hypot(x - centre, y - centre)
    uids = {}
    for number, label in ((1, "main"), (2, "fusion")):
        uids[label] = generate_uid()
        for index in range(SLICES):
            z = index * INTERVAL
            hu = numpy.full((SIZE, SIZE), -1000.0)
            hu[radial <= 80] = 40
            hu[numpy.sqrt(radial ** 2 + (z - (SLICES - 1) * INTERVAL / 2) ** 2) <= 40] = 800
            ds = Dataset()
            ds.file_meta = FileMetaDataset()
            ds.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
            ds.SOPClassUID, ds.SOPInstanceUID = CTImageStorage, generate_uid()
            ds.StudyInstanceUID, ds.SeriesInstanceUID, ds.FrameOfReferenceUID = study, uids[label], frame
            ds.PatientName, ds.PatientID = "SYNTHETIC^SURFACES", "SYN-636"
            ds.StudyDate, ds.StudyTime, ds.StudyID = "20260917", "120000", "636"
            ds.Modality, ds.SeriesNumber, ds.InstanceNumber = "CT", number, index + 1
            ds.SeriesDescription = f"phantom {label}"
            ds.Rows = ds.Columns = SIZE
            ds.SamplesPerPixel, ds.PhotometricInterpretation = 1, "MONOCHROME2"
            ds.BitsAllocated, ds.BitsStored, ds.HighBit, ds.PixelRepresentation = 16, 12, 11, 0
            ds.RescaleIntercept, ds.RescaleSlope = -1024, 1
            ds.WindowCenter, ds.WindowWidth = 40, 400
            ds.PixelSpacing, ds.SliceThickness, ds.SpacingBetweenSlices = [SPACING, SPACING], INTERVAL, INTERVAL
            ds.ImageOrientationPatient, ds.ImagePositionPatient = [1, 0, 0, 0, 1, 0], [0, 0, z]
            ds.SliceLocation = z
            ds.PixelData = (hu + 1024).astype(numpy.uint16).tobytes()
            ds.save_as(folder / f"{label}-{index + 1:03d}.dcm", enforce_file_format=True)
    return uids


def prepare_bundle(app: Path, work: Path):
    entitlements = plistlib.loads((ROOT / "build/Development/entitlements.plist").read_bytes())
    entitlements["com.apple.security.cs.allow-dyld-environment-variables"] = True
    path = work / "probe-entitlements.plist"
    path.write_bytes(plistlib.dumps(entitlements))
    subprocess.run(["/usr/bin/codesign", "--force", "--sign", "-", "--options", "runtime", "--entitlements", str(path),
                    str(app)], check=True, capture_output=True)


class Session:
    """One launch of the app with the probe; a database folder that outlives it."""

    def __init__(self, app: Path, root: Path, dylib: Path, log: Path):
        self.app, self.root, self.dylib, self.log = app, root, dylib, log
        self.commands = Path(tempfile.mkdtemp(prefix="sr-commands-", dir=str(root.parent)))
        self.number = 0
        native_app.stop_all(app)
        # A relaunch after a crash must not stop at the system's offer to reopen the windows.
        self.process = native_app.launch(root, log, ["-ApplePersistenceIgnoreState", "YES"], app=app,
                                         environment={"DYLD_INSERT_LIBRARIES": str(dylib),
                                                      "HOROS_SR_COMMANDS": str(self.commands)})

    def alive(self):
        return self.process.poll() is None

    def command(self, payload: dict, timeout: float = 300):
        """The probe's answer, or None if the app died first."""
        self.number += 1
        answer = self.commands / f"{self.number}.out.json"
        staging = self.commands / f".{self.number}.json"
        staging.write_text(json.dumps(payload))
        os.rename(staging, self.commands / f"{self.number}.json")
        native_app.wait_for(lambda: answer.exists() or not self.alive(), timeout, interval=0.1,
                            description=f"the answer to {payload['action']}")
        if not answer.exists():
            return None
        return json.loads(answer.read_text())

    def stop(self):
        native_app.stop(self.process)
        shutil.rmtree(self.commands, ignore_errors=True)


def start(app: Path, root: Path, dylib: Path, log: Path, fixture: Path, uids: dict, import_fixture: bool) -> Session:
    session = Session(app, root, dylib, log)
    try:
        data = native_app.database_folder(root)
        native_app.wait_for(lambda: (data / "INCOMING.noindex").is_dir(), 90, description="the database to open")
        if not (session.command({"action": "ping"}, 90) or {}).get("ok"):
            raise RuntimeError(f"the probe did not answer (log {log})")
        if import_fixture:
            for path in sorted(fixture.glob("*.dcm")):
                staging = data / "INCOMING.noindex" / f".{path.name}.part"
                shutil.copyfile(path, staging)
                os.rename(staging, data / "INCOMING.noindex" / path.name)
        native_app.wait_for(lambda: (native_app.image_count(root) or 0) >= 2 * SLICES, 300, interval=0.5,
                            description="the import")
        time.sleep(2)
        opened = session.command({"action": "open", "main": uids["main"], "fusion": uids["fusion"]})
        if not opened or not opened.get("ok"):
            raise RuntimeError(f"could not open the Surface Rendering window: {opened}")
    except BaseException:
        session.stop()
        raise
    return session


def read_stl(path: Path):
    """Triangles as tuples of three vertices, each a tuple of the printed coordinates."""
    data = path.read_bytes()
    if data[:5] == b"solid" and b"facet" in data[:4096]:
        vertices = [tuple(float(value) for value in line.split()[1:4])
                    for line in data.decode("ascii").splitlines() if line.lstrip().startswith("vertex")]
    else:
        import struct
        count = struct.unpack_from("<I", data, 80)[0]
        vertices = []
        for index in range(count):
            values = struct.unpack_from("<12f", data, 84 + 50 * index)
            vertices += [tuple(values[3:6]), tuple(values[6:9]), tuple(values[9:12])]
    return [tuple(vertices[i:i + 3]) for i in range(0, len(vertices) - 2, 3)]


def canonical(triangles, digits=None):
    def vertex(v):
        return tuple(round(c, digits) for c in v) if digits is not None else v
    return collections.Counter(tuple(sorted(vertex(v) for v in triangle)) for triangle in triangles)


def overlap(a, b, digits=None):
    """The share of triangles the two surfaces have in common (1.0: the same geometry)."""
    if not a and not b:
        return 1.0
    ca, cb = canonical(a, digits), canonical(b, digits)
    return sum((ca & cb).values()) / max(len(a), len(b))


# #616: a second OK, its change, the cold case with the settings it ends with, and whether it rebuilds the geometry.
KEEP_CHECKS = (("recolour", "dson", False), ("invalidate", "dson", True), ("reiso", f"dson-iso{ISO + 25}", True))


def check_cases():
    for target in ("main", "fusion"):
        for surface in (0, 1):
            for combination, (decimate, smooth) in COMBINATIONS.items():
                yield {"name": f"{target}-s{surface}-{combination}", "target": target, "surface": surface,
                       "combination": combination, "decimate": decimate, "smooth": smooth}
            for keep, _, _ in KEEP_CHECKS:
                if keep != "reiso" or surface == 0:
                    yield {"name": f"{target}-s{surface}-dson-{keep}", "target": target, "surface": surface,
                           "combination": "dson", "decimate": True, "smooth": True, "keep": keep}
        yield {"name": f"{target}-s0-dson-iso{ISO + 25}", "target": target, "surface": 0, "combination": "dson",
               "decimate": True, "smooth": True, "first": ISO + 25}


def run_check(app: Path, out: Path, fixture: Path, uids: dict, dylib: Path) -> dict:
    check = out / "check"
    if check.exists():
        shutil.rmtree(check)
    check.mkdir(parents=True)
    root = check / "database"
    cases = list(check_cases())
    results, launches, session, imported = {}, 0, None, False
    try:
        for case in cases:
            if session is None or not session.alive():
                if session:
                    session.stop()
                launches += 1
                session = start(app, root, dylib, check / f"horos-{launches}.log", fixture, uids, not imported)
                imported = True
            path = check / f"{case['name']}.stl"
            payload = {"action": "export", "target": case["target"], "surfaces": [case["surface"]],
                       "decimate": case["decimate"], "smooth": case["smooth"], "first": case.get("first", ISO),
                       "second": ISO, "path": str(path)}
            if case.get("keep"):
                payload["keep"] = case["keep"]
            answer = session.command(payload)
            if answer is None:
                results[case["name"]] = dict(case, crashed=True)
                continue
            result = dict(case, crashed=False, answer=answer)
            if path.exists() and path.stat().st_size:
                triangles = read_stl(path)
                result.update(triangles=len(triangles), points=len({v for t in triangles for v in t}))
            results[case["name"]] = result
    finally:
        if session:
            session.stop()
    geometry = {name: read_stl(check / f"{name}.stl") for name, r in results.items()
                if not r["crashed"] and (check / f"{name}.stl").exists()}
    problems = []
    for name, result in results.items():
        if result["crashed"]:
            problems.append(f"{name}: the app crashed")
        elif not result.get("triangles"):
            problems.append(f"{name}: no geometry exported ({result.get('answer')})")
    for target in ("main", "fusion"):
        for surface in (0, 1):
            prefix = f"{target}-s{surface}"
            # Smooth on against Smooth off, with the same decimation: same triangles, moved vertices.
            for label, off_name, on_name in (("Decimate off", "dsoff", "doff_son"), ("Decimate on", "don_soff", "dson")):
                off, on = geometry.get(f"{prefix}-{off_name}"), geometry.get(f"{prefix}-{on_name}")
                if off is None or on is None:
                    continue
                if len(on) != len(off):
                    problems.append(f"{prefix}, {label}: smoothing changed the triangles ({len(off)} -> {len(on)})")
                shared = overlap(on, off, 2)
                if shared >= 0.5:
                    problems.append(f"{prefix}, {label}: Smooth on left {shared:.0%} of the triangles where they were")
            # Decimate on against Decimate off, with the same smoothing: fewer triangles.
            for label, plain_name, reduced_name in (("Smooth off", "dsoff", "don_soff"), ("Smooth on", "doff_son", "dson")):
                plain, reduced = geometry.get(f"{prefix}-{plain_name}"), geometry.get(f"{prefix}-{reduced_name}")
                if plain is None or reduced is None:
                    continue
                if len(reduced) > 0.75 * len(plain):
                    problems.append(f"{prefix}, {label}: decimation kept {len(reduced)} of {len(plain)} triangles")
    for name, result in results.items():
        keep = result.get("keep")
        if not keep or result["crashed"] or name not in geometry:
            continue
        cold_suffix, rebuilds = next((suffix, rebuilt) for change, suffix, rebuilt in KEEP_CHECKS if change == keep)
        prefix = f"{result['target']}-s{result['surface']}"
        cold = f"{prefix}-{cold_suffix}"
        if cold not in geometry:
            continue
        if canonical(geometry[name]) != canonical(geometry[cold]):
            problems.append(f"{name}: {overlap(geometry[name], geometry[cold]):.1%} of the triangles are {cold}'s")
        milliseconds, cold_milliseconds = result["answer"]["render_ms"], results[cold]["answer"]["render_ms"]
        if rebuilds and milliseconds < 0.15 * cold_milliseconds:
            problems.append(f"{name}: {milliseconds:.1f} ms against {cold_milliseconds:.1f} ms cold, not rebuilt")
        if not rebuilds and milliseconds > 0.05 * cold_milliseconds:
            problems.append(f"{name}: {milliseconds:.1f} ms against {cold_milliseconds:.1f} ms cold, rebuilt")
    parity = {}
    for combination in COMBINATIONS:
        first = geometry.get(f"main-s0-{combination}")
        for other, reference in ((f"main-s1-{combination}", first),
                                 (f"fusion-s0-{combination}", first),
                                 (f"fusion-s1-{combination}", geometry.get(f"main-s1-{combination}"))):
            if reference is None or geometry.get(other) is None:
                continue
            shared = overlap(reference, geometry[other], 2)
            parity[other] = shared
            if shared < 0.98:
                problems.append(f"{other}: {shared:.1%} of the triangles match the first surface's")
    summary = {"app": str(app), "launches": launches, "cases": results, "parity": parity, "problems": problems}
    for path in check.glob("*.stl"):
        path.unlink()
    shutil.rmtree(root, ignore_errors=True)
    (check / "summary.json").write_text(json.dumps(summary, indent=1) + "\n")
    return summary


def scenarios(reference: bool, keep: bool = False):
    for target in ("main", "fusion"):
        for combination, (decimate, smooth) in COMBINATIONS.items():
            yield {"name": f"{target}_{combination}", "target": target, "decimate": decimate, "smooth": smooth,
                   "first": ISO, "second": -500, "reference_path": REFERENCE_PATHS.get((target, combination))}
        if keep:
            # #616: a second OK on surfaces already there, changing only colours and transparencies, or an iso value.
            for change in ("recolour", "reiso"):
                yield {"name": f"{target}_{change}", "target": target, "decimate": True, "smooth": True,
                       "first": ISO, "second": -500, "reference_path": None, "keep": change}


def run_measure(app: Path, fixture: Path, uids: dict, dylib: Path, reference: bool, repetitions: int,
                keep: bool = False) -> dict:
    work = Path(tempfile.mkdtemp(prefix="sr-measure-", dir=str(fixture.parent)))
    session = start(app, work / "database", dylib, work / "horos.log", fixture, uids, True)
    try:
        answer = session.command({"action": "measure", "repetitions": repetitions, "reference": reference,
                                  "scenarios": list(scenarios(reference, keep))}, timeout=1800)
    finally:
        session.stop()
    if not answer or "error" in answer or "exception" in answer:
        raise RuntimeError(f"measure failed: {answer} (log {work / 'horos.log'})")
    shutil.rmtree(work, ignore_errors=True)
    return answer


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--run", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--fixture", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--dylib", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--reference", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--same-render", action="store_true",
                        help="the baseline renders as the candidate does, not the #636 reference (both revisions after #636)")
    parser.add_argument("--keep", action="store_true",
                        help="also time a second OK on surfaces already there: colours only, and an iso value (#616)")
    parser.add_argument("--check-only", action="store_true")
    parser.add_argument("--app", type=Path)
    parser.add_argument("--baseline-app", type=Path)
    parser.add_argument("--candidate-app", type=Path)
    parser.add_argument("--rounds", type=int, default=30)
    parser.add_argument("--repetitions", type=int, default=7)
    parser.add_argument("--limit", action="append", default=[])
    parser.add_argument("--out", type=Path)
    arguments = parser.parse_args()
    if arguments.run:
        uids = json.loads((arguments.fixture / "uids.json").read_text())
        print(json.dumps(run_measure(arguments.run, arguments.fixture / "series", uids, arguments.dylib,
                                     arguments.reference, arguments.repetitions, arguments.keep)))
        return 0

    out = arguments.out.resolve()
    if "local-validation" not in out.parts:
        parser.error("--out must be under local-validation")
    out.mkdir(parents=True, exist_ok=True)
    fixture = out / "fixture"
    if fixture.exists():
        shutil.rmtree(fixture)
    uids = generate(fixture / "series")
    (fixture / "uids.json").write_text(json.dumps(uids))
    dylib = out / "probe-sr-surfaces.dylib"
    subprocess.run(["xcrun", "clang", "-dynamiclib", "-fobjc-arc", "-framework", "Cocoa",
                    str(ROOT / "tools/probe-sr-surfaces.m"), "-o", str(dylib)], check=True)
    if arguments.check_only:
        app = arguments.app.resolve()
        prepare_bundle(app, out)
        summary = run_check(app, out, fixture / "series", uids, dylib)
        for name, result in summary["cases"].items():
            state = "crashed" if result["crashed"] else f"{result.get('triangles', 0)} triangles, {result.get('points', 0)} points"
            if not result["crashed"] and result.get("keep"):
                state += f", {result['answer']['render_ms']:.1f} ms"
            print(f"{name}: {state}")
        for name, shared in summary["parity"].items():
            print(f"parity {name}: {shared:.1%}")
        print("problems:" if summary["problems"] else "no problems")
        for problem in summary["problems"]:
            print(f"  {problem}")
        shutil.rmtree(fixture, ignore_errors=True)
        return 1 if summary["problems"] else 0

    import ab_protocol
    apps = {"baseline": arguments.baseline_app.resolve(), "candidate": arguments.candidate_app.resolve()}
    variants = {}
    for label, app in apps.items():
        prepare_bundle(app, out)
        described = app.parent / "variant.json"
        variants[label] = {"app": str(app), "variant": json.loads(described.read_text()) if described.exists() else None}

    def command(label):
        extra = (["--reference"] if label == "baseline" and not arguments.same_render else []) + (["--keep"] if arguments.keep else [])
        return [sys.executable, str(Path(__file__).resolve()), "--run", str(apps[label]), "--fixture", str(fixture),
                "--dylib", str(dylib), "--repetitions", str(arguments.repetitions)] + extra

    plan = {"variants": variants, "rounds": arguments.rounds, "repetitions": arguments.repetitions,
            "limits": arguments.limit, "protocol_version": ab_protocol.PROTOCOL_VERSION,
            "scenarios": {"baseline": list(scenarios(not arguments.same_render, arguments.keep)),
                          "candidate": list(scenarios(False, arguments.keep))},
            "design": "separate launches alternated by round, fresh database per launch, one warm-up pass, "
                      "renders timed on the main thread inside the app; the baseline renders the functional "
                      "reference where its own render was wrong or crashed"}
    (out / "plan.json").write_text(json.dumps(plan, indent=1) + "\n")
    limits = ab_protocol._parse_limits(arguments.limit)
    aa = ab_protocol.run_protocol({"A": command("baseline"), "A'": command("baseline")}, arguments.rounds, 1)
    (out / "aa.json").write_text(json.dumps(aa) + "\n")
    tolerance = ab_protocol.calibrate(aa, limits, set(), ab_protocol.DEFAULT_SEED, ab_protocol.DEFAULT_RESAMPLES)
    (out / "tolerance.json").write_text(json.dumps(tolerance, indent=1) + "\n")
    ab = ab_protocol.run_protocol({"baseline": command("baseline"), "candidate": command("candidate")}, arguments.rounds, 1)
    (out / "ab.json").write_text(json.dumps(ab) + "\n")
    analysis = ab_protocol.analyze(ab, tolerance, set(), ab_protocol.DEFAULT_SEED, ab_protocol.DEFAULT_RESAMPLES)
    (out / "analysis.json").write_text(json.dumps(analysis, indent=1) + "\n")
    table = ab_protocol.markdown(analysis, ("baseline", "candidate"))
    (out / "table.md").write_text(table)
    print(table)
    shutil.rmtree(fixture, ignore_errors=True)
    return 0 if analysis["overall"] == "non-inferior" else 1


if __name__ == "__main__":
    raise SystemExit(main())
