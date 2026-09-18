#!/usr/bin/env python3
"""The shared A/B protocol decides mechanically, and cannot be talked into a pass.

Drives tools/ab_protocol.py with synthetic rounds whose truth is known: a real
regression must be called a regression, identical variants must be called
non-inferior against their own A/A tolerance, noise wider than the relevance
limit must make the assay incapable instead of widening the tolerance, and the
runner must alternate the order inside each pair.
"""
import json
import math
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import ab_protocol as ab  # noqa: E402


def record(rounds_a, rounds_b, metric="latency_ms"):
    return {
        "schema": ab.SCHEMA,
        "variants": {"A": {"command": ["a"]}, "B": {"command": ["b"]}},
        "rounds": [
            {"index": i, "order": ab.round_order(i, ["A", "B"]),
             "results": {"A": {metric: list(a)}, "B": {metric: list(b)}}}
            for i, (a, b) in enumerate(zip(rounds_a, rounds_b))
        ],
    }


rng = np.random.default_rng(7)


def noisy(center, spread, rounds=30, per_round=10):
    return [list(center + spread * rng.standard_normal(per_round)) for _ in range(rounds)]


# Order alternates, so each variant runs first in half of the rounds.
orders = [tuple(ab.round_order(i, ["A", "B"])) for i in range(30)]
assert orders.count(("A", "B")) == 15 and orders.count(("B", "A")) == 15, orders

# Parsing keeps only the last JSON object and refuses what is not a finite number.
assert ab.parse_observations('warming up\n{"x": [1, 2.5]}\n') == {"x": [1.0, 2.5]}
for bad in ('{"x": [NaN]}', '{"x": ["1"]}', '{"x": true}', 'no json'):
    try:
        ab.parse_observations(bad)
    except ValueError:
        pass
    else:
        raise AssertionError(f"accepted {bad!r}")

# A/A of the same distribution: small tolerance, capable at a 5 % limit.
aa = record(noisy(10.0, 0.2), noisy(10.0, 0.2))
calibration = ab.calibrate(aa, {"latency_ms": 0.05}, set(), seed=1, resamples=800)
tolerance = calibration["tolerances"]["latency_ms:median"]
assert tolerance["capable"], tolerance
assert 0 < tolerance["tolerance"] < 0.05, tolerance

# Identical candidate: non-inferior against that tolerance.
same = record(noisy(10.0, 0.2), noisy(10.0, 0.2))
analysis = ab.analyze(same, calibration, set(), seed=1, resamples=800, statistics=("median",))
assert analysis["rows"][0]["decision"] in ("non-inferior", "inconclusive"), analysis["rows"][0]

# A candidate 20 % slower is a regression, whatever the order of the pairs.
slower = record(noisy(10.0, 0.2), noisy(12.0, 0.2))
analysis = ab.analyze(slower, calibration, set(), seed=1, resamples=800, statistics=("median",))
row = analysis["rows"][0]
assert row["decision"] == "regression" and analysis["overall"] == "regression", row
assert 0.15 < row["worsening"] < 0.25, row

# A faster candidate is non-inferior; for a throughput metric the direction flips.
faster = record(noisy(10.0, 0.2), noisy(8.0, 0.2))
assert ab.analyze(faster, calibration, set(), seed=1, resamples=800,
                  statistics=("median",))["rows"][0]["decision"] == "non-inferior"
throughput = record(noisy(10.0, 0.2), noisy(8.0, 0.2))
throughput_calibration = {"tolerances": {"latency_ms:median": dict(tolerance)}}
row = ab.analyze(throughput, throughput_calibration, {"latency_ms"}, seed=1, resamples=800,
                 statistics=("median",))["rows"][0]
assert row["direction"] == "higher" and row["decision"] == "regression", row

# Noise wider than the relevance limit: the assay is declared incapable, never passed.
wild = record(noisy(10.0, 4.0, per_round=3), noisy(10.0, 4.0, per_round=3))
wild_calibration = ab.calibrate(wild, {"latency_ms": 0.01}, set(), seed=1, resamples=800)
assert not wild_calibration["tolerances"]["latency_ms:median"]["capable"]
row = ab.analyze(same, wild_calibration, set(), seed=1, resamples=800, statistics=("median",))["rows"][0]
assert row["decision"] == "assay-incapable", row

# Counts compare absolute differences, so zero threads against one thread is +1, not infinity.
counts = record([[0]] * 10, [[1]] * 10, metric="threads_count")
row = ab.compare(counts, "threads_count", "median", seed=1, resamples=200)
assert row["mode"] == "absolute" and row["worsening"] == 1 and row["worsening_ci95"] == [1.0, 1.0], row

# The same seed gives the same interval; a p95 from a small sample is flagged.
first = ab.compare(slower, "latency_ms", "p95", seed=3, resamples=300)
second = ab.compare(slower, "latency_ms", "p95", seed=3, resamples=300)
assert first["worsening_ci95"] == second["worsening_ci95"]
assert not first["p95_sample_warning"]  # 300 observations per variant
small = ab.compare(record(noisy(10, 0.2, rounds=5), noisy(10, 0.2, rounds=5)), "latency_ms", "p95",
                   seed=3, resamples=100)
assert small["p95_sample_warning"]

# End to end through the command line, with real processes as probes.
with tempfile.TemporaryDirectory(prefix="horos-ab-") as folder:
    work = Path(folder)
    probe = work / "probe.py"
    probe.write_text("import json, os\n"
                     "v = os.environ['HOROS_AB_VARIANT']\n"
                     "print('noise on stdout first')\n"
                     "print(json.dumps({'work_ms': [1.0 if v == 'A' else 1.0] * 5, 'items_count': 3}))\n")
    out = work / "run.json"
    command = f"{sys.executable} {probe}"
    subprocess.run([sys.executable, str(ROOT / "tools/ab_protocol.py"), "run", "--rounds", "4", "--warmup", "1",
                    "--variant", f"A={command}", "--variant", f"B={command}", "--out", str(out)],
                   check=True, capture_output=True)
    data = json.loads(out.read_text())
    assert [r["order"] for r in data["rounds"]] == [["A", "B"], ["B", "A"], ["A", "B"], ["B", "A"]]
    assert data["environment"]["architecture"]
    tolerance_file = work / "tolerance.json"
    subprocess.run([sys.executable, str(ROOT / "tools/ab_protocol.py"), "calibrate", str(out),
                    "--out", str(tolerance_file), "--resamples", "100"], check=True, capture_output=True)
    result = subprocess.run([sys.executable, str(ROOT / "tools/ab_protocol.py"), "analyze", str(out),
                             "--tolerance", str(tolerance_file), "--resamples", "100"],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "non-inferior" in result.stdout

# Interleaved rounds: one invocation reports both variants, and the first
# variant alternates between rounds through HOROS_AB_FIRST.
with tempfile.TemporaryDirectory(prefix="horos-ab-joint-") as folder:
    probe = Path(folder) / "joint.py"
    probe.write_text("import json, os\n"
                     "first = os.environ['HOROS_AB_FIRST']\n"
                     "print(json.dumps({'A': {'t_us': [2.0, 2.0], 'first_count': int(first == 'A')},\n"
                     "                  'B': {'t_us': [3.0, 3.0], 'first_count': int(first == 'B')}}))\n")
    joint = ab.run_joint([sys.executable, str(probe)], ["A", "B"], rounds=4, warmup=1, log=open("/dev/null", "w"))
    assert [r["results"]["A"]["first_count"] for r in joint["rounds"]] == [[1.0], [0.0], [1.0], [0.0]], joint["rounds"]
    row = ab.compare(joint, "t_us", "median", seed=1, resamples=50)
    assert abs(row["worsening"] - 0.5) < 1e-9 and row["worsening_ci95"] == [0.5, 0.5], row
    try:
        ab.run_joint([sys.executable, "-c", "print('{\"A\": {\"x\": 1}}')"], ["A", "B"], rounds=1, warmup=0,
                     log=open("/dev/null", "w"))
    except ValueError:
        pass
    else:
        raise AssertionError("a probe that omits a variant must be refused")

# Protocol v2: a candidate identical to the baseline must pass almost always,
# while a worsening well beyond the instrument's resolution must not. v1 is kept
# to show the defect it had (roughly one false "inconclusive" in four).
def simulate(version, shift, trials=120):
    outcomes = {"non-inferior": 0, "inconclusive": 0, "regression": 0}
    sim = np.random.default_rng(11)
    for _ in range(trials):
        def rounds(center):
            return [list(center + 0.3 * sim.standard_normal(12)) for _ in range(20)]
        aa_record = record(rounds(10.0), rounds(10.0))
        cal = ab.calibrate(aa_record, {}, set(), seed=int(sim.integers(1 << 30)), resamples=200,
                           statistics=("median",), version=version)
        ab_record = record(rounds(10.0), rounds(10.0 * (1 + shift)))
        row = ab.analyze(ab_record, cal, set(), seed=int(sim.integers(1 << 30)), resamples=200,
                         statistics=("median",))["rows"][0]
        outcomes[row["decision"]] += 1
    return outcomes

v1_same = simulate(1, 0.0)
v2_same = simulate(2, 0.0)
v2_worse = simulate(2, 0.03)
assert v1_same["non-inferior"] / 120 < 0.9, v1_same            # the defect v2 fixes
assert v2_same["non-inferior"] / 120 >= 0.95, v2_same
assert v2_worse["non-inferior"] / 120 <= 0.05, v2_worse       # ~3 half-widths worse is never accepted

print("PASS: alternating rounds, strict parsing, A/A tolerance, regression, direction, incapable assay, counts, seed, "
      f"interleaved rounds, v2 decision rule (identical passes {v2_same['non-inferior']}/120, "
      f"v1 {v1_same['non-inferior']}/120; 3 % worse accepted {v2_worse['non-inferior']}/120)")
