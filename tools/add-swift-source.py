#!/usr/bin/env python3
"""Add a Swift file in Horos/Sources to the Xcode project, by copying a twin.

The project file is a 30 000-line plist of 24-character hexadecimal object ids,
and a Swift source that is not listed in it compiles to nothing: the bridging
header stops declaring the class and the first Objective-C call site fails with
`use of undeclared identifier`. Editing it by hand is how an id gets reused -
which does not fail, it silently drops whichever file loses.

So this copies the four lines an existing Swift file already has - its
`PBXBuildFile`, its `PBXFileReference`, its place in the group and its place in
the Sources build phase - substituting fresh ids, and refuses if either id is
already somewhere in the file.

    python3 tools/add-swift-source.py StudyNotOpenedReason.swift

Nothing happens if the name is already there, so it is safe to run twice.
"""
import io
import re
import sys
import uuid

MODEL = 'RetrieveListenerRequirement.swift'
MODEL_FILE_ID = '24200105551B5A3B9BA97357'
MODEL_BUILD_ID = '99E3A59DBF64555CAB4F65B6'
PROJECT = 'Horos.xcodeproj/project.pbxproj'

if len(sys.argv) != 2 or not sys.argv[1].endswith('.swift'):
    raise SystemExit('usage: %s <Name.swift>   (the file lives in Horos/Sources)' % sys.argv[0])
name = sys.argv[1]

project = io.open(PROJECT, encoding='utf-8').read()
if name in project:
    print('%s is already in the project' % name)
    raise SystemExit(0)
for identifier in (MODEL_FILE_ID, MODEL_BUILD_ID):
    if identifier not in project:
        raise SystemExit('the model file %s is no longer in the project; pick another twin' % MODEL)

build_id = uuid.uuid4().hex[:24].upper()
file_id = uuid.uuid4().hex[:24].upper()
assert build_id not in project and file_id not in project, 'generated an id the project already uses'

added = 0
for line in project.split('\n'):
    if MODEL in line and 'PBXBuildFile' in line:
        twin = re.sub(r'^(\s*)\S{24}', r'\g<1>' + build_id, line).replace(MODEL, name)
        twin = twin.replace('fileRef = ' + MODEL_FILE_ID, 'fileRef = ' + file_id)
        project = project.replace(line, line + '\n' + twin, 1)
        added += 1
        break
for line in project.split('\n'):
    if MODEL in line and 'PBXFileReference' in line:
        twin = re.sub(r'^(\s*)\S{24}', r'\g<1>' + file_id, line).replace(MODEL, name)
        project = project.replace(line, line + '\n' + twin, 1)
        added += 1
        break
for line in project.split('\n'):
    if line.strip() == '%s /* %s */,' % (MODEL_FILE_ID, MODEL):
        project = project.replace(line, line + '\n' + line.replace(MODEL_FILE_ID, file_id)
                                  .replace(MODEL, name), 1)
        added += 1
        break
for line in project.split('\n'):
    if line.strip() == '%s /* %s in Sources */,' % (MODEL_BUILD_ID, MODEL):
        project = project.replace(line, line + '\n' + line.replace(MODEL_BUILD_ID, build_id)
                                  .replace(MODEL, name), 1)
        added += 1
        break

if added != 4:
    raise SystemExit('only %d of the four places were found; the project layout has changed' % added)

io.open(PROJECT, 'w', encoding='utf-8').write(project)
print('added %s  (file %s, build %s)' % (name, file_id, build_id))
