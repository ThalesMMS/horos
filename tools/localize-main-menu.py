#!/usr/bin/env python3
"""Generate localized UI text from the current English XIB, preserving connections."""
import argparse
import html
import json
from pathlib import Path
import re
import subprocess
from xml.sax.saxutils import escape
root=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser();parser.add_argument('--check',action='store_true');parser.add_argument('--language',choices=['it-IT','es'],default='it-IT');args=parser.parse_args()
base=root/'Horos/Resources/en.lproj/MainMenu.xib'
target=root/f'Horos/Resources/{args.language}.lproj/MainMenu.xib'
catalog=json.loads(subprocess.check_output(['plutil','-convert','json','-o','-',str(target.with_name('Localizable.strings'))]))
text=base.read_text()
def translate(match):
    value=html.unescape(match[2])
    translated=catalog.get(value,value)
    return match[1]+'"'+escape(translated,{'"':'&quot;', '\n':'&#10;', '\r':'&#13;', '\t':'&#9;'})+'"'
text=re.sub(r'(\b(?:title|label|toolTip|placeholderString|alternateTitle|stringValue)=)"([^"]*)"',translate,text)
if args.check:
    if not target.exists() or target.read_text()!=text:
        raise SystemExit(f'{args.language} MainMenu.xib is stale; run tools/localize-main-menu.py --language {args.language}')
else:
    target.write_text(text)
