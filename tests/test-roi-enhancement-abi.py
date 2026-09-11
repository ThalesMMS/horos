#!/usr/bin/env python3
"""Identify the public ROI Enhancement Intel ABI and refuse it on arm64."""
from pathlib import Path
import plistlib
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
source = root / 'Horos/Sources/ROIEnhancement.swift'
if not source.is_file():
    raise SystemExit('FAIL: Horos/Sources/ROIEnhancement.swift is missing')

code = r'''
import Foundation

let legacy = ROIEnhancementCompatibility.inspect(
    info: [
        "CFBundleVersion": "2.3.1",
        "CFBundleShortVersionString": "2.3.1",
        "CFBundleExecutable": "ROI-Enhancement",
        "CFBundleIdentifier": "com.osirix.roienhancement",
        "NSPrincipalClass": "ROI_Enhancement_II",
        "MenuTitles": ["ROI Enhancement"],
        "pluginType": "roiTool"
    ],
    architectures: ["i386", "x86_64"],
    hostArchitecture: "arm64")
precondition(legacy.identified)
precondition(legacy.version == "2.3.1")
precondition(legacy.principalClass == "ROI_Enhancement_II")
precondition(!legacy.compatibleWithHost)
precondition(legacy.diagnostic.contains("2.3.1"))
precondition(legacy.diagnostic.contains("ROI_Enhancement_II"))
precondition(legacy.diagnostic.contains("arm64"))
precondition(legacy.diagnostic.contains("1.0"))
precondition(legacy.diagnostic.contains("cannot load"))

let native = ROIEnhancementCompatibility.inspect(
    info: [
        "CFBundleVersion": "1.0",
        "CFBundleExecutable": "ROI-Enhancement",
        "NSPrincipalClass": "ROIEnhancementFilter",
        "MenuTitles": ["ROI Enhancement"]
    ],
    architectures: ["arm64"],
    hostArchitecture: "arm64")
precondition(native.identified)
precondition(native.compatibleWithHost)
precondition(native.diagnostic.contains("arm64"))

let other = ROIEnhancementCompatibility.inspect(
    info: ["CFBundleVersion": "2.0", "NSPrincipalClass": "OtherFilter"],
    architectures: ["x86_64"],
    hostArchitecture: "arm64")
precondition(!other.identified)
precondition(other.diagnostic.isEmpty)

let arguments = CommandLine.arguments
if arguments.count > 1 {
    let path = arguments[1]
    let read = ROIEnhancementCompatibility.machOArchitectures(at: path + "/Contents/MacOS/ROI-Enhancement")
    precondition(read == ["x86_64"], "\(read)")
    let text = ROIEnhancementCompatibility.diagnostic(
        forBundleAtPath: path,
        loadErrorDomain: NSCocoaErrorDomain,
        loadErrorCode: NSExecutableArchitectureMismatchError)
    precondition(text?.contains("2.3.1") == true, text ?? "nil")
    precondition(text?.contains("cannot load") == true, text ?? "nil")
}

print("PASS: ROI Enhancement 2.3.1 Intel ABI is identified and rejected on arm64")
'''

with tempfile.TemporaryDirectory(prefix='horos-roi-enhancement-abi-') as directory:
    path = Path(directory)
    bundle = path / 'ROI-Enhancement.osirixplugin'
    executable = bundle / 'Contents/MacOS' / 'ROI-Enhancement'
    executable.parent.mkdir(parents=True)
    stub = path / 'stub.m'
    stub.write_text('''
#import <Foundation/Foundation.h>
@interface ROI_Enhancement_II : NSObject
@end
@implementation ROI_Enhancement_II
@end
''')
    subprocess.run([
        'xcrun', 'clang', '-bundle', '-arch', 'x86_64', '-framework', 'Foundation',
        str(stub), '-o', str(executable)
    ], check=True)
    info = {
        'CFBundleExecutable': 'ROI-Enhancement',
        'CFBundleIdentifier': 'org.horosproject.qa.roi-enhancement-legacy',
        'CFBundleName': 'ROI Enhancement',
        'CFBundleVersion': '2.3.1',
        'CFBundleShortVersionString': '2.3.1',
        'CFBundlePackageType': 'BNDL',
        'NSPrincipalClass': 'ROI_Enhancement_II',
        'pluginType': 'roiTool',
        'MenuTitles': ['ROI Enhancement'],
    }
    (bundle / 'Contents' / 'Info.plist').write_bytes(plistlib.dumps(info))
    (path / 'main.swift').write_text(code)
    subprocess.run([
        'xcrun', 'swiftc', str(source), str(path / 'main.swift'),
        '-o', str(path / 'test')
    ], check=True)
    subprocess.run([str(path / 'test'), str(bundle)], check=True)
