#!/usr/bin/env python3
"""The query window can sort on how much of a study is already here.

The percentage existed already, in the tooltip and as a pie next to the name, and
four places worked it out the same two ways: divide the local file count by the
remote one and clamp to 1. That reads a remote total of zero - what a node that
does not send NumberOfStudyRelatedInstances gives you - as 0%, which is
indistinguishable from a study none of which has arrived; and it reads more files
locally than the node reports as 100%, which is the one case where the counts
agreeing proves least.

HorosLocalCompleteness keeps the three states apart. It is Swift, and it is
compiled and run here; the column that shows and sorts on it is checked in
source.
"""
from pathlib import Path
import re
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
failures = []
completeness = root / 'Horos/Sources/LocalCompleteness.swift'
controller = (root / 'Horos/Sources/QueryController.mm').read_bytes().decode('latin1')

DRIVER = r'''
import Foundation

func emit(_ key: String, _ value: String) { print(key + "\t" + value) }

func row(_ name: String, _ local: Int, _ remote: NSNumber?) -> LocalCompleteness {
    let value = LocalCompleteness(localCount: local, remoteCount: remote)
    emit(name + ".text", value.text)
    emit(name + ".sort", String(format: "%.4f", value.sortValue))
    emit(name + ".complete", value.isComplete ? "yes" : "no")
    emit(name + ".known", value.remoteCountIsKnown ? "yes" : "no")
    emit(name + ".fraction", String(format: "%.4f", value.fraction))
    emit(name + ".explanation", value.explanation)
    return value
}

let none = row("none", 0, 10)
let half = row("half", 5, 10)
let all = row("all", 10, 10)
let unknown = row("unknown", 4, nil)
let zeroTotal = row("zeroTotal", 4, 0)
let excess = row("excess", 12, 10)
let nothingAtAll = row("nothingAtAll", 0, nil)

// Sorting is numeric, and the unknown total is not a low percentage.
let ordered = [all, unknown, half, excess, none].sorted { $0.compare($1) == .orderedAscending }
emit("order", ordered.map { $0.text }.joined(separator: " | "))
'''

# --- the value, compiled and run ---------------------------------------------
results = {}
swiftc = subprocess.run(['xcrun', '--sdk', 'macosx', '-f', 'swiftc'], capture_output=True, text=True)
if swiftc.returncode != 0:
    failures.append('no swiftc here: %s' % (swiftc.stderr or '').strip())
else:
    with tempfile.TemporaryDirectory(prefix='horos-completeness-') as directory:
        # Top-level statements are only allowed in a file called main.swift.
        (Path(directory) / 'main.swift').write_text(DRIVER)
        binary = Path(directory) / 'completeness'
        built = subprocess.run(['xcrun', '--sdk', 'macosx', 'swiftc', '-o', str(binary),
                                str(completeness), str(Path(directory) / 'main.swift')],
                               capture_output=True, text=True)
        if built.returncode != 0:
            failures.append('the completeness value does not compile:\n%s' % built.stderr[-1500:])
        else:
            run = subprocess.run([str(binary)], capture_output=True, text=True)
            if run.returncode != 0:
                failures.append('the driver failed: %s' % run.stderr[-800:])
            for line in run.stdout.splitlines():
                key, _, value = line.partition('\t')
                results[key] = value

if results:
    expected = {
        'none.text': '0% (0/10)', 'none.complete': 'no', 'none.sort': '0.0000',
        'half.text': '50% (5/10)', 'half.complete': 'no', 'half.sort': '0.5000',
        'all.text': '100% (10/10)', 'all.complete': 'yes', 'all.sort': '1.0000',
        # The node said nothing. That is not zero per cent, and it is not
        # complete either.
        'unknown.text': '? (4 local)', 'unknown.complete': 'no', 'unknown.known': 'no',
        'unknown.sort': '-1.0000', 'unknown.fraction': '0.0000',
        # A total of zero is the same as no total: it is what a node that does
        # not fill the field sends.
        'zeroTotal.text': '? (4 local)', 'zeroTotal.known': 'no',
        # More here than the node reports is not proof that nothing is missing.
        'excess.text': '>100% (12/10)', 'excess.complete': 'no',
        'nothingAtAll.text': '?',
    }
    for key, value in expected.items():
        if results.get(key) != value:
            failures.append('%s is %r, expected %r' % (key, results.get(key), value))
    if results.get('half.explanation') != '5 of 10 here; 5 still to retrieve.':
        failures.append('the explanation does not say what is left: %r'
                        % results.get('half.explanation'))
    if 'did not say' not in results.get('unknown.explanation', ''):
        failures.append('an unknown total is not explained: %r' % results.get('unknown.explanation'))
    # Ascending: unknown, then 0%, then 50%, then 100%, then more than the node says.
    order = results.get('order', '')
    if order != '? (4 local) | 0% (0/10) | 50% (5/10) | 100% (10/10) | >100% (12/10)':
        failures.append('the sort order is %r' % order)

# --- the column ---------------------------------------------------------------
for expected, missing in (
        (r'initWithIdentifier:\s*@"localCompleteness"', 'there is no completeness column'),
        (r'setSortDescriptorPrototype', 'the column cannot be sorted on'),
        (r'isEqualToString:\s*@"localCompleteness"\]\)\s*\n\s*\{\s*\n\s*HorosLocalCompleteness',
         'the column has no value')):
    if not re.search(expected, controller):
        failures.append(missing)

# One place reads the two counts, so the column, the tooltip and the pie agree.
# The remaining readers are the auto-retrieve decisions, which are a different
# question - whether to fetch again - and are left alone here.
def body(signature):
    at = controller.find(signature)
    if at < 0:
        failures.append('%s is gone' % signature.split(':')[0])
        return ''
    opening = controller.index('{', at)
    depth, index = 0, opening
    while index < len(controller):
        if controller[index] == '{':
            depth += 1
        elif controller[index] == '}':
            depth -= 1
            if depth == 0:
                return controller[opening:index + 1]
        index += 1
    return ''


for signature, what in (
        ('- (NSString *)outlineView:(NSOutlineView *)ov toolTipForCell:', 'the tooltip'),
        ('- (void)outlineView:(NSOutlineView *)oV willDisplayCell:', 'the cell'),
        ('- (id)outlineView:(NSOutlineView *)outlineView objectValueForTableColumn:', 'the column')):
    if 'rawNoFiles' in body(signature):
        failures.append('%s works the percentage out for itself again' % what)
if len(re.findall(r'localCompletenessForItem:', controller)) < 4:
    failures.append('the column, the tooltip, the pie and the sort do not all use one value')

# The sort compares rows, because completeness is not a property of the node.
sort = controller[controller.find('- (NSArray*) sortArray'):]
sort = sort[:sort.find('\n- (')]
if 'localCompleteness' not in sort or 'comparator' not in sort:
    failures.append('sorting by completeness does not compare the rows')

# A pie is a proportion; an unknown total has none to draw.
pie = controller[controller.find('pieChartImageWithPercentage: completeness.fraction') - 600:]
pie = pie[:700]
if 'remoteCountIsKnown' not in pie:
    failures.append('a pie is still drawn when the node did not say how many it holds')

for failure in failures:
    print('FAIL: %s' % failure)
if failures:
    sys.exit(1)
print('ok: completeness tells an unknown total from 0%, refuses to call a study complete when '
      'the counts do not match exactly, sorts numerically with the unknowns apart, and one '
      'value feeds the column, the tooltip, the pie and the sort')
