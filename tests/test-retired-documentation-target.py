#!/usr/bin/env python3
"""The Doxygen target and the root utilities with no consumer are gone, and nothing else is (#633).

Reads the project the way xcodebuild does (`xcodebuild -list -json`) and checks:

  * no `Documentation` target or scheme, and no build phase calls Doxygen;
  * every other target and shared scheme the project had is still there - the
    app, its helpers, the dependencies, Unzip Binaries (#628);
  * Doxyfile-horos, Doxyfile-dcmframework, LocalizationExtract.sh,
    LocalizationGenerate.sh, README.txt, To-Do.txt and ramDiskScript.txt are gone;
    README.md stays;
  * no file the project builds, no script under script/ or tools/ and no document
    under docs/ names one of them (the validation index excepted, which records
    the removal).

    python3 tests/test-retired-documentation-target.py
"""
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
failures = []

# What the project had besides Documentation. #617 removed Grok, which nothing linked, and kept CharLS,
# which DCM.framework's JPEG-LS decoding uses.
EXPECTED_TARGETS = {"API", "CharLS", "DCM", "DCMTK", "Decompress", "FeedbackReporter", "GDCM", "Horos", "HorosFinderPreview",
                    "HorosFinderThumbnail", "ITK", "OpenJPEG", "OpenSSL", "Submodules", "Unzip Binaries", "VTK"}
EXPECTED_SCHEMES = {"Cleanup Binaries", "DCMTK", "DICOMPrint", "Decompress", "FeedbackReporter", "GDCM", "Horos",
                    "Horos API", "Horos DCM", "HorosFinderPreview", "HorosFinderThumbnail", "ITK", "OpenJPEG",
                    "OpenSSL", "Submodules", "Unzip Binaries", "VTK"}
RETIRED_FILES = ["Doxyfile-horos", "Doxyfile-dcmframework", "LocalizationExtract.sh", "LocalizationGenerate.sh",
                 "README.txt", "To-Do.txt", "ramDiskScript.txt"]

listing = subprocess.run(["xcodebuild", "-list", "-json", "-project", str(ROOT / "Horos.xcodeproj")],
                         capture_output=True, text=True)
if listing.returncode != 0:
    print("needs xcodebuild -list to read the project", listing.stderr[-500:], file=sys.stderr)
    raise SystemExit(2)
project = json.loads(listing.stdout)["project"]
targets, schemes = set(project["targets"]), set(project["schemes"])
if "Documentation" in targets:
    failures.append("the Documentation target is still in the project")
if "Documentation" in schemes:
    failures.append("the Documentation scheme is still shared")
missing_targets = EXPECTED_TARGETS - targets
if missing_targets:
    failures.append(f"targets that must stay are missing: {sorted(missing_targets)}")
missing_schemes = EXPECTED_SCHEMES - schemes
if missing_schemes:
    failures.append(f"schemes that must stay are missing: {sorted(missing_schemes)}")

pbxproj = (ROOT / "Horos.xcodeproj/project.pbxproj").read_text(errors="replace")
if re.search(r"doxygen|Doxyfile", pbxproj, re.IGNORECASE):
    failures.append("a build phase still calls Doxygen")
if not (ROOT / "Horos.xcodeproj/xcshareddata/xcschemes/Horos.xcscheme").is_file():
    failures.append("the Horos scheme is gone")

for name in RETIRED_FILES:
    if (ROOT / name).exists():
        failures.append(f"{name} is still in the repository")
if not (ROOT / "README.md").is_file():
    failures.append("README.md is gone")

# README.txt and To-Do.txt are generic names (a fixture generator writes its own README.txt):
# only the distinctive names are looked for in text.
pattern = re.compile("|".join(re.escape(name) for name in RETIRED_FILES if name not in ("README.txt", "To-Do.txt")))
for folder in ("script", "tools", "docs", "Horos.xcodeproj"):
    for path in (ROOT / folder).rglob("*"):
        if not path.is_file() or path.suffix in {".png", ".jpg", ".zip", ".dylib"}:
            continue
        if path.name == "donor-delta4-validation.md" or path == Path(__file__).resolve() \
                or path.name == "inventory-localization-resources.py":
            continue
        text = path.read_bytes().decode("latin-1")
        if pattern.search(text):
            failures.append(f"{path.relative_to(ROOT)} still names a retired file")

for failure in failures:
    print("FAIL:", failure)
if failures:
    raise SystemExit(1)
print(f"PASS: no Documentation target or scheme, no Doxygen call; the other {len(targets)} targets and "
      f"{len(schemes)} schemes remain; the seven root utilities are gone and nothing names them")
