#!/usr/bin/env python3
"""A DICOM network failure is a notice, not a modal alert (#691).

+[DCMTKQueryNode errorMessage:] ran NSRunCriticalAlertPanel: while it was open the
main run loop ran only in the modal mode, and what the import hands to the main
thread waited until it was dismissed - once per retrieve of an instance the server
cannot send. -[AppController displayListenerError:] held the database window with a
sheet. Both now post to a panel that never becomes key or main. The notice log lists
the newest first, counts a repeat on the notice already listed and keeps at most its
capacity; hideListenerError still silences it.
"""
from pathlib import Path
import re
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]

main = r'''
import Foundation
var log = NetworkNoticeLog(capacity: 3)
let start = Date(timeIntervalSinceReferenceDate: 0)
log.add(title: "Get Failed", message: "0 of 1 arrived", at: start)
log.add(title: "Retrieve Incomplete", message: "1 missing", at: start.addingTimeInterval(1))
log.add(title: "Get Failed", message: "0 of 1 arrived", at: start.addingTimeInterval(2))
precondition(log.entries.map(\.title) == ["Get Failed", "Retrieve Incomplete"], "a repeat was listed again: \(log.entries)")
precondition(log.entries[0].count == 2 && log.entries[0].last == start.addingTimeInterval(2), "a repeat was not counted")
log.add(title: "Get Failed", message: "another study", at: start.addingTimeInterval(3))
log.add(title: "Move Failed", message: "x", at: start.addingTimeInterval(4))
log.add(title: "Query Failed", message: "y", at: start.addingTimeInterval(5))
precondition(log.entries.count == 3 && log.entries.map(\.title) == ["Query Failed", "Move Failed", "Get Failed"],
             "the capacity or the order was not kept: \(log.entries.map(\.title))")
var repeated = NetworkNoticeLog()
repeated.add(title: "Get Failed", message: "0 of 1 arrived", at: start)
repeated.add(title: "Get Failed", message: "0 of 1 arrived", at: start)
let formatter = DateFormatter()
formatter.dateFormat = "HH:mm:ss"
formatter.timeZone = TimeZone(identifier: "UTC")
let text = repeated.text(formatter: formatter)
precondition(text.contains("Get Failed") && text.contains("(2 times)") && text.contains("0 of 1 arrived"), text)
log.clear()
precondition(log.entries.isEmpty)
print("PASS: notices list newest first, count repeats, keep their capacity and clear")
'''

with tempfile.TemporaryDirectory(prefix='horos-network-notices-') as directory:
    p = Path(directory)
    (p/'main.swift').write_text(main)
    subprocess.run(['xcrun', 'swiftc', str(root/'Horos/Sources/NetworkNotices.swift'), str(p/'main.swift'),
                    '-o', str(p/'check')], check=True)
    subprocess.run([str(p/'check')], check=True)


def body(source, signature):
    start = source.find(signature)
    assert start != -1, f'{signature} is missing'
    depth, index = 0, source.index('{', start)
    for end in range(index, len(source)):
        depth += {'{': 1, '}': -1}.get(source[end], 0)
        if depth == 0:
            return source[index:end]
    raise AssertionError(f'{signature} does not close')


modal = re.compile(r'NSRunCriticalAlertPanel|NSRunAlertPanel|runModal|beginSheetModal|NSAlert')
query = (root/'Horos/Sources/DCMTKQueryNode.mm').read_text(encoding='utf-8', errors='replace')
error_message = body(query, '+ (void) errorMessage:(NSArray*) msg')
app = (root/'Horos/Sources/AppController.m').read_text(encoding='utf-8', errors='replace')
listener = body(app, '-(void) displayListenerError: (NSString*) err')
for name, text in [('+[DCMTKQueryNode errorMessage:]', error_message), ('-[AppController displayListenerError:]', listener)]:
    assert not modal.search(text), f'{name} still opens a modal alert or a sheet'
    assert 'HorosNetworkNotices postTitle:' in text, f'{name} does not post a notice'
    assert 'hideListenerError' in text, f'{name} no longer honours hideListenerError'

notices = (root/'Horos/Sources/NetworkNotices.swift').read_text()
assert '.nonactivatingPanel' in notices and 'becomesKeyOnlyIfNeeded = true' in notices, \
    'the notices panel must not take the keyboard or activate the app'
assert 'makeKey' not in notices and 'runModal' not in notices, 'the notices panel must not become key or run modally'
print('PASS: query and listener failures post to the non-modal notices panel, and hideListenerError still silences them')
