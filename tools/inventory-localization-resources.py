#!/usr/bin/env python3
"""SHA-256 inventory of the localization resources a revision carries (#633).

Lists every file under a `*.lproj` folder of the sources the project builds
(Horos, the preference panes, Nitrogen, the helpers) at a revision, or in a
built bundle, with its size and SHA-256, so that two inventories can be
compared: removing build scaffolding must leave every catalog, XIB and strings
file byte for byte.

    python3 tools/inventory-localization-resources.py --revision HEAD~1 --out before.json
    python3 tools/inventory-localization-resources.py --revision HEAD --out after.json --compare before.json
    python3 tools/inventory-localization-resources.py --bundle build/Development/HorosDevelopment.app --out bundle.json
"""
import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def from_revision(revision):
    listing = subprocess.run(["git", "-C", str(ROOT), "ls-tree", "-r", "-l", "--full-tree", revision],
                             capture_output=True, text=True, check=True).stdout
    entries = {}
    for line in listing.splitlines():
        meta, path = line.split("\t", 1)
        mode, kind, obj, size = meta.split()
        if kind != "blob" or ".lproj/" not in path or path.startswith(("local-validation/", "build/")):
            continue
        data = subprocess.run(["git", "-C", str(ROOT), "cat-file", "blob", obj], capture_output=True, check=True).stdout
        entries[path] = {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
    return entries


def from_bundle(bundle: Path):
    entries = {}
    for path in sorted(bundle.rglob("*")):
        if path.is_file() and ".lproj" in path.parts[-2]:
            data = path.read_bytes()
            entries[str(path.relative_to(bundle))] = {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
    return entries


parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
source = parser.add_mutually_exclusive_group(required=True)
source.add_argument("--revision")
source.add_argument("--bundle", type=Path)
parser.add_argument("--out", type=Path, required=True)
parser.add_argument("--compare", type=Path, help="an earlier inventory: report every difference")
arguments = parser.parse_args()
entries = from_revision(arguments.revision) if arguments.revision else from_bundle(arguments.bundle)
languages = sorted({part for path in entries for part in Path(path).parts if part.endswith(".lproj")})
report = {"source": arguments.revision or str(arguments.bundle), "files": len(entries), "languages": languages,
          "entries": entries}
arguments.out.parent.mkdir(parents=True, exist_ok=True)
arguments.out.write_text(json.dumps(report, indent=1, sort_keys=True) + "\n")
print(f"{len(entries)} localization files in {len(languages)} lproj folders: {', '.join(languages)}")
if arguments.compare:
    earlier = json.loads(arguments.compare.read_text())["entries"]
    added = sorted(set(entries) - set(earlier))
    removed = sorted(set(earlier) - set(entries))
    changed = sorted(p for p in set(entries) & set(earlier) if entries[p]["sha256"] != earlier[p]["sha256"])
    print(f"added {len(added)}, removed {len(removed)}, changed {len(changed)}")
    for label, paths in (("added", added), ("removed", removed), ("changed", changed)):
        for path in paths:
            print(f"  {label}: {path}")
    raise SystemExit(1 if added or removed or changed else 0)
