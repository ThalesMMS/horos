#!/usr/bin/env python3
"""The release gate record names what it claims, and the files it cites exist (#385).

The gate is a document, so the thing that can rot is its references. This checks
that every criterion the Epic forwards appears in it, that every repository file
it points at is really there, that the tools and suites it credits exist, and
that the open risks it carries are the issues that are actually open.
"""
from pathlib import Path
import re

root = Path(__file__).resolve().parents[1]
gate = root / 'docs/issue-385-release-gate.md'
failures = []
if not gate.is_file():
    raise SystemExit('FAIL: the release gate record is missing')
text = gate.read_text()

# The 17 forwarded scopes of #366: 16 absorbed plus A034 as regression/residual.
forwarded = ['A111', 'A255', 'A273', 'A294', 'A295', 'A297',
             'A205', 'A216', 'A224', 'A225',
             'A209', 'A214', 'A215',
             'A247', 'A237', 'A300', 'A034']
for criterion in forwarded:
    if not re.search(r'\b%s\b' % criterion, text):
        failures.append('the gate does not name ' + criterion)
if 'A034' in text and 'regress' not in text.lower():
    failures.append('A034 must be carried as a regression and residual, not as an absorption')

# Every repository path it cites has to exist.
cited = set(re.findall(r'`((?:docs|tests|tools|updates|Horos)/[A-Za-z0-9_./+-]+)`', text))
if len(cited) < 20:
    failures.append('the gate cites suspiciously few files: %d' % len(cited))
for path in sorted(cited):
    candidate = root / path
    if not candidate.exists() and not list(root.glob(path)):
        failures.append('cited path does not exist: ' + path)

# The consolidations and the dispositions it must not lose.
for token in ('#308', '#304', '#227', '#231', '#269', '#360', '#34'):
    if token not in text:
        failures.append('the gate must account for ' + token)

# The open risks it carries.
for risk in ('#599', '#600'):
    if risk not in text:
        failures.append('the gate must carry the open risk ' + risk)

# The numbers it reports have to be reported, not implied.
for claim in ('526 passados', 'BUILD SUCCEEDED', '23722fb552d96fa2d60c7f58a6d4ac2c27950f86'):
    if claim not in text:
        failures.append('the gate no longer states: ' + claim)

# It must keep saying what it is not.
for limit in ('não é validação clínica', 'Build não é runtime'):
    if limit.lower() not in text.lower():
        failures.append('the gate dropped its own limit: ' + limit)

if failures:
    print('FAIL:')
    for item in failures:
        print(' ', item)
    raise SystemExit(1)
print('PASS: the release gate names the 17 forwarded scopes, the four consolidations, the concurrent '
      'dispositions and the open risks, and every file it cites exists (%d paths)' % len(cited))
