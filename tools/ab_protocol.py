#!/usr/bin/env python3
"""Paired A/B performance protocol shared by the Δ4 deliveries (#624).

The Epic fixes the method before any candidate is measured:

1. calibrate with an A/A run of the baseline against itself, and derive each
   metric's tolerance from that run's own noise;
2. run the candidate in independent rounds, alternating the order inside each
   pair (AB, BA, AB, ...), so drift and position cannot favour one side;
3. resample *rounds* - never individual correlated observations - with a
   recorded seed, and report median, p95, dispersion and the 95 % interval of
   the paired difference;
4. decide mechanically: the upper bound of the worsening interval must stay
   inside the tolerance registered before the candidate ran.

Commands print one JSON object per invocation, mapping a metric name to a number
or a list of numbers observed in that invocation. Everything they print on
stderr is kept out of the record.

    ab_protocol.py run --out aa.json --rounds 30 \
        --variant A=./baseline-probe --variant B=./baseline-probe
    ab_protocol.py calibrate aa.json --out tolerance.json --limit latency_ms=0.05
    ab_protocol.py run --out ab.json --rounds 30 \
        --variant A=./baseline-probe --variant B=./candidate-probe
    ab_protocol.py analyze ab.json --tolerance tolerance.json --markdown table.md

A metric is "lower is better" unless its name is listed with --higher (for
throughput). Metrics whose name ends in `_count` compare absolute differences,
because a ratio against zero threads or zero descriptors means nothing.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import math
import os
import platform
import shlex
import subprocess
import sys
from pathlib import Path

import numpy as np

SCHEMA = "horos-ab-v1"
DEFAULT_SEED = 20260916
DEFAULT_RESAMPLES = 4000
# A p95 drawn from fewer observations than this is reported but flagged: the
# Epic forbids claiming a stable p95 from a small sample.
STABLE_P95_OBSERVATIONS = 200


def _run_text(command):
    try:
        return subprocess.run(command, capture_output=True, text=True, timeout=30).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def environment(root: Path | None = None) -> dict:
    root = root or Path(__file__).resolve().parents[1]
    return {
        "machine": _run_text(["/usr/sbin/sysctl", "-n", "hw.model"]),
        "cpu": _run_text(["/usr/sbin/sysctl", "-n", "machdep.cpu.brand_string"]),
        "memory_bytes": _run_text(["/usr/sbin/sysctl", "-n", "hw.memsize"]),
        "macos": _run_text(["/usr/bin/sw_vers", "-productVersion"]),
        "macos_build": _run_text(["/usr/bin/sw_vers", "-buildVersion"]),
        "xcode": " ".join(_run_text(["/usr/bin/xcrun", "xcodebuild", "-version"]).split()),
        "architecture": platform.machine(),
        "workbench_head": _run_text(["/usr/bin/git", "-C", str(root), "rev-parse", "HEAD"]),
        "python": platform.python_version(),
    }


def parse_observations(text: str) -> dict[str, list[float]]:
    """Take the last JSON object a probe printed; ignore any chatter before it."""
    for line in reversed(text.strip().splitlines()):
        line = line.strip()
        if line.startswith("{") and line.endswith("}"):
            payload = json.loads(line)
            break
    else:
        raise ValueError("probe printed no JSON object")
    observations = {}
    for name, value in payload.items():
        values = value if isinstance(value, list) else [value]
        numbers = []
        for item in values:
            if isinstance(item, bool) or not isinstance(item, (int, float)):
                raise ValueError(f"metric {name} has a non-numeric observation: {item!r}")
            if not math.isfinite(item):
                raise ValueError(f"metric {name} has a non-finite observation: {item!r}")
            numbers.append(float(item))
        observations[name] = numbers
    return observations


def round_order(index: int, names: list[str]) -> list[str]:
    """Alternate AB / BA so each variant runs first in half of the rounds."""
    return list(names) if index % 2 == 0 else list(reversed(names))


def run_protocol(variants: dict[str, list[str]], rounds: int, warmup: int,
                 env_extra: dict[str, str] | None = None, log=sys.stderr) -> dict:
    names = list(variants)
    if len(names) != 2:
        raise ValueError("exactly two variants are compared")
    base_env = dict(os.environ)
    base_env.update(env_extra or {})
    for index in range(warmup):
        for name in round_order(index, names):
            env = dict(base_env, HOROS_AB_ROUND="warmup", HOROS_AB_VARIANT=name)
            result = subprocess.run(variants[name], capture_output=True, text=True, env=env)
            if result.returncode != 0:
                raise RuntimeError(f"warm-up of {name} failed ({result.returncode}): {result.stderr[-2000:]}")
    records = []
    for index in range(rounds):
        order = round_order(index, names)
        results = {}
        for name in order:
            env = dict(base_env, HOROS_AB_ROUND=str(index), HOROS_AB_VARIANT=name)
            result = subprocess.run(variants[name], capture_output=True, text=True, env=env)
            if result.returncode != 0:
                raise RuntimeError(f"round {index} {name} failed ({result.returncode}): {result.stderr[-2000:]}")
            results[name] = parse_observations(result.stdout)
        records.append({"index": index, "order": order, "results": results})
        print(f"round {index + 1}/{rounds} done ({'→'.join(order)})", file=log)
    return {
        "schema": SCHEMA,
        "created": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "variants": {name: {"command": command} for name, command in variants.items()},
        "warmup_invocations_per_variant": warmup,
        "rounds": records,
        "environment": environment(),
    }


def run_joint(command: list[str], names: list[str], rounds: int, warmup: int,
              env_extra: dict[str, str] | None = None, log=sys.stderr) -> dict:
    """Rounds where one invocation measures both variants, interleaved.

    For operations whose noise comes in bursts longer than one call (a file
    system flushing, a daemon waking), separate processes let a burst land on
    one variant only. A probe that holds both implementations and alternates
    them call by call exposes both to the same burst. The probe prints
    {"<variant>": {metric: [...]}, ...}; HOROS_AB_ROUND tells it which variant
    goes first, so the start alternates between rounds like the paired runner.
    """
    if len(names) != 2:
        raise ValueError("exactly two variants are compared")
    base_env = dict(os.environ)
    base_env.update(env_extra or {})

    def invoke(index, label):
        env = dict(base_env, HOROS_AB_ROUND=str(index), HOROS_AB_FIRST=round_order(index, names)[0]
                   if isinstance(index, int) else names[0])
        result = subprocess.run(command, capture_output=True, text=True, env=env)
        if result.returncode != 0:
            raise RuntimeError(f"{label} failed ({result.returncode}): {result.stderr[-2000:]}")
        for line in reversed(result.stdout.strip().splitlines()):
            line = line.strip()
            if line.startswith("{") and line.endswith("}"):
                payload = json.loads(line)
                break
        else:
            raise ValueError(f"{label}: probe printed no JSON object")
        missing = [name for name in names if name not in payload]
        if missing:
            raise ValueError(f"{label}: probe did not report {missing}")
        return {name: parse_observations(json.dumps(payload[name])) for name in names}

    for index in range(warmup):
        invoke("warmup", f"warm-up {index}")
    records = []
    for index in range(rounds):
        results = invoke(index, f"round {index}")
        records.append({"index": index, "order": round_order(index, names) + ["interleaved"], "results": results})
        print(f"round {index + 1}/{rounds} done (interleaved, {round_order(index, names)[0]} first)", file=log)
    return {
        "schema": SCHEMA,
        "created": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "variants": {name: {"command": command, "interleaved": True} for name in names},
        "warmup_invocations": warmup,
        "rounds": records,
        "environment": environment(),
    }


def percentile(values: np.ndarray, q: float) -> float:
    return float(np.percentile(values, q, method="linear"))


def _statistic(values: np.ndarray, name: str) -> float:
    if name == "median":
        return percentile(values, 50)
    if name == "p95":
        return percentile(values, 95)
    if name == "mean":
        return float(values.mean())
    raise ValueError(name)


def _pooled(rounds: list[np.ndarray], picks: np.ndarray) -> np.ndarray:
    return np.concatenate([rounds[i] for i in picks])


def _worsening(a: float, b: float, higher_is_better: bool, absolute: bool) -> float:
    delta = (a - b) if higher_is_better else (b - a)
    if absolute:
        return delta
    if a == 0:
        return math.inf if delta > 0 else (0.0 if delta == 0 else -math.inf)
    return delta / abs(a)


def compare(record: dict, metric: str, statistic: str, *, higher: bool = False,
            seed: int = DEFAULT_SEED, resamples: int = DEFAULT_RESAMPLES,
            variants: tuple[str, str] | None = None) -> dict:
    names = variants or tuple(record["variants"])
    first, second = names
    rounds_a, rounds_b = [], []
    for entry in record["rounds"]:
        a = entry["results"][first].get(metric)
        b = entry["results"][second].get(metric)
        if a is None or b is None:
            raise KeyError(f"round {entry['index']} lacks {metric} for one variant")
        rounds_a.append(np.sort(np.asarray(a, dtype=float)))
        rounds_b.append(np.sort(np.asarray(b, dtype=float)))
    count = len(rounds_a)
    if count < 2:
        raise ValueError("at least two rounds are needed to resample")
    absolute = metric.endswith("_count")
    all_a = np.concatenate(rounds_a)
    all_b = np.concatenate(rounds_b)
    estimate_a = _statistic(all_a, statistic)
    estimate_b = _statistic(all_b, statistic)
    estimate = _worsening(estimate_a, estimate_b, higher, absolute)
    generator = np.random.default_rng(seed)
    draws = np.empty(resamples)
    for k in range(resamples):
        picks = generator.integers(0, count, size=count)
        draws[k] = _worsening(_statistic(_pooled(rounds_a, picks), statistic),
                              _statistic(_pooled(rounds_b, picks), statistic), higher, absolute)
    finite = draws[np.isfinite(draws)]
    if finite.size < draws.size:
        low, high = (-math.inf, math.inf)
    else:
        low, high = percentile(finite, 2.5), percentile(finite, 97.5)

    def spread(rounds):
        per_round = np.array([_statistic(r, statistic) for r in rounds])
        return {"per_round_min": float(per_round.min()), "per_round_max": float(per_round.max()),
                "per_round_iqr": float(percentile(per_round, 75) - percentile(per_round, 25))}

    return {
        "metric": metric,
        "statistic": statistic,
        "direction": "higher" if higher else "lower",
        "mode": "absolute" if absolute else "relative",
        "rounds": count,
        "observations": {first: int(all_a.size), second: int(all_b.size)},
        "value": {first: estimate_a, second: estimate_b},
        "dispersion": {first: spread(rounds_a), second: spread(rounds_b)},
        "worsening": estimate,
        "worsening_ci95": [low, high],
        "seed": seed,
        "resamples": resamples,
        "p95_sample_warning": statistic == "p95" and min(all_a.size, all_b.size) < STABLE_P95_OBSERVATIONS,
    }


def metrics_of(record: dict) -> list[str]:
    first = record["rounds"][0]["results"]
    names = None
    for variant in first.values():
        keys = set(variant)
        names = keys if names is None else names & keys
    return sorted(names or [])


PROTOCOL_VERSION = 2


def calibrate(record: dict, limits: dict[str, float], higher: set[str], seed: int,
              resamples: int, statistics=("median", "p95"), version: int = PROTOCOL_VERSION) -> dict:
    """Tolerance = the resolution of the paired comparison, measured by an A/A run.

    Version 1 took the largest excursion of the A/A interval, max(|lo|, |hi|).
    That cannot be met reliably by a candidate that is truly identical: its own
    upper bound is its noise plus the same half-width h, so it passes only when
    its noise is below the A/A's - about 75 % of the time per metric (for iid
    normal estimates X, Y, P(X <= |Y|) = 3/4). #613 produced exactly that: an
    estimate of +0.00 % declared inconclusive. Version 2 adds the A/A half-width,
    tolerance = max(|lo|, |hi|) + (hi - lo) / 2, under which an identical
    candidate passes about 99 % of the time and a worsening larger than about one
    half-width is still not accepted. tests/test-ab-protocol.py simulates both.

    `limits` states, per metric, the worsening the assay must still be able to
    see. A tolerance above it means the assay cannot distinguish a relevant
    regression: the calibration says so instead of widening anything.
    """
    tolerances = {}
    for metric in metrics_of(record):
        for statistic in statistics:
            result = compare(record, metric, statistic, higher=metric in higher, seed=seed, resamples=resamples)
            low, high = result["worsening_ci95"]
            excursion = max(abs(low), abs(high))
            tolerance = excursion + (high - low) / 2 if version >= 2 else excursion
            limit = limits.get(f"{metric}:{statistic}", limits.get(metric))
            tolerances[f"{metric}:{statistic}"] = {
                "tolerance": tolerance,
                "protocol_version": version,
                "derivation": ("max(|2.5 %|, |97.5 %|) + half-width of the A/A paired worsening interval, "
                               "bootstrap by round" if version >= 2 else
                               "max(|2.5 %|, |97.5 %|) of the A/A paired worsening, bootstrap by round"),
                "aa_worsening_ci95": [low, high],
                "relevance_limit": limit,
                "capable": limit is None or tolerance <= limit,
                "mode": result["mode"],
                "rounds": result["rounds"],
                "observations": result["observations"],
            }
    return {"schema": SCHEMA + "-tolerance", "created": _dt.datetime.now(_dt.timezone.utc).isoformat(),
            "protocol_version": version, "seed": seed, "resamples": resamples,
            "source_environment": record.get("environment"), "tolerances": tolerances}


def decide(result: dict, tolerance: dict | None) -> str:
    if tolerance is None:
        return "no-tolerance"
    if not tolerance.get("capable", True):
        return "assay-incapable"
    low, high = result["worsening_ci95"]
    limit = tolerance["tolerance"]
    if high <= limit:
        return "non-inferior"
    if low > limit:
        return "regression"
    return "inconclusive"


def analyze(record: dict, tolerance_record: dict | None, higher: set[str], seed: int,
            resamples: int, statistics=("median", "p95"), metrics: list[str] | None = None) -> dict:
    rows = []
    tolerances = (tolerance_record or {}).get("tolerances", {})
    for metric in metrics or metrics_of(record):
        for statistic in statistics:
            result = compare(record, metric, statistic, higher=metric in higher, seed=seed, resamples=resamples)
            key = f"{metric}:{statistic}"
            result["tolerance"] = tolerances.get(key, {}).get("tolerance")
            result["decision"] = decide(result, tolerances.get(key))
            rows.append(result)
    verdicts = {row["decision"] for row in rows}
    if "regression" in verdicts:
        overall = "regression"
    elif verdicts & {"inconclusive", "assay-incapable", "no-tolerance"}:
        overall = "pending"
    else:
        overall = "non-inferior"
    return {"schema": SCHEMA + "-analysis", "overall": overall, "rows": rows,
            "environment": record.get("environment")}


def _format(value: float, mode: str) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "–"
    if math.isinf(value):
        return "∞" if value > 0 else "−∞"
    if mode == "absolute":
        return f"{value:+.3g}"
    return f"{value * 100:+.2f} %"


def markdown(analysis: dict, names: tuple[str, str]) -> str:
    first, second = names
    lines = [
        f"| métrica | estatística | {first} | {second} | piora | IC 95 % da piora | tolerância | decisão |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for row in analysis["rows"]:
        low, high = row["worsening_ci95"]
        note = " ⚠︎ p95 < 200 obs." if row.get("p95_sample_warning") else ""
        tolerance = row.get("tolerance")
        lines.append(
            f"| {row['metric']} | {row['statistic']} | {row['value'][first]:.6g} | {row['value'][second]:.6g} "
            f"| {_format(row['worsening'], row['mode'])} | [{_format(low, row['mode'])}, {_format(high, row['mode'])}] "
            f"| {_format(tolerance, row['mode']) if tolerance is not None else '–'} | {row['decision']}{note} |")
    lines.append("")
    lines.append(f"Resultado global: **{analysis['overall']}** (piora positiva = pior; "
                 f"bootstrap por rodada, {analysis['rows'][0]['resamples'] if analysis['rows'] else 0} reamostragens, "
                 f"semente {analysis['rows'][0]['seed'] if analysis['rows'] else DEFAULT_SEED}).")
    return "\n".join(lines) + "\n"


def _parse_variant(text: str) -> tuple[str, list[str]]:
    name, _, command = text.partition("=")
    if not name or not command:
        raise argparse.ArgumentTypeError("variant must be NAME=command")
    return name, shlex.split(command)


def _parse_limits(items: list[str]) -> dict[str, float]:
    limits = {}
    for item in items or []:
        name, _, value = item.partition("=")
        limits[name] = float(value)
    return limits


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="execute paired rounds and record observations")
    run.add_argument("--variant", action="append", type=_parse_variant, required=True)
    run.add_argument("--rounds", type=int, default=30)
    run.add_argument("--warmup", type=int, default=1, help="unrecorded invocations per variant")
    run.add_argument("--out", type=Path, required=True)
    run.add_argument("--label", default="")

    cal = sub.add_parser("calibrate", help="derive tolerances from an A/A record")
    cal.add_argument("record", type=Path)
    cal.add_argument("--out", type=Path, required=True)
    cal.add_argument("--limit", action="append", default=[],
                     help="metric=max or metric:statistic=max tolerable worsening")
    cal.add_argument("--higher", action="append", default=[])
    cal.add_argument("--seed", type=int, default=DEFAULT_SEED)
    cal.add_argument("--resamples", type=int, default=DEFAULT_RESAMPLES)
    cal.add_argument("--protocol-version", type=int, default=PROTOCOL_VERSION, choices=(1, 2))

    ana = sub.add_parser("analyze", help="compare the variants of a record")
    ana.add_argument("record", type=Path)
    ana.add_argument("--tolerance", type=Path)
    ana.add_argument("--higher", action="append", default=[])
    ana.add_argument("--seed", type=int, default=DEFAULT_SEED)
    ana.add_argument("--resamples", type=int, default=DEFAULT_RESAMPLES)
    ana.add_argument("--json", type=Path)
    ana.add_argument("--markdown", type=Path)

    arguments = parser.parse_args(argv)
    if arguments.command == "run":
        variants = dict(arguments.variant)
        record = run_protocol(variants, arguments.rounds, arguments.warmup)
        record["label"] = arguments.label
        arguments.out.write_text(json.dumps(record, indent=1) + "\n")
        return 0
    if arguments.command == "calibrate":
        record = json.loads(arguments.record.read_text())
        result = calibrate(record, _parse_limits(arguments.limit), set(arguments.higher),
                           arguments.seed, arguments.resamples, version=arguments.protocol_version)
        arguments.out.write_text(json.dumps(result, indent=1) + "\n")
        for key, value in result["tolerances"].items():
            print(f"{key}: tolerance {_format(value['tolerance'], value['mode'])}"
                  f"{'' if value['capable'] else ' — ASSAY INCAPABLE'}")
        return 0
    record = json.loads(arguments.record.read_text())
    tolerance = json.loads(arguments.tolerance.read_text()) if arguments.tolerance else None
    analysis = analyze(record, tolerance, set(arguments.higher), arguments.seed, arguments.resamples)
    names = tuple(record["variants"])
    table = markdown(analysis, names)
    print(table)
    if arguments.json:
        arguments.json.write_text(json.dumps(analysis, indent=1) + "\n")
    if arguments.markdown:
        arguments.markdown.write_text(table)
    return 0 if analysis["overall"] == "non-inferior" else 1


if __name__ == "__main__":
    raise SystemExit(main())
