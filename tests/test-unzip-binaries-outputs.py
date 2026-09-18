#!/usr/bin/env python3
"""Every unzipped binary the Horos target consumes is a declared output of Unzip Binaries (#628).

`Horos` depends on the aggregate target `Unzip Binaries`, whose script expands
zips under Binaries/. Without declared outputs the build system does not know
that script produces, say, `Binaries/DB_Previous_Models/*.mom`, and on a clean
checkout it copied the models before they existed: the first build failed and
the second passed. This resolves every file reference of the project to its
path, keeps the ones the Horos target copies, links or embeds that live inside
something a zip of Unzip.sh expands, and requires each to be covered by a
declared output - and every declared output to come from one of those zips.
"""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
project = (ROOT / "Horos.xcodeproj/project.pbxproj").read_bytes().decode("latin1")
script = (ROOT / "Horos/Scripts/Horos/Unzip.sh").read_text()

phase = re.search(r"4A2F5930078D148300C514A2 /\* Unzip Binaries \*/ = \{(.*?)\n\t\t\};", project, re.S)
assert phase, "the Unzip Binaries script phase is gone"
outputs_block = re.search(r"outputPaths = \((.*?)\);", phase.group(1), re.S)
assert outputs_block, "Unzip Binaries declares no outputs: a clean checkout races the copy of what it expands"
outputs = [item.strip().strip(",").strip('"') for item in outputs_block.group(1).strip().splitlines() if item.strip()]
assert all(o.startswith("$(SRCROOT)/Binaries/") for o in outputs), outputs
declared = {o.replace("$(SRCROOT)/", "") for o in outputs}

# What the script expands: the top-level entries of each zip it unzips in Binaries/.
expanded = set()
for line in script.splitlines():
    line = line.strip()
    match = re.match(r"unzip -uo (\S+?)(?: -d (\S+))?$", line)
    if not match:
        continue
    pattern, destination = match.groups()
    for archive in sorted((ROOT / "Binaries").glob(pattern)):
        if destination:
            expanded.add(f"Binaries/{destination}")
            continue
        names = subprocess.run(["unzip", "-Z1", str(archive)], capture_output=True, text=True, check=True).stdout
        for name in names.splitlines():
            top = name.split("/", 1)[0]
            if top and top != "__MACOSX":
                expanded.add(f"Binaries/{top}")
assert "Binaries/DB_Previous_Models" in expanded and "Binaries/weasis" in expanded, expanded

# Resolve file reference paths through the group tree.
parents = {}
for group in re.finditer(r"(\w{24}) /\* [^*]* \*/ = \{\s*isa = (?:PBXGroup|PBXVariantGroup);(.*?)\n\t\t\};", project, re.S):
    children = re.search(r"children = \((.*?)\);", group.group(2), re.S)
    for child in re.findall(r"(\w{24}) /\*", children.group(1) if children else ""):
        parents[child] = group.group(1)
entries = {}
for entry in re.finditer(r"(\w{24}) /\* [^*]* \*/ = \{\s*isa = (PBXGroup|PBXVariantGroup|PBXFileReference);(.*?)\};", project, re.S):
    body = entry.group(3)
    path = re.search(r'\bpath = ("(?:[^"\\]|\\.)*"|[^;]*);', body)
    tree = re.search(r"sourceTree = ([^;]*);", body)
    entries[entry.group(1)] = (path.group(1).strip('"') if path else "", tree.group(1).strip('"') if tree else "<group>")


def resolve(identifier):
    path, tree = entries.get(identifier, ("", "<group>"))
    if tree == "SOURCE_ROOT":
        return Path(path)
    if tree != "<group>":
        return None
    parent = parents.get(identifier)
    base = resolve(parent) if parent else Path("")
    if base is None:
        return None
    return Path(__import__("os").path.normpath(base / path)) if path else base


target = re.search(r"(\w{24}) /\* Horos \*/ = \{\s*isa = PBXNativeTarget;(.*?)\n\t\t\};", project, re.S).group(2)
phases = re.findall(r"(\w{24}) /\*", re.search(r"buildPhases = \((.*?)\);", target, re.S).group(1))
consumed = set()
for phase_id in phases:
    body = re.search(phase_id + r" /\* [^*]* \*/ = \{(.*?)\n\t\t\};", project, re.S)
    files = re.search(r"files = \((.*?)\);", body.group(1), re.S) if body else None
    for build_file in re.findall(r"(\w{24}) /\*", files.group(1) if files else ""):
        reference = re.search(build_file + r" /\* [^*]* \*/ = \{isa = PBXBuildFile; fileRef = (\w{24})", project)
        if not reference:
            continue
        path = resolve(reference.group(1))
        if path is None:
            continue
        text = str(path)
        if any(text == item or text.startswith(item + "/") for item in expanded):
            consumed.add(text)

assert any(p.endswith(".mom") for p in consumed), f"the models were not found among consumed paths: {sorted(consumed)}"
missing = sorted(p for p in consumed if not any(p == d or p.startswith(d + "/") for d in declared))
assert not missing, f"consumed but not declared as outputs of Unzip Binaries: {missing}"
unexpanded = sorted(d for d in declared if not any(d == e or d.startswith(e + "/") for e in expanded))
assert not unexpanded, f"declared outputs no zip in Unzip.sh produces: {unexpanded}"
print(f"PASS: {len(consumed)} consumed unzipped paths all declared among {len(declared)} outputs of Unzip Binaries")
