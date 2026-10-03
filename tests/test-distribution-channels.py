#!/usr/bin/env python3
"""Compile both channel policies and verify their behavior and signed build entitlements."""
import private_tmpdir  # noqa: F401
from pathlib import Path
import os
import plistlib
import re
import subprocess
import tempfile
import uuid

root = Path(__file__).resolve().parents[1]
sources = root / 'Horos/Sources'

with tempfile.TemporaryDirectory(prefix='distribution-channels-') as temporary:
    work = Path(temporary)
    stub = work / 'PluginManagerController.swift'
    stub.write_text('import AppKit\n@MainActor final class PluginManagerController: NSWindowController {}\n')
    main = work / 'main.swift'
    main.write_text('''import AppKit
let domain = Bundle.main.bundleIdentifier!
defer { UserDefaults.standard.removePersistentDomain(forName: domain) }
UserDefaults.standard.set(false, forKey: "MACAPPSTORE")
UserDefaults.standard.set(true, forKey: "CheckHorosUpdates")
UserDefaults.standard.set(true, forKey: "checkForUpdatesPlugins")
DistributionChannel.configurePreferences()
let store = CommandLine.arguments.last == "appstore"
precondition(DistributionChannel.isAppStore == store)
precondition(DistributionChannel.supportsExternalPlugins == !store)
precondition(DistributionChannel.supportsGitHubUpdates == !store)
precondition(UserDefaults.standard.bool(forKey: "MACAPPSTORE") == store)
if store {
    precondition(!UserDefaults.standard.bool(forKey: "CheckHorosUpdates"))
    precondition(!UserDefaults.standard.bool(forKey: "checkForUpdatesPlugins"))
}
// Mutable defaults do not change the compiled channel's capabilities.
UserDefaults.standard.set(!store, forKey: "MACAPPSTORE")
precondition(DistributionChannel.supportsExternalPlugins == !store)
let menu = NSMenu()
let update = NSMenuItem(title: "Update", action: NSSelectorFromString("checkForUpdates:"), keyEquivalent: "")
menu.addItem(update)
let plugins = NSMenuItem(title: "Plugins", action: nil, keyEquivalent: "")
let submenu = NSMenu()
let manager = NSMenuItem(title: "Manager", action: NSSelectorFromString("showWindow:"), keyEquivalent: "")
let controller = PluginManagerController(window: nil)
manager.target = controller
submenu.addItem(manager)
plugins.submenu = submenu
menu.addItem(plugins)
let viewer = NSMenuItem(title: "Viewer", action: nil, keyEquivalent: "")
menu.addItem(viewer)
DistributionChannel.configureMenu(menu)
precondition(menu.items.count == (store ? 1 : 3))
precondition(menu.items.last === viewer)
print("channel behavior passed: \\(store ? "appstore" : "github")")
''')
    for channel in ('github', 'appstore'):
        app = work / f'{channel}.app'
        (app / 'Contents/MacOS').mkdir(parents=True)
        (app / 'Contents/Info.plist').write_bytes(plistlib.dumps({
            'CFBundleIdentifier': 'test.isis.channels.' + uuid.uuid4().hex,
            'CFBundleExecutable': 'test', 'CFBundlePackageType': 'APPL'}))
        program = app / 'Contents/MacOS/test'
        command = ['xcrun', 'swiftc', '-swift-version', '6', '-target', 'arm64-apple-macos26.0',
                   str(sources / 'DistributionChannel.swift'), str(sources / 'SandboxFileAccess.swift'),
                   str(stub), str(main), '-o', str(program)]
        if channel == 'appstore':
            command += ['-D', 'MACAPPSTORE']
        subprocess.run(command, check=True)
        subprocess.run([str(program), channel], check=True)

    absent = work / 'StoreExcluded.dylib'
    subprocess.run(['xcrun', 'swiftc', '-emit-library', '-D', 'MACAPPSTORE',
                    *[str(sources / f'{name}.swift') for name in ('UpdateArchive', 'UpdateInstaller', 'UpdateFeedClient')],
                    '-o', str(absent)], check=True)
    symbols = subprocess.check_output(['nm', '-g', str(absent)], text=True)
    assert all(name not in symbols for name in ('HorosUpdateInstaller', 'UpdateFeedClient', 'UpdateDownload'))

    # Execute the archive's real signing phase on a disposable helper.
    project = (root / 'Horos.xcodeproj/project.pbxproj').read_text()
    phase = re.search(r'CED88262125064F70085A861 /\* CodeSigning \*/ = \{(.*?)\n\t\t\};', project, re.S).group(1)
    signing = re.search(r'shellScript = "(.*)";', phase).group(1).encode().decode('unicode_escape')
    fixture = work / 'helper.c'
    fixture.write_text('int main(void) { return 0; }\n')
    for channel, entitlements in [('github', 'Decompress/Decompress.entitlements'),
                                  ('appstore', 'Horos/Configuration/AppStoreHelper.entitlements')]:
        products = work / ('archive-' + channel)
        resources = products / 'Fixture.app/Contents/Resources'
        resources.mkdir(parents=True)
        helper = resources / 'helper'
        subprocess.run(['xcrun', 'clang', str(fixture), '-o', str(helper)], check=True)
        subprocess.run(['/bin/sh', '-c', signing], check=True, env={**os.environ,
            'CODE_SIGNING_ALLOWED': 'YES', 'TARGET_BUILD_DIR': str(products),
            'UNLOCALIZED_RESOURCES_FOLDER_PATH': 'Fixture.app/Contents/Resources',
            'SRCROOT': str(root), 'HOROS_HELPER_ENTITLEMENTS': entitlements,
            'EXPANDED_CODE_SIGN_IDENTITY': '-'})
        actual = plistlib.loads(subprocess.check_output(['codesign', '-d', '--entitlements', ':-', str(helper)],
                                                        stderr=subprocess.DEVNULL))
        expected = plistlib.loads((root / entitlements).read_bytes())
        assert actual == expected
        print(f'archive helper signing passed: {channel}')

store = plistlib.loads((root / 'Horos/Configuration/AppStore.entitlements').read_bytes())
assert store['com.apple.security.app-sandbox']
assert store['com.apple.security.network.client'] and store['com.apple.security.network.server']
assert store['com.apple.security.files.user-selected.read-write']
assert store['com.apple.security.files.bookmarks.app-scope']
assert not store.get('com.apple.security.cs.disable-library-validation')
helper = plistlib.loads((root / 'Horos/Configuration/AppStoreHelper.entitlements').read_bytes())
assert helper == {'com.apple.security.app-sandbox': True, 'com.apple.security.inherit': True}
assert not plistlib.loads((root / 'Horos/Horos.entitlements').read_bytes()).get('com.apple.security.app-sandbox')

# Optional artifacts come from the two real build entry points, not a fixture.
if os.environ.get('ISIS_VERIFY_CHANNEL_BUILDS') == '1':
    for channel, folder in [('github', 'Release'), ('appstore', 'AppStore')]:
        app = root / 'build' / folder / 'Isis DICOM Viewer.app'
        subprocess.run(['codesign', '--verify', '--deep', '--strict', str(app)], check=True)
        data = subprocess.check_output(['codesign', '-d', '--entitlements', ':-', str(app)], stderr=subprocess.DEVNULL)
        entitlements = plistlib.loads(data)
        assert bool(entitlements.get('com.apple.security.app-sandbox')) == (channel == 'appstore')
        info = plistlib.loads((app / 'Contents/Info.plist').read_bytes())
        if channel == 'appstore':
            symbols = subprocess.check_output(['nm', '-g', str(app / 'Contents/MacOS' / info['CFBundleExecutable'])], text=True)
            assert '_OBJC_CLASS_$_HorosUpdateInstaller' not in symbols
            assert '_OBJC_CLASS_$_HorosUpdateFeedClient' not in symbols
        print(f'signed artifact passed: {channel}')
print('distribution channel checks passed')
