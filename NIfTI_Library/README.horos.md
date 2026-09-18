# NIfTI-1 I/O library, as vendored by Horos

The files named in `UPSTREAM.json` are byte-for-byte copies of
[NIFTI-Imaging/nifti_clib](https://github.com/NIFTI-Imaging/nifti_clib) at commit
`8f72d1165aa62320cc6982d6ddd71a7f6b9924c5` (20 December 2024), flattened from
upstream's `niftilib/` and `znzlib/` into this folder so the Xcode paths stay as
they were. That commit comes after the 3.0.1 package release and is not itself a
release. Its NIfTI-1 I/O library calls itself 2.1.0 and znzlib 3.0.0; those are
component versions, not the package's. The public-domain notice is `LICENSE`.

Before this update the folder held library version 1.43 (7 July 2010) with no
recorded revision, and `znzlib.c` differed from upstream by commented-out
declarations. Their hashes are kept under `replaced` in the manifest.

## What is and is not included

Only the NIfTI-1 (and Analyze 7.5 compatible) reader and writer and znzlib:
not NIfTI-2, nifticdf, the command-line tools, the tests or the CMake build. The
Horos target compiles `nifti1_io.c` and `znzlib.c` directly; `DCMPix.m` and
`DicomFile.mm` include `nifti1.h` and `nifti1_io.h`.

`HAVE_ZLIB` is not defined, as before, so `.nii.gz` is not readable through this
library and this update does not add it. The target's settings apply unchanged:
`-std=c11`, `-ffast-math`, `-fvisibility=default`, and `-Wno-unused-variable`,
which covers the declarations znzlib only uses with zlib.

ITK builds its own NIfTI copy into `libITK.a`. It is not linked: the linker
takes archive members only for undefined symbols, and every NIfTI symbol is
defined by this folder's objects first. The headers do not mix either - the two
Horos sources include this folder's copies through the header map, ahead of
ITK's installed headers.

Nothing here is modified. Anything Horos needs differently belongs in its callers
or in the project settings, not in these files.

## Checking the copy

`tests/test-nifti-upstream.py` needs no network. It checks every file against
the SHA-256 and git blob SHA-1 in `UPSTREAM.json`, that nothing else was added to
the folder, and that the project compiles the two sources. It also compiles the
calls Horos makes against these headers as C, Objective-C and Objective-C++.

The manifest was not produced from these files alone. The archive's SHA-256 is
recorded as downloaded, and each blob SHA-1 was compared with upstream's own git
tree for the commit:

```sh
gh api 'repos/NIFTI-Imaging/nifti_clib/git/trees/8f72d1165aa62320cc6982d6ddd71a7f6b9924c5?recursive=1' \
    --jq '.tree[] | select(.path | test("^(niftilib|znzlib)/|^LICENSE$")) | "\(.sha) \(.path)"'
```

## Updating

1. Pick an exact upstream commit, never a branch.
2. Download `https://codeload.github.com/NIFTI-Imaging/nifti_clib/tar.gz/<commit>`
   and record its SHA-256.
3. Diff the new `niftilib/nifti1_io.[ch]`, `nifti1.h` and `znzlib/` against this
   folder. Look first at what `DCMPix.m` and `DicomFile.mm` use: `nifti_read_header`,
   `nifti_image_read`, `nifti_image_free`, `nifti_image_to_ascii`,
   `nifti_mat44_to_orientation`, and the `nifti_image` and `nifti_1_header` fields.
4. Copy the files in the manifest from their `upstream_path`, unedited. If
   upstream needs a new header, add it to the manifest and to the project.
5. Update `revision`, `archive`, `archive_sha256` and every file's `size`,
   `sha256` and `git_blob_sha1` - compare the blob hashes with the command above -
   and move the old hashes to `replaced`.
6. Run `tests/test-nifti-upstream.py`, build Debug and Release, then repeat the
   native import matrix (`tools/exercise-native-nifti-import.py`, recorded in the
   #631 section of `docs/donor-delta4-validation.md`).
