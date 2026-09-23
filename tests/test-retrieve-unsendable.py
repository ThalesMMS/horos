#!/usr/bin/env python3
"""A retrieve remembers the instances the server declared it cannot send (#692).

OsiriX answers a C-GET for a file it cannot convert with a failed sub-operation and
no Failed SOP Instance UID List. Each retrieve asked for it again, failed, fetched
the whole study again at STUDY level and warned twice. The instances a C-GET asked
for that neither arrived nor were refused here are recorded, per server, when they
are exactly the failed count; a smart retrieve does not ask for them, does not fall
back to the STUDY level over them and warns only on the attempt that found them. The
query column says how many there are, and Retrieve with Option asks again.
"""
from pathlib import Path
import json
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]

driver = r'''
import Foundation
let directory = CommandLine.arguments[1]
let rows = (1...5).map { ["uid": "1.2.\($0)", "series": $0 <= 3 ? "A" : "B"] }
func begin(_ study: String) -> RetrieveInventory {
    RetrieveInventory.begin(study: study, series: "", endpoint: "OSIRIX@peer:11112", database: directory, instances: rows, confirmed: true)
}

// IMAGE level: 3, 4 and 5 asked, 5 not sent, one failed sub-operation.
let first = begin("10.1")
first.updateImportedUIDs(["1.2.1", "1.2.2"])
precondition(!first.nothingLeftToAsk && first.unsendableUIDs.isEmpty)
first.record(uid: "1.2.3", status: 0); first.record(uid: "1.2.4", status: 0)
first.recordUnsent(requested: ["1.2.3", "1.2.4", "1.2.5"], series: "", status: 0xB000, failed: 1, remaining: 0)
first.updateImportedUIDs(["1.2.1", "1.2.2", "1.2.3", "1.2.4"])
precondition(first.unsendableUIDs == ["1.2.5"] && first.nothingLeftToAsk && !first.isComplete)
precondition(first.needsAttention, "the attempt that found the refusal must say so")
precondition(first.summary.contains("1 missing (1 the server cannot send)"), first.summary)
first.finish()

// The next attempt: nothing to ask, nothing to report.
let second = begin("10.1")
second.updateImportedUIDs(["1.2.1", "1.2.2", "1.2.3", "1.2.4"])
precondition(second.nothingLeftToAsk && !second.needsAttention && second.unsendableUIDs == ["1.2.5"])
second.finish()

// A forced retrieve asks again and reports again.
let forced = begin("10.1")
forced.forgetPeerFailures()
forced.updateImportedUIDs(["1.2.1", "1.2.2", "1.2.3", "1.2.4"])
precondition(!forced.nothingLeftToAsk && forced.unsendableUIDs.isEmpty && forced.needsAttention)
forced.finish()

// Counts that do not match, and sub-operations still remaining, record nothing.
let mismatch = begin("11.1")
mismatch.updateImportedUIDs(["1.2.1", "1.2.2"])
mismatch.record(uid: "1.2.3", status: 0)
mismatch.recordUnsent(requested: ["1.2.3", "1.2.4", "1.2.5"], series: "", status: 0xB000, failed: 1, remaining: 0)
mismatch.recordUnsent(requested: ["1.2.3", "1.2.4", "1.2.5"], series: "", status: 0xB000, failed: 2, remaining: 1)
mismatch.recordUnsent(requested: ["1.2.3", "1.2.4", "1.2.5"], series: "", status: 0, failed: 0, remaining: 0)
// A refusal of the whole request names no instance.
mismatch.recordUnsent(requested: ["1.2.4", "1.2.5"], series: "", status: 0xC000, failed: 2, remaining: 0)
precondition(mismatch.unsendableUIDs.isEmpty && !mismatch.nothingLeftToAsk)
mismatch.finish()

// A store refused here is a failed sub-operation too, and not the peer's refusal.
let refused = begin("12.1")
refused.updateImportedUIDs(["1.2.1", "1.2.2"])
refused.record(uid: "1.2.3", status: 0); refused.record(uid: "1.2.4", status: 0xa700)
refused.recordUnsent(requested: ["1.2.3", "1.2.4", "1.2.5"], series: "", status: 0xA702, failed: 2, remaining: 0)
precondition(refused.unsendableUIDs == ["1.2.5"], "\(refused.unsendableUIDs)")
precondition(!refused.nothingLeftToAsk, "the instance refused here is still to ask for")
refused.finish()

// STUDY level asks for the whole study; SERIES level for the series.
let study = begin("13.1")
study.updateImportedUIDs([])
for i in [1, 2, 3, 4] { study.record(uid: "1.2.\(i)", status: 0) }
study.recordUnsent(requested: [], series: "", status: 0xB000, failed: 1, remaining: 0)
precondition(study.unsendableUIDs == ["1.2.5"])
study.finish()
let series = begin("14.1")
series.updateImportedUIDs([])
series.record(uid: "1.2.4", status: 0)
series.recordUnsent(requested: [], series: "B", status: 0xA702, failed: 1, remaining: 0)
precondition(series.unsendableUIDs == ["1.2.5"] && !series.nothingLeftToAsk)
series.finish()
print(first.path)
'''

column = r'''
import Foundation
let value = LocalCompleteness(localCount: 125, remoteCount: 126)
precondition(value.text == "99% (125/126)")
value.unsendableCount = 1
precondition(value.text == "99% (125/126) · 1 not sendable", value.text)
precondition(value.sortValue < 1 && !value.isComplete)
'''

with tempfile.TemporaryDirectory(prefix='horos-unsendable-') as directory:
    p = Path(directory)
    (p/'main.swift').write_text(driver)
    subprocess.run(['xcrun', 'swiftc', str(root/'Horos/Sources/RetrieveInventory.swift'), str(p/'main.swift'),
                    '-o', str(p/'inventory')], check=True)
    run = subprocess.run([str(p/'inventory'), directory], check=True, capture_output=True, text=True, timeout=20)
    manifest = json.loads(Path(run.stdout.strip()).read_text())
    assert manifest['peerFailed'] == [], 'a forced retrieve kept the refusals it asked again for'
    column_dir = p/'column'
    column_dir.mkdir()
    (column_dir/'main.swift').write_text(column)
    subprocess.run(['xcrun', 'swiftc', str(root/'Horos/Sources/LocalCompleteness.swift'), str(column_dir/'main.swift'),
                    '-o', str(column_dir/'column')], check=True)
    subprocess.run([str(column_dir/'column')], check=True)
print('PASS: refusals are recorded from the failed count, remembered per server, not reported twice, shown in the column and forgotten on a forced retrieve')

node = (root/'Horos/Sources/DCMTKQueryNode.mm').read_text(encoding='utf-8', errors='replace')
get = node[node.index('- (OFCondition)getSCU:'):]
get = get[:get.index('\n}\n')]
move = node[node.index('dataset:( DcmDataset *)dataset destination: (char*) destination\n'):]
move = move[:move.index('\n}\n')]
assert 'recordUnsentOfRequest:dataset status:rsp.DimseStatus' in get, 'a C-GET does not record what it did not receive'
assert get.index('recordOperation:@"C-GET"') < get.index('recordUnsentOfRequest:dataset')
assert 'recordUnsentOfRequest' not in move, 'C-MOVE stores may arrive in another process: nothing to infer'
begin = node[node.index('- (void)beginRetrieveInventory'):]
begin = begin[:begin.index('\n}\n')]
assert 'if (_noSmartMode) [_retrieveInventory forgetPeerFailures];' in begin
move_flow = node[node.index('- (void) move:(NSDictionary*) dict retrieveMode: (int) retrieveMode'):]
move_flow = move_flow[:move_flow.index('- (OFCondition) addPresentationContext')]
assert '_retrieveInventory.isComplete || _retrieveInventory.nothingLeftToAsk' in move_flow, \
    'a retrieve still asks when only unsendable instances are missing'
assert move_flow.count('[unsendableUIDs containsObject: [image uid]] == NO') == 2, 'IMAGE level still asks for unsendable instances'
assert move_flow.count('![HorosRetrieveThreadGroup anyCancelled: threads] || _retrieveInventory.nothingLeftToAsk') == 2, \
    'an IMAGE level refusal of only unsendable instances still falls back to the STUDY level'
query = (root/'Horos/Sources/QueryController.mm').read_bytes().decode('latin1')
retrieve = query[query.index('-(void) retrieve:(id)sender onlyIfNotAvailable:(BOOL) onlyIfNotAvailable forViewing: (BOOL) forViewing items:'):]
retrieve = retrieve[:retrieve.index('\n}\n')]
assert 'NSEventModifierFlagOption' in retrieve and '[item setNoSmartMode: retryEverything];' in retrieve, \
    'Retrieve with Option does not ask for everything again'
assert 'value.unsendableCount = inventory.unsendableUIDs.count' in query
print('PASS: C-GET records refusals, the move skips them, and Retrieve with Option asks again')
