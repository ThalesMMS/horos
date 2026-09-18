#!/usr/bin/env python3
"""Two NIfTI or Analyze files of one name are two studies, two series and two images (#641).

A NIfTI or Analyze file has no identifiers of its own, and `-[DicomFile getNIfTI]`
and `-getAnalyze` made them from the file's name: `subject1/brain.nii` and
`subject2/brain.nii` had one study ID, one series ID and one SOP instance UID, and
imported without copying (the database pointing at the files where they are) they
became a single series. Analyze took the study and the image from the header's
dataset name, which files from one tool share.

Each identifier now carries a key of the file's path, which a file keeps for as long
as it stays where it is: imported again, or read again after a relaunch.
"""
from pathlib import Path
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
failures = []

reader = (root / 'Horos/Sources/DicomFile.mm').read_bytes().decode('latin1')


def method(signature):
    begin = reader.index(signature)
    return reader[begin:reader.index('\n}\n', begin)]


for label, signature in (('NIfTI', '-(short) getNIfTI'), ('Analyze', '-(short) getAnalyze')):
    body = method(signature)
    if 'NSString *fileKey = [HorosFileIdentity keyForPath: filePath];' not in body:
        failures.append('%s: the identifiers do not take a key of the file\'s path' % label)
    for what in ('studyID = [[NSString alloc] initWithFormat:@"%@-%@", name, fileKey];',
                 'self.serieID = [NSString stringWithFormat:@"%@-%@", [[filePath lastPathComponent] stringByDeletingPathExtension], fileKey];',
                 'imageID = [[NSString alloc] initWithFormat:@"%@-%@", name, fileKey];'):
        if what not in body:
            failures.append('%s: %s is still made from the name alone' % (label, what.split(' =')[0]))
analyze = method('-(short) getAnalyze')
if '#ifndef DECOMPRESS_APP\n                NSString *fileKey = [HorosFileIdentity keyForPath: filePath];\n#else' not in analyze:
    failures.append('getAnalyze, also built into the Decompress helper, asks Swift for the key there too')

project = (root / 'Horos.xcodeproj/project.pbxproj').read_text()
if project.count('/* FileIdentity.swift in Sources */') != 2 or 'path = "FileIdentity.swift";' not in project:
    failures.append('FileIdentity.swift is not built into the app')

source = r'''
import Foundation

let one = FileIdentity.key(forPath: "/data/subject1/brain.nii")
let other = FileIdentity.key(forPath: "/data/subject2/brain.nii")
precondition(one != other, "two files of one name in two folders share a key")

// The same file, however its path is spelled, keeps its key.
precondition(FileIdentity.key(forPath: "/data/subject1/brain.nii") == one)
precondition(FileIdentity.key(forPath: "/data/subject1/../subject1/brain.nii") == one)
precondition(FileIdentity.key(forPath: "/data//subject1/./brain.nii") == one)

// Sixteen hexadecimal digits, the same from one run to the next.
precondition(one.count == 16 && one.allSatisfy { $0.isHexDigit && !$0.isUppercase })
precondition(FileIdentity.key(forPath: "/data/subject1/brain.nii") == "\(one)")
print(one)
'''

with tempfile.TemporaryDirectory() as temporary:
    work = Path(temporary)
    (work / 'main.swift').write_text(source)
    binary = work / 'identity'
    compiled = subprocess.run(['xcrun', 'swiftc', '-module-name', 'Identity', str(root / 'Horos/Sources/FileIdentity.swift'),
                               str(work / 'main.swift'), '-o', str(binary)], capture_output=True, text=True)
    if compiled.returncode != 0:
        failures.append('FileIdentity.swift does not compile: ' + compiled.stderr[-800:])
    else:
        keys = []
        for _ in range(2):
            run = subprocess.run([str(binary)], capture_output=True, text=True)
            if run.returncode != 0:
                failures.append('the file key answered wrongly: ' + (run.stderr or run.stdout)[-800:])
                break
            keys.append(run.stdout.strip())
        # The key is SHA-256 of the standardized path, so it is the same in any process and after a relaunch.
        import hashlib
        expected = hashlib.sha256(b'/data/subject1/brain.nii').hexdigest()[:16]
        if keys and any(key != expected for key in keys):
            failures.append('the key of a path changes between runs or is not its SHA-256: %s, expected %s' % (keys, expected))

if failures:
    print('\n'.join(failures))
    sys.exit(1)
print('NIfTI/Analyze identity: files of one name in different folders stay apart, and a file keeps its key')
