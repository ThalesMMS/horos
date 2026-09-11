#!/usr/bin/env python3
"""The dependency hash moves for what a dependency compiles from, and nothing else.

The helper is driven directly, one variable at a time, so each answer is about a
single change rather than about a whole build.
"""
from pathlib import Path
import os
import re
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
scripts = root / 'Horos/Scripts'
helper = scripts / 'dependency-hash.sh'

failures = []


def report(ok, message):
    if not ok:
        failures.append(message)


# What Xcode hands a dependency script on this project.
BASELINE = {
    'ARCHS': 'arm64',
    'CLANG_CXX_LANGUAGE_STANDARD': 'c++14',
    'CLANG_CXX_LIBRARY': 'libc++',
    'CONFIGURATION': 'Debug',
    'MACOSX_DEPLOYMENT_TARGET': '11.0',
    'NATIVE_ARCH_ACTUAL': 'arm64',
    'OTHER_CFLAGS': '',
    'OTHER_CPLUSPLUSFLAGS': '',
    'OTHER_LDFLAGS': '',
    'PROJECT_DIR': str(root),
    'SDK_NAME': 'macosx26.5',
    'TARGET_NAME': 'VTK',
    # Present in a real build, and none of it reaches a static library.
    'PRODUCT_NAME': 'VTK',
    'DEVELOPMENT_TEAM': 'ABCDE12345',
    'CODE_SIGN_IDENTITY': 'Apple Development',
    'CODE_SIGNING_ALLOWED': 'YES',
    'CODE_SIGN_STYLE': 'Automatic',
    'PRODUCT_BUNDLE_IDENTIFIER': 'org.horosproject.horos',
    'LLBUILD_BUILD_ID': '1',
    'LLBUILD_TASK_ID': '7',
    'TARGET_TEMP_DIR': '/tmp/whatever',
    'ONLY_ACTIVE_ARCH': 'YES',
    'HOROS_DEV_TEST_ROOT': '/tmp/private',
    'TERM': 'xterm-256color',
    # Xcode always hands a build phase the system directories; a shell that has
    # trimmed /sbin out would otherwise take md5 with it.
    'PATH': os.pathsep.join([os.environ['PATH'], '/usr/bin', '/bin', '/usr/sbin', '/sbin']),
    'HOME': os.environ['HOME'],
}


def digest(files, cwd=None, **overrides):
    """Run the helper the way a dependency script does and return its hash."""
    environment = dict(BASELINE)
    for name, value in overrides.items():
        if value is None:
            environment.pop(name, None)
        else:
            environment[name] = value
    arguments = ' '.join('"%s"' % path for path in files)
    script = '. "%s"\ndependency_hash %s\nprintf %%s "$hash"\n' % (helper, arguments)
    result = subprocess.run(['/bin/sh', '-c', script], env=environment,
                            cwd=cwd or str(root), capture_output=True, text=True)
    if result.returncode != 0:
        raise SystemExit('helper failed: %s' % result.stderr)
    return result.stdout


base = digest([helper])
report(len(base) > 0, 'the helper produced no hash')

# Without md5 every digest is the empty string and the hash is the same constant
# for every environment, so .cmakehash always matches and nothing is ever
# reconfigured. That has to be an error, not a hash.
empty = subprocess.run(['/bin/sh', '-c', '. "%s"\ndependency_hash "%s"\nprintf %%s "$hash"\n'
                        % (helper, helper)],
                       env=dict(BASELINE, PATH='/nowhere'), cwd=str(root),
                       capture_output=True, text=True)
report(empty.returncode != 0 and not empty.stdout,
       'the helper hashed nothing at all when md5 was unavailable')
report('md5' in empty.stderr, 'the helper did not say which tool it was missing')

# Repeating a build with nothing changed must not reconfigure anything.
report(digest([helper]) == base, 'the same environment produced a different hash')

# Signing, naming and local run variables are not compilation inputs.
for name, value in [('DEVELOPMENT_TEAM', 'ZZZZZ99999'),
                    ('CODE_SIGN_IDENTITY', '-'),
                    ('CODE_SIGNING_ALLOWED', 'NO'),
                    ('CODE_SIGN_STYLE', 'Manual'),
                    ('PRODUCT_NAME', 'Renamed'),
                    ('PRODUCT_BUNDLE_IDENTIFIER', 'org.horosproject.horos.local-development'),
                    ('LLBUILD_BUILD_ID', '2'),
                    ('LLBUILD_TASK_ID', '9'),
                    ('TARGET_TEMP_DIR', '/tmp/elsewhere'),
                    ('ONLY_ACTIVE_ARCH', 'NO'),
                    ('HOROS_DEV_TEST_ROOT', '/tmp/other'),
                    ('TERM', 'dumb'),
                    ('DISPLAY', ':0'),
                    ('SSH_AUTH_SOCK', '/tmp/ssh')]:
    report(digest([helper], **{name: value}) == base,
           'changing %s rebuilt the dependency' % name)

# The variables that do reach the configure step.
for name, value in [('ARCHS', 'x86_64'),
                    ('ARCHS', 'arm64 x86_64'),
                    ('MACOSX_DEPLOYMENT_TARGET', '12.0'),
                    ('CONFIGURATION', 'Release'),
                    ('SDK_NAME', 'macosx27.0'),
                    ('CLANG_CXX_LIBRARY', 'libstdc++'),
                    ('CLANG_CXX_LANGUAGE_STANDARD', 'c++17'),
                    ('OTHER_CFLAGS', '-DNDEBUG'),
                    ('OTHER_CPLUSPLUSFLAGS', '-fno-exceptions'),
                    ('OTHER_LDFLAGS', '-lz'),
                    ('NATIVE_ARCH_ACTUAL', 'x86_64'),
                    ('PROJECT_DIR', '/somewhere/else'),
                    ('TARGET_NAME', 'ITK')]:
    report(digest([helper], **{name: value}) != base,
           'changing %s did not rebuild the dependency' % name)

# An unset variable is not the same as an empty one only when it matters; what
# matters is that dropping a real input still moves the hash.
report(digest([helper], ARCHS=None) != base, 'dropping ARCHS did not rebuild')

with tempfile.TemporaryDirectory() as directory:
    temporary = Path(directory)

    # A different compiler is a different build.
    fake = temporary / 'bin'
    fake.mkdir()
    (fake / 'clang').write_text('#!/bin/sh\necho "Apple clang version 99.0.0 (clang-9900)"\n')
    (fake / 'clang').chmod(0o755)
    (fake / 'xcrun').write_text('#!/bin/sh\n[ "$1" = --find ] && echo "%s/clang"\n' % fake)
    (fake / 'xcrun').chmod(0o755)
    report(digest([helper], PATH='%s:%s' % (fake, BASELINE['PATH'])) != base,
           'a different toolchain did not rebuild the dependency')

    # The script and its patches are part of the recipe.
    edited = temporary / 'edited.sh'
    edited.write_text(helper.read_text() + '\n# changed\n')
    report(digest([edited]) != base, 'editing the script did not rebuild')

    patch = temporary / 'a.patch'
    patch.write_text('original\n')
    with_patch = digest([helper, patch])
    report(with_patch != base, 'adding a patch did not change the hash')
    patch.write_text('edited\n')
    report(digest([helper, patch]) != with_patch, 'editing a patch did not rebuild')

    # The working tree state is not a compilation input: the old hash folded in
    # `git describe --dirty`, so a single edited source file rebuilt everything.
    repository = temporary / 'repo'
    repository.mkdir()
    for command in (['init', '-q'], ['config', 'user.email', 't@e'],
                    ['config', 'user.name', 't']):
        subprocess.run(['git'] + command, cwd=repository, check=True,
                       capture_output=True)
    (repository / 'file').write_text('clean\n')
    subprocess.run(['git', 'add', 'file'], cwd=repository, check=True, capture_output=True)
    subprocess.run(['git', 'commit', '-qm', 'first'], cwd=repository, check=True,
                   capture_output=True)
    clean = digest([helper], cwd=repository)
    (repository / 'file').write_text('dirty\n')
    report(digest([helper], cwd=repository) == clean,
           'a dirty working tree rebuilt the dependency')
    report(clean == base, 'the hash depended on the working directory')

instructions = '\n'.join(line for line in helper.read_text().splitlines()
                          if not line.lstrip().startswith('#'))
report('git' not in instructions, 'the helper still consults git')

# Every dependency goes through the one helper, with its own recipe files.
call = re.compile(r'^\. "\$\(dirname "\$path"\)/\.\./dependency-hash\.sh"\n'
                  r'dependency_hash (.*)$', re.M)
recipes = sorted(list(scripts.glob('*/CMake.sh')) + list(scripts.glob('*/Config.sh')))
report(len(recipes) == 8, 'expected eight dependency scripts, found %d' % len(recipes))
for recipe in recipes:
    name = recipe.parent.name
    body = recipe.read_bytes().decode('latin1')
    match = call.search(body)
    if not match:
        failures.append('%s does not use the shared hash' % name)
        continue
    arguments = match.group(1).split()
    report(arguments[0] == '"$path"', '%s does not hash itself' % name)
    # Whatever patch files the script applies have to be in the hash.
    patches = set(re.findall(r'^(\w+_patch)=', body, re.M))
    hashed = {argument.strip('"$') for argument in arguments[1:]}
    report(patches <= hashed,
           '%s applies %s but hashes %s' % (name, sorted(patches), sorted(hashed)))
    if name == 'DCMTK':
        for item in ('revision_file', 'Make.sh', 'isolate-dcmtk-jpegls.py'):
            report(item in match.group(1), 'DCMTK does not hash ' + item)
    report('$(env|sort' not in body, '%s still hashes the whole environment' % name)
    report('git describe' not in body, '%s still hashes git describe' % name)
    # The comparison and the record still work the same way.
    stamp = '.cmakehash' if '.cmakehash' in body else '.buildhash'
    report(body.count(stamp) >= 2 and '"$hash"' in body,
           '%s no longer compares and records the hash' % name)

# What the old formula answered for the same questions, taken from the commit
# this change is built on rather than retyped, so the comparison stays honest.
previous = subprocess.run(['git', 'show', 'HEAD:Horos/Scripts/VTK/CMake.sh'],
                          cwd=str(root), capture_output=True, text=True)
if previous.returncode == 0 and 'env|sort' in previous.stdout:
    formula = '\n'.join(line for line in previous.stdout.splitlines()
                        if line.startswith('env=') or line.startswith('hash='))
    formula = formula.replace('"$path"', '"%s"' % helper)
    formula = formula.replace('-$(md5 -q "$eigen_patch")', '')

    def old(cwd=None, **overrides):
        environment = dict(BASELINE)
        environment.update({k: v for k, v in overrides.items() if v is not None})
        script = formula + '\nprintf %s "$hash"\n'
        return subprocess.run(['/bin/sh', '-c', script], env=environment,
                              cwd=cwd or str(root), capture_output=True,
                              text=True).stdout

    was = old()
    report(old() == was, 'the old formula was not even stable')
    report(old(DEVELOPMENT_TEAM='ZZZZZ99999') != was,
           'the old formula already ignored the signing team')
    report(old(PRODUCT_NAME='Renamed') != was,
           'the old formula already ignored the product name')
    report(old(TERM='dumb') != was,
           'the old formula already ignored unrelated environment')
    # The working tree: this checkout is dirty while the change is being made.
    clean_tree = subprocess.run(['git', 'status', '--porcelain'], cwd=str(root),
                                capture_output=True, text=True).stdout.strip() == ''
    described = subprocess.run(['git', 'describe', '--always', '--tags', '--dirty'],
                               cwd=str(root), capture_output=True, text=True).stdout
    report(('-dirty' in described) != clean_tree,
           'git describe disagreed with git status about this tree')
    report('git describe' in previous.stdout,
           'the old formula did not consult git describe after all')

if failures:
    for failure in failures:
        print('FAIL: %s' % failure)
    sys.exit(1)
print('ok')
