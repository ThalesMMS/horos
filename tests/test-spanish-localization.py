#!/usr/bin/env python3
"""Validate Spanish formats, current nib structure, and optional built resources."""
from collections import Counter
import json
from pathlib import Path
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
root=Path(__file__).resolve().parents[1]
def strings(path):
    return json.loads(subprocess.check_output(['plutil','-convert','json','-o','-',str(path)]))
en=strings(root/'Horos/Resources/en.lproj/Localizable.strings')
it=strings(root/'Horos/Resources/es.lproj/Localizable.strings')
assert en.keys()<=it.keys(), 'Catalog keys must contain the current English catalog'
fmt=re.compile(r'%(?:\d+\$)?[-+#0 ]*(?:\d+|\*)?(?:\.(?:\d+|\*))?(?:hh|ll|[hljztLq])?[@diuoxXfFeEgGaAcCsSpn%]')
for key in it:
    original=en.get(key,key)
    assert Counter(fmt.findall(original))==Counter(fmt.findall(it[key])),repr(key)
    assert it[key] or not original, f'Unexpected empty translation: {key}'
# Legacy rendering paths explicitly require ASCII in these catalog comments.
source=(root/'Horos/Resources/en.lproj/Localizable.strings').read_text(encoding='utf-16')
for comment, literal in re.findall(r'/\*(.*?)\*/\s*("(?:\\.|[^"\\])*")\s*=',source,re.S):
    if 'ASCII' in comment:
        key=json.loads(literal)
        assert it[key].isascii(), f'Non-ASCII translation in constrained rendering string: {key}'
subprocess.run([sys.executable,str(root/'tools/localize-main-menu.py'),'--check','--language','es'],check=True)
visible={'title','label','toolTip','placeholderString','alternateTitle','stringValue'}
def structural(node):
    return (node.tag, sorted((k,v) for k,v in node.attrib.items() if k not in visible),
            (node.text or '').strip(), [structural(child) for child in node])
en_tree=ET.parse(root/'Horos/Resources/en.lproj/MainMenu.xib').getroot()
it_tree=ET.parse(root/'Horos/Resources/es.lproj/MainMenu.xib').getroot()
assert structural(en_tree)==structural(it_tree), 'Localization changed nib structure/connections'
assert it_tree.find('.//menuItem[@identifier="org.horos.menu.viewer"]').get('title')=='Visor 2D'
if len(sys.argv)>1:
    resources=Path(sys.argv[1])/'Contents/Resources'
    assert (resources/'es.lproj/MainMenu.nib').exists()
    assert strings(resources/'es.lproj/Localizable.strings')==it
print(f'PASS: {len(it)} catalog keys, format arguments, regenerated menu, unchanged non-text nib structure'+('; built Spanish resources' if len(sys.argv)>1 else ''))
