#!/usr/bin/env python3
"""NIfTI_Library is the pinned upstream revision, unmodified, and still fits Horos (#631).

Offline checks of the vendored copy:

- every file in NIfTI_Library/UPSTREAM.json has the recorded size, SHA-256 and
  git blob SHA-1, and the folder holds nothing else but the manifest and its
  README - so a local edit, a stray file or a missing header fails here;
- the Horos target compiles nifti1_io.c and znzlib.c, references every header,
  and no project setting defines HAVE_ZLIB (this update does not add .nii.gz);
- the structures Horos reads - nifti_1_header, nifti_image, nifti1_extension,
  mat44 - keep the layout of the library they replaced (compared against the
  headers at efb2b0cef when git has that revision);
- the calls DCMPix.m and DicomFile.mm make compile against these headers as C,
  Objective-C and Objective-C++, with the types those callers assume.

The manifest's hashes were compared with upstream's own git tree when it was
written (NIfTI_Library/README.horos.md); this test needs no network.
"""
import hashlib
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
library = root / "NIfTI_Library"
failures = []

manifest = json.loads((library / "UPSTREAM.json").read_text())
if manifest.get("revision") != "8f72d1165aa62320cc6982d6ddd71a7f6b9924c5":
    failures.append(f"UPSTREAM.json pins {manifest.get('revision')}")
for name, entry in manifest["files"].items():
    path = library / name
    if not path.is_file():
        failures.append(f"{name} is missing")
        continue
    data = path.read_bytes()
    if len(data) != entry["size"]:
        failures.append(f"{name} is {len(data)} bytes, upstream's is {entry['size']}")
    if hashlib.sha256(data).hexdigest() != entry["sha256"]:
        failures.append(f"{name} differs from upstream (SHA-256)")
    blob = hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()
    if blob != entry["git_blob_sha1"]:
        failures.append(f"{name} differs from upstream's git blob")
present = {p.name for p in library.iterdir() if p.is_file() and p.name != ".DS_Store"}
extra = present - set(manifest["files"]) - {"UPSTREAM.json", "README.horos.md"}
if extra:
    failures.append(f"files in NIfTI_Library that are not upstream's: {sorted(extra)}")

project = (root / "Horos.xcodeproj/project.pbxproj").read_bytes().decode("latin-1")
for name in ("nifti1_io.c", "znzlib.c"):
    if not re.search(r"/\* %s in Sources \*/ = \{isa = PBXBuildFile" % re.escape(name), project):
        failures.append(f"the project no longer compiles {name}")
for name in ("nifti1.h", "nifti1_io.h", "znzlib.h", "nifti1_io_version.h", "znzlib_version.h"):
    if not re.search(r"isa = PBXFileReference;[^}]*path = %s;" % re.escape(name), project):
        failures.append(f"the project does not reference {name}")
if "HAVE_ZLIB" in project or any("HAVE_ZLIB" in p.read_text(errors="replace") for p in root.glob("*.xcconfig")):
    failures.append("HAVE_ZLIB is defined: .nii.gz reading is not part of this library update")

for failure in failures:
    print("FAIL:", failure)
reported = len(failures)

if subprocess.run(["xcrun", "--find", "clang"], capture_output=True).returncode != 0:
    print("skipped: needs clang for the layout and API checks", file=sys.stderr)
    raise SystemExit(1 if failures else 2)

LAYOUT = r'''
#include <stddef.h>
#include <stdio.h>
#include "nifti1_io.h"
#define F(type, field) printf("%s.%s %zu %zu\n", #type, #field, offsetof(type, field), sizeof(((type *)0)->field))
int main(void) {
    printf("nifti_1_header %zu\nnifti_image %zu\nnifti1_extension %zu\nmat44 %zu\n",
           sizeof(nifti_1_header), sizeof(nifti_image), sizeof(nifti1_extension), sizeof(mat44));
    F(nifti_1_header, sizeof_hdr); F(nifti_1_header, dim); F(nifti_1_header, datatype); F(nifti_1_header, pixdim);
    F(nifti_1_header, vox_offset); F(nifti_1_header, scl_slope); F(nifti_1_header, qform_code);
    F(nifti_1_header, sform_code); F(nifti_1_header, magic);
    F(nifti_image, dim); F(nifti_image, nvox); F(nifti_image, nbyper); F(nifti_image, datatype);
    F(nifti_image, qto_xyz); F(nifti_image, sto_xyz); F(nifti_image, data); F(nifti_image, num_ext);
    F(nifti_image, ext_list); F(nifti_image, scl_slope); F(nifti_image, iname_offset);
    F(nifti1_extension, esize); F(nifti1_extension, ecode); F(nifti1_extension, edata);
    return 0;
}
'''

# What the two callers use, with the types they assume.
CALLERS = r'''
#include "nifti1.h"
#include "nifti1_io.h"
static int horos_nifti_calls(const char *path) {
    struct nifti_1_header *header = (nifti_1_header *) nifti_read_header(path, 0, 0);
    int isNIfTI = header && header->magic[0] == 'n' && (header->magic[1] == 'i' || header->magic[1] == '+');
    short width = header ? header->dim[1] : 0; float spacing = header ? header->pixdim[3] : 0;
    short qform = header ? header->qform_code : 0, sform = header ? header->sform_code : 0, type = header ? header->datatype : 0;
    float offset = header ? header->vox_offset : 0;
    int bytesPerVoxel = 0, swapSize = 0;
    nifti_datatype_sizes(type, &bytesPerVoxel, &swapSize);
    nifti_image *image = nifti_image_read(path, 1);
    int icod = 0, jcod = 0, kcod = 0;
    if (image) {
        nifti_mat44_to_orientation(image->qto_xyz, &icod, &jcod, &kcod);
        nifti_mat44_to_orientation(image->sto_xyz, &icod, &jcod, &kcod);
        void *voxels = image->data;
        size_t bytes = image->nvox * image->nbyper;
        (void)voxels; (void)bytes;
    }
    char *ascii = image ? nifti_image_to_ascii(image) : 0;
    if (image && image->num_ext > 0 && image->ext_list) {
        nifti1_extension *extension = image->ext_list;
        int code = extension->ecode, size = extension->esize; char *text = extension->edata;
        (void)code; (void)size; (void)text;
    }
    free(ascii);
    nifti_image_free(image);
    free(header);
    return isNIfTI + width + (int)spacing + qform + sform + (int)offset + icod + jcod + kcod + NIFTI_L2R + NIFTI_S2I;
}
int main(int argc, char **argv) { return argc > 1 ? horos_nifti_calls(argv[1]) : 0; }
'''

with tempfile.TemporaryDirectory(prefix="horos-nifti-upstream-") as temporary:
    work = Path(temporary)
    layouts = {}
    sources = {"current": library}
    baseline = work / "efb2b0cef"
    baseline.mkdir()
    for name in ("nifti1.h", "nifti1_io.h", "znzlib.h"):
        shown = subprocess.run(["git", "-C", str(root), "show", f"efb2b0cef:NIfTI_Library/{name}"], capture_output=True)
        if shown.returncode != 0:
            baseline = None
            print("note: git has no efb2b0cef here; the layout is not compared with the replaced library")
            break
        (baseline / name).write_bytes(shown.stdout)
    if baseline:
        sources["efb2b0cef"] = baseline
    (work / "layout.c").write_text(LAYOUT)
    for label, folder in sources.items():
        binary = work / f"layout-{label}"
        built = subprocess.run(["xcrun", "clang", "-std=c11", "-I", str(folder), str(work / "layout.c"), "-o", str(binary)],
                               capture_output=True, text=True)
        if built.returncode != 0:
            failures.append(f"the layout probe does not compile against the {label} headers: {built.stderr[-600:]}")
            continue
        layouts[label] = subprocess.run([str(binary)], capture_output=True, text=True, check=True).stdout
    if len(layouts) == 2 and layouts["current"] != layouts["efb2b0cef"]:
        old, new = layouts["efb2b0cef"].splitlines(), layouts["current"].splitlines()
        changed = [f"{a} -> {b}" for a, b in zip(old, new) if a != b]
        failures.append(f"the structures Horos reads changed layout: {changed[:6]}")

    for language, suffix, extra in (("c", "c", ["-std=c11"]), ("objective-c", "m", ["-fobjc-arc"]),
                                    ("objective-c++", "mm", ["-std=c++17"])):
        source = work / f"callers.{suffix}"
        source.write_text(CALLERS)
        compiled = subprocess.run(["xcrun", "clang", "-x", language, *extra, "-fsyntax-only", "-Werror",
                                   "-Wincompatible-pointer-types", "-Wint-conversion", "-I", str(library), str(source)],
                                  capture_output=True, text=True)
        if compiled.returncode != 0:
            failures.append(f"Horos's NIfTI calls do not compile as {language}: {compiled.stderr.strip()[-800:]}")
    # The target's C settings (it does not treat warnings as errors): the library
    # and the calls link into one program, with no symbol missing.
    compiled = subprocess.run(["xcrun", "clang", "-std=c11", "-O3", "-ffast-math", "-fvisibility=default",
                               "-Wno-unused-variable", "-I", str(library), str(work / "callers.c"),
                               str(library / "nifti1_io.c"), str(library / "znzlib.c"), "-o", str(work / "callers")],
                              capture_output=True, text=True)
    if compiled.returncode != 0:
        failures.append(f"the library does not build and link with the target's settings: {compiled.stderr.strip()[-800:]}")

for failure in failures[reported:]:
    print("FAIL:", failure)
if failures:
    raise SystemExit(1)
print(f"ok: NIfTI_Library is nifti_clib {manifest['revision'][:12]}, unmodified; layouts "
      f"{'match the replaced library' if 'efb2b0cef' in sources else 'not compared'}; the callers' API compiles")
