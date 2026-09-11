#!/usr/bin/env python3
"""Development smoke-test helper for the Horos tumour-segmentation job contract.

Adapted from ystarrev/horos Scripts/metal3d_tumor_segmentation_mock.py at
SHA 23722fb552d96fa2d60c7f58a6d4ac2c27950f86. This is not a diagnostic tumour
algorithm. It exists to exercise `helper --job job.json` until a local nnU-Net
folder is configured. Missing weights must not be treated as a successful run.
"""

from __future__ import annotations

import argparse
import array
import json
import math
import sys


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--job", required=True)
    args = parser.parse_args()

    with open(args.job, "r", encoding="utf-8") as handle:
        job = json.load(handle)

    dimensions = job["dimensions"]
    expected_count = int(job["expectedVoxelCount"])
    input_path = job["inputVolume"]
    output_path = job["outputLabelmap"]
    result_path = job.get("resultJSON")

    values = array.array("f")
    with open(input_path, "rb") as handle:
        values.fromfile(handle, expected_count)

    if len(values) != expected_count:
        raise RuntimeError(f"input voxel count mismatch: {len(values)} != {expected_count}")

    finite_values = [value for value in values if math.isfinite(value)]
    if not finite_values:
        raise RuntimeError("input volume has no finite voxels")

    mean = sum(finite_values) / len(finite_values)
    variance = sum((value - mean) * (value - mean) for value in finite_values) / len(finite_values)
    threshold = mean + 1.5 * math.sqrt(max(variance, 0.0))

    labels = bytearray(expected_count)
    hit_count = 0
    for index, value in enumerate(values):
        if math.isfinite(value) and value >= threshold:
            labels[index] = 1
            hit_count += 1

    with open(output_path, "wb") as handle:
        handle.write(labels)

    result = {
        "status": "ok",
        "backend": "mock-threshold",
        "dimensions": dimensions,
        "threshold": threshold,
        "labels": {
            "0": "background",
            "1": "threshold smoke-test region",
        },
        "labelVoxelCounts": {
            "1": hit_count,
        },
        "message": "Development smoke-test only; not diagnostic.",
    }
    if result_path:
        with open(result_path, "w", encoding="utf-8") as handle:
            json.dump(result, handle, indent=2, sort_keys=True)
            handle.write("\n")

    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
