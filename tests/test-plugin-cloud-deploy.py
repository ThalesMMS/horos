#!/usr/bin/env python3
"""The bundled Horos Cloud copy is unpacked aside and published, or left alone.

A disabled or already-offered Cloud plugin must not be written back into the
live plugins folder. An interrupted unzip must not leave a half-written
HorosCloud.horosplugin where the loader will find it.
"""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import zipfile

root = Path(__file__).resolve().parents[1]
swift = root / 'Horos/Sources/PluginUpdateRecovery.swift'
if not swift.exists():
    print('FAIL: PluginUpdateRecovery.swift is required for bundled Cloud deploy')
    sys.exit(1)

program = r'''import Foundation

let root = CommandLine.arguments[1]
let archive = root + "/HorosCloud.horosplugin.zip"
let plugins = root + "/Plugins"
let disabled = root + "/Plugins Disabled"
try FileManager.default.createDirectory(atPath: plugins, withIntermediateDirectories: true)
try FileManager.default.createDirectory(atPath: disabled, withIntermediateDirectories: true)

// Disabled copy: do not extract, do not touch the live folder.
assert(!PluginUpdateRecovery.shouldDeployBundledCloud(
    alreadyDeployed: false, activeContainsCloud: false, inactiveContainsCloud: true))
var error: NSError?
let skipped = PluginUpdateRecovery.prepareBundledCloud(
    fromArchive: archive, into: plugins, alreadyDeployed: false,
    activeContainsCloud: false, inactiveContainsCloud: true, error: &error)
assert(skipped == nil, skipped ?? "nil")
assert(!FileManager.default.fileExists(atPath: plugins + "/HorosCloud.horosplugin"))

// Already offered once: same.
let remembered = PluginUpdateRecovery.prepareBundledCloud(
    fromArchive: archive, into: plugins, alreadyDeployed: true,
    activeContainsCloud: false, inactiveContainsCloud: false, error: &error)
assert(remembered == nil)

// First offer: extract beside the live folder, never as the live plugin itself.
let prepared = PluginUpdateRecovery.prepareBundledCloud(
    fromArchive: archive, into: plugins, alreadyDeployed: false,
    activeContainsCloud: false, inactiveContainsCloud: false, error: &error)
assert(prepared != nil, error?.localizedDescription ?? "no error")
assert(prepared!.contains("HorosCloud.horosplugin"), prepared!)
assert(!prepared!.hasPrefix(plugins + "/HorosCloud.horosplugin"), prepared!)
assert(!FileManager.default.fileExists(atPath: plugins + "/HorosCloud.horosplugin"),
       "prepare must not publish into the live plugins folder")
assert(FileManager.default.fileExists(atPath: prepared! + "/Contents/Info.plist"))

print("PASS: bundled Cloud stays out of the live folder until atomic publication")
'''

with tempfile.TemporaryDirectory(prefix='horos-cloud-deploy-') as directory:
    p = Path(directory)
    subprocess.run(['python3', str(root / 'tools/generate-plugin-load-fixtures.py'),
                    str(p / 'fixtures')], check=True)
    cloud = p / 'HorosCloud.horosplugin'
    shutil.copytree(p / 'fixtures/QAUniversal.horosplugin', cloud)
    info = cloud / 'Contents/Info.plist'
    # Keep the synthetic bundle loadable; only the folder name matters to deploy.
    archive = p / 'HorosCloud.horosplugin.zip'
    with zipfile.ZipFile(archive, 'w') as zipped:
        for item in cloud.rglob('*'):
            zipped.write(item, item.relative_to(p))
    (p / 'main.swift').write_text(program)
    compiled = subprocess.run(
        ['swiftc', str(swift), str(p / 'main.swift'), '-o', str(p / 'test')],
        capture_output=True, text=True)
    if compiled.returncode != 0:
        print('FAIL: bundled Cloud deploy harness did not compile')
        print(compiled.stderr)
        sys.exit(1)
    ran = subprocess.run([str(p / 'test'), str(p)], capture_output=True, text=True)
    sys.stdout.write(ran.stdout)
    sys.stderr.write(ran.stderr)
    if ran.returncode != 0:
        sys.exit(ran.returncode)
print('ok: bundled Cloud is prepared aside and a disabled copy is left alone')
