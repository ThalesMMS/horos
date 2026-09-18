#!/usr/bin/env python3
"""The NIfTI-1 I/O library against the #631 matrix, one revision at a time.

Each revision's NIfTI_Library/nifti1_io.c and znzlib.c are compiled with the
settings the Horos target applies to them (-std=c11 -O3 -ffast-math, no zlib)
into a dylib, and tools/probe-nifti-library.c reports what that build reads from
every file of tools/generate-nifti-matrix.py. The expectations come from the
generator, not from either build:

  valid cases   the header's dimensions, spacing, datatype and magic; the image
                loads, holds prod(dim) voxels and every sampled voxel's value
                (native byte order, unscaled); scl_slope and scl_inter as
                written; the orientation codes of the form the case sets; the
                extension codes the file carries
  bad cases     an impossible header: nifti_image_read with data refuses the file;
                voxels missing: the header still says how many bytes are needed and
                where (nifti_image_read does not refuse such a file - the callers
                compare it with the file size)

    python3 tools/check-nifti-library.py --revision efb2b0cef --revision WORKTREE \\
        [--matrix <dir>] [--out result.json]

WORKTREE is the checkout as it is. Prints one line per disagreement and a table
of where the revisions differ. Exit 0 when the last revision given meets every
expectation, 1 otherwise, 2 when numpy or clang is missing.
"""
import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CODES = {"L2R": 1, "R2L": 2, "P2A": 3, "A2P": 4, "I2S": 5, "S2I": 6}
MAGIC = {"nii": "n+1", "ni1": "ni1", "analyze": ""}
SOURCES = ("nifti1_io.c", "znzlib.c")
HEADERS = ("nifti1.h", "nifti1_io.h", "znzlib.h", "nifti1_io_version.h", "znzlib_version.h")
FLAGS = ["-std=c11", "-O3", "-ffast-math", "-fvisibility=default", "-fno-common", "-DNDEBUG",
         "-Wno-unused-variable", "-arch", "arm64", "-mmacosx-version-min=26.0"]


def build(revision, work):
    folder = work / revision.replace("/", "_")
    folder.mkdir(parents=True)
    for name in SOURCES + HEADERS:
        if revision == "WORKTREE":
            source = ROOT / "NIfTI_Library" / name
            if source.exists():
                (folder / name).write_bytes(source.read_bytes())
        else:
            shown = subprocess.run(["git", "-C", str(ROOT), "show", f"{revision}:NIfTI_Library/{name}"],
                                   capture_output=True)
            if shown.returncode == 0:
                (folder / name).write_bytes(shown.stdout)
    dylib = work / f"libnifti-{folder.name}.dylib"
    subprocess.run(["xcrun", "clang", "-dynamiclib", *FLAGS, "-I", str(folder), *(str(folder / s) for s in SOURCES),
                    "-install_name", f"@rpath/{dylib.name}", "-o", str(dylib)], check=True, capture_output=True)
    return dylib


def close(a, b):
    if a is None or b is None:
        return False
    return abs(float(a) - float(b)) <= 1e-4 * max(1.0, abs(float(b)))


def judge(name, case, report):
    problems = []
    loaded = report["loaded"]
    if not case["valid"]:
        if case["defect_kind"] == "invalid-header":
            if loaded is not None:
                problems.append(f"loads although {case['defect']}")
            return problems
        # Short data: nifti_image_read does not refuse it. nifti_read_buffer answers
        # a short read with (size_t)-1, which nifti_image_load's `ii < ntot` then
        # takes for success, and the missing voxels stay zero - in 1.43 and in
        # 2.1.0. What the callers need instead is a header that says truthfully
        # where the voxels are, so they can see that the file does not hold them.
        image = report["image"]
        if image is None:
            return [f"the header cannot be read, so a caller cannot see that {case['defect']}"]
        if image["nvox"] * image["nbyper"] != case["data_bytes"] or max(image["iname_offset"], 0) != case["data_offset"]:
            problems.append(f"the header places {image['nvox'] * image['nbyper']} bytes at {image['iname_offset']}, "
                            f"not {case['data_bytes']} at {case['data_offset']}")
        return problems
    header = report["header"]
    nx, ny, nz = case["dims"]
    if header is None:
        return ["nifti_read_header refused it"]
    if header["dim"][1:4] != [nx, ny, nz]:
        problems.append(f"header dim {header['dim'][1:4]}")
    if not all(close(a, b) for a, b in zip(header["pixdim"][1:4], case["spacing"])):
        problems.append(f"header pixdim {header['pixdim'][1:4]}")
    if header["datatype"] != case["datatype_code"]:
        problems.append(f"header datatype {header['datatype']}")
    if header["magic"] != MAGIC[case["format"]]:
        problems.append(f"magic {header['magic']!r}")
    if loaded is None:
        return problems + ["nifti_image_read refused the data"]
    if loaded["nvox"] != nx * ny * nz * case["volumes"]:
        problems.append(f"nvox {loaded['nvox']}")
    if case["volumes"] > 1 and loaded["dim"][4] != case["volumes"]:
        problems.append(f"dim[4] {loaded['dim'][4]}")
    data = loaded["data"]
    for k, i, j, value in case["samples"]:
        got = data[i + nx * (j + ny * k)]
        if not close(got, value):
            problems.append(f"voxel ({i}, {j}, {k}) = {got}, expected {value}")
            break
    if case["format"] != "analyze":
        if not (close(loaded["scl_slope"], case["scl_slope"]) or (case["scl_slope"] == 1.0 and loaded["scl_slope"] == 0)):
            problems.append(f"scl_slope {loaded['scl_slope']}")
        if case["scl_slope"] != 1.0 and not close(loaded["scl_inter"], case["scl_inter"]):
            problems.append(f"scl_inter {loaded['scl_inter']}")
    if case["transform"] in ("qform", "sform"):
        codes = loaded["orientation_q" if case["transform"] == "qform" else "orientation_s"]
        if codes != [CODES[c] for c in case["orientation_codes"]]:
            problems.append(f"{case['transform']} orientation {codes}, expected {case['orientation_codes']}")
    ecodes = [e["ecode"] for e in loaded["extensions"]]
    if ecodes != case["extensions"]:
        problems.append(f"extension codes {ecodes}, expected {case['extensions']}")
    for e in loaded["extensions"]:
        text = case.get("extension_texts", {}).get(str(e["ecode"]))
        if text is not None and e["text"] != text:
            problems.append(f"extension {e['ecode']} reads {e['text']!r}")
    return problems


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--revision", action="append", required=True)
    parser.add_argument("--matrix", type=Path)
    parser.add_argument("--out", type=Path)
    arguments = parser.parse_args()
    try:
        import numpy  # noqa: F401  (the generator needs it)
    except ImportError:
        print("skipped: the matrix generator needs numpy")
        return 2
    if subprocess.run(["xcrun", "--find", "clang"], capture_output=True).returncode != 0:
        print("skipped: needs clang")
        return 2
    with tempfile.TemporaryDirectory(prefix="horos-nifti-library-") as temporary:
        work = Path(temporary)
        matrix = arguments.matrix
        if matrix is None:
            matrix = work / "matrix"
            subprocess.run([sys.executable, str(ROOT / "tools/generate-nifti-matrix.py"), str(matrix)],
                           check=True, capture_output=True)
        expected = json.loads((matrix / "expected.json").read_text())
        probe = work / "probe-nifti-library"
        subprocess.run(["xcrun", "clang", "-O2", "-I", str(ROOT / "NIfTI_Library"), str(ROOT / "tools/probe-nifti-library.c"),
                        "-o", str(probe)], check=True)
        names = sorted(expected["cases"])
        results = {}
        for revision in arguments.revision:
            dylib = build(revision, work)
            files = [str(matrix / name / expected["cases"][name]["header_file"]) for name in names]
            dumped = subprocess.run([str(probe), "dump", str(dylib), *files], capture_output=True, text=True)
            if dumped.returncode != 0:
                print(dumped.stderr[-2000:])
                return 1
            reports = [json.loads(line) for line in dumped.stdout.splitlines() if line.startswith("{")]
            results[revision] = {name: {"problems": judge(name, expected["cases"][name], report),
                                        "report": {k: v for k, v in report.items() if k != "loaded"} |
                                                  {"loaded": None if report["loaded"] is None else
                                                   {k: v for k, v in report["loaded"].items() if k != "data"}}}
                                 for name, report in zip(names, reports)}
    width = max(len(n) for n in names)
    print(f"{'case':<{width}}  " + "  ".join(f"{r[:12]:<12}" for r in arguments.revision))
    for name in names:
        cells = ["ok" if not results[r][name]["problems"] else f"{len(results[r][name]['problems'])} problem(s)"
                 for r in arguments.revision]
        print(f"{name:<{width}}  " + "  ".join(f"{c:<12}" for c in cells))
    for revision in arguments.revision:
        for name in names:
            for problem in results[revision][name]["problems"]:
                print(f"{revision[:12]} {name}: {problem}")
    if arguments.out:
        arguments.out.parent.mkdir(parents=True, exist_ok=True)
        arguments.out.write_text(json.dumps({"revisions": arguments.revision, "matrix": str(matrix),
                                             "flags": FLAGS, "results": results}, indent=1) + "\n")
    last = results[arguments.revision[-1]]
    return 0 if all(not v["problems"] for v in last.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
