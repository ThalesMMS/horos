#!/usr/bin/env python3
"""Pages is found by more than the one bundle identifier it used to have.

`Reports.m` asked `NSWorkspace` for `com.apple.iWork.Pages`, which is what Pages
'09 answered to. Measured on a machine with Pages 15.3.1 installed and signed by
Apple:

    com.apple.iWork.Pages: nil
    com.apple.Pages: /Applications/Pages.app
    apps that open a .pages document: Pages.app

so every Pages report ended at "Pages is not installed or could not be located"
with Pages in the Applications folder.

The lookup asks for both identifiers and then for whatever is registered to open
a Pages document - and takes that one only if it is Apple's, because everything
Horos does with the file afterwards is Pages and nothing else.
"""
from pathlib import Path
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
failures = []

reports = (root / 'Horos/Sources/Reports.m').read_bytes().decode('utf-8')
if 'URLForApplicationWithBundleIdentifier:@"com.apple.iWork.Pages"' in reports:
    failures.append('Pages is still looked up by one identifier only')
if '[HorosPagesApplication url]' not in reports:
    failures.append('the report generator does not use the shared lookup')
if '[HorosPagesApplication information]' not in reports:
    failures.append('the version that decides where templates live is not read through it')

lookup = (root / 'Horos/Sources/PagesApplication.swift').read_text()
for identifier in ('com.apple.iWork.Pages', 'com.apple.Pages'):
    if identifier not in lookup:
        failures.append('%s is not among the identifiers asked for' % identifier)
if 'com.apple.iwork.pages.pages' not in lookup:
    failures.append('the document type is not used as the last resort')
if 'hasPrefix("com.apple.")' not in lookup:
    failures.append("an application that is not Apple's could be driven as though it were Pages")

source = r'''
import AppKit
import UniformTypeIdentifiers

// What this machine answers, which is the measurement the fix was made from.
let workspace = NSWorkspace.shared
let old = workspace.urlForApplication(withBundleIdentifier: "com.apple.iWork.Pages")
let new = workspace.urlForApplication(withBundleIdentifier: "com.apple.Pages")
print("com.apple.iWork.Pages: \(old?.lastPathComponent ?? "nil")")
print("com.apple.Pages:       \(new?.lastPathComponent ?? "nil")")

let found = PagesApplication.url()
print("the lookup answers:    \(found?.lastPathComponent ?? "nil")")

// Whatever this machine has, the lookup must not answer with less than the two
// identifiers do, and must not answer with something that is not Apple's.
if old != nil || new != nil {
    precondition(found != nil, "Pages is installed and the lookup did not find it")
}
if let found {
    let bundle = Bundle(url: found)
    precondition(bundle?.bundleIdentifier?.hasPrefix("com.apple.") == true,
                 "the lookup answered with \(bundle?.bundleIdentifier ?? "an unsigned bundle")")
    let information = PagesApplication.information()
    precondition(information?["CFBundleIdentifier"] as? String == bundle?.bundleIdentifier)
    print("its identifier:        \(bundle?.bundleIdentifier ?? "?")")
    print("its version:           \((information?["CFBundleShortVersionString"] as? String) ?? "?")")
} else {
    print("Pages is not installed here; the lookup answering nil is the right answer")
}
print("PASS")
'''
with tempfile.TemporaryDirectory(prefix='horos-pages-lookup-') as tmp:
    p = Path(tmp)
    (p / 'main.swift').write_text(source)
    subprocess.run(['xcrun', 'swiftc', str(root / 'Horos/Sources/PagesApplication.swift'),
                    str(p / 'main.swift'), '-o', str(p / 'test')], check=True)
    subprocess.run([str(p / 'test')], check=True)

for failure in failures:
    print('FAIL: %s' % failure)
if failures:
    sys.exit(1)
print('ok: Pages is looked up by both identifiers and by the document type, and only '
      "Apple's own is accepted")
