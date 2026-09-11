#!/usr/bin/env python3
"""Identify the public T2 1.3 Intel ABI and refuse it on arm64."""
from pathlib import Path
import plistlib
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
source = root / 'Horos/Sources/T2FitMap.swift'
if not source.is_file():
    raise SystemExit('FAIL: Horos/Sources/T2FitMap.swift is missing')

code = r'''
import Foundation

let legacy = T2FitMapCompatibility.inspect(
    info: [
        "CFBundleVersion": "1.3",
        "CFBundleExecutable": "T2 Fit Map",
        "NSPrincipalClass": "MappingT2FitFilter",
        "MenuTitles": ["T2 Fit Map"],
        "pluginType": "imageFilter"
    ],
    architectures: ["x86_64", "ppc"],
    hostArchitecture: "arm64")
precondition(legacy.identified)
precondition(legacy.version == "1.3")
precondition(legacy.principalClass == "MappingT2FitFilter")
precondition(!legacy.compatibleWithHost)
precondition(legacy.diagnostic.contains("1.3"))
precondition(legacy.diagnostic.contains("MappingT2FitFilter"))
precondition(legacy.diagnostic.contains("arm64"))
precondition(legacy.diagnostic.contains("1.0"))
precondition(legacy.diagnostic.contains("cannot load"))

let native = T2FitMapCompatibility.inspect(
    info: [
        "CFBundleVersion": "1.0",
        "CFBundleExecutable": "T2 Fit Map",
        "NSPrincipalClass": "T2FitMapFilter",
        "MenuTitles": ["T2 Fit Map"]
    ],
    architectures: ["arm64"],
    hostArchitecture: "arm64")
precondition(native.identified)
precondition(native.compatibleWithHost)
precondition(native.diagnostic.contains("arm64"))

let other = T2FitMapCompatibility.inspect(
    info: ["CFBundleVersion": "2.0", "NSPrincipalClass": "OtherFilter"],
    architectures: ["x86_64"],
    hostArchitecture: "arm64")
precondition(!other.identified)
precondition(other.diagnostic.isEmpty)

let arguments = CommandLine.arguments
if arguments.count > 1 {
    let path = arguments[1]
    let read = T2FitMapCompatibility.machOArchitectures(at: path + "/Contents/MacOS/T2 Fit Map")
    precondition(read == ["x86_64"], "\(read)")
    let text = T2FitMapCompatibility.diagnostic(
        forBundleAtPath: path,
        loadErrorDomain: NSCocoaErrorDomain,
        loadErrorCode: NSExecutableArchitectureMismatchError)
    precondition(text?.contains("1.3") == true, text ?? "nil")
    precondition(text?.contains("cannot load") == true, text ?? "nil")
}

print("PASS: T2 Fit Map 1.3 Intel/PPC ABI is identified and rejected on arm64")
'''

with tempfile.TemporaryDirectory(prefix='horos-t2-fit-abi-') as directory:
    path = Path(directory)
    bundle = path / 'T2 Fit Map.osirixplugin'
    executable = bundle / 'Contents/MacOS' / 'T2 Fit Map'
    executable.parent.mkdir(parents=True)
    stub = path / 'stub.m'
    stub.write_text('''
#import <Foundation/Foundation.h>
@interface MappingT2FitFilter : NSObject
@end
@implementation MappingT2FitFilter
@end
''')
    subprocess.run([
        'xcrun', 'clang', '-bundle', '-arch', 'x86_64', '-framework', 'Foundation',
        str(stub), '-o', str(executable)
    ], check=True)
    info = {
        'CFBundleExecutable': 'T2 Fit Map',
        'CFBundleIdentifier': 'org.horosproject.qa.t2-fit-map-legacy',
        'CFBundleName': 'T2 Fit Map',
        'CFBundleVersion': '1.3',
        'CFBundlePackageType': 'BNDL',
        'NSPrincipalClass': 'MappingT2FitFilter',
        'pluginType': 'imageFilter',
        'MenuTitles': ['T2 Fit Map'],
    }
    (bundle / 'Contents' / 'Info.plist').write_bytes(plistlib.dumps(info))
    (path / 'main.swift').write_text(code)
    subprocess.run([
        'xcrun', 'swiftc', str(source), str(path / 'main.swift'),
        '-o', str(path / 'test')
    ], check=True)
    subprocess.run([str(path / 'test'), str(bundle)], check=True)
