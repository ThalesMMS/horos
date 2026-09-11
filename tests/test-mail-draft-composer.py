#!/usr/bin/env python3
"""Compile the Mail draft composer and exercise consent, arguments and handler errors."""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
viewer = (root / 'Horos/Sources/ViewerController.m').read_text(encoding='latin1')
browser = (root / 'Horos/Sources/BrowserController.m').read_text(encoding='latin1')
script = (root / 'Horos/Resources/Mail.applescript').read_text()
assert 'HorosMailDraftComposer' in viewer and 'HorosMailDraftComposer' in browser
assert 'defaultaddress@mac.com' not in viewer and 'defaultaddress@mac.com' not in browser
assert 'tell application "Finder"' not in script
assert ' send ' not in script.lower()
harness = r'''
import Foundation
import AppKit

func fail(_ code: Int32) -> Never { exit(code) }

let denied = MailDraftComposer.message(errorInfo: [NSAppleScript.errorNumber: -1743], result: nil) ?? ""
if !denied.contains("Automation") || !denied.contains("denied") { fail(1) }
let timeout = MailDraftComposer.message(errorInfo: [NSAppleScript.errorNumber: -1712], result: nil) ?? ""
if !timeout.contains("1712") || !timeout.contains("Automation") || !timeout.contains("incomplete") { fail(2) }
if MailDraftComposer.message(errorInfo: nil, result: NSAppleEventDescriptor(int32: 0)) != nil { fail(3) }
if MailDraftComposer.message(errorInfo: nil, result: nil) == nil { fail(4) }

let arguments = MailDraftComposer.arguments(subject: "subject", filePaths: ["/tmp/0002.jpg", "/tmp/0001.jpg"])
if arguments.atIndex(1)?.stringValue != "subject" { fail(5) }
if arguments.atIndex(2)?.stringValue != "" { fail(6) }
if arguments.atIndex(3)?.int32Value != 2 { fail(7) }
if arguments.atIndex(4)?.atIndex(1)?.stringValue?.hasSuffix("0002.jpg") != true { fail(8) }
if arguments.atIndex(4)?.atIndex(2)?.stringValue?.hasSuffix("0001.jpg") != true { fail(9) }

let missing = MailDraftComposer.compose(
    subject: "subject",
    filePaths: ["/missing-horos-mail-attachment.jpg"],
    scriptURL: nil,
    injectedConsent: NSNumber(value: 0)
) ?? ""
if !missing.contains("missing") || missing.localizedCaseInsensitiveContains("sent") == false { fail(10) }

let denial = MailDraftComposer.compose(
    subject: "subject",
    filePaths: [],
    scriptURL: URL(fileURLWithPath: "/tmp/unused.scpt"),
    injectedConsent: NSNumber(value: -1743)
) ?? ""
if !denial.contains("Automation") || !denial.contains("denied") { fail(11) }

let timeoutConsent = MailDraftComposer.compose(
    subject: "subject",
    filePaths: [],
    scriptURL: URL(fileURLWithPath: CommandLine.arguments[1]),
    injectedConsent: NSNumber(value: 0)
)
// The injected script returns success without talking to Mail.
if timeoutConsent != nil { fail(12) }

let failed = MailDraftComposer.compose(
    subject: "subject",
    filePaths: [],
    scriptURL: URL(fileURLWithPath: CommandLine.arguments[2]),
    injectedConsent: NSNumber(value: 0)
) ?? ""
if !failed.contains("1712") || !failed.contains("Automation") { fail(13) }

fputs("PASS: composer keeps recipient empty, maps consent and timeout, and never sends\n", stdout)
'''

denied_script = '''
on mail_images(email_subject, default_address, image_count, new_files, new_captions, new_comments, cancel_string)
	error "Synthetic timeout" number -1712
end mail_images
'''
successful_script = '''
on mail_images(email_subject, default_address, image_count, new_files, new_captions, new_comments, cancel_string)
	if default_address is not "" then error "recipient was supplied" number 1
	return 0
end mail_images
'''

with tempfile.TemporaryDirectory(prefix='horos-mail-composer-') as folder:
    path = Path(folder)
    (path / 'main.swift').write_text(harness)
    (path / 'successful.applescript').write_text(successful_script)
    (path / 'timeout.applescript').write_text(denied_script)
    subprocess.run(['osacompile', '-o', str(path / 'successful.scpt'), str(path / 'successful.applescript')], check=True)
    subprocess.run(['osacompile', '-o', str(path / 'timeout.scpt'), str(path / 'timeout.applescript')], check=True)
    compiled = subprocess.run(
        ['xcrun', '--sdk', 'macosx', 'swiftc', '-sanitize=address',
         str(root / 'Horos/Sources/MailDraftComposer.swift'), str(path / 'main.swift'),
         '-o', str(path / 'test')],
        capture_output=True, text=True)
    if compiled.returncode != 0:
        raise SystemExit(compiled.stderr or compiled.stdout)
    subprocess.run([str(path / 'test'), str(path / 'successful.scpt'), str(path / 'timeout.scpt')], check=True)
