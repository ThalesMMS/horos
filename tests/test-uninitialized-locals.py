#!/usr/bin/env python3
"""The locals that clang reported as used-uninitialised stay initialised.

Four sweeps of the build warnings turned up locals read before assignment, each
in a place where the wrong value is not obviously wrong to look at: an
ultrasound unit string (#523), a selected-row index (#525), a NIfTI orientation
code and a plugin's menu item (#527). The first two have their own behavioural
checks; this one guards the declarations themselves, so the warnings cannot
quietly come back.

Reading declarations is weaker than compiling the code, and is meant to be:
these are one-line invariants in files far too entangled to extract.
"""
from pathlib import Path
import re
import sys

root = Path(__file__).resolve().parents[1]
failures = []


def source(name):
    return (root / name).read_bytes().decode('latin1')


# --- NIfTI orientation: no qform and no sform must not read the stack --------
pix = source('Horos/Sources/DCMPix.m')
orientation = re.search(r'int\s+icod\s*(=[^;]*)?,\s*jcod\s*(=[^;]*)?,\s*kcod\s*(=[^;]*)?;', pix)
if not orientation:
    failures.append('the NIfTI orientation codes are gone from DCMPix.m')
elif not all(orientation.group(i) for i in (1, 2, 3)):
    failures.append('icod/jcod/kcod are declared without values; a NIfTI with neither '
                    'qform nor sform then decides its orientation from the stack')
else:
    # 1..6 are the real codes, so the unset value must not collide with one.
    for group in (1, 2, 3):
        value = orientation.group(group).lstrip('= ').strip()
        if value != '0':
            failures.append('an orientation code starts at %s; it has to be outside the '
                            '1..6 the library returns, so no comparison matches' % value)

# --- a plugin menu item that already exists ---------------------------------
plugins = source('Horos/Sources/PluginManager.m')
item = re.search(r'id\s+subMenuItem\s*(=\s*([^;]+))?;', plugins)
if not item:
    failures.append('subMenuItem is gone from PluginManager.m')
elif not item.group(1):
    failures.append('subMenuItem is declared without a value; a plugin whose menu item '
                    'already exists then gets setRepresentedObject: through a wild pointer')
elif item.group(2).strip() != 'nil':
    failures.append('subMenuItem starts at %s, not nil' % item.group(2).strip())

if failures:
    for entry in failures:
        print('FAIL:', entry, file=sys.stderr)
    sys.exit(1)
print('PASS: the reported locals are initialised where they are declared')
