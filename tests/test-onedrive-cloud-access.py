#!/usr/bin/env python3
"""Classify local, hydrated, placeholder and offline cloud files without a OneDrive account."""
from pathlib import Path
import os
import re
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
failures = []
helper = root / 'Horos/Sources/CloudFileAccess.swift'
copy_header = root / 'Horos/Sources/HorosFileCopy.h'
detector = root / 'Horos/Sources/ICloudDriveDetector.m'
first_use = root / 'Horos/Sources/DatabaseFirstUse.swift'
database = root / 'Horos/Sources/DicomDatabase.mm'
export = root / 'Horos/Sources/BrowserController.m'
project = root / 'Horos.xcodeproj/project.pbxproj'

DRIVER = r'''
import Foundation

func emit(_ key: String, _ value: String) { print("\(key)\t\(value)") }

CloudFileAccess.resetIgnoredWarningForTests()

let root = URL(fileURLWithPath: CommandLine.arguments[1])
let manager = FileManager.default
let oneDrive = root.appendingPathComponent("Library/CloudStorage/OneDrive-Personal/Synthetic")
try manager.createDirectory(at: oneDrive, withIntermediateDirectories: true)

let local = root.appendingPathComponent("local.dcm")
try Data("local-bytes".utf8).write(to: local)

let hydrated = oneDrive.appendingPathComponent("hydrated.dcm")
try Data("hydrated-bytes".utf8).write(to: hydrated)

let placeholder = oneDrive.appendingPathComponent("placeholder.dcm")
try Data("placeholder-bytes".utf8).write(to: placeholder)
try CloudFileAccess.setFixturePresence(CloudFileAccess.presencePlaceholder, atPath: placeholder.path)

let sparse = oneDrive.appendingPathComponent("sparse.dcm")
manager.createFile(atPath: sparse.path, contents: nil)
let sparseHandle = try FileHandle(forWritingTo: sparse)
try sparseHandle.truncate(atOffset: 4096)
try sparseHandle.close()

let offline = oneDrive.appendingPathComponent("offline.dcm")
try Data("offline-bytes".utf8).write(to: offline)
try CloudFileAccess.setFixturePresence(CloudFileAccess.presenceOffline, atPath: offline.path)

let missing = oneDrive.appendingPathComponent("missing.dcm")
let database = oneDrive.appendingPathComponent("Horos Data")
try manager.createDirectory(at: database, withIntermediateDirectories: true)
let nosync = root.appendingPathComponent("Library/CloudStorage/OneDrive-Personal/Horos Data.nosync")
try manager.createDirectory(at: nosync, withIntermediateDirectories: true)

emit("local-provider", CloudFileAccess.providerName(forPath: local.path) ?? "nil")
emit("onedrive-provider", CloudFileAccess.providerName(forPath: hydrated.path) ?? "nil")
emit("icloud-provider", CloudFileAccess.providerName(forPath: root.appendingPathComponent("Library/Mobile Documents/com~apple~CloudDocs/x").path) ?? "nil")
emit("legacy-provider", CloudFileAccess.providerName(forPath: root.appendingPathComponent("OneDrive/file.dcm").path) ?? "nil")

emit("local", CloudFileAccess.presence(ofPath: local.path))
emit("hydrated", CloudFileAccess.presence(ofPath: hydrated.path))
emit("placeholder", CloudFileAccess.presence(ofPath: placeholder.path))
emit("sparse", CloudFileAccess.presence(ofPath: sparse.path))
emit("offline", CloudFileAccess.presence(ofPath: offline.path))
emit("missing", CloudFileAccess.presence(ofPath: missing.path))

var error: NSError?
let destLocal = root.appendingPathComponent("out-local.dcm")
emit("prep-local", CloudFileAccess.prepareCopy(fromPath: local.path, toPath: destLocal.path, error: &error) ? "yes" : "no")
emit("prep-local-error", error?.localizedDescription ?? "")

error = nil
let destHydrated = root.appendingPathComponent("out-hydrated.dcm")
emit("prep-hydrated", CloudFileAccess.prepareCopy(fromPath: hydrated.path, toPath: destHydrated.path, error: &error) ? "yes" : "no")
emit("prep-hydrated-error", error?.localizedDescription ?? "")

error = nil
let destPlaceholder = root.appendingPathComponent("out-placeholder.dcm")
let placeholderOK = CloudFileAccess.prepareCopy(fromPath: placeholder.path, toPath: destPlaceholder.path, error: &error)
emit("prep-placeholder", placeholderOK ? "yes" : "no")
emit("prep-placeholder-error", error?.localizedDescription ?? "")
emit("prep-placeholder-code", String(error?.code ?? -1))
emit("placeholder-dest", manager.fileExists(atPath: destPlaceholder.path) ? "exists" : "absent")
emit("placeholder-source", (try? Data(contentsOf: placeholder)) == Data("placeholder-bytes".utf8) ? "intact" : "changed")

error = nil
let destOffline = root.appendingPathComponent("out-offline.dcm")
let offlineOK = CloudFileAccess.prepareCopy(fromPath: offline.path, toPath: destOffline.path, error: &error)
emit("prep-offline", offlineOK ? "yes" : "no")
emit("prep-offline-error", error?.localizedDescription ?? "")
emit("offline-dest", manager.fileExists(atPath: destOffline.path) ? "exists" : "absent")
emit("offline-source", (try? Data(contentsOf: offline)) == Data("offline-bytes".utf8) ? "intact" : "changed")

emit("warn-local", CloudFileAccess.shouldWarnAboutActiveDatabase(atPath: local.path) ? "yes" : "no")
emit("warn-onedrive", CloudFileAccess.shouldWarnAboutActiveDatabase(atPath: database.path) ? "yes" : "no")
emit("warn-nosync", CloudFileAccess.shouldWarnAboutActiveDatabase(atPath: nosync.path) ? "yes" : "no")
let warning = CloudFileAccess.activeDatabaseWarning(forPath: database.path)
emit("warning-onedrive", warning.contains("Do not keep the live database") && warning.contains("OneDrive") ? "ok" : warning)
emit("warning-recommends", warning.lowercased().contains("you should store") || warning.lowercased().contains("safe to keep") ? "yes" : "no")
'''

results = {}
if not helper.exists():
    failures.append('CloudFileAccess.swift is missing')
else:
    with tempfile.TemporaryDirectory(prefix='horos-onedrive-access-') as directory:
        (Path(directory) / 'main.swift').write_text(DRIVER)
        binary = Path(directory) / 'access'
        built = subprocess.run(
            ['xcrun', '--sdk', 'macosx', 'swiftc', '-o', str(binary),
             str(helper), str(Path(directory) / 'main.swift')],
            capture_output=True, text=True)
        if built.returncode != 0:
            failures.append('CloudFileAccess does not compile:\n%s' % built.stderr[-2000:])
        else:
            data = Path(directory) / 'data'
            data.mkdir()
            run = subprocess.run([str(binary), str(data)], capture_output=True, text=True, timeout=30)
            if run.returncode != 0:
                failures.append('the driver failed: %s%s' % (run.stderr[-800:], run.stdout[-400:]))
            for line in run.stdout.splitlines():
                key, _, value = line.partition('\t')
                results[key] = value

if results:
    expected = {
        'local-provider': 'nil',
        'onedrive-provider': 'OneDrive',
        'icloud-provider': 'iCloud',
        'legacy-provider': 'OneDrive',
        'local': 'local',
        'hydrated': 'hydrated',
        'placeholder': 'placeholder',
        'sparse': 'placeholder',
        'offline': 'offline',
        'missing': 'offline',
        'prep-local': 'yes',
        'prep-hydrated': 'yes',
        'prep-placeholder': 'no',
        'placeholder-dest': 'absent',
        'placeholder-source': 'intact',
        'prep-offline': 'no',
        'offline-dest': 'absent',
        'offline-source': 'intact',
        'warn-local': 'no',
        'warn-onedrive': 'yes',
        'warn-nosync': 'no',
        'warning-onedrive': 'ok',
        'warning-recommends': 'no',
    }
    for key, want in expected.items():
        got = results.get(key)
        if got != want:
            failures.append('%s: %r, expected %r' % (key, got, want))
    for key in ('prep-placeholder-error', 'prep-offline-error'):
        text = results.get(key, '')
        if 'available offline' not in text or 'unchanged' not in text:
            failures.append('%s does not mention hydration/offline preservation: %r' % (key, text))
    if results.get('prep-placeholder-code') != '1651':
        failures.append('placeholder error code is %r' % results.get('prep-placeholder-code'))

# --- production call sites must ask the helper --------------------------------
if 'HorosPrepareCloudCopy' not in copy_header.read_text(encoding='utf-8', errors='replace'):
    failures.append('HorosFileCopy.h does not coordinate cloud copies')
if 'HorosCloudFileAccess' not in detector.read_text(encoding='utf-8', errors='replace'):
    failures.append('ICloudDriveDetector does not warn for OneDrive database paths')
if 'CloudFileAccess' not in first_use.read_text(encoding='utf-8', errors='replace'):
    failures.append('first-use location choice does not warn about cloud folders')
if 'HorosCopyFileForPublication' not in database.read_text(encoding='utf-8', errors='replace'):
    failures.append('import no longer uses the publication copy helper')
export_text = export.read_bytes().decode('latin1')
if 'HorosCopyFileForPublication' not in export_text:
    failures.append('DICOM export no longer uses the publication copy helper')
if not re.search(r'OneDrive or another cloud provider', export_text):
    failures.append('export errors no longer mention cloud hydration')
if 'CloudFileAccess.swift' not in project.read_text(encoding='utf-8', errors='replace'):
    failures.append('CloudFileAccess.swift is not in the Xcode project')

for failure in failures:
    print('FAIL: %s' % failure)
if failures:
    sys.exit(1)
print('ok: local/hydrated/placeholder/offline matrix, hydration errors preserve files, '
      'and an active database on OneDrive is not recommended')
