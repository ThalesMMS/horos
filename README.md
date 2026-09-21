# Horos

A fork of the Horos DICOM viewer. This file is for someone building it locally
for the first time. Everything below was run on the machine described under
[Verified on](#verified-on).

## Prerequisites

| Tool | Why | Checked with |
|---|---|---|
| Xcode | builds the application and the dependencies | `xcodebuild -version` |
| `cmake` | configures ITK, VTK, GDCM, DCMTK, OpenJPEG, OpenSSL, CharLS | `cmake --version` |
| `pkg-config` | same | `pkg-config --version` |
| `git-lfs` | VTK-m assets | `git-lfs --version` |

`cmake` and `pkg-config` must be on `PATH`, or in `/opt/homebrew/bin` (Apple
Silicon) or `/opt/local/bin` (Intel) — the dependency scripts add those two
directories themselves.

## Getting the source

```sh
git clone https://github.com/ThalesMMS/horos.git
```

That is all. **This fork has no git submodules to initialise.** `.gitmodules`
still lists nine, but the dependency trees are committed directly: `git ls-files`
reports 71,225 files and no gitlink entries, and the history is about 350 MB.
`git submodule update --init --recursive` does nothing here.

Some binaries ship zipped and are unpacked by the `Unzip Binaries` target during
the build; you can run that target on its own if you want them earlier.

## Building

```sh
make
```

which is `xcodebuild -project Horos.xcodeproj -scheme Horos -configuration Debug
-derivedDataPath build`. `make CONFIG=Release` builds Release. In Xcode, open
`Horos.xcodeproj` and build the `Horos` scheme.

To prepare a Release app for your Applications folder:

```sh
script/build_release.sh
```

Copy `build/Release/Horos.app` to Applications when it finishes. The script
builds Release, signs the app and its helpers ad hoc for use on this Mac, and
verifies the bundle. It keeps the normal Horos bundle identifier and preserves
the previous output with a timestamp. It does not install or launch the app.
Logs are saved to `build/logs/build-release.log` and
`build/logs/release-signing.log`. This local build uses the Homebrew libraries
installed on the build machine and is not a notarized distribution package.

The first build compiles every dependency. On the machine below, ten cores, that
took about five minutes; on a slower or older Mac expect considerably longer.
Afterwards, a change to application sources alone rebuilds in a minute or two.

**Changing a build setting rebuilds every dependency.** The scripts under
`Horos/Scripts/` decide whether to rebuild by hashing the whole build
environment, so altering a signing setting, or passing a flag one build has and
the next does not, throws away ITK, VTK and the rest and starts over. In
particular, alternating between `make` and a command that adds
`CODE_SIGNING_ALLOWED=NO` rebuilds them each time — measured here at roughly four
minutes each way. Pick one and stay with it. This is issue #333.

## Signing

`Config.xcconfig` leaves `HOROS_DEVELOPMENT_TEAM` empty, so a checkout carrying
no credentials builds. To sign with your own identity, create an untracked
`Config.local.xcconfig` beside it — copy `Config.local.xcconfig.example` — or
pass `HOROS_DEVELOPMENT_TEAM=<your team>` on the `xcodebuild` command line.
Nothing personal belongs in a tracked file.

## Running it locally

```sh
script/build_and_run.sh
```

builds Debug, copies the result to `build/Development/HorosDevelopment.app` under
its own bundle identifier, signs it ad hoc, and launches it against a private
database in `local-validation/runtime-private`. It does not disturb an installed
Horos and does not touch your real database. This is the smoke test: the
application should reach its database window.

For performance measurements, use the optimized Release configuration with the
same isolated bundle and database:

```sh
HOROS_DEV_CONFIGURATION=Release script/build_and_run.sh --verify
```

The JPEG 2000 loading comparison, the 3D MPR Metal implementation with its
Retina correction, pixel validation and scroll measurements, and the native VR
Metal option with its CPU/OsiriX comparison each have a validation record with
reproduction steps, kept per issue with the rest of the documentation.

| | |
|---|---|
| `script/build_and_run.sh --verify` | launch and report the process identifier, then return |
| `script/build_and_run.sh --debug` | launch under `lldb` |
| `script/build_and_run.sh --logs` | stream the unified log for the process |
| `script/build_and_run.sh --diagnostics` | run in the foreground under Xcode's Main Thread Checker |

## Tests

Each file under `tests/` is a standalone Python script that compiles the real
production code — extracted from the sources, or the Swift files directly — and
exercises it. They need Xcode's command line tools and nothing else:

```sh
python3 tests/test-view-clipping.py
```

Most take a commit as an optional argument to run against that revision instead
of the working tree. `docs/` holds one validation record per issue, naming what
was checked, on what build, and what was left unverified.

## Architecture, and what does not work

- `Config.xcconfig` sets `ARCHS = arm64`, one architecture at a time. **No
  universal or Intel build is produced**; every dependency would have to be
  rebuilt for `x86_64` first.
- The **product** minimum is **macOS 26**, and `MACOSX_DEPLOYMENT_TARGET` now
  encodes `26.0`. The compile SDK must support this deployment target.
  The policy keeps the product
  minimum, the SDK and the encoded target as three separate numbers
  (`HorosPlatformPolicy`). A package built for 26 must not be offered as an
  installable update to a Mac below it.
- Most prebuilt binaries under `Binaries/` that lack `arm64` are inert — the
  linker reports ignoring them, or nothing references them. The helper that
  reaches a user is `dciodvfy` (Meta-Data → Validator), now an arm64 binary
  in `Binaries/dciodvfy.zip`.

## License and credits

Horos is LGPLv3, based on OsiriX (LGPLv3). Other
linked libraries keep their own terms (DCMTK, ITK, VTK, GDCM, OpenJPEG,
OpenSSL, CharLS). See [LICENSE](LICENSE), [COPYING.LESSER](COPYING.LESSER) and
[NOTICE](NOTICE). Selected excerpts were adapted from **ystarrev/horos**,
authored by Yves Starreveld, and the About window carries that credit. This
workbench keeps the Purview/HorosCloud notice that the origin LICENSE omits.
Plugins and the DICOMweb client are not removed to simplify licensing. This is
not legal advice.

## ROI interchange

ROIs can be exported and imported as documented JSON.

## Verified on

macOS 26.6.2, Apple Silicon, Xcode 26.6 (17F113), cmake 4.3.4, pkg-config 2.5.1,
git-lfs 3.8.0. `make` was run to completion in this checkout and succeeded. A clean clone into
an empty directory was not built, so the "first build" figure comes from a build
that recompiled the dependencies in an existing checkout, not from a measured
clean clone.
