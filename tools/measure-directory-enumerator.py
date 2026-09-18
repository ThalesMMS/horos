#!/usr/bin/env python3
"""Interleaved A/A and A/B of N2DirectoryEnumerator (Δ4 protocol, #627).

A class cannot be loaded twice under one name, so the two implementations
share a process by renaming one at compile time: the baseline object is built
with the app's own clang command plus
`-DN2DirectoryEnumerator=N2DirectoryEnumeratorBaseline`. For the A/A the second
copy of the baseline keeps the class name and renames its private releaser
class instead, so the two copies do not collide. tools/probe-directory-enumerator.m
alternates the two scan by scan.

    python3 tools/measure-directory-enumerator.py --baseline efb2b0cef --candidate <sha> \
        --configuration Release --out local-validation/delta4/627-Release
"""
import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import ab_protocol  # noqa: E402
import object_probe  # noqa: E402

SOURCE = "Nitrogen/Sources/N2DirectoryEnumerator.mm"


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--configuration", default="Debug", choices=("Debug", "Release"))
    parser.add_argument("--rounds", type=int, default=30)
    parser.add_argument("--scans", type=int, default=10)
    parser.add_argument("--limit", action="append", default=[])
    parser.add_argument("--out", type=Path, required=True)
    arguments = parser.parse_args()

    out = arguments.out
    out.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="horos-enumerator-ab-"))
    command = object_probe.compile_command(SOURCE, arguments.configuration)

    def compile_variant(revision, label, defines):
        source = object_probe.revision_source(SOURCE, revision, work / label / "N2DirectoryEnumerator.mm")
        obj = work / label / "N2DirectoryEnumerator.o"
        subprocess.run(command + defines + ["-c", str(source), "-o", str(obj)], check=True)
        return obj

    baseline_renamed = compile_variant(arguments.baseline, "baseline-renamed",
                                       ["-DN2DirectoryEnumerator=N2DirectoryEnumeratorBaseline"])
    baseline_copy = compile_variant(arguments.baseline, "baseline-copy",
                                    ["-DN2DirectoryEnumeratorReleaser=N2DirectoryEnumeratorReleaserCopy"])
    candidate = compile_variant(arguments.candidate, "candidate", [])
    probes = {
        "aa": object_probe.link_probe(ROOT / "tools/probe-directory-enumerator.m", [baseline_renamed, baseline_copy],
                                      work / "probe-aa"),
        "ab": object_probe.link_probe(ROOT / "tools/probe-directory-enumerator.m", [baseline_renamed, candidate],
                                      work / "probe-ab"),
    }
    scratch = work / "trees"
    scratch.mkdir()
    plan = {"source": SOURCE, "baseline_revision": arguments.baseline, "candidate_revision": arguments.candidate,
            "configuration": arguments.configuration, "compile_command": command, "rounds": arguments.rounds,
            "scans_per_round": arguments.scans, "limits": arguments.limit,
            "protocol_version": ab_protocol.PROTOCOL_VERSION,
            "design": "one process, baseline class renamed at compile time, ABBA scans"}
    (out / "plan.json").write_text(json.dumps(plan, indent=1) + "\n")
    limits = ab_protocol._parse_limits(arguments.limit)
    aa = ab_protocol.run_joint([str(probes["aa"]), "interleave", str(scratch), str(arguments.scans)], ["A", "B"],
                               arguments.rounds, 1)
    (out / "aa.json").write_text(json.dumps(aa) + "\n")
    tolerance = ab_protocol.calibrate(aa, limits, set(), ab_protocol.DEFAULT_SEED, ab_protocol.DEFAULT_RESAMPLES)
    (out / "tolerance.json").write_text(json.dumps(tolerance, indent=1) + "\n")
    for key, value in tolerance["tolerances"].items():
        print(f"A/A {key}: tolerance {value['tolerance']:.4g} (limit {value['relevance_limit']}) "
              f"{'capable' if value['capable'] else 'INCAPABLE'}")
    ab = ab_protocol.run_joint([str(probes["ab"]), "interleave", str(scratch), str(arguments.scans)], ["A", "B"],
                               arguments.rounds, 1)
    ab["variants"] = {"A": {"revision": arguments.baseline}, "B": {"revision": arguments.candidate}}
    (out / "ab.json").write_text(json.dumps(ab) + "\n")
    analysis = ab_protocol.analyze(ab, tolerance, set(), ab_protocol.DEFAULT_SEED, ab_protocol.DEFAULT_RESAMPLES)
    (out / "analysis.json").write_text(json.dumps(analysis, indent=1) + "\n")
    table = ab_protocol.markdown(analysis, ("A", "B")).replace("| A | B |", "| baseline | candidate |", 1)
    (out / "table.md").write_text(table)
    print(table)
    shutil.rmtree(work, ignore_errors=True)
    return 0 if analysis["overall"] == "non-inferior" else 1


if __name__ == "__main__":
    raise SystemExit(main())
