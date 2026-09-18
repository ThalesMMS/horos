#!/usr/bin/env python3
"""Interleaved in-process A/A and A/B of one compiled source file (Δ4 protocol, #624).

For file-system-sized operations, noise arrives in bursts longer than a call;
with one process per variant a burst lands on one side only. Here each
revision's object - compiled with the exact command xcodebuild logged for the
app - becomes a dylib, a single probe process loads both, and the probe
alternates the two implementations call by call. The A/A loads the baseline
dylib and a byte-identical copy of it under another name.

    python3 tools/measure-object-interleaved.py \
        --source Nitrogen/Sources/NSFileManager+N2.mm \
        --probe tools/probe-noindex-directory.m \
        --baseline efb2b0cef --candidate 55599337f --configuration Release \
        --build-root ../horos-workbench-baseline \
        --args 'interleave {A} {B} {scratch} 400 40 {suffix_A} {suffix_B}' \
        --variant-arg suffix:baseline=.noindex --variant-arg 'suffix:candidate=' \
        --limit existing_us:median=0.05 --out local-validation/delta4/612-Release-c3

`{A}`/`{B}` become the two dylib paths, `{scratch}` a scratch folder, and
`{name_A}`/`{name_B}` the per-revision value given with --variant-arg for the
revision loaded in that slot.

A Swift --source (#620) is compiled with swiftc and the flags xcodebuild gives
the Horos target in that configuration, with its --companion-source files taken
at the same revision and a --swift-shim compiled into each dylib: the shim
exposes the C entry points the probe calls, since the revisions' own Swift has
none; a Swift companion absent at a revision (a file the candidate adds) is left
out of that revision's dylib. --swift-define REVISION=NAME compiles that
revision's dylib with -D NAME, so the shim can do each revision's work the way
the host does it:

    python3 tools/measure-object-interleaved.py \
        --source Horos/Sources/MPRMetalReslicer.swift \
        --companion-source Horos/Sources/VolumeAllocation.swift \
        --companion-source Horos/Sources/VolumeSession.swift \
        --companion-source Horos/Sources/MetalPerformanceTrace.swift \
        --swift-shim tools/probe-mpr-reslice-shim.swift --swift-define candidate=HOROS_RESLICE_INTO \
        --probe tools/probe-mpr-reslice.m --framework Metal \
        --baseline 9d70501fd --candidate 7fe5f8bde --configuration Release \
        --args 'interleave {A} {B}' --separate-args 'first {dylib}' --out local-validation/delta4/620-Release
"""
import argparse
import json
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import ab_protocol  # noqa: E402
import object_probe  # noqa: E402

# What xcodebuild passes swiftc for the Horos target (its SwiftDriver line in a build log): the module is
# optimized in both configurations, and Debug adds debug information and testability.
SWIFT_FLAGS = {"Debug": ["-O", "-g", "-enable-testing"], "Release": ["-O"]}


def swift_dylib(sources: list[Path], shim: Path, output: Path, configuration: str, defines: list[str]) -> Path:
    """One revision's Swift sources and the shim as a loadable image. Each image gets a module name of its own,
    so the two revisions' types never share a mangled name in the probe process."""
    module = "HorosAB" + "".join(part.capitalize() for part in output.stem.replace("-", "_").split("_"))
    argv = ["xcrun", "swiftc", "-emit-library", "-module-name", module, "-target", "arm64-apple-macos26.0",
            "-swift-version", "5", *SWIFT_FLAGS[configuration]]
    for define in defines:
        argv += ["-D", define]
    argv += [*map(str, sources), str(shim), "-Xlinker", "-install_name", "-Xlinker", f"@rpath/{output.name}",
             "-o", str(output)]
    subprocess.run(argv, check=True)
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", required=True)
    parser.add_argument("--probe", required=True, type=Path)
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--candidate", default="WORKTREE")
    parser.add_argument("--baseline-file", type=Path,
                        help="use this source file as the baseline instead of --baseline's revision "
                             "(a generated functional reference); --baseline then only labels it")
    parser.add_argument("--configuration", default="Debug", choices=("Debug", "Release"))
    parser.add_argument("--build-root", type=Path, default=ROOT)
    parser.add_argument("--build-log", type=Path)
    parser.add_argument("--args", required=True)
    parser.add_argument("--variant-arg", action="append", default=[],
                        help="name:baseline=value or name:candidate=value")
    parser.add_argument("--limit", action="append", default=[])
    parser.add_argument("--higher", action="append", default=[])
    parser.add_argument("--rounds", type=int, default=30)
    parser.add_argument("--warmup", type=int, default=1)
    parser.add_argument("--resamples", type=int, default=ab_protocol.DEFAULT_RESAMPLES)
    parser.add_argument("--seed", type=int, default=ab_protocol.DEFAULT_SEED)
    parser.add_argument("--framework", action="append", default=[])
    parser.add_argument("--extra-object", action="append", default=[],
                        help="an object of the app (by name, same configuration) the probe links and exports")
    parser.add_argument("--companion-source", action="append", default=[],
                        help="another source compiled per revision, like --source, into the same dylib "
                             "(a library in more than one file)")
    parser.add_argument("--swift-shim", type=Path,
                        help="a Swift file compiled into each revision's dylib with a Swift --source; it exposes the "
                             "C entry points the probe calls")
    parser.add_argument("--swift-define", action="append", default=[],
                        help="REVISION=NAME: compile that revision's Swift with -D NAME (baseline or candidate)")
    parser.add_argument("--companion-header", action="append", default=[],
                        help="a header taken from each revision and searched before the app's include paths, "
                             "so a revision's sources never compile against the checkout's headers "
                             "(a file absent at a revision is left out)")
    parser.add_argument("--separate-rounds", type=int, help="rounds of the separate-process measurement (default --rounds)")
    parser.add_argument("--skip-interleaved", action="store_true",
                        help="run only the separate-process measurement of --separate-args")
    parser.add_argument("--separate-args",
                        help="also measure in separate processes, alternated by round (a cold first call): "
                             "{dylib} becomes the revision's dylib; results go to cold-*.json and cold-table.md")
    parser.add_argument("--out", required=True, type=Path)
    arguments = parser.parse_args()
    if arguments.skip_interleaved and not arguments.separate_args:
        parser.error("--skip-interleaved needs --separate-args")
    swift = arguments.source.endswith(".swift")
    if swift and not arguments.swift_shim:
        parser.error("a Swift --source needs --swift-shim")
    swift_defines = {"baseline": [], "candidate": []}
    for item in arguments.swift_define:
        revision, _, name = item.partition("=")
        if revision not in swift_defines or not name:
            parser.error(f"--swift-define takes baseline=NAME or candidate=NAME, not {item!r}")
        swift_defines[revision].append(name)

    per_revision = {"baseline": {}, "candidate": {}}
    for item in arguments.variant_arg:
        key, _, value = item.partition("=")
        name, _, revision = key.partition(":")
        per_revision[revision][name] = value

    out = arguments.out
    out.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="horos-interleaved-"))
    scratch = work / "scratch"
    scratch.mkdir()
    if swift:
        command = ["xcrun", "swiftc", *SWIFT_FLAGS[arguments.configuration]]
        companions = [(companion, None) for companion in arguments.companion_source]
    else:
        command = object_probe.compile_command(arguments.source, arguments.configuration,
                                               root=arguments.build_root.resolve(), log=arguments.build_log)
        companions = [(companion, object_probe.compile_command(companion, arguments.configuration,
                                                               root=arguments.build_root.resolve(), log=arguments.build_log))
                      for companion in arguments.companion_source]
    name = Path(arguments.source).name
    frameworks = ["Foundation"] + arguments.framework
    dylibs = {}
    for label, revision in (("baseline", arguments.baseline), ("candidate", arguments.candidate)):
        if label == "baseline" and arguments.baseline_file:
            source = work / label / name
            source.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(arguments.baseline_file, source)
        elif revision == "WORKTREE":
            source = work / label / name
            source.parent.mkdir(parents=True)
            shutil.copyfile(ROOT / arguments.source, source)
        else:
            source = object_probe.revision_source(arguments.source, revision, work / label / name)
        for header in arguments.companion_header:
            destination = work / label / Path(header).name
            if revision == "WORKTREE":
                if (ROOT / header).exists():
                    shutil.copyfile(ROOT / header, destination)
            else:
                shown = subprocess.run(["git", "-C", str(ROOT), "show", f"{revision}:{header}"], capture_output=True)
                if shown.returncode == 0:
                    destination.write_bytes(shown.stdout)
        if swift:
            sources = [source]
            for companion, _ in companions:
                destination = work / label / Path(companion).name
                if revision == "WORKTREE":
                    if not (ROOT / companion).exists():
                        continue
                    shutil.copyfile(ROOT / companion, destination)
                else:
                    if subprocess.run(["git", "-C", str(ROOT), "cat-file", "-e", f"{revision}:{companion}"],
                                      capture_output=True).returncode != 0:
                        continue
                    object_probe.revision_source(companion, revision, destination)
                sources.append(destination)
            dylibs[label] = swift_dylib(sources, arguments.swift_shim, work / f"{label}.dylib", arguments.configuration,
                                        swift_defines[label])
            continue
        revision_includes = ["-iquote", str(work / label), "-I", str(work / label)] if arguments.companion_header else []
        obj = work / label / (Path(name).stem + ".o")
        object_probe.compile_source(command[:1] + revision_includes + command[1:], source, obj)
        objects = [obj]
        # Companions sit beside the main source, as in the checkout, so quoted
        # includes between them resolve to the same revision's files.
        for companion, companion_command in companions:
            destination = work / label / Path(companion).name
            if revision == "WORKTREE":
                shutil.copyfile(ROOT / companion, destination)
            else:
                object_probe.revision_source(companion, revision, destination)
            objects.append(work / label / (Path(companion).stem + ".o"))
            object_probe.compile_source(companion_command[:1] + revision_includes + companion_command[1:],
                                        destination, objects[-1])
        dylibs[label] = object_probe.link_dylib(objects, work / f"{label}.dylib", frameworks)
    dylibs["baseline-copy"] = work / "baseline-copy.dylib"
    shutil.copyfile(dylibs["baseline"], dylibs["baseline-copy"])
    subprocess.run(["install_name_tool", "-id", "@rpath/baseline-copy.dylib", str(dylibs["baseline-copy"])], check=True)
    subprocess.run(["codesign", "--force", "--sign", "-", str(dylibs["baseline-copy"])], check=True,
                   capture_output=True)
    probe = work / "probe"
    extras = []
    for extra in arguments.extra_object:
        found = object_probe.app_object(extra, arguments.configuration, arguments.build_root.resolve()) \
            or object_probe.app_object(extra, arguments.configuration)
        if found is None:
            raise SystemExit(f"needs {extra}.o built in {arguments.configuration}")
        extras.append(str(found))
    argv = ["xcrun", "clang", "-O2", "-g0", "-arch", "arm64", "-mmacosx-version-min=26.0", "-fno-objc-arc",
            str(arguments.probe)] + extras
    for framework in frameworks:
        argv += ["-framework", framework]
    argv += ["-lc++", "-Wl,-undefined,dynamic_lookup", "-Wl,-export_dynamic", "-o", str(probe)]
    subprocess.run(argv, check=True)

    def command_for(slot_a, slot_b, revision_a, revision_b):
        values = {"A": str(dylibs[slot_a]), "B": str(dylibs[slot_b]), "scratch": str(scratch)}
        for key, value in per_revision[revision_a].items():
            values[f"{key}_A"] = value
        for key, value in per_revision[revision_b].items():
            values[f"{key}_B"] = value
        parts = []
        for part in shlex.split(arguments.args):
            for key, value in values.items():
                part = part.replace("{" + key + "}", value)
            parts.append(part)
        return [str(probe)] + parts

    head = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    provenance = {"source": arguments.source, "companion_sources": arguments.companion_source,
                  "companion_headers": arguments.companion_header,
                  "baseline_revision": arguments.baseline,
                  "baseline_file": str(arguments.baseline_file) if arguments.baseline_file else None,
                  "candidate_revision": arguments.candidate, "workbench_head": head,
                  "configuration": arguments.configuration, "compile_command": command,
                  "swift_shim": str(arguments.swift_shim) if arguments.swift_shim else None,
                  "swift_defines": swift_defines if swift else None,
                  "build_root": str(arguments.build_root.resolve()), "probe": str(arguments.probe),
                  "design": "interleaved in-process, ABBA pairs, start alternating per round",
                  "limits": arguments.limit, "rounds": arguments.rounds, "warmup": arguments.warmup,
                  "seed": arguments.seed, "resamples": arguments.resamples,
                  "separate_args": arguments.separate_args, "separate_rounds": arguments.separate_rounds,
                  "skip_interleaved": arguments.skip_interleaved}
    (out / "plan.json").write_text(json.dumps(provenance, indent=1) + "\n")

    limits = ab_protocol._parse_limits(arguments.limit)
    higher = set(arguments.higher)
    overall = []
    if not arguments.skip_interleaved:
        aa = ab_protocol.run_joint(command_for("baseline", "baseline-copy", "baseline", "baseline"), ["A", "B"],
                                   arguments.rounds, arguments.warmup)
        aa["provenance"] = provenance
        (out / "aa.json").write_text(json.dumps(aa) + "\n")
        tolerance = ab_protocol.calibrate(aa, limits, higher, arguments.seed, arguments.resamples)
        (out / "tolerance.json").write_text(json.dumps(tolerance, indent=1) + "\n")
        for key, value in tolerance["tolerances"].items():
            print(f"A/A {key}: tolerance {value['tolerance']:.4g} (limit {value['relevance_limit']}) "
                  f"{'capable' if value['capable'] else 'INCAPABLE'}")

        ab = ab_protocol.run_joint(command_for("baseline", "candidate", "baseline", "candidate"), ["A", "B"],
                                   arguments.rounds, arguments.warmup)
        ab["provenance"] = provenance
        ab["variants"] = {"A": {"revision": arguments.baseline, "interleaved": True},
                          "B": {"revision": arguments.candidate, "interleaved": True}}
        (out / "ab.json").write_text(json.dumps(ab) + "\n")
        analysis = ab_protocol.analyze(ab, tolerance, higher, arguments.seed, arguments.resamples)
        (out / "analysis.json").write_text(json.dumps(analysis, indent=1) + "\n")
        table = ab_protocol.markdown(analysis, ("A", "B")).replace("| A | B |", "| baseline | candidate |", 1)
        (out / "table.md").write_text(table)
        print(table)
        overall.append(analysis["overall"])

    if arguments.separate_args:
        def separate(slot):
            return [str(probe)] + [part.replace("{dylib}", str(dylibs[slot])) for part in shlex.split(arguments.separate_args)]
        cold_rounds = arguments.separate_rounds or arguments.rounds
        cold_aa = ab_protocol.run_protocol({"A": separate("baseline"), "A'": separate("baseline-copy")},
                                           cold_rounds, arguments.warmup)
        cold_aa["provenance"] = provenance
        (out / "cold-aa.json").write_text(json.dumps(cold_aa) + "\n")
        cold_tolerance = ab_protocol.calibrate(cold_aa, limits, higher, arguments.seed, arguments.resamples)
        (out / "cold-tolerance.json").write_text(json.dumps(cold_tolerance, indent=1) + "\n")
        cold_ab = ab_protocol.run_protocol({"baseline": separate("baseline"), "candidate": separate("candidate")},
                                           cold_rounds, arguments.warmup)
        cold_ab["provenance"] = provenance
        (out / "cold-ab.json").write_text(json.dumps(cold_ab) + "\n")
        cold_analysis = ab_protocol.analyze(cold_ab, cold_tolerance, higher, arguments.seed, arguments.resamples)
        (out / "cold-analysis.json").write_text(json.dumps(cold_analysis, indent=1) + "\n")
        cold_table = ab_protocol.markdown(cold_analysis, ("baseline", "candidate"))
        (out / "cold-table.md").write_text(cold_table)
        print(cold_table)
        overall.append(cold_analysis["overall"])

    shutil.rmtree(work, ignore_errors=True)
    return 0 if all(value == "non-inferior" for value in overall) else 1


if __name__ == "__main__":
    raise SystemExit(main())
