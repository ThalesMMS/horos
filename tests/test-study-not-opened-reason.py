#!/usr/bin/env python3
"""A study that will not open says why, instead of answering success in silence.

Every order from outside the application - an XML-RPC `DisplaySeries` or
`DisplayStudy`, a `horos://` link from a worklist, a plugin - ends at
`-[BrowserController displayStudy:object:command:]`, which begins by selecting
the study in the database list. `selectThisStudy:` had five ways to return `NO`
and a sixth for an exception, logged nothing on any of them, and every caller
threw the answer away. The
XML-RPC reply said `error 0`. The link handler set `succeeded = YES` before
asking. No viewer appeared and nothing anywhere said why - which is what "the 2D
viewer never opened" reports are made of.

The reasons are distinct sentences, they name the study, and each refusal is
reported where it happens.
"""
from pathlib import Path
import re
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
failures = []


def strip(text):
    text = re.sub(r'//[^\n]*', '', text)
    return re.sub(r'/\*.*?\*/', '', text, flags=re.S)


browser = (root / 'Horos/Sources/BrowserController.m').read_bytes().decode('latin1')
header = (root / 'Horos/Sources/BrowserController.h').read_bytes().decode('latin1')
rpc = (root / 'Horos/Sources/XMLRPCMethods.mm').read_bytes().decode('latin1')
application = (root / 'Horos/Sources/AppController.m').read_bytes().decode('latin1')

# --- the browser records a reason rather than a bare NO -----------------------
if '@property(copy) NSString *lastStudyNotOpenedReason;' not in header:
    failures.append('the browser has nowhere to record why the last study did not open')

select = strip(browser)
at = select.find('- (BOOL) selectThisStudy: (NSManagedObject*)study')
body = select[at:] if at >= 0 else ''
if not body:
    failures.append('selectThisStudy: is gone')
else:
    body = body[:body.index('\n}') + 2]
    bare = re.findall(r'return NO;', body)
    if bare:
        failures.append('selectThisStudy: still has %d silent refusal(s)' % len(bare))
    for reason in ('reasonForNoDatabase', 'reasonForNoStudy', 'reasonForUnknownDatabase',
                   'reasonForStudyOutsideAnyDatabase', 'reasonForStudyNotListed',
                   'reasonForErrorWhileSelecting'):
        if reason not in body:
            failures.append('selectThisStudy: never reports %s' % reason)
    # The study that was found has to clear the last reason, or the next caller
    # to ask would be handed a stale one and report a failure that did not happen.
    if 'lastStudyNotOpenedReason = nil' not in body:
        failures.append('a study that does open leaves the previous reason in place')

if 'NSLog' not in strip(browser)[select.find('- (BOOL) refuseToSelectStudy:'):][:600]:
    failures.append('the refusal is recorded on the browser and never logged')

# --- the XML-RPC opener acts on the answer -----------------------------------
for entry in ('_onMainThreadOpenObjectsWithIDs:', '_onMainThreadSelectObjectsWithIDs:'):
    at = strip(rpc).find('-(void)%s' % entry)
    opener = strip(rpc)[at:at + 1500] if at >= 0 else ''
    if not opener:
        failures.append('%s is gone' % entry)
        continue
    if 'reportStudyNotOpened' not in opener:
        failures.append('%s does not say when nothing opened' % entry)
    # A reason left over from an older refusal would silence this one.
    if 'lastStudyNotOpenedReason = nil' not in opener:
        failures.append('%s does not clear the previous reason before trying' % entry)
    if not re.search(r'if\(\s*\[\[BrowserController currentBrowser\] displayStudy:', opener):
        failures.append('%s still discards the answer from displayStudy:' % entry)

# --- and the link handler stops claiming success before it has it ------------
at = application.find('BOOL succeeded = NO;')
handler = application[at:at + 4200] if at >= 0 else ''
if not handler:
    failures.append('the horos:// image handler is gone')
else:
    if 'succeeded = YES;' in handler:
        failures.append('the link handler still records success before asking whether the study '
                        'opened, which also skips the whole-database search that follows')
    if handler.count('succeeded = [[BrowserController currentBrowser] displayStudy:') != 2:
        failures.append('the link handler does not take its answer from displayStudy: in both '
                        'searches')
    if 'NSRunAlertPanel' not in handler or 'lastStudyNotOpenedReason' not in handler:
        failures.append('somebody who clicked a link is still told nothing when no viewer opens')
    # Nothing may have matched at all, in which case the browser was never asked
    # and logged nothing: this line has to carry the reason and what was asked for.
    if not re.search(r'NSLog\([^;]*reason[^;]*sopinstanceuid', handler):
        failures.append('the line the link handler logs does not carry both the reason and the '
                        'image the link asked for')
    if handler.count('lastStudyNotOpenedReason = nil') != 1:
        failures.append('the link handler does not clear the previous reason before searching')

for failure in failures:
    print('FAIL: %s' % failure)

main = r'''import Foundation

let uid = "1.2.826.0.1.3680043.8.498.102"
let reasons = [
    StudyNotOpenedReason.reasonForNoDatabase(),
    StudyNotOpenedReason.reasonForNoStudy(),
    StudyNotOpenedReason.reasonForStudyOutsideAnyDatabase(uid),
    StudyNotOpenedReason.reasonForUnknownDatabase(uid),
    StudyNotOpenedReason.reasonForStudyNotListed(uid),
    StudyNotOpenedReason.reasonForNoImageSeries(uid),
    StudyNotOpenedReason.reasonForErrorWhileSelecting(),
]
assert(Set(reasons).count == reasons.count, "the reasons have to be told apart")
for reason in reasons {
    assert(!reason.isEmpty && reason.count < 90, reason)
}

// The four that are about one study name it, so a log line is enough to go on.
for named in reasons[2..<6] {
    assert(named.contains(uid), named)
}
// An exception while searching does not claim the study is missing.
let raised = StudyNotOpenedReason.reasonForErrorWhileSelecting()
assert(!raised.lowercased().contains("no longer") && !raised.contains(uid), raised)
// And they read as a sentence without it, when the study has no UID to give.
assert(StudyNotOpenedReason.reasonForStudyNotListed(nil)
       == "That study is not in the database list")
assert(StudyNotOpenedReason.reasonForStudyNotListed("   ")
       == "That study is not in the database list")
assert(StudyNotOpenedReason.reasonForNoImageSeries(" 1.2.3 ").contains("(1.2.3)"))

// One word in front of every reason, so a search of the log finds them all.
assert(StudyNotOpenedReason.logPrefix().lowercased().contains("not opened"))

print("PASS: seven distinct reasons, the study named, one prefix in front of each")
'''

with tempfile.TemporaryDirectory(prefix='horos-study-not-opened-') as tmp:
    p = Path(tmp)
    (p / 'main.swift').write_text(main)
    subprocess.run(['swiftc', str(root / 'Horos/Sources/StudyNotOpenedReason.swift'),
                    str(p / 'main.swift'), '-o', str(p / 'test')], check=True)
    subprocess.run([str(p / 'test')], check=True)

if failures:
    sys.exit(1)
print('ok: every refusal to open a study is named, recorded and acted on by its caller')
