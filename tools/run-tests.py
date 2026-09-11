#!/usr/bin/env python3
"""Run the focused tests in tests/ and report pass, fail and skip.

Some tests need something this repository does not carry: a built helper from
`build/`, a synthetic DICOM fixture, an adapted external plugin source, or the
built application bundle. Those exit 2 and are reported as skipped with the
argument they wanted, so a sweep of the suite says what was not exercised
instead of burying it among failures.
"""
import argparse
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIPPED = 2

# Keep the last twelve lines for context, but surface assertion text that a
# crash stack would otherwise push off the excerpt (see #391).
_FAILURE_MARKS = ("FAIL:", "failed:", "Assertion failure",
                  "uncaught exception", "reason:")


def failure_excerpt(out, err, tail=12):
    lines = (out + err).strip().splitlines()
    interesting = [line for line in lines if any(mark in line for mark in _FAILURE_MARKS)]
    excerpt = list(dict.fromkeys(interesting + lines[-tail:]))
    return "\n".join(excerpt)


# A long abort stack must not hide the assertion that actually failed (#391).
assert "FAIL: count >= floor(expected)-1" in failure_excerpt(
    "", "FAIL: count >= floor(expected)-1\n" + "\n".join(f"frame {i}" for i in range(20)))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("pattern", nargs="?", default="test-*.py",
                        help="glob within tests/, e.g. 'test-dicom-*.py'")
    parser.add_argument("--verbose", action="store_true",
                        help="print each test as it finishes")
    arguments = parser.parse_args()

    tests = sorted((ROOT / "tests").glob(arguments.pattern))
    if not tests:
        raise SystemExit(f"no tests match {arguments.pattern}")

    passed, failed, skipped = [], [], []
    started = time.monotonic()
    for test in tests:
        result = subprocess.run([sys.executable, str(test)],
                                capture_output=True, text=True, cwd=ROOT)
        if result.returncode == 0:
            passed.append(test.name)
            state = "pass"
        elif result.returncode == SKIPPED:
            skipped.append((test.name, result.stderr.strip().splitlines()[-1]
                            if result.stderr.strip() else ""))
            state = "skip"
        else:
            failed.append((test.name, result.stdout, result.stderr))
            state = "FAIL"
        if arguments.verbose or state == "FAIL":
            print(f"{state:>4}  {test.name}", flush=True)

    for name, out, err in failed:
        print(f"\n--- {name} ---")
        print(failure_excerpt(out, err))
    if skipped:
        print("\nskipped, needing input this repository does not carry:")
        for name, why in skipped:
            print(f"  {name}: {why}")
    print(f"\n{len(passed)} passed, {len(failed)} failed, {len(skipped)} skipped "
          f"in {time.monotonic() - started:.0f}s")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
