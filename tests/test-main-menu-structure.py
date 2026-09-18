#!/usr/bin/env python3
"""Every language's main menu is the English one, with its text translated (#640).

`ja-JP.lproj/MainMenu.xib` had been translated by hand and stopped following the English
menu: no Format menu at all, 436 items against 438 - `Show Primary Measurement Only` and
`Restore Views` were missing - so a user in Japanese could not reach those actions.

Each localized menu is generated from the English one by `tools/localize-main-menu.py`,
which replaces only the text. Checked here, for Italian, Spanish and Japanese:

* the tree is the English tree once the visible text is left out: same elements, same
  attributes, same order;
* every identifier, action, target and key equivalent of the English menu is there, as
  often as in English;
* the file is exactly what the generator writes today, so a hand edit cannot drift again.

A title with no catalog entry stays English: that is a fallback, not a missing item.
"""
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET
from collections import Counter

root = Path(__file__).resolve().parents[1]
LANGUAGES = ('it-IT', 'es', 'ja-JP')
VISIBLE = {'title', 'label', 'toolTip', 'placeholderString', 'alternateTitle', 'stringValue'}
failures = []


def tree(language):
    return ET.parse(root / f'Horos/Resources/{language}.lproj/MainMenu.xib').getroot()


def structural(node):
    return (node.tag, sorted((k, v) for k, v in node.attrib.items() if k not in VISIBLE),
            (node.text or '').strip(), [structural(child) for child in node])


def wiring(node):
    """What a menu item does, by identifier, action, target and key equivalent."""
    counts = Counter()
    for element in node.iter():
        for attribute in ('identifier', 'keyEquivalent', 'keyEquivalentModifierMask'):
            if element.get(attribute):
                counts[(element.tag, attribute, element.get(attribute))] += 1
        if element.tag == 'action':
            counts[('action', element.get('selector', ''), element.get('target', ''))] += 1
    return counts


english = tree('en')
english_structure, english_wiring = structural(english), wiring(english)
english_items = len(list(english.iter('menuItem')))

for language in LANGUAGES:
    localized = tree(language)
    items = len(list(localized.iter('menuItem')))
    if items != english_items:
        failures.append(f'{language}: {items} menu items, English has {english_items}')
    if structural(localized) != english_structure:
        failures.append(f'{language}: the menu is not the English menu with its text translated')
    missing = english_wiring - wiring(localized)
    if missing:
        failures.append(f'{language}: {sum(missing.values())} identifiers, actions or shortcuts of the English menu '
                        f'are missing, among them {list(missing)[:3]}')
    check = subprocess.run([sys.executable, str(root / 'tools/localize-main-menu.py'), '--check', '--language', language],
                           capture_output=True, text=True)
    if check.returncode != 0:
        failures.append(f'{language}: ' + (check.stdout + check.stderr).strip())

if failures:
    print('\n'.join('FAIL: ' + failure for failure in failures))
    raise SystemExit(1)
print(f'main menu: {", ".join(LANGUAGES)} carry the English structure, wiring and {english_items} items')
