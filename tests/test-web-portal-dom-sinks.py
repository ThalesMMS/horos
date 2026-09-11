#!/usr/bin/env python3
"""The web portal's own scripts do not write untrusted text as markup.

ZSL-2016-5385 is a DOM-based XSS in the Horos 2.1.0 web portal. Its body names
the sink exactly:

    document.getElementById('fileName').innerHTML = 'Name: ' + file.name; // xss

A file whose name is `<img src=x onerror=...>` - which macOS allows - runs script
in the portal's origin when the user picks it for upload. The same three lines
were still in Horos/Resources/WebServicesHTML/English/main.html, unchanged.

They now write `textContent`. The overlay in study.html, which concatenated two
identifiers into an anchor and an image, builds elements instead.
"""
from pathlib import Path
import re
import sys

root = Path(__file__).resolve().parents[1]
failures = []
portal = root / 'Horos/Resources/WebServicesHTML'

# --- the sink the advisory names ---------------------------------------------
main = (portal / 'English/main.html').read_text()
for element in ('fileName', 'fileSize', 'fileType'):
    if re.search(r"getElementById\('%s'\)\.innerHTML" % element, main):
        failures.append("the upload page still writes %s as markup" % element)
    if not re.search(r"getElementById\('%s'\)\.textContent" % element, main):
        failures.append("the upload page no longer shows %s at all" % element)
if 'file.name' not in main:
    failures.append('the upload page no longer shows the chosen file name, which is not the fix')

# --- and nothing else in the portal's own scripts writes markup ---------------
for page in sorted(portal.rglob('*.html')):
    text = page.read_text(errors='replace')
    for number, line in enumerate(text.splitlines(), 1):
        if '.innerHTML' not in line:
            continue
        # A comment explaining why is not a sink.
        stripped = line.strip()
        if stripped.startswith('//') or stripped.startswith('*') or stripped.startswith('<!--'):
            continue
        failures.append('%s:%d writes markup: %s'
                        % (page.relative_to(root), number, stripped[:90]))

# --- the overlay builds elements, and encodes what goes in a query string -----
study = (portal / 'English/study.html').read_text()
at = study.find('function imageClick')
if at < 0:
    failures.append('imageClick is gone')
else:
    body = study[at:at + 1400]
    if 'createElement' not in body:
        failures.append('imageClick no longer builds the overlay as elements')
    if body.count('encodeURIComponent') != 2:
        failures.append('imageClick does not encode both identifiers for the query strings')
    if 'textContent' not in body:
        failures.append('the Close label is not set as text')

for failure in failures:
    print('FAIL: %s' % failure)
if failures:
    sys.exit(1)
print('ok: the portal pages write the chosen file name and the overlay as text and elements, '
      'never as markup')
