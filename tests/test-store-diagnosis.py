#!/usr/bin/env python3
"""A DICOM send says which of three things went wrong, per file, and carries on.

A send that lost files told the user `Errors ! 7 of 7 files generated errors.`
and, in the alert, `Unsuccessful Store Encountered, see
Applications/Utilities/Console.app for more detailed informations.` What was
there to see was fprintf(stderr) from a released application, and it did not
distinguish

  - the file - unreadable, or carrying no SOP Class and SOP Instance UID, which
    is what produces `DIMSE Inappropriate data for message`;
  - the negotiation - no presentation context for that SOP class in that
    transfer syntax, which a successful C-ECHO says nothing about;
  - the DIMSE message - the node answered the C-STORE with a failure status.

The first two are properties of one file and leave the association usable. The
send used to stop at the first failure of any kind, so one refused instance kept
six good ones from ever being offered.
"""
from pathlib import Path
import re
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
failures = []
report = root / 'Horos/Sources/StoreReport.swift'
scu = (root / 'Horos/Sources/DCMTKStoreSCU.mm').read_bytes().decode('latin1')

DRIVER = r'''
import Foundation

func emit(_ key: String, _ value: String) { print(key + "\t" + value) }

let report = StoreReport()
report.recordSent(path: "/db/1.dcm", statusText: "status 0x0000 (Success)")
report.recordRejected(path: "/db/2.dcm", statusText: "status 0xa700 (Refused: OutOfResources)")
emit("afterRejected.fileLevel", report.lastFailureIsFileLevel ? "yes" : "no")
report.recordNoPresentationContext(path: "/db/3.dcm",
                                   sopClassUID: "1.2.840.10008.5.1.4.1.1.6.1 (US)",
                                   transferSyntax: "LittleEndianExplicit")
emit("afterNegotiation.fileLevel", report.lastFailureIsFileLevel ? "yes" : "no")
report.recordWithoutIdentity(path: "/db/4.dcm")
emit("afterIdentity.fileLevel", report.lastFailureIsFileLevel ? "yes" : "no")
emit("sent", String(report.sentCount))
emit("failed", String(report.failedCount))
emit("complete", report.isComplete ? "yes" : "no")
emit("failedPaths", report.failedPaths.joined(separator: ","))
emit("summary", report.summary)
emit("detail", report.detail(limit: 10).replacingOccurrences(of: "\n", with: " | "))
emit("bounded", report.detail(limit: 1).replacingOccurrences(of: "\n", with: " | "))

// A transmission that failed is not about one file: nothing after it is worth
// attempting on the same association.
let broken = StoreReport()
broken.recordTransportFailure(path: "/db/5.dcm", reason: "DUL peer aborted")
emit("transport.fileLevel", broken.lastFailureIsFileLevel ? "yes" : "no")
emit("transport.detail", broken.detail(limit: 10).replacingOccurrences(of: "\n", with: " | "))

let unreadable = StoreReport()
unreadable.recordUnreadable(path: "/db/6.dcm", reason: "Invalid stream header")
unreadable.recordNonStorage(path: "/db/7.dcm", sopClassUID: "1.2.840.10008.5.1.4.38.1")
emit("other.detail", unreadable.detail(limit: 10).replacingOccurrences(of: "\n", with: " | "))

let clean = StoreReport()
clean.recordSent(path: "/db/8.dcm", statusText: "status 0x0000 (Success)")
emit("clean.summary", clean.summary)
emit("clean.complete", clean.isComplete ? "yes" : "no")
'''

# --- the report, compiled and run --------------------------------------------
results = {}
swiftc = subprocess.run(['xcrun', '--sdk', 'macosx', '-f', 'swiftc'], capture_output=True, text=True)
if swiftc.returncode != 0:
    failures.append('no swiftc here: %s' % (swiftc.stderr or '').strip())
else:
    with tempfile.TemporaryDirectory(prefix='horos-store-report-') as directory:
        # Top-level statements are only allowed in a file called main.swift.
        (Path(directory) / 'main.swift').write_text(DRIVER)
        binary = Path(directory) / 'report'
        built = subprocess.run(['xcrun', '--sdk', 'macosx', 'swiftc', '-o', str(binary),
                                str(report), str(Path(directory) / 'main.swift')],
                               capture_output=True, text=True)
        if built.returncode != 0:
            failures.append('the report does not compile:\n%s' % built.stderr[-1500:])
        else:
            run = subprocess.run([str(binary)], capture_output=True, text=True)
            if run.returncode != 0:
                failures.append('the report driver failed: %s' % run.stderr[-800:])
            for line in run.stdout.splitlines():
                key, _, value = line.partition('\t')
                results[key] = value

if results:
    expected = {
        # All three leave the association usable, so the send goes on.
        'afterRejected.fileLevel': 'yes',
        'afterNegotiation.fileLevel': 'yes',
        'afterIdentity.fileLevel': 'yes',
        # A failed transmission does not.
        'transport.fileLevel': 'no',
        'sent': '1', 'failed': '3', 'complete': 'no',
        'failedPaths': '/db/2.dcm,/db/3.dcm,/db/4.dcm',
        'clean.summary': '1 of 1 sent.', 'clean.complete': 'yes',
    }
    for key, value in expected.items():
        if results.get(key) != value:
            failures.append('%s is %r, expected %r' % (key, results.get(key), value))

    summary = results.get('summary', '')
    for fragment in ('1 of 4 sent', '3 failed',
                     'the node refused the C-STORE',
                     'the node accepted no presentation context',
                     'could not be read or names no SOP Instance'):
        if fragment not in summary:
            failures.append('the summary does not count %r: %r' % (fragment, summary))

    detail = results.get('detail', '')
    for fragment in ('2.dcm: the node answered the C-STORE with status 0xa700',
                     '3.dcm: the node accepted no presentation context for '
                     '1.2.840.10008.5.1.4.1.1.6.1 (US) in LittleEndianExplicit',
                     '4.dcm: the file has no SOP Class and SOP Instance UID'):
        if fragment not in detail:
            failures.append('the detail does not say %r: %r' % (fragment, detail))
    if 'C-ECHO' not in detail:
        failures.append('the negotiation failure does not say a C-ECHO proves nothing about it')
    if '/db/' in detail:
        failures.append('the detail prints whole database paths: %r' % detail)
    if 'and 2 more' not in results.get('bounded', ''):
        failures.append('the detail is not bounded: %r' % results.get('bounded'))
    if 'the transmission failed — DUL peer aborted' not in results.get('transport.detail', ''):
        failures.append('a failed transmission is not explained: %r' % results.get('transport.detail'))
    other = results.get('other.detail', '')
    if 'could not be read as DICOM — Invalid stream header' not in other:
        failures.append('an unreadable file is not explained: %r' % other)
    if 'is not a storage SOP class' not in other:
        failures.append('a non-storage SOP class is not explained: %r' % other)

# --- the send -----------------------------------------------------------------
for expected, missing in (
        ('recordUnreadablePath:', 'a file that cannot be read is not recorded'),
        ('recordPathWithoutIdentity:', 'a file with no SOP Class UID is not recorded'),
        ('recordNoPresentationContextPath:', 'a refused negotiation is not recorded'),
        ('recordRejectedPath:', 'a C-STORE the node refused is not recorded'),
        ('recordTransportFailurePath:', 'a failed transmission is not recorded'),
        ('recordSentPath:', 'a successful store is not recorded')):
    if expected not in scu:
        failures.append(missing)

# One file the node will not take no longer ends the send.
at = scu.find('cond = cstore(context, assoc, *iter);')
if at < 0:
    failures.append('the send loop is gone')
else:
    loop = scu[at - 400:at + 1200]
    if 'while ((iter != enditer) && (cond == EC_Normal))' in loop:
        failures.append('the send still stops at the first failure of any kind')
    if 'lastFailureIsFileLevel' not in loop:
        failures.append('the send does not ask whether the failure was about the file')
    if 'associationLost' not in loop:
        failures.append('the send does not stop when the association is gone')

# And the user is told what happened, not where to go looking.
# Look at the code rather than the prose: a comment quotes the old sentence,
# and an older version of the line is commented out below it.
code = '\n'.join(re.sub(r'//.*$', '', line) for line in scu.splitlines())
if re.search(r'reason:\s*@"Unsuccessful Store Encountered', code):
    failures.append('the failure still tells the user to open Console.app')
if not re.search(r'localException = \[\[NSException exceptionWithName:[^\]]*reason:\s*\[_report detailWithLimit:', code):
    failures.append('the exception the user sees does not carry the per-file detail')
if 'detailWithLimit:' not in scu:
    failures.append('the failure does not carry the per-file detail')

for failure in failures:
    print('FAIL: %s' % failure)
if failures:
    sys.exit(1)
print('ok: each file that does not arrive is named with which of the three things happened, '
      'and only a failed transmission stops the send')
