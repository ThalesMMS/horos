#!/usr/bin/env python3
"""Objective-C has to spell a Swift class by its `@objc` name.

`@objc(HorosROIAssociationItem) class ROIAssociationItem` is `ROIAssociationItem`
in Swift and `HorosROIAssociationItem` everywhere else. Writing the Swift name in
Objective-C compiles nowhere:

    ViewerController+ROIInterchange.m:402:41: error: unknown type name
    'ROIAssociationItem'; did you mean 'HorosROIAssociationItem'?

The mistake is invisible in review because the Swift side reads correctly, and it
only surfaces once every earlier build error is out of the way.
"""
from pathlib import Path
import re
import sys

root = Path(__file__).resolve().parents[1]
failures = []

sources = root / 'Horos/Sources'
exposed = {}
for source in sorted(sources.glob('*.swift')):
    text = source.read_text(encoding='utf-8', errors='replace')
    for objc_name, swift_name in re.findall(
            r'@objc\((\w+)\)\s*(?:@\w+\s*)*(?:public\s+|internal\s+|final\s+|open\s+)*'
            r'(?:class|enum|protocol)\s+(\w+)', text):
        if objc_name != swift_name:
            exposed[swift_name] = (objc_name, source.name)

if not exposed:
    print('FAIL: no renamed @objc Swift declaration was found to check', file=sys.stderr)
    sys.exit(1)

# A name that Objective-C also declares itself is its own type there, not a
# misspelling of the Swift one.
objc_declared = set()
for pattern in ('**/*.h', '**/*.m', '**/*.mm'):
    for source in root.glob('Horos/' + pattern):
        text = source.read_text(encoding='utf-8', errors='replace')
        objc_declared.update(re.findall(r'@(?:interface|protocol)\s+(\w+)', text))
        objc_declared.update(re.findall(r'@class\s+([\w\s,]+);',
                                        text) and re.findall(r'@class\s+(\w+)', text))
        objc_declared.update(re.findall(r'typedef\s+(?:NS_ENUM|NS_OPTIONS)\s*\([^,]+,\s*(\w+)\)', text))

comment = re.compile(r'//[^\n]*|/\*.*?\*/', re.S)
string = re.compile(r'@"(?:[^"\\]|\\.)*"')

for swift_name, (objc_name, declared_in) in sorted(exposed.items()):
    if swift_name in objc_declared:
        continue
    word = re.compile(r'\b%s\b' % re.escape(swift_name))
    for pattern in ('*.m', '*.mm', '*.h'):
        for source in sorted(sources.glob(pattern)):
            text = source.read_text(encoding='utf-8', errors='replace')
            # Neither a comment nor a literal reaches the compiler as a name.
            stripped = string.sub('@""', comment.sub(' ', text))
            if word.search(stripped):
                line = next((n for n, l in enumerate(stripped.splitlines(), 1)
                             if word.search(l)), 0)
                failures.append(
                    '%s:%d writes the Swift name %s; Objective-C sees %s (from %s)'
                    % (source.relative_to(root), line, swift_name, objc_name, declared_in))

if failures:
    for item in sorted(set(failures)):
        print('FAIL:', item, file=sys.stderr)
    sys.exit(1)
print('PASS: %d renamed Swift declaration(s) are not written by their Swift name in Objective-C'
      % len(exposed))
