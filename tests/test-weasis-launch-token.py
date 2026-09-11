#!/usr/bin/env python3
"""The Weasis launch link must not carry the session, only a one-shot token."""
from pathlib import Path
import re, sys

root = Path(__file__).resolve().parents[1]
pages = sorted((root / 'Horos/Resources/WebServicesHTML').rglob('*.html'))
assert pages, 'no portal pages found'
failures = []
launches = 0
for page in pages:
    text = page.read_bytes().decode('latin1')
    for link in re.findall(r'href="[^"]*weasis\.jnlp\?[^"]*"', text):
        launches += 1
        where = f'{page.relative_to(root)}: {link}'
        if 'Info.SID' in link:
            failures.append(f'the session id is back in a launch link — {where}')
        if 'Info.newToken' not in link:
            failures.append(f'the launch link carries no one-shot token — {where}')
        if 'User.name' not in link:
            failures.append(f'the launch link names no user, so the token cannot be checked — {where}')
        if 'IF:User' not in link:
            failures.append(f'the launch link is not guarded for an anonymous portal — {where}')
assert launches, 'no Weasis launch link found in the portal pages'
# The template that Java Web Start itself fetches already worked this way.
jnlp = (root / 'Horos/Resources/WebServicesHTML/weasis.jnlp').read_bytes().decode('latin1')
if 'Info.newToken' not in jnlp:
    failures.append('weasis.jnlp no longer asks for a one-shot token for its own call')
if 'Info.SID' in jnlp:
    failures.append('weasis.jnlp now carries the session id')
# A token has to be consumed when it is used, or it is not one-shot.
session = (root / 'Horos/Sources/WebPortal.mm').read_bytes().decode('latin1')
if 'doConsume: YES' not in session:
    failures.append('a launch token is no longer consumed when it is used')
for failure in failures:
    print('FAIL: %s' % failure)
if failures:
    sys.exit(1)
print(f'PASS: {launches} Weasis launch link(s) carry a one-shot token and no session id')
