#!/usr/bin/env python3
"""Every reference in the Xcode projects points at an object that exists, and every
source of the app is compiled (#648, #652).

`Horos.xcodeproj/project.pbxproj` listed `HorosDCMFacade.swift` twice: the target's
Sources phase carried a build file that no object defined, and a file reference of
its own that no group contained. The build passed - Xcode ignores a pending
reference - and only a structural check shows it.

Both projects are read here (`plutil` converts the old-style plist to JSON) and
checked:

* every identifier a `files`, `children`, `buildPhases`, `targets`, `fileRef` or
  the like names is an object of the project;
* every object, apart from the root, is named by something;
* every file a Sources phase compiles exists on disk;
* every source in `Horos/Sources` is in a Sources phase, unless it is listed below
  with the reason - 48 sources were there, compiled by nothing, and two of them were
  even corrected as if they ran (#652).
"""
from pathlib import Path
import json
import os
import re
import subprocess

root = Path(__file__).resolve().parents[1]
# Xcode writes 24 hexadecimal characters; entries added by hand here use other letters too.
IDENTIFIER = re.compile(r'^[0-9A-Za-z]{24}$')
# What a proxy names lives in the other project file, or is resolved by Xcode at build time.
IGNORED_KEYS = {'remoteGlobalIDString', 'containerPortal'}
# Keys whose value is a name, not an identifier, even when it looks like one.
NAME_KEYS = {'isa', 'path', 'name', 'productName', 'remoteInfo', 'fileType', 'explicitFileType', 'sourceTree'}
# A source of the app that no target compiles, and why it is still here.
UNCOMPILED_SOURCES = {}
failures = []


def identifiers(value):
    if isinstance(value, str):
        return [value] if IDENTIFIER.match(value) else []
    if isinstance(value, list):
        return [item for entry in value for item in identifiers(entry)]
    return []


def path_of(objects, identifier, groups):
    """A file reference's path, through the groups that hold it."""
    entry = objects[identifier]
    tree, path = entry.get('sourceTree', '<group>'), entry.get('path', '')
    if tree == '<absolute>':
        return Path(path)
    if tree in ('SDKROOT', 'BUILT_PRODUCTS_DIR', 'DEVELOPER_DIR'):
        return None
    prefix = Path()
    if tree == '<group>':
        parent = groups.get(identifier)
        while parent is not None:
            group = objects[parent]
            if group.get('sourceTree') == 'SOURCE_ROOT':
                prefix = Path(group.get('path', '')) / prefix
                break
            prefix = Path(group.get('path', '')) / prefix
            parent = groups.get(parent)
    return prefix / path


for project in ('Horos.xcodeproj/project.pbxproj', 'Nitrogen/Nitrogen.xcodeproj/project.pbxproj'):
    path = root / project
    if not path.is_file():
        failures.append(f'{project} is missing')
        continue
    data = json.loads(subprocess.check_output(['plutil', '-convert', 'json', '-o', '-', str(path)]))
    objects = data['objects']
    groups = {}
    for identifier, entry in objects.items():
        for child in entry.get('children', []):
            groups[child] = identifier

    referenced = set()
    for identifier, entry in objects.items():
        for key, value in entry.items():
            if key in IGNORED_KEYS or key in NAME_KEYS:
                continue
            for named in identifiers(value):
                referenced.add(named)
                if named not in objects:
                    failures.append(f'{project}: {entry.get("isa", "?")} {identifier} names {named} in {key}, '
                                    f'which no object defines')

    for identifier, entry in objects.items():
        if identifier == data['rootObject'] or identifier in referenced:
            continue
        failures.append(f'{project}: {entry.get("isa", "?")} {identifier} '
                        f'({entry.get("path") or entry.get("name") or ""}) is in no group and nothing names it')

    base = path.parent.parent
    for identifier, entry in objects.items():
        if entry.get('isa') != 'PBXSourcesBuildPhase':
            continue
        for build in entry.get('files', []):
            reference = objects.get(build, {}).get('fileRef')
            if reference is None or reference not in objects:
                continue
            relative = path_of(objects, reference, groups)
            if relative is None:
                continue
            # A reference may walk out of a folder it names (path = Horos.xcodeproj/../file.m).
            absolute = Path(os.path.normpath(relative if relative.is_absolute() else base / relative))
            if not absolute.exists():
                failures.append(f'{project}: the Sources phase compiles {relative}, which is not on disk')

# Every source of the app is compiled by some target.
compiled = set()
data = json.loads(subprocess.check_output(['plutil', '-convert', 'json', '-o', '-',
                                          str(root / 'Horos.xcodeproj/project.pbxproj')]))
objects = data['objects']
for entry in objects.values():
    if entry.get('isa') != 'PBXSourcesBuildPhase':
        continue
    for build in entry.get('files', []):
        reference = objects.get(build, {}).get('fileRef')
        if reference in objects:
            compiled.add(Path(objects[reference].get('path', '')).name)
for source in sorted((root / 'Horos/Sources').iterdir()):
    if source.suffix not in ('.m', '.mm', '.c', '.cpp', '.swift') or source.name in compiled:
        continue
    if source.name in UNCOMPILED_SOURCES:
        continue
    failures.append(f'Horos/Sources/{source.name} is in no Sources phase: it is never compiled, '
                    f'and editing it changes nothing in the app')
for name, reason in UNCOMPILED_SOURCES.items():
    if (root / 'Horos/Sources' / name).exists() and name in compiled:
        failures.append(f'Horos/Sources/{name} is compiled now; take it off the list ({reason})')

if failures:
    print('\n'.join('FAIL: ' + failure for failure in failures[:40]))
    if len(failures) > 40:
        print(f'FAIL: ... and {len(failures) - 40} more')
    raise SystemExit(1)
print('Xcode projects: every reference names an object, every object is named, every compiled file is on disk, '
      'and every source of the app is compiled')
