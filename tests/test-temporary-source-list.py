#!/usr/bin/env python3
"""A database opened from a temporary place is not remembered as a source.

Every database the browser opens that is not already listed is written into the
`localDatabasePaths` preference, and that list is never cleaned. A CD is copied
under the user's temporary directory and opened from there, so inserting one left
a permanent entry pointing at a path that stops existing when the media is
ejected — or when the system empties its temporary folders, which it does on its
own. Those are the unavailable entries that accumulate and that removing the
media does not remove.

Measured before the change, through the XML-RPC `opendb` method against a
database under `$(getconf DARWIN_USER_TEMP_DIR)`:

    localDatabasePaths = ( { Description = "cd-source-test DB";
                             Path = "/private/var/folders/…/T/cd-source-test"; } )

`AppController` did prune three temporary prefixes by hand — `/tmp/`,
`/private/tmp/`, `/private/var/tmp/` — and missed the only one macOS actually
uses for the per-user temporary directory.
"""
from pathlib import Path
import re
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
failures = []
location = root / 'Horos/Sources/SourceLocation.swift'
sources = (root / 'Horos/Sources/BrowserController+Sources.m').read_bytes().decode('latin1')
browser = (root / 'Horos/Sources/BrowserController.m').read_bytes().decode('latin1')
app = (root / 'Horos/Sources/AppController.m').read_bytes().decode('latin1')

DRIVER = '''
import Foundation

func emit(_ key: String, _ value: String) { print("\\(key)\\t\\(value)") }

let temporary = NSTemporaryDirectory() + "cd-source-test"
emit("temp", SourceLocation.isTemporaryLocation(temporary) ? "yes" : "no")
// The path as it is written into the preference, resolved through /private.
emit("temp-private", SourceLocation.isTemporaryLocation(
        "/private/var/folders/vr/kh908gkn06jgh4yy6pxh59ym0000gn/T/cd-source-test") ? "yes" : "no")
emit("tmp", SourceLocation.isTemporaryLocation("/tmp/somewhere") ? "yes" : "no")
emit("volume", SourceLocation.isTemporaryLocation("/Volumes/SomeDisk") ? "yes" : "no")
emit("home", SourceLocation.isTemporaryLocation("/Users/someone/Documents") ? "yes" : "no")
emit("empty", SourceLocation.isTemporaryLocation("") ? "yes" : "no")
emit("nil", SourceLocation.isTemporaryLocation(nil) ? "yes" : "no")

let entries: [[String: Any]] = [
    ["Path": "/Volumes/SomeDisk", "Description": "External DB"],
    ["Path": temporary, "Description": "cd-source-test DB"],
    ["Path": "/Volumes/SomeDisk", "Description": "External DB again"],
    ["Description": "no path at all"],
]
let kept = SourceLocation.permanentEntries(in: entries, pathKey: "Path")
emit("kept", kept.compactMap { $0["Path"] as? String }.joined(separator: "|"))
emit("dropped", SourceLocation.temporaryEntries(in: entries, pathKey: "Path").count.description)
'''

results = {}
if not location.exists():
    failures.append('there is no rule for what a source location is worth remembering')
else:
    swiftc = subprocess.run(['xcrun', '--sdk', 'macosx', '-f', 'swiftc'], capture_output=True, text=True)
    if swiftc.returncode != 0:
        failures.append('no swiftc here: %s' % (swiftc.stderr or '').strip())
    else:
        with tempfile.TemporaryDirectory(prefix='horos-sources-') as directory:
            # Top-level statements are only allowed in a file called main.swift.
            (Path(directory) / 'main.swift').write_text(DRIVER)
            binary = Path(directory) / 'sources'
            built = subprocess.run(['xcrun', '--sdk', 'macosx', 'swiftc', '-o', str(binary),
                                    str(location), str(Path(directory) / 'main.swift')],
                                   capture_output=True, text=True)
            if built.returncode != 0:
                failures.append('the source location rule does not compile:\n%s' % built.stderr[-1500:])
            else:
                run = subprocess.run([str(binary)], capture_output=True, text=True)
                if run.returncode != 0:
                    failures.append('the driver failed: %s' % run.stderr[-800:])
                for line in run.stdout.splitlines():
                    key, _, value = line.partition('\t')
                    results[key] = value

if results:
    expected = {
        'temp': 'yes', 'temp-private': 'yes', 'tmp': 'yes',
        # An external disk is meant to be remembered, listed while it is away,
        # and removed deliberately.
        'volume': 'no', 'home': 'no', 'empty': 'no', 'nil': 'no',
        'kept': '/Volumes/SomeDisk',
        'dropped': '1',
    }
    for key, want in expected.items():
        got = results.get(key)
        if got != want:
            failures.append('%s: %r, expected %r' % (key, got, want))

# --- and the three places that touch the list have to use it ------------------
if 'HorosSourceLocation' not in sources:
    failures.append('opening a database from a temporary place still writes it into the list')
if 'HorosSourceLocation' not in browser:
    failures.append('the list is not cleaned of temporary entries when the browser opens')
if 'HorosSourceLocation' not in app:
    failures.append('the startup pass still prunes by a hand-written list of prefixes')

code = re.sub(r'//[^\n]*', '', app)
if 'hasPrefix: @"/private/var/tmp/"' in code:
    failures.append('the hand-written prefix list is still there, and it misses '
                    '/private/var/folders/.../T - the one macOS actually uses')

for failure in failures:
    print('FAIL: %s' % failure)
if failures:
    sys.exit(1)
print('ok: a database opened from a temporary place is not remembered, an entry already there is '
      'forgotten, and one on an external disk is kept even while the disk is away')
