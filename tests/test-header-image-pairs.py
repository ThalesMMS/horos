#!/usr/bin/env python3
"""An Analyze or two-file NIfTI volume goes into the database as a pair (#642).

The header, `volume.hdr`, and its voxels, `volume.img`, have to stay side by side
under one name: `-[DicomFile getAnalyze]` and `-getNIfTI` open the image from the
header's path. The database stores what it imports under numbers of its own, and
it numbered the two files separately: through INCOMING or with "copy files", the
header became `123.hdr` beside no image and could not be read, and the image, not a
file the database indexes on its own, was refused - and deleted, with
DELETEFILELISTENER (the default) - in INCOMING. Analyze 7.5 headers carry no
NIfTI magic, so INCOMING refused and deleted them too.

`HorosHeaderImagePair` says which files are a pair; the import takes the image
along with its header, under the header's new name, and an unreadable header
leaves the database folder with its image.
"""
from pathlib import Path
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
failures = []

database = (root / 'Horos/Sources/DicomDatabase.mm').read_text()


def block(text, start, end):
    begin = text.index(start)
    return text[begin:text.index(end, begin)]


incoming = block(database, '-(NSInteger)importFilesFromIncomingDir: (NSNumber*) showGUI\n', '-(void)importFilesFromIncomingDirThread')
skip = incoming.index('[HorosHeaderImagePair headerPathForImage: srcPath]') if '[HorosHeaderImagePair headerPathForImage: srcPath]' in incoming else -1
if skip < 0:
    failures.append('INCOMING takes an .img with its header beside it on its own')
elif skip > incoming.index('isDicomFile = [DicomFile isDICOMFile:srcPath'):
    failures.append('INCOMING decides about an .img of a pair only after reading it as a file of its own')
if 'pairedImage ||' not in incoming:
    failures.append('INCOMING does not accept a header with its image beside it (an Analyze header has no NIfTI magic)')
if incoming.count('[HorosHeaderImagePair imagePathBesideStoredHeader: dstPath]') != 2:
    failures.append('INCOMING does not store the image beside the header, both when moving and when copying an alias')

copying = block(database, '-(void)copyFilesThread:(NSDictionary*)dict\n', '[queue addOperationWithBlock:^{')
if 'if (imageHeader && [inputHeaders containsObject: [imageHeader lowercaseString]])\n' not in copying:
    failures.append('the copy import copies an .img whose header it is also importing on its own')
if '[HorosHeaderImagePair imagePathBesideStoredHeader: dstPath]' not in copying:
    failures.append('the copy import does not copy the image beside the copied header')

unreadable = block(database, 'void (^disposeOfUnreadable)(NSString*) = ^(NSString *unreadable)', '\n        };\n')
if '[HorosHeaderImagePair imagePathForHeader: unreadable]' not in unreadable:
    failures.append('an unreadable header leaves its image behind in the database folder')

project = (root / 'Horos.xcodeproj/project.pbxproj').read_text()
if project.count('/* HeaderImagePair.swift in Sources */') != 2 or 'path = "HeaderImagePair.swift";' not in project:
    failures.append('HeaderImagePair.swift is not built into the app')

source = r'''
import Foundation

let manager = FileManager.default
let folder = URL(fileURLWithPath: CommandLine.arguments[1])
func touch(_ name: String) -> String {
    let path = folder.appendingPathComponent(name).path
    precondition(manager.createFile(atPath: path, contents: Data([1])))
    return path
}

// A header with its image, and the image with its header.
let header = touch("volume.hdr"), image = touch("volume.img")
precondition(HeaderImagePair.imagePath(forHeader: header) == image)
precondition(HeaderImagePair.headerPath(forImage: image) == header)

// Upper-case names: the file that is there, whatever the case of the other one.
let upperHeader = touch("SCAN.HDR"), upperImage = touch("SCAN.IMG")
precondition(HeaderImagePair.imagePath(forHeader: upperHeader) != nil)
precondition(HeaderImagePair.headerPath(forImage: upperImage) != nil)

// Half a pair, other files and nothing at all.
let lonelyHeader = touch("lonely.hdr"), lonelyImage = touch("alone.img")
precondition(HeaderImagePair.imagePath(forHeader: lonelyHeader) == nil)
precondition(HeaderImagePair.headerPath(forImage: lonelyImage) == nil)
precondition(HeaderImagePair.imagePath(forHeader: image) == nil, "an image is not a header")
precondition(HeaderImagePair.headerPath(forImage: header) == nil, "a header is not an image")
let nifti = touch("brain.nii")
_ = touch("brain.img")
precondition(HeaderImagePair.imagePath(forHeader: nifti) == nil)
precondition(HeaderImagePair.imagePath(forHeader: nil) == nil)
precondition(HeaderImagePair.imagePath(forHeader: "") == nil)
precondition(HeaderImagePair.headerPath(forImage: nil) == nil)

// A directory named like the image is not one.
precondition((try? manager.createDirectory(atPath: folder.appendingPathComponent("folder.img").path,
                                           withIntermediateDirectories: false)) != nil)
precondition(HeaderImagePair.imagePath(forHeader: touch("folder.hdr")) == nil)

// Where the image of a stored header goes: the header's name, with the extension the readers open.
precondition(HeaderImagePair.imagePath(besideStoredHeader: "/db/10000/123.hdr") == "/db/10000/123.img")
precondition(HeaderImagePair.imagePath(besideStoredHeader: "/db/10000/124.HDR") == "/db/10000/124.img")
print("ok")
'''

with tempfile.TemporaryDirectory() as temporary:
    work = Path(temporary)
    (work / 'main.swift').write_text(source)
    binary = work / 'pairs'
    compiled = subprocess.run(['xcrun', 'swiftc', '-module-name', 'Pairs', str(root / 'Horos/Sources/HeaderImagePair.swift'),
                               str(work / 'main.swift'), '-o', str(binary)], capture_output=True, text=True)
    if compiled.returncode != 0:
        failures.append('HeaderImagePair.swift does not compile: ' + compiled.stderr[-800:])
    else:
        files = work / 'files'
        files.mkdir()
        run = subprocess.run([str(binary), str(files)], capture_output=True, text=True)
        if run.returncode != 0 or run.stdout.strip() != 'ok':
            failures.append('the pair helper answered wrongly: ' + (run.stderr or run.stdout)[-800:])

if failures:
    print('\n'.join(failures))
    sys.exit(1)
print('header/image pairs: INCOMING, copy import and unreadable files keep them together')
