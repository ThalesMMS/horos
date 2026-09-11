#!/usr/bin/env python3
"""Every string drawn into a viewer texture asks for antialiasing.

StringTexture rasterizes with antialiasing off unless a caller turns it on. A
caller that forgets produces hard-edged glyphs beside the smooth ones drawn by
callers that remember, which is what "pixelated annotations" looks like.
"""
import re, subprocess, sys, tempfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sources = sorted(list((root / 'Horos/Sources').rglob('*.m')) + list((root / 'Horos/Sources').rglob('*.mm')))
creations, missing = 0, []
for source in sources:
    text = source.read_bytes().decode('latin1')
    for m in re.finditer(r'\[\[StringTexture alloc\]', text):
        creations += 1
        # The flag has to be set before the texture is generated from it.
        window = text[m.start():]
        generated = window.find('genTexture')
        if generated < 0:
            generated = 700
        if 'setAntiAliasing' not in window[:generated]:
            missing.append('%s:%d' % (source.relative_to(root), text[:m.start()].count('\n') + 1))

if creations < 10:
    print('FAIL: expected the viewer texture call sites, found %d' % creations)
    sys.exit(1)
if missing:
    print('FAIL: StringTexture built without antialiasing at:')
    for m in missing:
        print(' ', m)
    sys.exit(1)

# The default really is off, so the call sites above are load-bearing.
default_off = re.search(r'antialiasing\s*=\s*NO\s*;',
                        (root / 'Horos/Sources/StringTexture.m').read_bytes().decode('latin1'))
if not default_off:
    print('FAIL: StringTexture no longer defaults antialiasing off; this test needs revisiting')
    sys.exit(1)

# And it is what actually reaches the rasterizer.
applied = re.search(r'setShouldAntialias:\s*antialiasing',
                    (root / 'Horos/Sources/StringTexture.m').read_bytes().decode('latin1'))
if not applied:
    print('FAIL: StringTexture no longer applies its antialiasing flag when drawing')
    sys.exit(1)

print('PASS: all %d StringTexture call sites request antialiasing before generating, '
      'and the flag still defaults off and still reaches the rasterizer' % creations)
