#!/usr/bin/env python3
"""NIfTI-1 and Analyze 7.5 files whose every field and voxel is known (#631).

Like tools/generate-nifti-fixture.py, the headers are packed field by field with
`struct` - no NIfTI library writes them - so the expectations in expected.json
come from the format and from the numbers chosen here, not from the reader
under test. Each case is a folder holding its file or pair:

    nii-<type>          .nii (n+1), little-endian, qform axial; the datatypes
                        Horos reads: uint8, int8, int16, int32, float32, float64
    nii-<type>-be       the same, big-endian (header and voxels)
    nii-sform-sagittal  sform only, slices stacked left to right
    nii-qform-coronal   qform only, slices stacked anterior to posterior
    nii-no-transform    qform_code and sform_code 0 (#527)
    nii-scaled          scl_slope 2.5, scl_inter -100
    nii-extensions      a comment (ecode 6) and a MATLAB (ecode 40) extension
    nii-4d              dim[0] 4, three volumes
    pair-ni1 / -352 / -be   two-file NIfTI: .hdr of 348 or 352 bytes, and .img
    analyze / analyze-be    Analyze 7.5 .hdr (no magic) and .img
    bad-*               truncated voxels, header only, impossible sizeof_hdr and
                        dim[0], datatype 0, empty file, random bytes, short .img;
                        defect_kind says which: "short-data" (a readable header whose
                        voxels are not all there: data_file, data_offset and
                        data_bytes say where they should be) or "invalid-header"

Every valid volume is 20 x 12 x 7 (not square, so rows and columns cannot be
confused) at 0.6 x 0.9 x 3.5 mm (no two spacings alike), and voxel (i, j, k)
holds a value built from i, j and k, so a wrong offset, a swapped axis or
unswapped bytes shows up as a number. expected.json lists, per case, the header
fields, the voxel formula's samples, the orientation codes the affine implies,
and whether the file is valid.

    python3 tools/generate-nifti-matrix.py <empty dir>
"""
import argparse
import json
import math
import random
import struct
from pathlib import Path

import numpy

parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument("destination", type=Path)
parser.add_argument("--size", default="20,12,7", help="columns,rows,slices")
parser.add_argument("--only", action="append", help="generate only these cases")
parser.add_argument("--same-names", action="store_true",
                    help="every case's files named volume.* (#641: files of one name in different folders)")
arguments = parser.parse_args()

destination = arguments.destination
destination.mkdir(parents=True, exist_ok=True)
if any(destination.iterdir()):
    raise SystemExit(f"{destination} is not empty")
NX, NY, NZ = (int(v) for v in arguments.size.split(","))
SPACING = (0.6, 0.9, 3.5)
OFFSET = (-6.0, -5.4, 10.0)

DATATYPES = {  # name: (code, bitpix, numpy dtype, voxel formula)
    "uint8": (2, 8, "u1", lambda i, j, k, t: 20 * k + 3 * j + i),
    "int8": (256, 8, "i1", lambda i, j, k, t: 10 * k + 2 * j + i - 60),
    "int16": (4, 16, "i2", lambda i, j, k, t: 1000 * (k + 1) + 300 * t + 5 * j + i),
    "int32": (8, 32, "i4", lambda i, j, k, t: -20000 + 1000 * k + 10 * j + i),
    "float32": (16, 32, "f4", lambda i, j, k, t: k + 0.25 * j + 0.01 * i - 3.5),
    "float64": (64, 64, "f8", lambda i, j, k, t: k + 0.25 * j + 0.001 * i - 3.5),
    # Past what a short holds (#643): unsigned above 32767, int32 below -32768.
    "uint16": (512, 16, "u2", lambda i, j, k, t: 40000 + 1000 * k + 10 * j + i),
    "uint32": (768, 32, "u4", lambda i, j, k, t: 100000 + 10000 * k + 100 * j + i),
    "int32wide": (8, 32, "i4", lambda i, j, k, t: -200000 + 50000 * k + 100 * j + i),
    # Three bytes a voxel (#643); a sample is red x 65536 + green x 256 + blue.
    "rgb24": (128, 24, "u1", lambda i, j, k, t: ((20 * k + i) % 256) * 65536 + ((3 * j + 40) % 256) * 256 + (100 + 7 * k) % 256),
}
# NIfTI orientation codes (nifti1_io.h): the direction an index axis runs in
# RAS+ world coordinates.
CODES = {(0, 1): "L2R", (0, -1): "R2L", (1, 1): "P2A", (1, -1): "A2P", (2, 1): "I2S", (2, -1): "S2I"}
ROTATIONS = {  # columns: where i, j and k point
    "axial": ((1, 0, 0), (0, 1, 0), (0, 0, 1)),
    "sagittal": ((0, 1, 0), (0, 0, 1), (1, 0, 0)),
    "coronal": ((1, 0, 0), (0, 0, 1), (0, -1, 0)),
}


def axis_codes(columns):
    codes = []
    for column in columns:
        axis = max(range(3), key=lambda a: abs(column[a]))
        codes.append(CODES[(axis, 1 if column[axis] > 0 else -1)])
    return codes


def quaternion(columns):
    """nifti_mat44_to_quatern for a proper rotation, from the NIfTI-1 standard."""
    r = [[columns[c][r] for c in range(3)] for r in range(3)]  # r[row][column]
    a = r[0][0] + r[1][1] + r[2][2] + 1.0
    if a > 0.5:
        a = 0.5 * math.sqrt(a)
        b = 0.25 * (r[2][1] - r[1][2]) / a
        c = 0.25 * (r[0][2] - r[2][0]) / a
        d = 0.25 * (r[1][0] - r[0][1]) / a
    else:
        xd = 1.0 + r[0][0] - (r[1][1] + r[2][2])
        yd = 1.0 + r[1][1] - (r[0][0] + r[2][2])
        zd = 1.0 + r[2][2] - (r[0][0] + r[1][1])
        if xd > 1.0:
            b = 0.5 * math.sqrt(xd); c = 0.25 * (r[0][1] + r[1][0]) / b
            d = 0.25 * (r[0][2] + r[2][0]) / b; a = 0.25 * (r[2][1] - r[1][2]) / b
        elif yd > 1.0:
            c = 0.5 * math.sqrt(yd); b = 0.25 * (r[0][1] + r[1][0]) / c
            d = 0.25 * (r[1][2] + r[2][1]) / c; a = 0.25 * (r[0][2] - r[2][0]) / c
        else:
            d = 0.5 * math.sqrt(zd); b = 0.25 * (r[0][2] + r[2][0]) / d
            c = 0.25 * (r[1][2] + r[2][1]) / d; a = 0.25 * (r[1][0] - r[0][1]) / d
        if a < 0:
            b, c, d = -b, -c, -d
    return b, c, d


def volume(name, dims, volumes=1):
    code, bitpix, dtype, formula = DATATYPES[name]
    nx, ny, nz = dims
    t, k, j, i = numpy.meshgrid(numpy.arange(volumes), numpy.arange(nz), numpy.arange(ny), numpy.arange(nx), indexing="ij")
    values = formula(i, j, k, t)
    if name == "rgb24":
        packed = numpy.asarray(values, dtype=numpy.int64)
        return numpy.stack([(packed >> 16) & 255, (packed >> 8) & 255, packed & 255], axis=-1).astype("u1")
    return numpy.asarray(values, dtype=numpy.float64).astype(dtype)


def samples(name, dims, volumes=1):
    nx, ny, nz = dims
    formula = DATATYPES[name][3]
    dtype = numpy.dtype(DATATYPES[name][2])
    points = [(0, 0), (nx - 1, 0), (0, ny - 1), (nx - 1, ny - 1), (nx // 2, ny // 3), (1, 2)]
    out = []
    for k in range(nz):
        for (i, j) in points:
            if name == "rgb24":
                out.append([k, i, j, float(formula(i, j, k, 0))])
                continue
            value = numpy.array([formula(i, j, k, 0)], dtype=numpy.float64).astype(dtype)[0]
            out.append([k, i, j, float(value)])
    return out


def nifti_header(*, datatype, dims, endian="<", magic=b"n+1\0", vox_offset=352.0, qform=None, sform=None,
                 scl=(1.0, 0.0), dim0=None, volumes=1, sizeof_hdr=348, dim0_raw=None, descrip=b"horos #631 synthetic"):
    code, bitpix = DATATYPES[datatype][:2] if isinstance(datatype, str) else (datatype, 16)
    header = bytearray(348)
    put = lambda offset, form, *values: struct.pack_into(endian + form, header, offset, *values)
    nx, ny, nz = dims
    ndim = dim0 if dim0 is not None else (4 if volumes > 1 else 3)
    put(0, "i", sizeof_hdr)
    put(38, "c", b"r")
    put(40, "8h", dim0_raw if dim0_raw is not None else ndim, nx, ny, nz, volumes, 1, 1, 1)
    put(70, "h", code)
    put(72, "h", bitpix)
    put(76, "8f", 1.0, *SPACING, 1.0 if volumes > 1 else 0.0, 0, 0, 0)
    put(108, "f", vox_offset)
    put(112, "2f", *scl)
    put(123, "B", 2 | 8)  # mm, s
    put(148, "80s", descrip)
    qcode, scode = (1 if qform else 0), (1 if sform else 0)
    put(252, "2h", qcode, scode)
    if qform:
        put(256, "3f", *quaternion(ROTATIONS[qform]))
        put(268, "3f", *OFFSET)
    if sform:
        columns = ROTATIONS[sform]
        for row, offset in enumerate((280, 296, 312)):
            put(offset, "4f", *(columns[c][row] * SPACING[c] for c in range(3)), OFFSET[row])
    header[344:348] = magic
    return bytes(header)


def analyze_header(*, datatype, dims, endian="<"):
    code, bitpix = DATATYPES[datatype][:2]
    header = bytearray(348)
    put = lambda offset, form, *values: struct.pack_into(endian + form, header, offset, *values)
    nx, ny, nz = dims
    put(0, "i", 348)
    put(14, "18s", b"SYNTH_ANALYZE")
    put(32, "i", 16384)
    put(38, "c", b"r")
    put(40, "8h", 4, nx, ny, nz, 1, 0, 0, 0)
    put(56, "4s", b"mm")
    put(70, "h", code)
    put(72, "h", bitpix)
    put(76, "8f", 0.0, *SPACING, 0, 0, 0, 0)
    put(148, "80s", b"horos #631 synthetic analyze")
    put(293, "10s", b"20260916")
    return bytes(header)


def extensions_block(entries, endian="<"):
    block = bytearray(struct.pack("4B", 1, 0, 0, 0))
    for ecode, text in entries:
        data = text.encode() + b"\0"
        esize = 8 + len(data)
        esize += (-esize) % 16
        block += struct.pack(endian + "2i", esize, ecode) + data + b"\0" * (esize - 8 - len(data))
    return bytes(block)


expected = {"generator": "tools/generate-nifti-matrix.py", "dims": [NX, NY, NZ], "spacing": list(SPACING),
            "orientation_codes": "NIfTI-1: the RAS+ direction each index axis runs", "cases": {}}


def write_case(name, files, **info):
    if arguments.only and name not in arguments.only:
        return
    folder = destination / name
    folder.mkdir()
    # Each case's files carry its name: the app names a NIfTI series after its file alone (#641),
    # so cases named alike would become one series once imported without copying.
    def own(filename):
        if arguments.same_names:
            return filename
        return name + filename[len("volume"):] if filename.startswith("volume.") else filename
    files = {own(filename): data for filename, data in files.items()}
    for key in ("header_file", "pixel_source", "data_file"):
        if key in info:
            info[key] = own(info[key])
    for filename, data in files.items():
        (folder / filename).write_bytes(data)
    info.setdefault("valid", True)
    info["files"] = sorted(files)
    info["sizes"] = {filename: len(data) for filename, data in files.items()}
    expected["cases"][name] = info


def valid_info(datatype, *, format, endian, rotation, transform, volumes=1, extensions=(), scl=(1.0, 0.0),
               header_file, pixel_source):
    code, bitpix = DATATYPES[datatype][:2]
    info = {"format": format, "endian": "big" if endian == ">" else "little", "datatype": datatype,
            "datatype_code": code, "bitpix": bitpix, "dims": [NX, NY, NZ], "volumes": volumes,
            "frames": NZ, "spacing": list(SPACING), "header_file": header_file, "pixel_source": pixel_source,
            "transform": transform, "scl_slope": scl[0], "scl_inter": scl[1],
            "extensions": [code for code, _ in extensions],
            "samples": samples(datatype, (NX, NY, NZ), volumes)}
    if rotation:
        info["rotation"] = rotation
        info["orientation_codes"] = axis_codes(ROTATIONS[rotation])
    return info


dims = (NX, NY, NZ)
for datatype in DATATYPES:
    for endian in ("<", ">"):
        suffix = "-be" if endian == ">" else ""
        data = volume(datatype, dims).astype(numpy.dtype(DATATYPES[datatype][2]).newbyteorder(endian)).tobytes()
        write_case(f"nii-{datatype}{suffix}",
                   {"volume.nii": nifti_header(datatype=datatype, dims=dims, endian=endian, qform="axial") + b"\0" * 4 + data},
                   **valid_info(datatype, format="nii", endian=endian, rotation="axial", transform="qform",
                                header_file="volume.nii", pixel_source="volume.nii"))

int16 = volume("int16", dims).astype("<i2").tobytes()
write_case("nii-sform-sagittal", {"volume.nii": nifti_header(datatype="int16", dims=dims, sform="sagittal") + b"\0" * 4 + int16},
           **valid_info("int16", format="nii", endian="<", rotation="sagittal", transform="sform",
                        header_file="volume.nii", pixel_source="volume.nii"))
write_case("nii-qform-coronal", {"volume.nii": nifti_header(datatype="int16", dims=dims, qform="coronal") + b"\0" * 4 + int16},
           **valid_info("int16", format="nii", endian="<", rotation="coronal", transform="qform",
                        header_file="volume.nii", pixel_source="volume.nii"))
write_case("nii-no-transform", {"volume.nii": nifti_header(datatype="int16", dims=dims) + b"\0" * 4 + int16},
           **valid_info("int16", format="nii", endian="<", rotation=None, transform="none",
                        header_file="volume.nii", pixel_source="volume.nii"))
write_case("nii-scaled", {"volume.nii": nifti_header(datatype="int16", dims=dims, qform="axial", scl=(2.5, -100.0)) + b"\0" * 4 + int16},
           **valid_info("int16", format="nii", endian="<", rotation="axial", transform="qform", scl=(2.5, -100.0),
                        header_file="volume.nii", pixel_source="volume.nii"))
entries = [(6, "horos #631 comment extension"), (40, "horos #631 matlab extension")]
block = extensions_block(entries)
write_case("nii-extensions",
           {"volume.nii": nifti_header(datatype="int16", dims=dims, qform="axial", vox_offset=348.0 + len(block)) + block + int16},
           **valid_info("int16", format="nii", endian="<", rotation="axial", transform="qform", extensions=entries,
                        header_file="volume.nii", pixel_source="volume.nii"),
           extension_texts={str(code): text for code, text in entries})
four_d = volume("int16", dims, volumes=3).astype("<i2").tobytes()
write_case("nii-4d", {"volume.nii": nifti_header(datatype="int16", dims=dims, qform="axial", volumes=3) + b"\0" * 4 + four_d},
           **valid_info("int16", format="nii", endian="<", rotation="axial", transform="qform", volumes=3,
                        header_file="volume.nii", pixel_source="volume.nii"))
write_case("pair-ni1", {"volume.hdr": nifti_header(datatype="int16", dims=dims, magic=b"ni1\0", vox_offset=0.0, qform="axial"),
                        "volume.img": int16},
           **valid_info("int16", format="ni1", endian="<", rotation="axial", transform="qform",
                        header_file="volume.hdr", pixel_source="volume.img"))
write_case("pair-ni1-352", {"volume.hdr": nifti_header(datatype="int16", dims=dims, magic=b"ni1\0", vox_offset=0.0, qform="axial") + b"\0" * 4,
                            "volume.img": int16},
           **valid_info("int16", format="ni1", endian="<", rotation="axial", transform="qform",
                        header_file="volume.hdr", pixel_source="volume.img"))
write_case("pair-ni1-be", {"volume.hdr": nifti_header(datatype="int16", dims=dims, endian=">", magic=b"ni1\0", vox_offset=0.0, qform="axial") + b"\0" * 4,
                           "volume.img": volume("int16", dims).astype(">i2").tobytes()},
           **valid_info("int16", format="ni1", endian=">", rotation="axial", transform="qform",
                        header_file="volume.hdr", pixel_source="volume.img"))
for endian in ("<", ">"):
    suffix = "-be" if endian == ">" else ""
    write_case(f"analyze{suffix}", {"volume.hdr": analyze_header(datatype="int16", dims=dims, endian=endian),
                                    "volume.img": volume("int16", dims).astype(endian + "i2").tobytes()},
               **valid_info("int16", format="analyze", endian=endian, rotation=None, transform="none",
                            header_file="volume.hdr", pixel_source="volume.img"))

good = nifti_header(datatype="int16", dims=dims, qform="axial") + b"\0" * 4
write_case("bad-nii-truncated", {"volume.nii": good + int16[: len(int16) * 3 // 5]}, valid=False, format="nii",
           defect="the voxels stop at 60 %", defect_kind="short-data", header_file="volume.nii",
           data_file="volume.nii", data_offset=352, data_bytes=len(int16))
write_case("bad-nii-header-only", {"volume.nii": good}, valid=False, format="nii", defect="no voxels", defect_kind="short-data",
           header_file="volume.nii", data_file="volume.nii", data_offset=352, data_bytes=len(int16))
write_case("bad-nii-sizeof-hdr", {"volume.nii": nifti_header(datatype="int16", dims=dims, qform="axial", sizeof_hdr=4660, dim0_raw=30583) + b"\0" * 4 + int16},
           valid=False, format="nii", defect="sizeof_hdr 4660 and dim[0] 30583, impossible in either byte order",
           defect_kind="invalid-header", header_file="volume.nii")
write_case("bad-nii-datatype0", {"volume.nii": nifti_header(datatype=0, dims=dims, qform="axial") + b"\0" * 4 + int16},
           valid=False, format="nii", defect="datatype 0 (DT_UNKNOWN)", defect_kind="invalid-header", header_file="volume.nii")
write_case("bad-nii-empty", {"volume.nii": b""}, valid=False, format="nii", defect="an empty file", defect_kind="invalid-header",
           header_file="volume.nii")
generator = random.Random(631)
write_case("bad-nii-random", {"volume.nii": bytes(generator.randrange(256) for _ in range(4096))}, valid=False, format="nii",
           defect="4096 random bytes", defect_kind="invalid-header", header_file="volume.nii")
write_case("bad-pair-ni1-short-img", {"volume.hdr": nifti_header(datatype="int16", dims=dims, magic=b"ni1\0", vox_offset=0.0, qform="axial") + b"\0" * 4,
                                      "volume.img": int16[: len(int16) // 2]},
           valid=False, format="ni1", defect="the .img holds half the voxels", defect_kind="short-data", header_file="volume.hdr",
           data_file="volume.img", data_offset=0, data_bytes=len(int16))
write_case("bad-analyze-short-img", {"volume.hdr": analyze_header(datatype="int16", dims=dims),
                                     "volume.img": int16[: len(int16) // 2]},
           valid=False, format="analyze", defect="the .img holds half the voxels", defect_kind="short-data",
           header_file="volume.hdr", data_file="volume.img", data_offset=0, data_bytes=len(int16))

(destination / "expected.json").write_text(json.dumps(expected, indent=1) + "\n")
print(f"{len(expected['cases'])} cases in {destination}")
