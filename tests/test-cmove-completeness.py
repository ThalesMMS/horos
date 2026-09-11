#!/usr/bin/env python3
"""A retrieval that lost instances has to say so, and a C-MOVE did not.

A C-MOVE whose peer cannot send some of its sub-operations does not fail: it
answers `0xB000`, "sub-operations complete, one or more failures", which is a
warning, and the association is released as though the study were whole.
`-[DCMTKQueryNode moveSCU:network:dataset:destination:]` printed the counts to
`stdout` under `_verbose` and told the user nothing.

Measured against `tools/serve-cmove-fixture.py` with two of six sub-operations
failed - a mixed study of 2 CT, 1 MR, 1 US and two ultrasound multiframes of 8
and 12 frames:

    C-Move RSP: MsgID: 1 [Status=Warning: SubOperationsCompleteOneOrMoreFailures]
      NumberOfCompletedSubOperations: 4
      NumberOfFailedSubOperations: 2

    studies: [('CMOVE^FIXTURE', -11)]
    image rows: 11   distinct files: 4

Eleven of twenty-four frames, and the retrieval reported success.

The counts are read now, by the same type the C-GET path uses, so the two cannot
drift apart. The C-MOVE does not turn the shortfall into an error condition:
`setupNetworkWithSyntax:` cancels its thread on one, and an image-level retrieve
would stop fetching the instances still to come.
"""
from pathlib import Path
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
failures = []
completion = root / 'Horos/Sources/RetrieveCompletion.swift'
node = (root / 'Horos/Sources/DCMTKQueryNode.mm').read_bytes().decode('latin1')


def body(signature, source):
    at = source.find(signature)
    if at < 0:
        return ''
    opening = source.index('{', at)
    depth, index = 0, opening
    while index < len(source):
        if source[index] == '{':
            depth += 1
        elif source[index] == '}':
            depth -= 1
            if depth == 0:
                return source[opening:index + 1]
        index += 1
    return ''


DRIVER = '''
import Foundation

func emit(_ key: String, _ value: String) { print("\\(key)\\t\\(value)") }

func report(_ operation: String, _ status: UInt, _ text: String?,
            _ completed: UInt, _ failed: UInt, _ warnings: UInt, _ remaining: UInt)
    -> RetrieveCompletion {
    return RetrieveCompletion(operation: operation, status: status, statusText: text,
                              completed: completed, failed: failed,
                              warnings: warnings, remaining: remaining)
}

let whole = report("C-MOVE", 0, "Success", 6, 0, 0, 0)
emit("whole", whole.everythingArrived ? "yes" : "no")
emit("wholeSummary", whole.summary)

// What the fixture measured: four of six arrived and the peer called it a warning.
let partial = report("C-MOVE", 0xb000, "Warning: SubOperationsCompleteOneOrMoreFailures",
                     4, 2, 0, 0)
emit("partial", partial.everythingArrived ? "yes" : "no")
emit("partialSummary", partial.summary)
emit("partialAccounted", String(partial.accountedFor))

// A peer that gave up part way still reports what it managed.
let stopped = report("C-MOVE", 0xc000, "Failed: UnableToProcess", 2, 4, 0, 4)
emit("stopped", stopped.everythingArrived ? "yes" : "no")
emit("stoppedSummary", stopped.summary)

// A sub-operation that arrived with a warning arrived, but is not clean.
let warned = report("C-GET", 0xb000, "Warning", 5, 0, 1, 0)
emit("warned", warned.everythingArrived ? "yes" : "no")
emit("warnedSummary", warned.summary)

// A refusal before any sub-operation carries no counts at all.
let refused = report("C-GET", 0xa701, "Refused: OutOfResourcesNumberOfMatches", 0, 0, 0, 0)
emit("refused", refused.everythingArrived ? "yes" : "no")
emit("refusedSummary", refused.summary)

// The three ways a C-MOVE fails have to read differently. Measured against the
// fixture: a destination nothing answers at, and a destination that answers and
// then cannot write what it receives.
emit("unreachableSummary",
     report("C-MOVE", 0xa801, "Failed: MoveDestinationUnknown", 0, 0, 0, 0).summary)
emit("cannotStoreSummary",
     report("C-MOVE", 0xa702, "Refused: OutOfResourcesSubOperations", 0, 6, 0, 0).summary)

emit("cancelConfirmed", RetrieveCompletion.cancellationSummary(operation: "C-MOVE", received: 1, expected: 6, confirmed: true))
emit("cancelPartial", RetrieveCompletion.cancellationSummary(operation: "C-GET", received: 1, expected: 6, confirmed: false))
emit("cancelUnknown", RetrieveCompletion.cancellationSummary(operation: "C-GET", received: 0, expected: 0, confirmed: false))

// And a peer that says nothing about the status still produces a sentence.
emit("silent", report("C-MOVE", 0xb000, nil, 1, 1, 0, 0).summary)

// A status the network layer cannot name gives the number back; saying it twice
// is not saying more.
emit("unnamed", report("C-GET", 0xc000, "Unknown Status: 0xc000", 2, 4, 0, 4).summary)
'''

results = {}
if not completion.exists():
    failures.append('nothing reads the sub-operation counts a retrieval ends with')
else:
    swiftc = subprocess.run(['xcrun', '--sdk', 'macosx', '-f', 'swiftc'], capture_output=True, text=True)
    if swiftc.returncode != 0:
        failures.append('no swiftc here: %s' % (swiftc.stderr or '').strip())
    else:
        with tempfile.TemporaryDirectory(prefix='horos-cmove-') as directory:
            # Top-level statements are only allowed in a file called main.swift.
            (Path(directory) / 'main.swift').write_text(DRIVER)
            binary = Path(directory) / 'completeness'
            built = subprocess.run(['xcrun', '--sdk', 'macosx', 'swiftc', '-o', str(binary),
                                    str(completion), str(Path(directory) / 'main.swift')],
                                   capture_output=True, text=True)
            if built.returncode != 0:
                failures.append('the completion report does not compile:\n%s' % built.stderr[-1500:])
            else:
                run = subprocess.run([str(binary)], capture_output=True, text=True)
                if run.returncode != 0:
                    failures.append('the driver failed: %s' % run.stderr[-800:])
                for line in run.stdout.splitlines():
                    key, _, value = line.partition('\t')
                    results[key] = value

if results:
    expected = {
        'cancelConfirmed': 'C-MOVE cancelled: 1 of 6 instances received.',
        'cancelPartial': 'C-GET cancelled: 1 of 6 instances confirmed received in the last response; final count not confirmed.',
        'cancelUnknown': 'C-GET cancelled: 0 instances (total unknown) confirmed received in the last response; final count not confirmed.',

        'whole': 'yes',
        'wholeSummary': 'C-MOVE complete: 6 of 6 sub-operations arrived (status 0x0000 Success)',
        'partial': 'no',
        'partialSummary': 'C-MOVE incomplete: 4 of 6 sub-operations arrived, 2 failed, '
                          '0 with warnings, 0 not attempted '
                          '(status 0xb000 Warning: SubOperationsCompleteOneOrMoreFailures)',
        'partialAccounted': '6',
        'stopped': 'no',
        'stoppedSummary': 'C-MOVE incomplete: 2 of 10 sub-operations arrived, 4 failed, '
                          '0 with warnings, 4 not attempted '
                          '(status 0xc000 Failed: UnableToProcess)',
        'warned': 'no',
        'warnedSummary': 'C-GET incomplete: 5 of 6 sub-operations arrived, 0 failed, '
                         '1 with warnings, 0 not attempted (status 0xb000 Warning)',
        'refused': 'no',
        'refusedSummary': 'C-GET failed: the peer reported no sub-operations '
                          '(status 0xa701 Refused: OutOfResourcesNumberOfMatches)',
        'unreachableSummary': 'C-MOVE failed: the peer reported no sub-operations '
                              '(status 0xa801 Failed: MoveDestinationUnknown)',
        'cannotStoreSummary': 'C-MOVE incomplete: 0 of 6 sub-operations arrived, 6 failed, '
                              '0 with warnings, 0 not attempted '
                              '(status 0xa702 Refused: OutOfResourcesSubOperations)',
        'silent': 'C-MOVE incomplete: 1 of 2 sub-operations arrived, 1 failed, '
                  '0 with warnings, 0 not attempted (status 0xb000)',
        'unnamed': 'C-GET incomplete: 2 of 10 sub-operations arrived, 4 failed, '
                   '0 with warnings, 4 not attempted (status 0xc000)',
    }
    for key, want in expected.items():
        got = results.get(key)
        if got != want:
            failures.append('%s: %r, expected %r' % (key, got, want))

# --- the move reports what it lost --------------------------------------------
move = body('- (OFCondition)moveSCU:(T_ASC_Association *)assoc  network:(T_ASC_Network *)net '
            'dataset:( DcmDataset *)dataset destination:', node)
if not move:
    failures.append('-moveSCU:network:dataset:destination: is gone')
else:
    if 'HorosRetrieveCompletion' not in move:
        failures.append('the move does not read the sub-operation counts it came back with, so a '
                        'partial retrieval is reported as a whole study')
    for field in ('NumberOfCompletedSubOperations', 'NumberOfFailedSubOperations',
                  'NumberOfWarningSubOperations', 'NumberOfRemainingSubOperations'):
        if move.count(field) < 2:
            failures.append('%s reaches the counters but not the report' % field)
    if 'everythingArrived' not in move:
        failures.append('nothing decides whether the move brought back everything')
    if 'Move Failed' not in move or 'completion.summary' not in move:
        failures.append('an incomplete move is not reported to the user with what it lost')
    # 0xB000 is a warning; branching on the status is what missed it.
    if 'DICOM_WARNING_STATUS' in move:
        failures.append('the move still decides by status, which reads 0xB000 as an arrival')
    at = move.find('everythingArrived')
    branch = move[at:at + 1200]
    if 'makeDcmnetCondition' in branch or 'cond = ' in branch:
        failures.append('the shortfall is turned into an error condition, which cancels the '
                        'thread an image-level retrieve is still fetching on')

# --- and the get uses the same words ------------------------------------------
get = body('- (OFCondition)getSCU:', node)
if not get:
    failures.append('-getSCU:network:dataset: is gone')
else:
    if 'HorosRetrieveCompletion' not in get or 'completion.summary' not in get:
        failures.append('the C-GET report has drifted away from the C-MOVE one')
    if 'Get Failed' not in get:
        failures.append('an incomplete retrieval is not reported to the user at all')

for failure in failures:
    print('FAIL: %s' % failure)
if failures:
    sys.exit(1)
print('ok: a C-MOVE or C-GET that lost sub-operations names what arrived and what did not, '
      'without cancelling the retrieve that is still running')
