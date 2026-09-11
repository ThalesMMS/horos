#!/usr/bin/env python3
"""A study on an ejected disc looked broken rather than disconnected.

Horos can copy what it imports into its own folder or leave it where it is and
keep a link. A study imported as links to a CD, opened with the CD out, said one
thing:

    not readable: /Volumes/HOROS79/study/iso-ir-144.dcm

and the alert behind it said "No files available (readable) in this series." -
which is what it also says for a file it cannot decode. The study reads as
damaged, and nothing suggests putting the disc back.

Measured on a 20 MB disk image with one study on it (macOS 26.6.2 arm64):

    COPYDATABASE=YES   the file is copied; after ejecting, the study opens with
                       no complaint at all
    COPYDATABASE=NO    the row keeps /Volumes/HOROS79/study/iso-ir-144.dcm, and
                       after ejecting the application now says

      ---- /Volumes/HOROS79/study/iso-ir-144.dcm is a link into /Volumes/HOROS79,
           which is not mounted

    and after attaching the image again the file is reachable and the database
    still holds one study, one series, one image - nothing was duplicated.
"""
from pathlib import Path
import re
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
failures = []
reason = root / 'Horos/Sources/MissingFileReason.swift'
browser = (root / 'Horos/Sources/BrowserController.m').read_bytes().decode('latin1')

DRIVER = '''
import Foundation

func emit(_ key: String, _ value: String) { print("\\(key)\\t\\(value)") }

let directory = NSTemporaryDirectory() + "horos-missing-\\(getpid())"
try? FileManager.default.createDirectory(atPath: directory, withIntermediateDirectories: true)
let present = directory + "/present.dcm"
FileManager.default.createFile(atPath: present, contents: Data([0, 1, 2]))

emit("presentInFolder", MissingFileReason.reason(forPath: present, inDatabaseFolder: true))
emit("presentLink", MissingFileReason.reason(forPath: present, inDatabaseFolder: false))
emit("goneFromFolder",
     MissingFileReason.reason(forPath: directory + "/gone.dcm", inDatabaseFolder: true))
// A volume that is not mounted: the removable-media case.
emit("volumeGone",
     MissingFileReason.reason(forPath: "/Volumes/NoSuchVolume90/study/one.dcm",
                              inDatabaseFolder: false))
// A link that is not on a volume at all, and is not there.
emit("linkGone",
     MissingFileReason.reason(forPath: directory + "/gone.dcm", inDatabaseFolder: false))
emit("noPath", MissingFileReason.reason(forPath: nil, inDatabaseFolder: false))
emit("empty", MissingFileReason.reason(forPath: "", inDatabaseFolder: true))

emit("volumeOf", MissingFileReason.volumeOf(path: "/Volumes/Disc/study/one.dcm") ?? "nil")
emit("volumeOfNone", MissingFileReason.volumeOf(path: "/Users/someone/one.dcm") ?? "nil")
emit("volumeOfRoot", MissingFileReason.volumeOf(path: "/Volumes") ?? "nil")

try? FileManager.default.removeItem(atPath: directory)
'''

results = {}
if not reason.exists():
    failures.append('nothing says why a file the database points at is not there')
else:
    with tempfile.TemporaryDirectory(prefix='horos-reason-') as directory:
        (Path(directory) / 'main.swift').write_text(DRIVER)
        binary = Path(directory) / 'reason'
        built = subprocess.run(['xcrun', '--sdk', 'macosx', 'swiftc', '-o', str(binary),
                                str(reason), str(Path(directory) / 'main.swift')],
                               capture_output=True, text=True)
        if built.returncode != 0:
            failures.append('the reason does not compile:\n%s' % built.stderr[-1500:])
        else:
            run = subprocess.run([str(binary)], capture_output=True, text=True, timeout=120)
            if run.returncode != 0:
                failures.append('the driver failed: %s' % run.stderr[-500:])
            for line in run.stdout.splitlines():
                key, _, value = line.partition('\t')
                results[key] = value

if results:
    def endswith(key, ending):
        got = results.get(key, '')
        if not got.endswith(ending):
            failures.append('%s says %r, which does not end in %r' % (key, got, ending))

    endswith('presentInFolder', 'is in the database folder and could not be read')
    endswith('presentLink', 'is a link and could not be read')
    endswith('goneFromFolder', 'is missing from the database folder')
    endswith('linkGone', 'is a link and the file is no longer there')
    if results.get('volumeGone') != ('/Volumes/NoSuchVolume90/study/one.dcm is a link into '
                                     '/Volumes/NoSuchVolume90, which is not mounted'):
        failures.append('an ejected volume is described as %r' % results.get('volumeGone'))
    for key in ('noPath', 'empty'):
        if 'no path' not in results.get(key, ''):
            failures.append('%s says %r' % (key, results.get(key)))
    if results.get('volumeOf') != '/Volumes/Disc':
        failures.append('the volume of a path on one is %r' % results.get('volumeOf'))
    for key in ('volumeOfNone', 'volumeOfRoot'):
        if results.get(key) != 'nil':
            failures.append('%s is %r, expected no volume' % (key, results.get(key)))

# --- and the browser says it, in the log and in the alert ---------------------
code = re.sub(r'//[^\n]*', '', browser)
if 'HorosMissingFileReason' not in code:
    failures.append('the browser still says only "not readable"')
else:
    if 'not readable: %@' in code:
        failures.append('the old message is still there, so which one appears depends on the path')
    if code.count('HorosMissingFileReason') < 2:
        failures.append('the reason reaches the log but not the alert, or the other way round')
    at = code.find('Files not available (readable)')
    window = code[max(at - 200, 0):at + 800] if at >= 0 else ''
    if 'missingFileReason' not in window:
        failures.append('the alert the user sees does not carry the reason')

for failure in failures:
    print('FAIL: %s' % failure)
if failures:
    sys.exit(1)
print('ok: a file that is not there is described by why - a link into a volume that is not '
      'mounted, a link that is gone, or a file missing from the database folder')
