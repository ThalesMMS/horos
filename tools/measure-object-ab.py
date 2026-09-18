#!/usr/bin/env python3
"""A/A calibration and A/B comparison of one compiled source file (Δ4 protocol, #624).

Recompiles `--source` at the baseline revision and at the candidate (a revision
or the working tree) with the exact clang command xcodebuild logged for the
application, links each object into the same probe, and runs
tools/ab_protocol.py twice: baseline against itself to fix the tolerances, then
baseline against candidate. Baseline and candidate differ only in that one
file; flags, headers and the probe are shared.

    python3 tools/measure-object-ab.py \
        --source Nitrogen/Sources/NSFileManager+N2.mm \
        --probe tools/probe-noindex-directory.m \
        --baseline efb2b0cef --candidate WORKTREE --configuration Debug \
        --args-baseline 'bench {scratch} 400 40 .noindex' \
        --args-candidate 'bench {scratch} 400 40 ""' \
        --limit existing_us:median=0.05 --limit existing_us:p95=0.10 \
        --out local-validation/delta4/612-Debug

`{scratch}` is replaced by a scratch folder created for the run. The tolerance
file is written before the candidate is run, and the A/B run reuses it
unchanged.
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


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", required=True)
    parser.add_argument("--probe", required=True, type=Path)
    parser.add_argument("--extra-source", action="append", default=[], type=Path)
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--candidate", default="WORKTREE")
    parser.add_argument("--baseline-file", type=Path,
                        help="use this source file as the baseline instead of --baseline's revision "
                             "(a generated functional reference); --baseline then only labels it")
    parser.add_argument("--configuration", default="Debug", choices=("Debug", "Release"))
    parser.add_argument("--build-log", type=Path, help="xcodebuild log holding the compile command")
    parser.add_argument("--build-root", type=Path, default=ROOT,
                        help="checkout whose build logged the command (e.g. a baseline worktree)")
    parser.add_argument("--args-baseline", required=True)
    parser.add_argument("--args-candidate", required=True)
    parser.add_argument("--limit", action="append", default=[])
    parser.add_argument("--higher", action="append", default=[])
    parser.add_argument("--rounds", type=int, default=30)
    parser.add_argument("--warmup", type=int, default=1)
    parser.add_argument("--resamples", type=int, default=ab_protocol.DEFAULT_RESAMPLES)
    parser.add_argument("--seed", type=int, default=ab_protocol.DEFAULT_SEED)
    parser.add_argument("--probe-optimization", default="-O2")
    parser.add_argument("--framework", action="append", default=[])
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--skip-aa", action="store_true", help="reuse <out>/tolerance.json from an earlier A/A")
    arguments = parser.parse_args()

    out = arguments.out
    out.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="horos-object-ab-"))
    scratch = work / "scratch"
    scratch.mkdir()

    command = object_probe.compile_command(arguments.source, arguments.configuration,
                                           root=arguments.build_root.resolve(), log=arguments.build_log)
    name = Path(arguments.source).name
    objects = {}
    revisions = {"baseline": arguments.baseline, "candidate": arguments.candidate}
    for label, revision in revisions.items():
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
        obj = work / label / (Path(name).stem + ".o")
        object_probe.compile_source(command, source, obj)
        objects[label] = obj

    frameworks = ["Foundation"] + arguments.framework
    probes = {}
    for label, obj in objects.items():
        probes[label] = object_probe.link_probe(arguments.probe, [obj], work / f"probe-{label}",
                                                extra_sources=arguments.extra_source,
                                                optimization=arguments.probe_optimization,
                                                frameworks=frameworks)

    def argv(label):
        template = arguments.args_baseline if label == "baseline" else arguments.args_candidate
        return [str(probes[label])] + [part.replace("{scratch}", str(scratch)) for part in shlex.split(template)]

    head = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    provenance = {
        "source": arguments.source,
        "baseline_revision": arguments.baseline,
        "baseline_file": str(arguments.baseline_file) if arguments.baseline_file else None,
        "candidate_revision": arguments.candidate,
        "workbench_head": head,
        "configuration": arguments.configuration,
        "compile_command": command,
        "build_root": str(arguments.build_root.resolve()),
        "probe": str(arguments.probe),
        "probe_optimization": arguments.probe_optimization,
        "limits": arguments.limit,
        "rounds": arguments.rounds,
        "warmup": arguments.warmup,
        "seed": arguments.seed,
        "resamples": arguments.resamples,
    }
    (out / "plan.json").write_text(json.dumps(provenance, indent=1) + "\n")

    limits = ab_protocol._parse_limits(arguments.limit)
    higher = set(arguments.higher)
    tolerance_path = out / "tolerance.json"
    if not arguments.skip_aa:
        aa = ab_protocol.run_protocol({"A": argv("baseline"), "A'": argv("baseline")},
                                      arguments.rounds, arguments.warmup)
        aa["provenance"] = provenance
        (out / "aa.json").write_text(json.dumps(aa) + "\n")
        tolerance = ab_protocol.calibrate(aa, limits, higher, arguments.seed, arguments.resamples)
        tolerance_path.write_text(json.dumps(tolerance, indent=1) + "\n")
        for key, value in tolerance["tolerances"].items():
            print(f"A/A {key}: tolerance {value['tolerance']:.4g} (limit {value['relevance_limit']}) "
                  f"{'capable' if value['capable'] else 'INCAPABLE'}")
    tolerance = json.loads(tolerance_path.read_text())

    ab = ab_protocol.run_protocol({"baseline": argv("baseline"), "candidate": argv("candidate")},
                                  arguments.rounds, arguments.warmup)
    ab["provenance"] = provenance
    (out / "ab.json").write_text(json.dumps(ab) + "\n")
    analysis = ab_protocol.analyze(ab, tolerance, higher, arguments.seed, arguments.resamples)
    (out / "analysis.json").write_text(json.dumps(analysis, indent=1) + "\n")
    table = ab_protocol.markdown(analysis, ("baseline", "candidate"))
    (out / "table.md").write_text(table)
    print(table)
    shutil.rmtree(work, ignore_errors=True)
    return 0 if analysis["overall"] == "non-inferior" else 1


if __name__ == "__main__":
    raise SystemExit(main())
