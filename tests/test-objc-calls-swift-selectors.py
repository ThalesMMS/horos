#!/usr/bin/env python3
"""Objective-C may only send a Swift class a selector that class exports.

Swift decides the Objective-C name itself unless told otherwise, and the rules
are not guessable at a glance: `job(from:source:)` becomes `jobFrom:source:`,
while `displayOrigin(name:path:)` becomes `displayOriginWithName:path:`.
Calling the name that reads well instead of the name that exists compiles with
only a warning and crashes at run time with an unrecognised selector - which is
how File > Print on the database window came to be broken (#529).

Rather than reimplement Swift's naming rules, this reads the generated
`Horos-Swift.h`, which is what the compiler actually publishes, and checks the
class-method sends aimed at those classes. Without a build there is no header,
so it skips.
"""
from pathlib import Path
import re
import sys

root = Path(__file__).resolve().parents[1]
header = next((p for p in (
    root / 'build/Build/Intermediates.noindex/Horos.build/Debug/Horos.build/DerivedSources/Horos-Swift.h',
    root / 'build/Build/Intermediates.noindex/Horos.build/Release/Horos.build/DerivedSources/Horos-Swift.h',
) if p.is_file()), None)
if header is None:
    print('skipped: needs the generated Horos-Swift.h; build the Horos target first',
          file=sys.stderr)
    raise SystemExit(2)

text = header.read_text(errors='replace')
failures = []

# --- what each Swift class publishes to Objective-C --------------------------
classes = {}
for block in re.finditer(r'@interface\s+(\w+)[^\n]*\n(.*?)\n@end', text, re.S):
    name, body = block.group(1), block.group(2)
    selectors = set()
    for method in re.finditer(r'^\s*\+\s*\([^)]*\)\s*([^;]+);', body, re.M):
        signature = method.group(1)
        parts = re.findall(r'(\w+):', signature)
        selectors.add(':'.join(parts) + ':' if parts else signature.strip().split()[0])
    for prop in re.finditer(r'^\s*\+\s*\([^)]*\)\s*(\w+)\s*(?:SWIFT_\w+\s*)*;', body, re.M):
        selectors.add(prop.group(1))
    classes.setdefault(name, set()).update(selectors)

if not classes:
    print('FAIL: no class interface was found in the generated header', file=sys.stderr)
    sys.exit(1)

# A Swift class can also be extended by an Objective-C category in this project -
# HorosGSPSDocument gets +documentWithContentsOfFile: that way - and those
# selectors are real even though the generated header knows nothing about them.
for head in sorted((root / 'Horos/Sources').glob('*.h')):
    body = head.read_text(errors='replace')
    for block in re.finditer(r'@interface\s+(\w+)\s*\([^)]*\)(.*?)@end', body, re.S):
        name, members = block.group(1), block.group(2)
        if name not in classes:
            continue
        for method in re.finditer(r'^\s*\+\s*\([^)]*\)\s*([^;]+);', members, re.M):
            parts = re.findall(r'(\w+):', method.group(1))
            classes[name].add(':'.join(parts) + ':' if parts
                              else method.group(1).strip().split()[0])

# NSObject answers these on every class; the generated header does not list them.
INHERITED = {'alloc', 'new', 'class', 'self', 'superclass', 'load', 'initialize',
             'description', 'debugDescription', 'hash', 'allocWithZone:',
             'instancesRespondToSelector:', 'conformsToProtocol:',
             'respondsToSelector:', 'isSubclassOfClass:', 'resolveClassMethod:',
             'resolveInstanceMethod:', 'keyPathsForValuesAffectingValueForKey:',
             'automaticallyNotifiesObserversForKey:', 'accessInstanceVariablesDirectly',
             'setVersion:', 'version', 'instanceMethodForSelector:'}

comment = re.compile(r'//[^\n]*|/\*.*?\*/', re.S)
checked = 0
for path in sorted(list((root / 'Horos/Sources').glob('*.m'))
                   + list((root / 'Horos/Sources').glob('*.mm'))):
    body = comment.sub(' ', path.read_text(encoding='latin1'))
    for name, selectors in classes.items():
        # A class-method send: [ClassName first... — take the first keyword only,
        # which is enough to catch a name that does not exist at all.
        for send in re.finditer(r'\[\s*%s\s+([A-Za-z_][A-Za-z0-9_]*:?)' % re.escape(name), body):
            first = send.group(1)
            if first in INHERITED:
                continue
            checked += 1
            if first.endswith(':'):
                ok = any(s.startswith(first) for s in selectors)
            else:
                ok = first in selectors or any(s == first for s in selectors)
            if not ok:
                line = body[:send.start()].count('\n') + 1
                failures.append('%s:%d sends +%s to %s; the generated header publishes '
                                'no such class method'
                                % (path.name, line, first, name))

if failures:
    for item in sorted(set(failures)):
        print('FAIL:', item, file=sys.stderr)
    sys.exit(1)
print('PASS: %d class-method send(s) to %d Swift class(es) name published selectors'
      % (checked, len(classes)))
