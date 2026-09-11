#!/usr/bin/env python3
"""A plugin that breaks startup can be switched off, and the note saying which one it was is read by somebody.

`PluginManager` writes the path of each plugin before opening its bundle and
removes it afterwards, so a file left behind names the plugin that was loading
when the application went away. The note was written to `/tmp/PluginCrashed`
while the startup check read `Plugin_Loading` in the application support folder:
two different files, so nothing ever read what was written and the recovery
could not run at all. `/tmp` was the wrong place besides - writable by everybody
on the machine, and shared by every Horos and OsiriX on it.

One file now, inside the folder Horos keeps its plugins in, one per bundle
identifier so a development build and an installed one do not accuse each other.
And the recovery offers to *disable* the plugin - move it to the "Disabled"
folder beside the one it is in, which Plugin Manager can undo - instead of
deleting the copy the person installed.
"""
from pathlib import Path
import re
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
failures = []

source = root / 'Horos/Sources/PluginQuarantine.swift'
if not source.exists():
    print('FAIL: %s is gone' % source.name)
    sys.exit(1)

manager = (root / 'Horos/Sources/PluginManager.m').read_bytes().decode('latin1')

# --- one file, and not in /tmp ------------------------------------------------
if 'PluginCrashed' in manager:
    failures.append('the crash note is still written to /tmp, where every user and every copy of '
                    'Horos and OsiriX on the machine shares one file')
if manager.count('+ (NSString*) crashMarkerPath') != 1:
    failures.append('there is no single place that says where the crash note lives')
for what, near in (('startProtectForCrashWithPath', 'writes'),
                   ('endProtectForCrash', 'removes')):
    at = manager.find('+ (void) %s' % what)
    body = manager[at:at + 700] if at >= 0 else ''
    if 'crashMarkerPath' not in body:
        failures.append('%s does not use crashMarkerPath, so the note %s a file nobody reads'
                        % (what, near))

# --- the recovery disables, and does not delete -------------------------------
at = manager.find('NSString *pluginCrash = [PluginManager crashMarkerPath];')
recovery = manager[at:at + 3600] if at >= 0 else ''
if not recovery:
    failures.append('the startup recovery no longer reads the crash note')
else:
    if 'inactivePathForPluginAt' not in recovery:
        failures.append('the recovery does not work out where to disable the plugin to')
    if 'movePluginFromPath' not in recovery:
        failures.append('the recovery does not move the plugin anywhere')
    if re.search(r'removeItemAtPath:\s*pluginCrashPath', recovery):
        failures.append('the recovery still deletes the plugin, which cannot be undone')
    # The note itself is cleared either way, or the alert returns every start.
    if 'removeItemAtPath: pluginCrash error' not in recovery:
        failures.append('the recovery leaves the note behind, so it would ask again every start')
    # Nothing in here may touch the database: a plugin that breaks startup is not
    # a reason to lose a database, which is what people were doing instead.
    for forbidden in ('DicomDatabase', 'Database.sql', 'DATABASEPATH'):
        if forbidden in recovery:
            failures.append('the recovery touches %s; disabling a plugin must not' % forbidden)

if '+ (NSString*) crashMarkerPath;' not in (root / 'Horos/Sources/PluginManager.h').read_bytes().decode('latin1'):
    failures.append('crashMarkerPath is not declared, so nothing outside can ask where the note is')

for failure in failures:
    print('FAIL: %s' % failure)

main = r'''import Foundation

// One note per bundle identifier, inside the folder given.
let support = "/Users/somebody/Library/Application Support/Horos"
let marker = PluginQuarantine.markerPath(inDirectory: support, forBundle: "org.horosproject.horos")
assert(marker == support + "/Plugin_Loading.org.horosproject.horos", marker)
let development = PluginQuarantine.markerPath(inDirectory: support,
                                              forBundle: "org.horosproject.horos.local-development")
assert(development != marker, "two builds must not share one note")
// A bundle with no identifier still has somewhere to write, and cannot escape
// the directory it was given.
let anonymous = PluginQuarantine.markerPath(inDirectory: support, forBundle: nil)
assert(anonymous == support + "/Plugin_Loading.unknown", anonymous)
assert(PluginQuarantine.markerPath(inDirectory: support, forBundle: "a/b")
       == support + "/Plugin_Loading.a_b")

// Where a plugin goes when it is switched off: the Disabled folder paired with
// the one it is in, by position, the way PluginManager lists them.
let active = ["/Users/somebody/Library/Application Support/Horos/Plugins/",
              "/Library/Application Support/Horos/Plugins/",
              "/Applications/Horos.app/Contents/PlugIns"]
let inactive = ["/Users/somebody/Library/Application Support/Horos/Plugins Disabled/",
                "/Library/Application Support/Horos/Plugins Disabled/",
                "/Applications/Horos.app/Contents/PlugIns Disabled"]

let user = PluginQuarantine.inactivePath(
    forPluginAt: "/Users/somebody/Library/Application Support/Horos/Plugins/Thing.horosplugin",
    active: active, inactive: inactive)
assert(user == "/Users/somebody/Library/Application Support/Horos/Plugins Disabled/Thing.horosplugin",
       user ?? "nil")

// Trailing slashes are how PluginManager spells those directories; they must not
// decide the answer.
let inside = PluginQuarantine.inactivePath(
    forPluginAt: "/Applications/Horos.app/Contents/PlugIns/Thing.horosplugin",
    active: active, inactive: inactive)
assert(inside == "/Applications/Horos.app/Contents/PlugIns Disabled/Thing.horosplugin", inside ?? "nil")

// A plugin loaded from somewhere else has nowhere to be disabled to, and saying
// so is better than moving it somewhere unrelated.
assert(PluginQuarantine.inactivePath(forPluginAt: "/tmp/Thing.horosplugin",
                                     active: active, inactive: inactive) == nil)
assert(PluginQuarantine.inactivePath(forPluginAt: "/", active: active, inactive: inactive) == nil)
// And a list that has fewer Disabled folders than active ones is not guessed at.
assert(PluginQuarantine.inactivePath(
    forPluginAt: "/Applications/Horos.app/Contents/PlugIns/Thing.horosplugin",
    active: active, inactive: Array(inactive.prefix(1))) == nil)

// The sentence the person reads says which plugin, and what disabling does.
let canDisable = PluginQuarantine.explanation(pluginNamed: "Thing.horosplugin", canDisable: true)
assert(canDisable.contains("Thing.horosplugin"), canDisable)
assert(canDisable.lowercased().contains("disabl"), canDisable)
assert(canDisable.contains("nothing else is touched"), canDisable)
assert(!canDisable.lowercased().contains("delete"), canDisable)
let cannot = PluginQuarantine.explanation(pluginNamed: "Thing.horosplugin", canDisable: false)
assert(cannot.contains("Thing.horosplugin"), cannot)
assert(cannot.contains("cannot disable"), cannot)

print("PASS: one note per build, a Disabled folder that matches, and a sentence that names the plugin")
'''

with tempfile.TemporaryDirectory(prefix='horos-plugin-quarantine-') as tmp:
    p = Path(tmp)
    (p / 'main.swift').write_text(main)
    subprocess.run(['swiftc', str(source), str(p / 'main.swift'), '-o', str(p / 'test')], check=True)
    subprocess.run([str(p / 'test')], check=True)

if failures:
    sys.exit(1)
print('ok: the crash note is read where it is written, and the recovery disables instead of deleting')
