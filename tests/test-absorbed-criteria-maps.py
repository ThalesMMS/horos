#!/usr/bin/env python3
"""#365: every absorbed criterion has a row, a state, and files that exist.

#365 requires the criteria absorbed into the post-backlog issues to keep their
`A…` identifiers and for no requirement to be left orphaned. Three maps carry
that link — one per issue that absorbed any — and a map is only worth having if
it cannot quietly rot: a row that points at a test deleted last month reads
exactly like a row that points at one still there.

So this checks the maps against the repository, not the maps against themselves:
every criterion the issue absorbed has a row, every row says what state it is in,
and every file a row names exists.
"""
from pathlib import Path
import re

root = Path(__file__).resolve().parents[1]
failures = []

MAPS = {
    'docs/issue-373-absorbed-criteria-map.md': ['A111', 'A255', 'A273', 'A294', 'A295', 'A297'],
    'docs/issue-374-absorbed-criteria-map.md': ['A205', 'A216', 'A224', 'A225'],
    'docs/issue-375-absorbed-criteria-map.md': ['A034', 'A209', 'A214', 'A215'],
    'docs/issue-377-absorbed-criteria-map.md': ['A247'],
    'docs/issue-378-absorbed-criteria-map.md': ['A237'],
    'docs/issue-380-absorbed-criteria-map.md': ['A300'],
}

# A row's state has to be one of these words, so "partial" cannot be written as
# a shrug. "não coberto" is a state too, and the most important one to allow.
STATES = ('coberto', 'parcial', 'não coberto', 'preservado', 'defeito provado')

for name, criteria in MAPS.items():
    path = root / name
    if not path.is_file():
        failures.append('%s is missing' % name)
        continue
    text = path.read_text(encoding='utf-8')

    rows = {}
    for line in text.split('\n'):
        if not line.startswith('| **A'):
            continue
        cells = [cell.strip() for cell in line.strip('|').split('|')]
        identifier = re.match(r'\*\*(A\d+)\*\*', cells[0])
        if identifier:
            rows[identifier.group(1)] = cells

    for criterion in criteria:
        if criterion not in rows:
            failures.append('%s has no row for %s' % (name, criterion))
            continue
        cells = rows[criterion]
        if len(cells) < 4:
            failures.append('%s: the %s row has %d columns, expected 4' % (name, criterion, len(cells)))
            continue
        if not any(state in cells[3].lower() for state in STATES):
            failures.append('%s: the %s row does not say what state it is in: %r'
                            % (name, criterion, cells[3][:60]))
        if not cells[2].strip():
            failures.append('%s: the %s row says nothing about what exists' % (name, criterion))

    extra = set(rows) - set(criteria)
    if extra:
        failures.append('%s has rows for criteria the issue did not absorb: %s'
                        % (name, ', '.join(sorted(extra))))

    # Every file a map names has to be there. A map is a finding aid; one that
    # points at nothing is worse than no map.
    for match in re.finditer(r'`((?:docs|tests|tools|Horos)/[^`]+?\.(?:py|md|m|mm|swift|json))`', text):
        named = match.group(1)
        if not (root / named).exists():
            failures.append('%s names %s, which does not exist' % (name, named))

    if 'Nenhuma linha abaixo aprova um critério' not in text:
        failures.append('%s must keep saying that no row approves a criterion' % name)
    if '#385' not in text:
        failures.append('%s must say that the integrated check belongs to #385' % name)

if failures:
    print('FAIL:')
    for item in failures:
        print(' ', item)
    raise SystemExit(1)

print('PASS: %d maps, %d absorbed criteria, each with a row, a state and files that exist'
      % (len(MAPS), sum(len(c) for c in MAPS.values())))
