#!/usr/bin/env python3
"""The API alias frameworks carry a seal over what they actually contain.

Horos/Scripts/Horos/API.sh clones Horos.framework four times, because plugins are
hard-linked against the API framework under names it had over the years. Each
clone gets its binary renamed, its headers dropped and its identifier rewritten -
all of it underneath the signature that cp -R brought along. A bundle whose seal
covers content that is no longer there fails codesign --verify --deep --strict,
and an application containing one cannot be notarised.

This runs the real script against a synthetic signed framework laid out like the
built one, and then verifies each alias the way a notarisation check would.
"""
from pathlib import Path
import plistlib
import os
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
script = root / 'Horos/Scripts/Horos/API.sh'
ALIASES = ['HorosAPI', 'OsiriXAPI', 'OsiriX Headers', 'HorosDCM']
# The one alias whose identifier is not simply thalesmms.isis.workstation.<name>.
IDENTIFIERS = dict({a: 'thalesmms.isis.workstation.' + a for a in ALIASES},
                   **{'OsiriX Headers': 'thalesmms.isis.workstation.OsiriXHeaders'})
failures = []


def build_framework(frameworks):
    """A minimal versioned framework, signed, laid out like the built one."""
    framework = frameworks / 'Horos.framework'
    versions = framework / 'Versions/A'
    (versions / 'Resources').mkdir(parents=True)
    (versions / 'Headers').mkdir()
    (versions / 'Headers/Horos.h').write_text('// header\n')
    source = frameworks / 'horos.c'
    source.write_text('int HorosAPIVersion(void){return 1;}\n')
    subprocess.run(['xcrun', 'clang', '-dynamiclib', '-o', str(versions / 'Horos'),
                    '-install_name', '@rpath/Horos.framework/Versions/A/Horos', str(source)],
                   check=True, capture_output=True)
    source.unlink()
    with open(versions / 'Resources/Info.plist', 'wb') as out:
        plistlib.dump({'CFBundleIdentifier': 'thalesmms.isis.workstation.api',
                       'CFBundleExecutable': 'Horos',
                       'CFBundleName': 'Horos',
                       'CFBundlePackageType': 'FMWK',
                       'CFBundleInfoDictionaryVersion': '6.0',
                       'CFBundleVersion': '1'}, out)
    (framework / 'Versions/Current').symlink_to('A')
    for link in ('Horos', 'Resources', 'Headers'):
        (framework / link).symlink_to('Versions/Current/' + link)
    # Signed, as Xcode signs it before the application target copies it in. This
    # is the seal the aliases used to inherit.
    subprocess.run(['/usr/bin/codesign', '--force', '--sign', '-', '--options', 'runtime',
                    str(framework)], check=True, capture_output=True)
    return framework


def run(script_path, directory, channel="github"):
    frameworks = Path(directory) / 'Isis DICOM Viewer.app/Contents/Frameworks'
    frameworks.mkdir(parents=True)
    build_framework(frameworks)
    derived = Path(directory) / 'DerivedSources'
    derived.mkdir()
    (derived / 'Horos-Swift.h').write_text('// generated interface stand-in\n')
    environment = {'TARGET_BUILD_DIR': directory, 'DERIVED_FILE_DIR': str(derived),
                   'FRAMEWORKS_FOLDER_PATH': 'Isis DICOM Viewer.app/Contents/Frameworks',
                   'EXPANDED_CODE_SIGN_IDENTITY': '-', 'ISIS_BUILD_CHANNEL': channel,
                   'PATH': '/usr/bin:/bin:/usr/sbin:/sbin'}
    completed = subprocess.run(['/bin/sh', str(script_path)], env=environment,
                               capture_output=True, text=True)
    return frameworks, completed


def verify(frameworks):
    """What survives a notarisation-grade check, per alias."""
    bad = []
    for alias in ALIASES:
        framework = frameworks / (alias + '.framework')
        if not framework.is_dir():
            bad.append('%s was not produced' % alias)
            continue
        checked = subprocess.run(['/usr/bin/codesign', '--verify', '--strict', str(framework)],
                                 capture_output=True, text=True)
        if checked.returncode != 0:
            bad.append('%s: %s' % (alias, (checked.stderr or checked.stdout).strip().splitlines()[0]))
    return bad


with tempfile.TemporaryDirectory(prefix='horos-api-seal-') as directory:
    frameworks, completed = run(script, directory)
    if completed.returncode != 0:
        failures.append('API.sh failed: %s' % (completed.stderr or completed.stdout).strip()[-400:])
    failures += verify(frameworks)

    for alias in ALIASES:
        framework = frameworks / (alias + '.framework')
        if not framework.is_dir():
            continue
        # The alias is the whole point of the copy: the binary is renamed, the
        # headers are gone, and the symlink points at the new name.
        if not (framework / ('Versions/A/' + alias)).is_file():
            failures.append('%s has no binary under its own name' % alias)
        if (framework / 'Versions/A/Horos').exists():
            failures.append('%s kept the original binary' % alias)
        if (framework / 'Versions/A/Headers').exists() or (framework / 'Headers').exists():
            failures.append('%s kept the headers' % alias)
        link = framework / alias
        if not link.is_symlink() or os.readlink(link) != 'Versions/Current/' + alias:
            failures.append('%s does not link to its binary' % alias)
        # And the seal records the identifier the edits left behind, not the one
        # it was copied from.
        with open(framework / 'Versions/A/Resources/Info.plist', 'rb') as stream:
            identifier = plistlib.load(stream)['CFBundleIdentifier']
        if identifier != IDENTIFIERS[alias]:
            failures.append('%s declares %s, expected %s' % (alias, identifier, IDENTIFIERS[alias]))
        shown = subprocess.run(['/usr/bin/codesign', '-dv', str(framework)],
                               capture_output=True, text=True)
        sealed = [line[len('Identifier='):] for line in shown.stderr.splitlines()
                  if line.startswith('Identifier=')]
        if sealed != [identifier]:
            failures.append('%s is sealed as %s but declares %s' % (alias, sealed, identifier))

with tempfile.TemporaryDirectory(prefix='isis-store-api-') as directory:
    frameworks, completed = run(script, directory, 'appstore')
    if completed.returncode:
        failures.append('API.sh failed for the store channel: ' + completed.stderr[-400:])
    if any((frameworks / (alias + '.framework')).exists() for alias in ALIASES):
        failures.append('The store channel included external plugin compatibility frameworks')
    checked = subprocess.run(['codesign', '--verify', '--strict',
                              str(frameworks / 'Horos.framework')], capture_output=True)
    if checked.returncode:
        failures.append('The store API framework signature is invalid')

# Signing has to be skipped, not failed, when the build is not signing at all -
# script/build_and_run.sh builds that way and signs the copy itself afterwards.
with tempfile.TemporaryDirectory(prefix='horos-api-seal-unsigned-') as directory:
    frameworks = Path(directory) / 'Isis DICOM Viewer.app/Contents/Frameworks'
    frameworks.mkdir(parents=True)
    build_framework(frameworks)
    derived = Path(directory) / 'DerivedSources'
    derived.mkdir()
    (derived / 'Horos-Swift.h').write_text('// generated interface stand-in\n')
    completed = subprocess.run(
        ['/bin/sh', str(script)],
        env={'TARGET_BUILD_DIR': directory, 'DERIVED_FILE_DIR': str(derived),
             'FRAMEWORKS_FOLDER_PATH': 'Isis DICOM Viewer.app/Contents/Frameworks',
             'CODE_SIGNING_ALLOWED': 'NO', 'PATH': '/usr/bin:/bin:/usr/sbin:/sbin'},
        capture_output=True, text=True)
    if completed.returncode != 0:
        failures.append('API.sh failed with signing disabled: %s'
                        % (completed.stderr or completed.stdout).strip()[-400:])
    # Classes implemented in Swift keep <Horos/Name.h> through the generated header (#708).
    if not (frameworks / 'Horos.framework/Versions/A/Headers/Horos-Swift.h').is_file():
        failures.append('API.sh did not publish Horos-Swift.h in Horos.framework')
    for alias in ALIASES:
        if (frameworks / (alias + '.framework/Versions/A/_CodeSignature')).exists():
            failures.append('%s carries an inherited seal when signing is disabled' % alias)

# A missing build directory must stop the script rather than let it improvise a
# path and carry on to sign whatever it finds there.
completed = subprocess.run(['/bin/sh', str(script)],
                           env={'PATH': '/usr/bin:/bin:/usr/sbin:/sbin'},
                           capture_output=True, text=True)
if completed.returncode == 0:
    failures.append('API.sh succeeded with no TARGET_BUILD_DIR')

# The same run against the script as it was before the fix has to fail, or this
# test proves nothing. Take it from history rather than from HEAD.
# The public revision before the fork's signing changes supplies the
# unsealed aliases used as the negative control.
previous = subprocess.run(['git', '-C', str(root), 'show',
                           '2a130506f2ae651fcd52becbd5469c107bbbf795:Horos/Scripts/Horos/API.sh'],
                          capture_output=True, text=True)
if previous.returncode != 0:
    # A shallow clone may omit the public reference revision, so the before/after half cannot
    # run. Skip rather than fail: nothing was measured either way.
    for failure in failures:
        print('FAIL: %s' % failure)
    if failures:
        sys.exit(1)
    print('skipped: needs the public reference revision for the before/after half; '
          'a shallow clone does not carry it', file=sys.stderr)
    sys.exit(2)
else:
    with tempfile.TemporaryDirectory(prefix='horos-api-seal-before-') as directory:
        before = Path(directory) / 'API-before.sh'
        before.write_text(previous.stdout)
        frameworks, _ = run(before, directory)
        if not verify(frameworks):
            failures.append('the previous API.sh already produced verifiable aliases; '
                            'this test does not exercise the defect')
        else:
            print('previous API.sh, as expected: ' + '; '.join(verify(frameworks)))

for failure in failures:
    print('FAIL: %s' % failure)
if failures:
    sys.exit(1)
print('ok: %d API alias frameworks pass codesign --verify --strict, each sealed under its own '
      'identifier, with the binary renamed and the headers dropped' % len(ALIASES))
