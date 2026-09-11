#!/usr/bin/env python3
"""A database on a volume that goes away says so, and survives it.

An external disk ejected under a running database makes every directory the
database asks for fail, and the file system's own answer is *"You don't have
permission to save the file"* — which sends the reader to permissions they never
changed. The message named no path either, so there was nothing in it to act on:

    NSGenericException (in -[DicomDatabase initWithPath:context:mainDatabase:]):
        Couldn't create directory: You don't have permission to save the file

and the next thing in the log was a stack trace under `*************** WTF`.
"""
from pathlib import Path
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
failures = []
failure = root / 'Horos/Sources/StorageFailure.swift'
manager = (root / 'Nitrogen/Sources/NSFileManager+N2.mm').read_bytes().decode('latin1')
database = (root / 'Horos/Sources/DicomDatabase.mm').read_bytes().decode('latin1')

DRIVER = '''
import Foundation

func emit(_ key: String, _ value: String) { print("\\(key)\\t\\(value)") }

let denied = NSError(domain: NSCocoaErrorDomain, code: NSFileWriteNoPermissionError,
                     userInfo: [NSLocalizedDescriptionKey: "You don\\u{2019}t have permission to save the file"])

// A volume that is not mounted: the cause the file system does not name.
emit("gone", StorageFailure.reason(forError: denied, path: "/Volumes/NotThere/Horos Data"))
emit("volume", StorageFailure.volume(ofPath: "/Volumes/NotThere/Horos Data") ?? "nil")
emit("volume.boot", StorageFailure.volume(ofPath: "/Users/someone/Horos Data") ?? "nil")

// A place that is there and cannot be written.
let manager = FileManager.default
let base = URL(fileURLWithPath: NSTemporaryDirectory())
    .appendingPathComponent("horos-storage-" + UUID().uuidString)
try? manager.createDirectory(at: base, withIntermediateDirectories: true)
try? manager.setAttributes([.posixPermissions: 0o500], ofItemAtPath: base.path)
let inside = base.appendingPathComponent("Horos Data").path
emit("readonly.names-path", StorageFailure.reason(forError: denied, path: inside).contains(inside) ? "yes" : "no")
emit("readonly.says-writable", StorageFailure.reason(forError: denied, path: inside).contains("not writable") ? "yes" : "no")
try? manager.setAttributes([.posixPermissions: 0o700], ofItemAtPath: base.path)

// The nearest folder that is actually there.
emit("ancestor", StorageFailure.deepestExistingAncestor(of: base.appendingPathComponent("a/b/c").path) ?? "nil")
emit("ancestor.is-base", (StorageFailure.deepestExistingAncestor(of: base.appendingPathComponent("a/b/c").path) == base.path) ? "yes" : "no")
try? manager.removeItem(at: base)
'''

results = {}
if not failure.exists():
    failures.append('there is no storage failure diagnosis')
else:
    swiftc = subprocess.run(['xcrun', '--sdk', 'macosx', '-f', 'swiftc'], capture_output=True, text=True)
    if swiftc.returncode != 0:
        failures.append('no swiftc here: %s' % (swiftc.stderr or '').strip())
    else:
        with tempfile.TemporaryDirectory(prefix='horos-storage-') as directory:
            # Top-level statements are only allowed in a file called main.swift.
            (Path(directory) / 'main.swift').write_text(DRIVER)
            binary = Path(directory) / 'storage'
            built = subprocess.run(['xcrun', '--sdk', 'macosx', 'swiftc', '-o', str(binary),
                                    str(failure), str(Path(directory) / 'main.swift')],
                                   capture_output=True, text=True)
            if built.returncode != 0:
                failures.append('the storage diagnosis does not compile:\n%s' % built.stderr[-1500:])
            else:
                run = subprocess.run([str(binary)], capture_output=True, text=True)
                if run.returncode != 0:
                    failures.append('the driver failed: %s' % run.stderr[-800:])
                for line in run.stdout.splitlines():
                    key, _, value = line.partition('\t')
                    results[key] = value

if results:
    gone = results.get('gone', '')
    if '/Volumes/NotThere/Horos Data' not in gone:
        failures.append('the message about an unmounted volume does not name the path: %r' % gone)
    if 'not mounted' not in gone:
        failures.append('an ejected volume is still reported as whatever the file system said, '
                        'which is a permission problem it is not: %r' % gone)
    expected = {
        'volume': '/Volumes/NotThere',
        'volume.boot': 'nil',
        'readonly.names-path': 'yes',
        'readonly.says-writable': 'yes',
        'ancestor.is-base': 'yes',
    }
    for key, want in expected.items():
        got = results.get(key)
        if got != want:
            failures.append('%s: %r, expected %r' % (key, got, want))

# --- and the file manager has to use it --------------------------------------
if 'HorosStorageFailure' not in manager:
    failures.append('the directory that cannot be created still reports the raw file system '
                    'message, with no path in it')
if "Couldn't create directory: %@" in manager:
    failures.append('the old pathless message is still there')

at = manager.find('is writable == NO')
window = manager[max(0, at - 900):at + 200] if at >= 0 else ''
if window and 'containsObject' not in window:
    failures.append('the read-only warning is still logged once per asking part, more than '
                    'twenty times a launch, which buries everything else')

# --- and a database that never opened says what happened ---------------------
if 'N2LogStackTrace( @"*************** WTF")' in database:
    failures.append('a database released before it finished opening still logs a stack trace '
                    'under "WTF" instead of saying what happened')

for failure_text in failures:
    print('FAIL: %s' % failure_text)
if failures:
    sys.exit(1)
print('ok: a directory that cannot be made names its path and says whether the volume is gone, '
      'the place is unwritable, or something else')
