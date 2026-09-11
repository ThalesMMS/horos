#!/usr/bin/env python3
"""What each Epic is still waiting for, from the checklists themselves.

The area Epics (#309–#318), the umbrella #318 and the migration phase #366 all
carry a checklist of the issues they cover. Those checkboxes are written by hand
and drift: an issue closes and the box stays empty, so an Epic looks further from
done than it is -- or nearer, which is worse.

This reads every checklist, asks GitHub for the real state of each child, and
prints the disagreements and what is genuinely left. It talks to the network, so
it is a tool and not a test: `tools/run-tests.py` has to work in a clean clone
with no credentials.

    python3 tools/report-epic-status.py            # table
    python3 tools/report-epic-status.py --check    # exit 1 if any box disagrees
"""
import argparse
import json
import re
import subprocess
import sys

EPICS = [309, 310, 311, 312, 313, 314, 315, 316, 317, 318, 366]


def body(issue):
    return subprocess.run(['gh', 'issue', 'view', str(issue), '--json', 'body', '-q', '.body'],
                          capture_output=True, text=True, check=True).stdout


def states():
    listing = json.loads(subprocess.run(
        ['gh', 'issue', 'list', '--state', 'all', '--limit', '1000', '--json', 'number,state'],
        capture_output=True, text=True, check=True).stdout)
    return {item['number']: item['state'] for item in listing}


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--check', action='store_true',
                        help='exit non-zero when a checkbox disagrees with the issue')
    arguments = parser.parse_args()

    known = states()
    disagreements = []
    rows = []
    for epic in EPICS:
        marks = re.findall(r'^- \[([ x])\]\s*#(\d+)', body(epic), re.M)
        children = [(mark, int(number)) for mark, number in marks]
        for mark, number in children:
            state = known.get(number)
            if state is None:
                continue
            if mark == ' ' and state == 'CLOSED':
                disagreements.append('#%d: #%d is closed but unticked' % (epic, number))
            if mark == 'x' and state == 'OPEN':
                disagreements.append('#%d: #%d is ticked but open' % (epic, number))
        openChildren = sorted({number for _, number in children if known.get(number) == 'OPEN'})
        rows.append((epic, len(children), openChildren))

    width = max(len(str(epic)) for epic, _, _ in rows)
    for epic, total, openChildren in rows:
        waiting = ', '.join('#%d' % number for number in openChildren) or 'nothing — could close'
        print('#%-*d  %2d children  %2d open  %s' % (width, epic, total, len(openChildren), waiting))

    blocking = {}
    for _, _, openChildren in rows:
        for number in openChildren:
            blocking[number] = blocking.get(number, 0) + 1
    if blocking:
        print('\nHolding the most Epics open:')
        for number, count in sorted(blocking.items(), key=lambda pair: (-pair[1], pair[0]))[:5]:
            print('  #%d blocks %d' % (number, count))

    if disagreements:
        print('\nCheckboxes that disagree with the issues:')
        for line in disagreements:
            print(' ', line)
        if arguments.check:
            return 1
    elif arguments.check:
        print('\nEvery checkbox agrees with its issue.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
