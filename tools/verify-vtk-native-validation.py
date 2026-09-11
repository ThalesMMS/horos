#!/usr/bin/env python3
"""Verify local synthetic snapshots described in docs/vtk-native-validation.md.

This checks captured data, not event delivery or the visible UI. Run the native
gestures and inspect their screenshots separately. No patient data is needed.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import struct


def require(condition, message):
    if not condition:
        raise ValueError(message)


def close(a, b):
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(close(x, y) for x, y in zip(a, b))
    return math.isclose(float(a), float(b), rel_tol=0, abs_tol=1e-6)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    root = parser.parse_args().directory
    report = {}
    baseline = [x + 2*y + 3*z for z in range(16)
                for y in range(32) for x in range(32)]
    full_bounds = [0, 108.5, 0, 108.5, 0, 52.5]
    normals = [[1, 0, 0], [-1, 0, 0], [0, 1, 0],
               [0, -1, 0], [0, 0, 1], [0, 0, -1]]

    def pixels(label):
        data = (root / (label + ".f32")).read_bytes()
        require(len(data) == 65536, f"{label}: incomplete volume")
        return list(struct.unpack("<16384f", data))

    def state(label, scale, unchanged_volume=True):
        value = json.loads((root / (label + ".json")).read_text())
        require(value["backingScale"] == scale, f"{label}: backing scale")
        planes = value["planes"]
        require(len(planes) == 6 and all(len(p) == 6 for p in planes),
                f"{label}: six planes required")
        require(all(math.isfinite(x) for p in planes for x in p),
                f"{label}: nonfinite plane")
        require(close([p[3:] for p in planes], normals),
                f"{label}: unexpected rotation of the box")
        if unchanged_volume:
            require(pixels(label) == baseline, f"{label}: volume changed")
        return value

    def same_camera(a, b):
        for key in ("position", "focalPoint", "viewUp", "parallelScale",
                    "viewAngle", "eyeAngle"):
            require(a[key] == b[key], f"camera changed: {key}")

    def bounds(s):
        return [p[i // 2] for i, p in enumerate(s["planes"])]

    def inward(a, b, label):
        same_camera(a, b)
        require(all(y > x if i % 2 == 0 else y < x
                    for i, (x, y) in enumerate(zip(bounds(a), bounds(b)))),
                f"{label}: not all six faces moved inward")

    for scale in (1, 2):
        prefix = f"scissors-{scale}x-"
        original = state(prefix + "before", scale)
        expected = baseline.copy()
        for quadrant, xr, zr in (("nw", (3, 10), (10, 13)),
                                 ("ne", (21, 28), (10, 13)),
                                 ("sw", (3, 10), (2, 5)),
                                 ("se", (21, 28), (2, 5))):
            current = state(prefix + quadrant, scale, False)
            same_camera(original, current)
            require(close(original["planes"], current["planes"]),
                    "scissors changed cropping planes")
            for z in range(zr[0], zr[1] + 1):
                for y in range(32):
                    for x in range(xr[0], xr[1] + 1):
                        expected[(z * 32 + y) * 32 + x] = 0
            require(pixels(prefix + quadrant) == expected,
                    f"{prefix + quadrant}: wrong voxels or outside edits")
        restored = state(prefix + "restored", scale)
        same_camera(original, restored)
        report[f"scissors_{scale}x"] = "four disjoint 1024-voxel cuts; exact revert"

        prefix = f"crop-{scale}x-"
        xz, xyz = state(prefix + "xz", scale), state(prefix + "xyz", scale)
        require(close([bounds(xz)[i] for i in (2, 3)], [0, 108.5]),
                "coronal drag changed Y faces")
        require(close([bounds(xz)[i] for i in (0, 1, 4, 5)],
                      [bounds(xyz)[i] for i in (0, 1, 4, 5)]),
                "sagittal drag changed X/Z faces")
        require(all(0 < bounds(xyz)[i] < bounds(xyz)[i+1] < full_bounds[i+1]
                    for i in (0, 2, 4)), "orthogonal faces did not all move")

        suffix = "oblique-full-" if scale == 1 else "oblique-"
        before = state(prefix + suffix + "before", scale)
        after = state(prefix + suffix + "all", scale)
        if scale == 2:
            require(close(xyz["planes"], before["planes"]),
                    "camera rotation changed clipping planes")
        else:
            require(close(bounds(before), full_bounds), "expected fresh box")
        inward(before, after, prefix + suffix)
        center_label = prefix + (suffix + "center" if scale == 1 else "center")
        center, off = state(center_label, scale), state(prefix + "off", scale)
        same_camera(after, center)
        delta = [y - x for x, y in zip(after["planes"][0][:3],
                                      center["planes"][0][:3])]
        require(sum(x*x for x in delta) > 1, "center did not translate")
        require(all(close([y-x for x, y in zip(a[:3], b[:3])], delta)
                    for a, b in zip(after["planes"], center["planes"])),
                "center did not translate all six planes equally")
        same_camera(center, off)
        require(close(center["planes"], off["planes"]),
                "hiding handles changed the retained crop")
        report[f"crop_{scale}x"] = {"faces": 6, "oblique_faces": 6,
                                    "center_translation": delta}

        small = state(prefix + "small-before", scale)
        moved = state(prefix + "small-after", scale)
        same_camera(small, moved)
        require(close(bounds(small), full_bounds), "small: expected fresh box")
        require(bounds(moved)[3] > 108.5, "small Y+ handle was missed")
        require(close([bounds(moved)[i] for i in (0, 1, 2, 4, 5)],
                      [full_bounds[i] for i in (0, 1, 2, 4, 5)]),
                "small handle changed another bound")
        view_numbers = re.findall(r"[\d.]+", small["viewBounds"])
        height = float(view_numbers[3]) * scale
        diameter = .015 * math.sqrt(2*108.5**2 + 52.5**2) * height / (
            2 * float(small["parallelScale"]))
        require(3 < diameter < 4, "small handle is not 3–4 backing pixels")
        report[f"small_{scale}x_diameter_pixels"] = diameter

    hashes = json.loads((root / "fixture-hashes.json").read_text())
    require(len(hashes) == 16, "expected 16 source DICOMs")
    for name, digest in hashes.items():
        require(Path(name).name == name, "fixture hash must use a basename")
        source = root / "fixture-axial" / name
        require(hashlib.sha256(source.read_bytes()).hexdigest() == digest,
                "original synthetic fixture changed")
    report["original_dicoms_preserved"] = len(hashes)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
