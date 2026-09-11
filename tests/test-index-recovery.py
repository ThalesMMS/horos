#!/usr/bin/env python3
"""An index that will not open is kept, diagnosed, and only then replaced.

The index is a SQLite file; the images are files beside it. It holds the studies,
the albums, the comments and the ROIs, and none of those are in a file. On the
first failed attempt to open it the code used to run

    if (self.deleteSQLFileIfOpeningFailed)
        [NSFileManager.defaultManager removeItemAtPath:sqlFilePath error:nil];

outside the branch that asked, so the file was deleted whether or not the person
at the keyboard agreed — and off the main thread, where no alert is shown at all,
without a word. It also ran for every cause alike: a file the process cannot
read, or one on a volume that is not mounted, or a cloud file that has not been
downloaded, is intact and opens once the cause is gone. Replacing it there
destroys a database that was never damaged.
"""
from pathlib import Path
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
failures = []
recovery = root / 'Horos/Sources/IndexRecovery.swift'
managed = (root / 'Nitrogen/Sources/N2ManagedDatabase.mm').read_bytes().decode('latin1')

DRIVER = '''
import CoreData
import Foundation

func emit(_ key: String, _ value: String) { print("\\(key)\\t\\(value)") }

func cocoa(_ code: Int) -> NSError { NSError(domain: NSCocoaErrorDomain, code: code) }
func posix(_ code: Int32) -> NSError { NSError(domain: NSPOSIXErrorDomain, code: Int(code)) }

let corrupt = cocoa(NSFileReadCorruptFileError)
let denied = cocoa(NSFileReadNoPermissionError)
let missing = cocoa(NSFileReadNoSuchFileError)
let migration = cocoa(NSMigrationMissingMappingModelError)
// Core Data reports the real cause underneath a generic one often enough to matter.
let wrapped = NSError(domain: NSCocoaErrorDomain, code: 134060,
                      userInfo: [NSUnderlyingErrorKey: posix(EACCES)])

for (name, error) in [("corrupt", corrupt), ("denied", denied), ("missing", missing),
                      ("migration", migration), ("wrapped", wrapped)] {
    emit("cause." + name, IndexRecovery.cause(forError: error))
    emit("aside." + name, IndexRecovery.indexCanBeSetAside(forError: error) ? "yes" : "no")
}
emit("cause.none", IndexRecovery.cause(forError: nil))
emit("aside.none", IndexRecovery.indexCanBeSetAside(forError: nil) ? "yes" : "no")

emit("says.corrupt", IndexRecovery.diagnosis(forError: corrupt, path: "/db/Database.sql"))
emit("says.denied", IndexRecovery.diagnosis(forError: denied, path: "/db/Database.sql"))

// The preserved name is beside the file and is not the file.
let preserved = IndexRecovery.preservedPath(forIndexAtPath: "/db/Database.sql")
emit("preserved.beside", preserved.hasPrefix("/db/Database.sql.unreadable-") ? "yes" : "no")
emit("preserved.differs", preserved == "/db/Database.sql" ? "no" : "yes")

// And the count of what a rebuild would have to work from.
let manager = FileManager.default
let base = URL(fileURLWithPath: NSTemporaryDirectory())
    .appendingPathComponent("horos-recovery-" + UUID().uuidString)
let images = base.appendingPathComponent("DATABASE.noindex").appendingPathComponent("10000")
try? manager.createDirectory(at: images, withIntermediateDirectories: true)
for n in 1...4 {
    manager.createFile(atPath: images.appendingPathComponent("\\(n).dcm").path, contents: Data("x".utf8))
}
emit("recoverable", "\\(IndexRecovery.recoverableFileCount(besideIndexAtPath: base.appendingPathComponent("Database.sql").path))")
emit("recoverable.none", "\\(IndexRecovery.recoverableFileCount(besideIndexAtPath: "/nowhere/Database.sql"))")
try? manager.removeItem(at: base)
'''

results = {}
if not recovery.exists():
    failures.append('there is no index recovery policy')
else:
    swiftc = subprocess.run(['xcrun', '--sdk', 'macosx', '-f', 'swiftc'], capture_output=True, text=True)
    if swiftc.returncode != 0:
        failures.append('no swiftc here: %s' % (swiftc.stderr or '').strip())
    else:
        with tempfile.TemporaryDirectory(prefix='horos-recovery-') as directory:
            # Top-level statements are only allowed in a file called main.swift.
            (Path(directory) / 'main.swift').write_text(DRIVER)
            binary = Path(directory) / 'recovery'
            built = subprocess.run(['xcrun', '--sdk', 'macosx', 'swiftc', '-o', str(binary),
                                    str(recovery), str(Path(directory) / 'main.swift')],
                                   capture_output=True, text=True)
            if built.returncode != 0:
                failures.append('the recovery policy does not compile:\n%s' % built.stderr[-1500:])
            else:
                run = subprocess.run([str(binary)], capture_output=True, text=True)
                if run.returncode != 0:
                    failures.append('the driver failed: %s' % run.stderr[-800:])
                for line in run.stdout.splitlines():
                    key, _, value = line.partition('\t')
                    results[key] = value

if results:
    expected = {
        'cause.corrupt': 'corrupt', 'aside.corrupt': 'yes',
        'cause.migration': 'migration', 'aside.migration': 'yes',
        # Intact files. Replacing either of these destroys a database that works.
        'cause.denied': 'permissions', 'aside.denied': 'no',
        'cause.missing': 'unavailable', 'aside.missing': 'no',
        'cause.wrapped': 'permissions', 'aside.wrapped': 'no',
        'cause.none': 'unknown', 'aside.none': 'no',
        'preserved.beside': 'yes', 'preserved.differs': 'yes',
        'recoverable': '4', 'recoverable.none': '-1',
    }
    for key, want in expected.items():
        got = results.get(key)
        if got != want:
            failures.append('%s: %r, expected %r' % (key, got, want))
    for key in ('says.corrupt', 'says.denied'):
        if 'Database.sql' not in results.get(key, ''):
            failures.append('%s does not name the file' % key)
    if results.get('says.corrupt') == results.get('says.denied'):
        failures.append('a corrupted index and one that cannot be read are reported identically')

# --- and the database has to act on it ---------------------------------------
if 'HorosIndexRecovery' not in managed:
    failures.append('the store failure path does not consult the recovery policy')
at = managed.find('if (!pStore && i == 1)')
window = managed[at:at + 3000] if at >= 0 else ''
if not window:
    failures.append('the branch that handles a store that will not open is gone')
else:
    if 'removeItemAtPath:sqlFilePath' in window:
        failures.append('the index is still deleted when it will not open')
    if 'moveItemAtPath:sqlFilePath' not in window:
        failures.append('the index that will not open is not kept anywhere')
    if 'indexCanBeSetAsideForError' not in window:
        failures.append('every cause is treated as a damaged file, so an intact index behind a '
                        'permission or availability problem is replaced')
    if 'recoverableFileCountBesideIndexAtPath' not in window:
        failures.append('nothing counts what a rebuild would have to work from, and that count '
                        'can only be taken before the index is replaced')

for failure in failures:
    print('FAIL: %s' % failure)
if failures:
    sys.exit(1)
print('ok: an index that will not open is diagnosed by cause, kept beside itself when it is the '
      'damaged one, and left untouched when it is not')
