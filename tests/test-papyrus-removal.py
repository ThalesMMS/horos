#!/usr/bin/env python3
"""What #630 removed stays removed, and what it had to keep is kept.

An inventory guard, read from the sources and the project; the compiled
behaviour (images read, cache, locks under concurrency) is validated in the
app, see docs/donor-delta4-validation.md.

Removed: the Papyrus3 toolkit folder and any project or include reference to it;
the always-NO `gUSEPAPYRUSDCMPIX` flag, its branch and the fallback that re-read
a whole file to call a reader that always failed; the group cache nothing
filled (`cachedPapyGroups`, `-clearCachedPapyGroups`); the unused
`PapyrusLockFunction`; the `USEPAPYRUSDCMPIX4` default; extern declarations of
the lock in files that never take it.

Kept: the `PapyrusLock` global, allocated at launch and still taken around the
parsed-file cache, the annotations and the DCMTK reads in DicomFile; the store
listener locks; the photometric interpretation codes of the YBR conversion;
`-loadDICOMPapyrus` and `-clearCachedDCMFrameworkFiles` in the SDK header;
`TOOLKITPARSER4`, whose presence DicomFile reads; the annotations method named
`loadCustomImageAnnotationsPapyLink:DCMLink:`.

    python3 tests/test-papyrus-removal.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
failures = []


def text(path):
    return (ROOT / path).read_bytes().decode("latin-1")


def check(condition, message):
    if not condition:
        failures.append(message)


# Removed.
check(not (ROOT / "Papyrus3").exists(), "the Papyrus3 folder is still there")
for project in ("Horos.xcodeproj/project.pbxproj",):
    check(not re.search(r"Papyrus3|PapyrusLockFunction", text(project)), f"{project} still names Papyrus3")
sources = [p for p in (ROOT / "Horos/Sources").rglob("*") if p.suffix in {".h", ".m", ".mm", ".c", ".swift"}]
for path in sources:
    body = path.read_bytes().decode("latin-1")
    rel = path.relative_to(ROOT)
    check('"Papyrus3/' not in body, f"{rel} still includes a Papyrus3 header")
    check("gUSEPAPYRUSDCMPIX" not in body, f"{rel} still has the gUSEPAPYRUSDCMPIX flag")
    check("cachedPapyGroups" not in body and "clearCachedPapyGroups" not in body, f"{rel} still has the Papyrus group cache")
    check("PapyrusLockFunction" not in body, f"{rel} still has PapyrusLockFunction")
    check("USEPAPYRUSDCMPIX4" not in body, f"{rel} still names USEPAPYRUSDCMPIX4")
pix = text("Horos/Sources/DCMPix.m")
check("success = [self loadDICOMPapyrus]" not in pix, "DCMPix still falls back to the Papyrus stub")
for path in ("Horos/Sources/BrowserControllerDCMTKCategory.mm", "Horos/Sources/XMLControllerDCMTKCategory.mm",
             "Horos/Sources/NSImage+OsiriX.m", "Horos/Sources/DicomFile.mm"):
    check("PapyrusLock" not in text(path), f"{path} still declares a lock it never takes")

# Kept.
app = text("Horos/Sources/AppController.m")
check(re.search(r"NSRecursiveLock\s+\*PapyrusLock = nil", app) is not None, "the PapyrusLock global is gone")
check("PapyrusLock = [[NSRecursiveLock alloc] init];" in app, "PapyrusLock is no longer allocated at launch")
for lock in ("STORESCP", "STORESCPTLS"):
    check(f"*{lock} = nil" in app and f"{lock} = [[NSRecursiveLock alloc] init];" in app, f"the {lock} lock is gone")
check(pix.count("[PapyrusLock lock]") >= 4 and pix.count("[PapyrusLock lock]") == pix.count("[PapyrusLock unlock]"),
      "DCMPix no longer takes PapyrusLock in balanced pairs around the parsed-file cache and annotations")
dcmtk = text("Horos/Sources/DicomFileDCMTKCategory.mm")
check(dcmtk.count("[PapyrusLock lock]") >= 5 and dcmtk.count("[PapyrusLock lock]") == dcmtk.count("[PapyrusLock unlock]"),
      "DicomFileDCMTKCategory no longer takes PapyrusLock in balanced pairs around DCMTK reads")
codes = re.search(r"enum EPhoto_Interpret\s*\{([^}]+)\}", pix)
check(codes is not None and [c.strip() for c in codes.group(1).split(",")] == [
    "MONOCHROME1", "MONOCHROME2", "PALETTE", "RGB", "HSV", "ARGB", "CMYK", "YBR_FULL", "YBR_FULL_422",
    "YBR_PARTIAL_422", "YBR_RCT", "YBR_ICT", "YUV_RCT", "UNKNOWN_COLOR"], "the photometric interpretation codes changed")
header = text("Horos/Sources/DCMPix.h")
check("- (BOOL) loadDICOMPapyrus;" in header and "- (BOOL) loadDICOMPapyrus" in pix, "-loadDICOMPapyrus left the SDK")
check("- (void) clearCachedDCMFrameworkFiles;" in header, "-clearCachedDCMFrameworkFiles left the SDK")
check("loadCustomImageAnnotationsPapyLink:(int)fileNb DCMLink:" in header, "the annotations method left the SDK")
check('forKey: @"TOOLKITPARSER4"' in text("Horos/Sources/DefaultsOsiriX.m"), "the TOOLKITPARSER4 default is gone")
check('objectForKey: @"TOOLKITPARSER4"' in text("Horos/Sources/DicomFile.mm"), "DicomFile no longer reads TOOLKITPARSER4")

for failure in failures:
    print("FAIL:", failure)
if failures:
    print(f"{len(failures)} failure(s)")
    raise SystemExit(1)
print("PASS: the Papyrus3 toolkit, the always-NO flag, its fallback, the empty group cache, the C lock wrapper, the "
      "default and the stray extern declarations are gone; PapyrusLock (allocated, balanced around the cache, "
      "annotations and DCMTK reads), the store locks, the colour codes, the SDK methods and TOOLKITPARSER4 remain")
