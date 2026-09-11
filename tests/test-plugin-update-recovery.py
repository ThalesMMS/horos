#!/usr/bin/env python3
"""An interrupted or incompatible plugin update keeps a usable copy, and a
failed start does not take the database with it.

Issue #159: Horos Cloud (and any other plugin) can be updated in place. The
atomic swap already publishes a complete bundle, but it then deleted the
previous copy, so a candidate that passed preflight and then broke startup left
nothing to go back to. The bundled Cloud unzip wrote into the live plugins
folder and treated a disabled copy as missing, so safe deactivation did not
stick. A leftover Loading file still offered to rebuild the database even when
the crash note already named the plugin.
"""
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
failures = []

install = (root / 'Horos/Sources/HorosPluginInstall.h').read_text()
manager = (root / 'Horos/Sources/PluginManager.m').read_bytes().decode('latin1')
app = (root / 'Horos/Sources/AppController.m').read_bytes().decode('latin1')
swift = root / 'Horos/Sources/PluginUpdateRecovery.swift'

if not swift.exists():
    failures.append('PluginUpdateRecovery.swift is gone; the update recovery policy has no home')

# --- previous copy survives a successful publication --------------------------
if 'HorosPluginPreviousPath' not in install:
    failures.append('the installer has no stable place for the previous working plugin')
if install.count('removeItemAtPath:staging') and '.horos-plugin-previous' not in install:
    failures.append('successful publication still deletes the previous plugin with the staging directory')

# --- Cloud auto-deploy must not undo disable or unzip onto the live folder ----
at = manager.find('+ (void) deployHorosCloudPluginAtPath:')
deploy = manager[at:at + 4500] if at >= 0 else ''
if not deploy:
    failures.append('bundled Horos Cloud deploy is gone')
else:
    if 'HOROSCLOUD_PLUGIN_DEPLOYED' not in deploy:
        failures.append('Cloud deploy no longer records that the bundled copy was already offered')
    if 'setBool:' not in deploy and 'setObject:' not in deploy:
        failures.append('Cloud deploy never records HOROSCLOUD_PLUGIN_DEPLOYED, so a removed or disabled copy is forced back')
    if 'HorosInstallPlugin' not in deploy:
        failures.append('Cloud deploy does not publish through the atomic installer')
    if 'inactiveDirectories' not in deploy and 'inactiveContains' not in deploy:
        failures.append('Cloud deploy does not look in the Disabled folders before unzipping again')
    if 'shouldDeployBundledCloud' not in deploy:
        failures.append('Cloud deploy does not ask the recovery policy whether a bundled copy should be installed')
    # The live plugins directory must not be unzip's -d target.
    if re.search(r'setArguments:[^\n]*-d', deploy) or (
            '[aTask setLaunchPath:@"/usr/bin/unzip"]' in deploy and
            'stringByDeletingLastPathComponent' in deploy):
        failures.append('Cloud deploy still unzips onto the live plugins folder')

# --- crash recovery: plugin-less, restore, no database ------------------------
at = manager.find('NSString *pluginCrash = [PluginManager crashMarkerPath];')
recovery = manager[at:at + 3200] if at >= 0 else ''
if not recovery:
    failures.append('startup recovery no longer reads the crash note')
else:
    if 'setRunOsiriXInProtectedMode' not in recovery:
        failures.append('a plugin crash does not enter plugin-less mode for the rest of the session')
    if 'restorePrevious' not in recovery:
        failures.append('recovery cannot put the previous working plugin back')
    if 'inactivePathForPluginAt' not in recovery:
        failures.append('recovery does not work out where to disable the plugin to')
    if 'movePluginFromPath' not in recovery:
        failures.append('recovery does not move the plugin anywhere when disabling')
    if re.search(r'removeItemAtPath:\s*pluginCrashPath', recovery):
        failures.append('recovery still deletes the plugin')
    if 'removeItemAtPath: pluginCrash error' not in recovery:
        failures.append('recovery leaves the crash note behind')
    for forbidden in ('DicomDatabase', 'Database.sql', 'DATABASEPATH', 'NEEDTOREBUILD', 'COMPLETEREBUILD'):
        if forbidden in recovery:
            failures.append('plugin recovery touches %s; a plugin must not take the database with it' % forbidden)

# --- leftover Loading file is not a corrupt database when a plugin is named ---
loading_at = app.find('stringByAppendingPathComponent:@"Loading"]')
loading = app[loading_at:loading_at + 1800] if loading_at >= 0 else ''
if not loading:
    failures.append('the startup Loading file check is gone')
else:
    if 'crashMarkerPath' not in loading:
        failures.append('the Loading dialog does not look at the plugin crash note')
    if 'shouldOfferDatabaseRebuild' not in loading:
        failures.append('the Loading dialog still offers a database rebuild without asking whether a plugin failed')

if failures:
    for failure in failures:
        print('FAIL: %s' % failure)
    # Keep going into the Swift/C harness only when the sources exist; a missing
    # Swift file is already recorded above.
    if not swift.exists():
        sys.exit(1)

main = r'''import Foundation

let destination = "/Users/somebody/Library/Application Support/Horos/Plugins/HorosCloud.horosplugin"
let previous = PluginUpdateRecovery.previousPath(forDestination: destination)
assert(previous.hasSuffix("/.horos-plugin-previous/HorosCloud.horosplugin"), previous)
assert((previous as NSString).deletingLastPathComponent.hasSuffix("/Plugins/.horos-plugin-previous"), previous)

assert(PluginUpdateRecovery.shouldEnterPluginLessMode(markerExists: true))
assert(!PluginUpdateRecovery.shouldEnterPluginLessMode(markerExists: false))

assert(PluginUpdateRecovery.shouldOfferDatabaseRebuild(loadingFileExists: true, pluginMarkerExists: false))
assert(!PluginUpdateRecovery.shouldOfferDatabaseRebuild(loadingFileExists: true, pluginMarkerExists: true))
assert(!PluginUpdateRecovery.shouldOfferDatabaseRebuild(loadingFileExists: false, pluginMarkerExists: true))
assert(!PluginUpdateRecovery.shouldOfferDatabaseRebuild(loadingFileExists: false, pluginMarkerExists: false))

assert(PluginUpdateRecovery.shouldDeployBundledCloud(alreadyDeployed: false, activeContainsCloud: false, inactiveContainsCloud: false))
assert(!PluginUpdateRecovery.shouldDeployBundledCloud(alreadyDeployed: true, activeContainsCloud: false, inactiveContainsCloud: false))
assert(!PluginUpdateRecovery.shouldDeployBundledCloud(alreadyDeployed: false, activeContainsCloud: true, inactiveContainsCloud: false))
assert(!PluginUpdateRecovery.shouldDeployBundledCloud(alreadyDeployed: false, activeContainsCloud: false, inactiveContainsCloud: true))
assert(PluginUpdateRecovery.isCloudPluginName("HorosCloud"))
assert(PluginUpdateRecovery.isCloudPluginName("horoscloud.horosplugin"))
assert(!PluginUpdateRecovery.isCloudPluginName("TotalSegmentator"))

let restore = PluginUpdateRecovery.explanation(pluginNamed: "HorosCloud.horosplugin", canRestore: true, canDisable: true)
assert(restore.contains("HorosCloud.horosplugin"), restore)
assert(restore.lowercased().contains("previous") || restore.lowercased().contains("restore"), restore)
assert(restore.lowercased().contains("disabl"), restore)
assert(!restore.lowercased().contains("delete"), restore)
assert(!restore.lowercased().contains("database"), restore)
assert(!restore.lowercased().contains("rebuild"), restore)
let disableOnly = PluginUpdateRecovery.explanation(pluginNamed: "HorosCloud.horosplugin", canRestore: false, canDisable: true)
assert(disableOnly.contains("HorosCloud.horosplugin"), disableOnly)
assert(disableOnly.lowercased().contains("disabl"), disableOnly)
assert(!disableOnly.lowercased().contains("delete"), disableOnly)

print("PASS: previous path, plugin-less mode, no database rebuild, Cloud deploy policy, and a sentence that names the plugin")
'''

program = r'''
#import <Foundation/Foundation.h>
#import "HorosPluginInstall.h"
int main(int argc, char **argv) { @autoreleasepool {
 NSString *root = [NSString stringWithUTF8String:argv[1]];
 NSString *source = [root stringByAppendingPathComponent:@"new/QAUniversal.horosplugin"];
 NSString *destination = [root stringByAppendingPathComponent:@"installed/QAUniversal.horosplugin"];
 NSString *payload = @"Contents/Resources/seal.txt";
 NSData *old = [NSData dataWithContentsOfFile:[destination stringByAppendingPathComponent:payload]];
 NSData *updated = [NSData dataWithContentsOfFile:[source stringByAppendingPathComponent:payload]];
 NSCAssert(old && updated && ![old isEqual:updated], @"fixture versions must differ");
 NSError *error = nil;
 NSCAssert(HorosInstallPlugin(source, destination, &error), @"valid update must publish: %@", error);
 NSCAssert([[NSData dataWithContentsOfFile:[destination stringByAppendingPathComponent:payload]] isEqual:updated], @"published version must be the new one");
 NSString *previous = HorosPluginPreviousPath(destination);
 NSCAssert([[NSData dataWithContentsOfFile:[previous stringByAppendingPathComponent:payload]] isEqual:old], @"successful update must keep the previous working plugin");
 for (NSString *entry in [[NSFileManager defaultManager] contentsOfDirectoryAtPath:destination.stringByDeletingLastPathComponent error:NULL])
  NSCAssert(![entry hasPrefix:@".horos-plugin-update-"], @"normal completion must clean staging");
 NSCAssert(HorosRestorePreviousPlugin(destination, &error), @"restore must put the previous plugin back: %@", error);
 NSCAssert([[NSData dataWithContentsOfFile:[destination stringByAppendingPathComponent:payload]] isEqual:old], @"restore must publish the previous working plugin");
 puts("PASS: published update keeps the previous plugin and restore puts it back");
} }
'''

with tempfile.TemporaryDirectory(prefix='horos-plugin-update-recovery-') as directory:
    p = Path(directory)
    if swift.exists():
        (p / 'main.swift').write_text(main)
        compiled = subprocess.run(
            ['swiftc', str(swift), str(p / 'main.swift'), '-o', str(p / 'policy')],
            capture_output=True, text=True)
        if compiled.returncode != 0:
            print('FAIL: PluginUpdateRecovery.swift did not compile')
            print(compiled.stderr)
            failures.append('PluginUpdateRecovery.swift did not compile')
        else:
            ran = subprocess.run([str(p / 'policy')], capture_output=True, text=True)
            sys.stdout.write(ran.stdout)
            sys.stderr.write(ran.stderr)
            if ran.returncode != 0:
                failures.append('PluginUpdateRecovery policy assertions failed')

    subprocess.run(['python3', str(root / 'tools/generate-plugin-load-fixtures.py'),
                    str(p / 'fixtures')], check=True)
    data = p / 'fs'
    for parent in ('new', 'installed'):
        shutil.copytree(p / 'fixtures/QAUniversal.horosplugin',
                        data / parent / 'QAUniversal.horosplugin')
    (data / 'new/QAUniversal.horosplugin/Contents/Resources/seal.txt').write_text(
        'Updated synthetic resource')
    subprocess.run(['codesign', '--force', '--sign', '-',
                    str(data / 'new/QAUniversal.horosplugin')],
                   check=True, capture_output=True)
    (p / 'retain.m').write_text(program)
    compiled = subprocess.run(
        ['xcrun', 'clang', '-framework', 'Foundation', '-framework', 'Security',
         '-fsanitize=address', '-I', str(root / 'Horos/Sources'),
         str(p / 'retain.m'), '-o', str(p / 'retain')],
        capture_output=True, text=True)
    if compiled.returncode != 0:
        print('FAIL: previous-version installer harness did not compile')
        print(compiled.stderr)
        failures.append('previous-version installer harness did not compile')
    else:
        ran = subprocess.run([str(p / 'retain'), str(data)], capture_output=True, text=True)
        sys.stdout.write(ran.stdout)
        sys.stderr.write(ran.stderr)
        if ran.returncode != 0:
            failures.append('previous-version installer harness failed')

    leftover = p / 'leftover'
    installed = leftover / 'QAUniversal.horosplugin'
    shutil.copytree(p / 'fixtures/QAUniversal.horosplugin', installed)
    staging = leftover / '.horos-plugin-update-deadbeef' / 'QAUniversal.horosplugin'
    shutil.copytree(p / 'fixtures/QAUniversal.horosplugin', staging)
    (staging / 'Contents/Resources/seal.txt').write_text('Previous working copy')
    if swift.exists() and (p / 'policy').exists():
        adopt = r'''import Foundation
let root = CommandLine.arguments[1]
let adopted = PluginUpdateRecovery.adoptLeftoverStaging(inDirectory: root)
assert(adopted != nil, "leftover staging after a published swap must become the previous copy")
let previous = PluginUpdateRecovery.previousPath(forDestination: root + "/QAUniversal.horosplugin")
assert(adopted == previous, adopted ?? "nil")
assert((try? String(contentsOfFile: previous + "/Contents/Resources/seal.txt")) == "Previous working copy")
assert(!FileManager.default.fileExists(atPath: root + "/.horos-plugin-update-deadbeef"))
PluginUpdateRecovery.discardPrevious(forDestination: root + "/QAUniversal.horosplugin")
assert(!FileManager.default.fileExists(atPath: previous))
print("PASS: leftover staging is adopted as the previous plugin and can be discarded")
'''
        adopt_dir = p / 'adopt-main'
        adopt_dir.mkdir()
        (adopt_dir / 'main.swift').write_text(adopt)
        compiled = subprocess.run(
            ['swiftc', str(swift), str(adopt_dir / 'main.swift'), '-o', str(p / 'adopt')],
            capture_output=True, text=True)
        if compiled.returncode != 0:
            print('FAIL: leftover-staging harness did not compile')
            print(compiled.stderr)
            failures.append('leftover-staging harness did not compile')
        else:
            ran = subprocess.run([str(p / 'adopt'), str(leftover)], capture_output=True, text=True)
            sys.stdout.write(ran.stdout)
            sys.stderr.write(ran.stderr)
            if ran.returncode != 0:
                failures.append('leftover-staging harness failed')

if failures:
    for failure in failures:
        print('FAIL: %s' % failure)
    sys.exit(1)
print('ok: previous plugin kept, Cloud deploy will not force itself back, plugin-less start leaves the database alone')
