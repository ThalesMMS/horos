#!/usr/bin/env python3
"""Read the #631 matrix with nibabel, a reader that shares no code with Horos.

tools/generate-nifti-matrix.py writes the headers field by field and derives its
expectations from the numbers it chose. This checks those expectations against
an independent implementation of the formats before anything of Horos reads
them: shape, voxel spacing, the raw stored value at every sample, the direction
each index axis runs (from the affine nibabel builds out of qform or sform), and
the extension codes. A bad case has to be refused, or to hold fewer voxels than
its header describes.

    python tools/verify-nifti-matrix.py <matrix dir>

Needs nibabel (5.4.2 was used) and numpy. Exit 0 when every case agrees, 1
otherwise, 2 when nibabel is missing.
"""
import json
import sys
from pathlib import Path

try:
    import nibabel
    import numpy
except ImportError as missing:
    print(f"skipped: needs nibabel and numpy ({missing})")
    raise SystemExit(2)

matrix = Path(sys.argv[1])
expected = json.loads((matrix / "expected.json").read_text())
failures = []
# nibabel names the direction an axis runs towards; NIfTI names where it comes from.
TOWARDS = {"R": "L2R", "L": "R2L", "A": "P2A", "P": "A2P", "S": "I2S", "I": "S2I"}

for name, case in expected["cases"].items():
    path = matrix / name / case["header_file"]
    if not case["valid"]:
        try:
            image = nibabel.load(str(path))
            described = int(numpy.prod(image.shape)) * image.get_data_dtype().itemsize
            data_file = path.with_suffix(".img") if path.suffix == ".hdr" else path
            offset = int(image.header.get("vox_offset", 0)) if data_file == path else 0
            available = data_file.stat().st_size - offset
            if available >= described and image.get_data_dtype().itemsize:
                failures.append(f"{name}: nibabel reads it as whole ({case['defect']})")
        except Exception:
            pass  # refused, as a bad case should be
        continue
    image = nibabel.load(str(path))
    dims = case["dims"]
    shape = tuple(dims) + ((case["volumes"],) if case["volumes"] > 1 else ())
    # Analyze headers usually say four dimensions with a fourth of 1.
    actual = tuple(image.shape)
    while len(actual) > len(shape) and actual[-1] == 1:
        actual = actual[:-1]
    if actual != shape:
        failures.append(f"{name}: shape {image.shape}, expected {shape}")
        continue
    zooms = [round(float(z), 5) for z in image.header.get_zooms()[:3]]
    if zooms != [round(s, 5) for s in case["spacing"]]:
        failures.append(f"{name}: spacing {zooms}, expected {case['spacing']}")
    raw = numpy.asanyarray(image.dataobj.get_unscaled())
    for k, i, j, value in case["samples"]:
        got = raw[(i, j, k) + (0,) * (raw.ndim - 3)]
        if raw.dtype.names:  # RGB24: red x 65536 + green x 256 + blue, as the matrix packs it (#643)
            got = int(got["R"]) * 65536 + int(got["G"]) * 256 + int(got["B"])
        if abs(float(got) - value) > 1e-4 * max(1.0, abs(value)):
            failures.append(f"{name}: voxel ({i}, {j}, {k}) holds {got}, expected {value}")
            break
    if "orientation_codes" in case:
        codes = [TOWARDS[c] for c in nibabel.orientations.aff2axcodes(image.affine)]
        if codes != case["orientation_codes"]:
            failures.append(f"{name}: axes run {codes}, expected {case['orientation_codes']}")
    if case["format"] == "nii":
        form = case["transform"]
        qcode, scode = int(image.header["qform_code"]), int(image.header["sform_code"])
        if (qcode > 0, scode > 0) != (form == "qform", form == "sform"):
            failures.append(f"{name}: qform_code {qcode}, sform_code {scode} for a {form} case")
        # nibabel moves the scaling from the header it loaded into the data proxy.
        slope, inter = float(image.dataobj.slope), float(image.dataobj.inter)
        if case["scl_slope"] != 1.0 and (slope, inter) != (case["scl_slope"], case["scl_inter"]):
            failures.append(f"{name}: scaling {slope}, {inter}")
        codes = [int(extension.get_code()) for extension in image.header.extensions]
        if codes != case["extensions"]:
            failures.append(f"{name}: extension codes {codes}, expected {case['extensions']}")
    endian = "big" if image.header.endianness == ">" else "little"
    if endian != case["endian"]:
        failures.append(f"{name}: {endian}-endian, expected {case['endian']}")

for failure in failures:
    print("FAIL:", failure)
print(f"nibabel {nibabel.__version__}: {len(expected['cases']) - len(failures)} of {len(expected['cases'])} cases as expected")
raise SystemExit(1 if failures else 0)
