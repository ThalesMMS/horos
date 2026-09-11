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
for caller in [viewer, browser]:
    assert 'filePaths:mailFilePaths completion:^(NSString *mailError)' in caller
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

precondition(MailDraftComposer.checkWithoutPrompt {
    precondition(!Thread.isMainThread)
    return -1743
} == -1743)
let releaseSlowCheck = DispatchSemaphore(value: 0)
precondition(MailDraftComposer.checkWithoutPrompt(timeout: .milliseconds(25)) {
    releaseSlowCheck.wait()
    return 0
} == -1712)
releaseSlowCheck.signal()

@MainActor func settle(until condition: () -> Bool) async {
    for _ in 0..<300 {
        if condition() { return }
        try! await Task.sleep(nanoseconds: 10_000_000)
    }
    preconditionFailure("asynchronous Mail composition did not complete")
}
var asynchronousTestsFinished = false
Task { @MainActor in
    let started = DispatchSemaphore(value: 0)
    let respond = DispatchSemaphore(value: 0)
    var completed = false, heartbeat = false, calls = 0
    MailDraftComposer.compose(subject: "subject", filePaths: [], scriptURL: nil, using: {
        precondition(!Thread.isMainThread)
        started.signal()
        respond.wait()
        return -1743
    }) { error in
        precondition(Thread.isMainThread && error?.contains("denied") == true)
        calls += 1; completed = true
    }
    DispatchQueue.main.async { heartbeat = true }
    await settle { heartbeat && started.wait(timeout: .now()) == .success }
    precondition(!completed)
    MailDraftComposer.compose(subject: "subject", filePaths: [], scriptURL: nil, using: {
        fatalError("duplicate composition must not start another permission request")
    }) { error in precondition(error?.contains("already pending") == true) }
    respond.signal()
    await settle { completed }
    precondition(calls == 1)

    completed = false
    MailDraftComposer.compose(subject: "subject", filePaths: [],
        scriptURL: URL(fileURLWithPath: CommandLine.arguments[1]), using: { 0 }) { error in
        precondition(Thread.isMainThread && error == nil)
        calls += 1; completed = true
    }
    await settle { completed }
    precondition(calls == 2)

    // A selection/export may disappear while a person considers permission.
    // Never call the Mail handler with attachments that vanished in that time.
    let attachment = URL(fileURLWithPath: CommandLine.arguments[1]).deletingLastPathComponent()
        .appendingPathComponent("transient.jpg")
    try! Data("synthetic attachment".utf8).write(to: attachment)
    completed = false
    MailDraftComposer.compose(subject: "subject", filePaths: [attachment.path],
        scriptURL: URL(fileURLWithPath: CommandLine.arguments[1]), using: {
        precondition(!Thread.isMainThread)
        started.signal()
        respond.wait()
        return 0
    }) { error in
        precondition(Thread.isMainThread && error?.contains("missing") == true)
        completed = true
    }
    await settle { started.wait(timeout: .now()) == .success }
    try! FileManager.default.removeItem(at: attachment)
    respond.signal()
    await settle { completed }
    asynchronousTestsFinished = true
}
let deadline = Date(timeIntervalSinceNow: 10)
while !asynchronousTestsFinished && Date() < deadline {
    RunLoop.current.run(until: Date(timeIntervalSinceNow: 0.005))
}
precondition(asynchronousTestsFinished)
fputs("PASS: recipient-free handler, errors, off-main consent, responsive main queue, duplicate guard, refusal/retry, bounded legacy check and expired attachments\n", stdout)
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
