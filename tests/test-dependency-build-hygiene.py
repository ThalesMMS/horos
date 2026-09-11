#!/usr/bin/env python3
"""The dependency builds fail loudly, and the frameworks are what they claim.

Two things a build system must not do: reuse a Makefile from a configure step
that failed, and link a framework built for another architecture without saying
so. This checks the first in source and reports the second from the binaries
themselves.

The Debug and Release builds that go with this are recorded in
docs/dependency-build-validation.md.
"""
from pathlib import Path
import re
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
failures = []
scripts = root / 'Horos/Scripts'

# --- every dependency script stops at the first failure ----------------------
for script in sorted(set(scripts.glob('*/CMake.sh')) | set(scripts.glob('*/Make.sh')) |
                     set(scripts.glob('*/Config.sh'))):
    text = script.read_text(errors='replace')
    if not re.search(r'^\s*set -e', text, re.M):
        failures.append('%s does not stop at the first failure' % script.relative_to(root))

# --- and a configure that failed leaves no stamp to skip it next time --------
for script in sorted(scripts.glob('*/CMake.sh')):
    text = script.read_text(errors='replace')
    # Two spellings of the same idea live in this tree.
    stamp_name = next((n for n in ('.cmakehash', '.buildhash') if n in text), None)
    if stamp_name is None:
        failures.append('%s has no stamp, so it reconfigures every build or never'
                        % script.relative_to(root))
        continue
    # The stamp must be written after cmake runs, or a failed configure would be
    # remembered as a good one.
    configure = text.rfind('\ncmake "${args[@]}"')
    if configure < 0:
        configure = text.rfind('cmake ')
    stamp = text.rfind(stamp_name)
    read = text.find(stamp_name)
    if configure < 0 or stamp < configure:
        failures.append('%s writes its stamp before cmake runs' % script.relative_to(root))
    if read > configure:
        failures.append('%s does not check its stamp before configuring' % script.relative_to(root))

# OpenSSL has no CMake step; it marks its install directory instead.
openssl = (scripts / 'OpenSSL/Make.sh').read_text(errors='replace')
if '.incomplete' not in openssl:
    failures.append('the OpenSSL build has no marker, so an interrupted one looks finished')
else:
    touched = openssl.find('touch "$install_dir/.incomplete"')
    removed = openssl.find('rm -f "$install_dir/.incomplete"')
    if touched < 0 or removed < 0 or removed < touched:
        failures.append('the OpenSSL marker is not created before the build and removed after it')

# --- no private signing identity is baked into the project -------------------
project = (root / 'Horos.xcodeproj/project.pbxproj').read_text(errors='replace')
teams = set(re.findall(r'DEVELOPMENT_TEAM = ([^;]+);', project))
for team in teams:
    if '$(' not in team and team.strip('" ') not in ('', '-'):
        failures.append('a development team is baked into the project: %s' % team)
identities = set(re.findall(r'CODE_SIGN_IDENTITY[^=]*= ([^;]+);', project))
for identity in identities:
    value = identity.strip('" ')
    if value not in ('', '-', 'Apple Development', 'Mac Developer') and '$(' not in identity:
        failures.append('a signing identity is baked into the project: %s' % identity)

# --- the frameworks that ship with the application ---------------------------
report = []
for framework in sorted((root / 'Binaries').glob('*.framework')):
    name = framework.name[:-len('.framework')]
    binary = framework / name
    if not binary.is_file():
        binary = framework / 'Versions/A' / name
    if not binary.is_file():
        continue
    archs = subprocess.run(['lipo', '-archs', str(binary)], capture_output=True, text=True)
    report.append((framework.name, archs.stdout.strip()))

if not report:
    # Binaries/ carries no framework in a fresh checkout, so there is nothing to
    # read the architecture of. Skip; the source half above already ran.
    for failure in failures:
        print('FAIL: %s' % failure)
    if failures:
        sys.exit(1)
    print('skipped: no prebuilt framework in Binaries/ to inspect', file=sys.stderr)
    sys.exit(2)
else:
    for name, archs in report:
        print('  %-34s %s' % (name, archs))
    # This is what the audit found; if it changes, the document needs redoing.
    expected = {'3DconnexionClient.framework': 'x86_64 i386', 'homephone.framework': 'x86_64'}
    for name, archs in report:
        if name in expected and archs != expected[name]:
            failures.append('%s is now %s, not %s; docs/dependency-build-validation.md needs '
                            'redoing' % (name, archs, expected[name]))

for failure in failures:
    print('FAIL: %s' % failure)
if failures:
    sys.exit(1)
print('ok: every dependency script stops at the first failure and cannot remember a configure '
      'that did not finish, no signing identity is baked in, and the prebuilt frameworks are '
      'listed with the architectures they hold')
