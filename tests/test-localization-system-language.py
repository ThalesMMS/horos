#!/usr/bin/env python3
"""System Settings resolves es-ES and it-IT to the packaged host localizations."""
import plistlib
import subprocess
import tempfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
info = plistlib.loads((root / "Horos/Info.plist").read_bytes())
assert info.get("CFBundleDevelopmentRegion") == "en"

for folder in ("en.lproj", "es.lproj", "it-IT.lproj", "ja-JP.lproj"):
    assert (root / "Horos/Resources" / folder).is_dir(), folder

with tempfile.TemporaryDirectory(prefix="horos-system-language-") as folder:
    probe = Path(folder) / "Probe.app/Contents"
    resources = probe / "Resources"
    for name in ("en.lproj", "es.lproj", "it-IT.lproj", "ja-JP.lproj", "Base.lproj"):
        (resources / name).mkdir(parents=True)
    (probe / "Info.plist").write_bytes(plistlib.dumps({
        "CFBundleIdentifier": "org.horosproject.language-probe",
        "CFBundleDevelopmentRegion": "en",
    }))
    source = Path(folder) / "test.m"
    source.write_text(r'''
#import <Foundation/Foundation.h>
int main(int argc, char **argv) {@autoreleasepool {
    NSBundle *bundle = [NSBundle bundleWithPath:[NSString stringWithUTF8String:argv[1]]];
    NSArray *packaged = bundle.localizations;
    if (![packaged containsObject:@"es"] || ![packaged containsObject:@"it-IT"]
        || ![packaged containsObject:@"en"]) {
        NSLog(@"FAIL packaged: %@", packaged);
        return 1;
    }
    NSArray *spanish = [NSBundle preferredLocalizationsFromArray:packaged
                                                 forPreferences:@[@"es-ES"]];
    NSArray *italian = [NSBundle preferredLocalizationsFromArray:packaged
                                                 forPreferences:@[@"it-IT"]];
    if (![spanish.firstObject isEqualToString:@"es"]
        || ![italian.firstObject isEqualToString:@"it-IT"]) {
        NSLog(@"FAIL resolve es=%@ it=%@", spanish, italian);
        return 1;
    }
    NSLog(@"PASS: System Settings language tags resolve to packaged es and it-IT");
}}
''')
    executable = Path(folder) / "test"
    subprocess.run(["xcrun", "clang", "-framework", "Foundation",
                    str(source), "-o", str(executable)], check=True)
    subprocess.run([str(executable), str(probe.parent)], check=True)
