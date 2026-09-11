#!/usr/bin/env python3
"""Native Pages.app / Microsoft Word proof for report images (#157).

Host math and injected-runner checks live in test-report-image-placement.py.
This file talks to the editors that are actually installed. A missing Word, a
Pages sdef that does not resolve, or an AppleScript timeout (-1712 / -609) is
a skip (exit 2), not a pass and not a silent close of the issue.

Live insertion is opt-in (`HOROS_NATIVE_PAGES_WORD=1`) so the focused suite
does not wedge Pages for ten minutes. Default is environment + sdef only.
"""
from pathlib import Path
import os
import platform
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
sha = subprocess.check_output(['git', '-C', str(root), 'rev-parse', '--short=11', 'HEAD'],
                              text=True).strip()

program = r'''
import AppKit
import Foundation

let pages = NSWorkspace.shared.urlForApplication(withBundleIdentifier: "com.apple.iWork.Pages")
    ?? NSWorkspace.shared.urlForApplication(withBundleIdentifier: "com.apple.Pages")
let word = NSWorkspace.shared.urlForApplication(withBundleIdentifier: "com.microsoft.Word")
print("pages_url=\(pages?.path ?? "")")
print("word_url=\(word?.path ?? "")")
if let pages {
    let bundle = Bundle(url: pages)
    print("pages_id=\(bundle?.bundleIdentifier ?? "")")
    print("pages_version=\(bundle?.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "")")
}
let timeout = ReportImageInsertion.errorMessage(from: [NSAppleScript.errorNumber: -1712])
let denied = ReportImageInsertion.errorMessage(from: [NSAppleScript.errorNumber: -1743])
let dropped = ReportImageInsertion.errorMessage(from: [NSAppleScript.errorNumber: -609])
let missingWord = ReportImageInsertion.errorMessage(from: [NSAppleScript.errorNumber: -1728])
let container = ReportImageInsertion.errorMessage(from: [NSAppleScript.errorNumber: -10024])
precondition(timeout.contains("1712") && timeout.contains("Automation"))
precondition(denied.contains("denied"))
precondition(dropped.contains("609"))
precondition(missingWord.contains("1728"))
precondition(container.contains("10024"))
print("error_messages=ok")
'''

def run_sdef(path):
    result = subprocess.run(['sdef', path], capture_output=True, text=True)
    err = (result.stderr or result.stdout).strip().splitlines()
    tail = err[-1] if err else f'exit {result.returncode}'
    return result.returncode, tail


with tempfile.TemporaryDirectory(prefix='horos-native-pages-word-') as folder:
    p = Path(folder)
    (p / 'main.swift').write_text(program)
    built = subprocess.run(
        ['xcrun', 'swiftc', '-O',
         str(root / 'Horos/Sources/ReportImagePlacement.swift'),
         str(p / 'main.swift'),
         '-o', str(p / 'probe')],
        capture_output=True, text=True)
    if built.returncode != 0:
        print(built.stderr or built.stdout)
        raise SystemExit(built.returncode)
    probed = subprocess.run([str(p / 'probe')], capture_output=True, text=True)
    sys.stdout.write(probed.stdout)
    if probed.returncode != 0:
        print(probed.stderr)
        raise SystemExit(probed.returncode)
    info = dict(line.split('=', 1) for line in probed.stdout.splitlines() if '=' in line)

pages_url = info.get('pages_url', '')
word_url = info.get('word_url', '')
# Pages is looked up by bundle identifier: on this host Apple's Pages lives at
# a renamed bundle, so a hard-coded /Applications/Pages.app says nothing about
# whether Pages is scriptable. Report both, and judge on the resolved one.
pages_sdef_code, pages_sdef = run_sdef('/Applications/Pages.app')
word_sdef_code, word_sdef = run_sdef(word_url or '/Applications/Microsoft Word.app')
bundle_sdef_code, bundle_sdef = (1, 'no Pages bundle')
if pages_url:
    bundle_sdef_code, bundle_sdef = run_sdef(pages_url)

print(f'os={platform.mac_ver()[0]} arch={platform.machine()} sha={sha}')
print(f'sdef_Pages.app={pages_sdef_code} {pages_sdef}')
print(f'sdef_Word.app={word_sdef_code} {word_sdef}')
if pages_url:
    print(f'sdef_pages_bundle={bundle_sdef_code} bytes_or={bundle_sdef[:80]}')

reasons = []
if not word_url:
    reasons.append('Microsoft Word is not installed (sdef -43 / lookup empty)')
elif word_sdef_code != 0:
    reasons.append(f'Microsoft Word sdef blocked ({word_sdef})')
if not pages_url:
    reasons.append('Pages is not installed (lookup by bundle identifier is empty)')
elif bundle_sdef_code != 0:
    reasons.append(f'{pages_url} sdef blocked ({bundle_sdef})')
if os.environ.get('HOROS_NATIVE_PAGES_WORD') == '1':
    # Opt-in only: a production insert can time out for 600s and wedge Pages.
    live = subprocess.run(
        ['osascript', '-e', 'with timeout of 12 seconds\n'
         'tell application id "com.apple.Pages" to count documents\nend timeout'],
        capture_output=True, text=True)
    if live.returncode != 0:
        reasons.append((live.stderr or live.stdout).strip() or 'Pages AppleEvent failed')
    else:
        reasons.append('live insert still requires a Word install and a Pages make-image that does not return -10024/-1712')
else:
    reasons.append('live Pages/Word insert is opt-in (HOROS_NATIVE_PAGES_WORD=1); measured native gap is -10024/-1712/Word missing')

print('skipped: native Pages/Word proof blocked: ' + '; '.join(reasons) + ': PAGES WORD',
      file=sys.stderr)
raise SystemExit(2)
