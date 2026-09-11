#!/usr/bin/env python3
"""No personal signing identifier is versioned, and the override still reaches the build."""
import re, subprocess, sys, tempfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
failures = []

# 1. An Apple team identifier is ten uppercase alphanumerics. None may be
#    committed anywhere the build reads.
team = re.compile(r'\b(?![A-Z]{10}\b)[A-Z0-9]{10}\b')
# Vendored dependencies carry their upstream projects; only this project's own
# build files are in scope.
vendored = ('VTK/', 'ITK/', 'GDCM/', 'DCMTK/', 'OpenSSL/', 'OpenJPEG/', 'Grok/',
            'CharLS/', 'Papyrus3/', 'MSRG/', 'NIfTI_Library/', 'cocoahttpserver/')
tracked = subprocess.check_output(['git', '-C', str(root), 'ls-files'], text=True).split('\n')
for name in tracked:
    if not name.endswith(('.xcconfig', '.pbxproj', '.plist', '.entitlements')):
        continue
    if name.startswith(vendored):
        continue
    text = (root / name).read_bytes().decode('latin1')
    for line in text.split('\n'):
        if line.lstrip().startswith(('//', '#', '<!--')):
            continue
        for m in re.finditer(r'(DEVELOPMENT_TEAM|TeamIdentifier\w*|com\.apple\.application-identifier)\s*[=>:]\s*"?([^;"\n<]*)', line):
            value = m.group(2).strip()
            if team.fullmatch(value):
                failures.append('%s: %s is a committed team identifier (%s)' % (name, m.group(1), value))

# 2. The default has to be empty so a checkout without credentials resolves.
config = (root / 'Config.xcconfig').read_text()
if not re.search(r'^HOROS_DEVELOPMENT_TEAM\s*=\s*$', config, re.M):
    failures.append('Config.xcconfig: HOROS_DEVELOPMENT_TEAM no longer defaults to empty')
if not re.search(r'^DEVELOPMENT_TEAM\s*=\s*\$\(HOROS_DEVELOPMENT_TEAM\)\s*$', config, re.M):
    failures.append('Config.xcconfig: DEVELOPMENT_TEAM no longer follows HOROS_DEVELOPMENT_TEAM')
if '#include? "Config.local.xcconfig"' not in config:
    failures.append('Config.xcconfig: the untracked local override is no longer included')

# 3. That local file must stay untracked.
ignored = subprocess.run(['git', '-C', str(root), 'check-ignore', '-q', 'Config.local.xcconfig'])
if ignored.returncode != 0:
    failures.append('.gitignore: Config.local.xcconfig would be committed')
if not (root / 'Config.local.xcconfig.example').exists():
    failures.append('Config.local.xcconfig.example is missing, so the override is undocumented')

# 4. Every target has to follow the variable rather than carrying its own team.
project = (root / 'Horos.xcodeproj/project.pbxproj').read_text()
own = [v for v in re.findall(r'DEVELOPMENT_TEAM = ([^;]+);', project)
       if '$(HOROS_DEVELOPMENT_TEAM)' not in v]
if own:
    failures.append('project.pbxproj: targets carrying their own team: %s' % sorted(set(own)))

if failures:
    print('FAIL:')
    for f in failures:
        print(' ', f)
    sys.exit(1)

# 6. Every executable that ends up inside the bundle has to be signed, or an
#    archive containing it cannot be notarised. Xcode signs the bundle, its
#    frameworks and its embedded bundles; a bare executable copied by Copy Bundle
#    Resources is data to it, so the application target signs those itself.
phase = re.search(r'CED88262125064F70085A861 /\* CodeSigning \*/ = \{(.*?)\n\t\t\};',
                  project, re.S)
if not phase:
    failures.append('project.pbxproj: the CodeSigning phase is gone')
else:
    body = phase.group(1).encode().decode('unicode_escape')
    if 'codesign' not in body:
        failures.append('project.pbxproj: the CodeSigning phase signs nothing')
    if 'alwaysOutOfDate = 1' not in phase.group(1):
        failures.append('project.pbxproj: the CodeSigning phase would be skipped on a rebuild')
    # It walks a directory tree signing what it finds, so an unset build
    # variable must not let that tree become "/".
    if 'TARGET_BUILD_DIR' not in body or 'UNLOCALIZED_RESOURCES_FOLDER_PATH' not in body:
        failures.append('project.pbxproj: the CodeSigning phase does not name the resources folder')
    if 'run it from Xcode' not in body:
        failures.append('project.pbxproj: the CodeSigning phase does not refuse an empty build directory')
    # EXPANDED_CODE_SIGN_IDENTITY_NAME is a display name codesign cannot look up.
    if 'EXPANDED_CODE_SIGN_IDENTITY_NAME' in body:
        failures.append('project.pbxproj: the CodeSigning phase signs with a display name')
    if 'CODE_SIGNING_ALLOWED' not in body:
        failures.append('project.pbxproj: the CodeSigning phase ignores CODE_SIGNING_ALLOWED')

# The same gap exists in the local development bundle, which is re-signed after
# its identifier is changed; codesign --deep does not reach these either.
launcher = (root / 'script/build_and_run.sh').read_text()
if 'Contents/Resources" -type f -perm -u+x' not in launcher or 'codesign' not in launcher:
    failures.append('script/build_and_run.sh: the helpers in Resources are not signed')

# 7. If a bundle has been built, every Mach-O in it has to carry a signature,
#    and must be something this product minimum still needs. HorosPlatformPolicy
#    owns both the minimum and what it implies for the bundle, so ask it.
def askPolicy():
    driver = """
import Foundation

@main struct Check {
    static func main() {
        let minimum = HorosPlatformPolicy.productMinimumDisplay()
        let embeds = HorosPlatformPolicy.bundleMayEmbedSwiftRuntime(productMinimum: minimum)
        print(embeds ? "embeds" : "bare")
        for name in ["libswift_Concurrency.dylib", "libswiftCore.dylib", "Horos", "libgdcmMSFF.dylib"] {
            print(name, HorosPlatformPolicy.embeddedFileIsSwiftRuntime(name) ? "swift" : "other")
        }
    }
}
"""
    with tempfile.TemporaryDirectory(prefix='horos-signing-policy-') as folder:
        path = Path(folder)
        (path / 'Check.swift').write_text(driver)
        build = subprocess.run(
            ['xcrun', 'swiftc', '-parse-as-library',
             str(root / 'Horos/Sources/HorosPlatformPolicy.swift'),
             str(path / 'Check.swift'), '-o', str(path / 'check')],
            capture_output=True, text=True)
        if build.returncode:
            return None, None
        run = subprocess.run([str(path / 'check')], capture_output=True, text=True)
        if run.returncode:
            return None, None
    lines = run.stdout.split()
    names = dict(zip(lines[1::2], lines[2::2]))
    return lines[0] == 'embeds', names

embedsSwiftRuntime, classification = askPolicy()
if classification is None:
    failures.append('HorosPlatformPolicy does not answer what the bundle may embed')
    embedsSwiftRuntime = False
    classification = {}
elif classification != {'libswift_Concurrency.dylib': 'swift', 'libswiftCore.dylib': 'swift',
                        'Horos': 'other', 'libgdcmMSFF.dylib': 'other'}:
    failures.append('HorosPlatformPolicy no longer recognises the Swift runtime by name: %s'
                    % classification)
if embedsSwiftRuntime:
    failures.append('the product minimum fell below macOS 10.14.4; this check needs revisiting')

def swiftRuntime(name):
    return name.startswith('libswift') and name.endswith('.dylib')


def machO(path):
    with open(path, 'rb') as handle:
        return handle.read(4) in (b'\xcf\xfa\xed\xfe', b'\xce\xfa\xed\xfe',
                                  b'\xca\xfe\xba\xbe', b'\xbe\xba\xfe\xca')

# Every configuration's product counts, not just the one most recently built by
# hand: an incremental products directory keeps what the current build no longer
# produces, and whether that orphan happens to be signed depends on when each
# configuration was last built (#555).
for bundle in (root / 'build/Development/HorosDevelopment.app',
               root / 'build/Build/Products/Debug/Horos.app',
               root / 'build/Build/Products/Release/Horos.app'):
    if not bundle.is_dir():
        continue
    # Two of the three are called Horos.app; name them by configuration.
    label = '%s/%s' % (bundle.parent.name, bundle.name)
    # A bundle built with CODE_SIGNING_ALLOWED=NO is unsigned all the way through
    # on purpose, so there are no signatures to check inside it. The linker still
    # puts an ad hoc signature on the arm64 executable, so that is not a sign
    # that codesign ever ran. Orphans are checked either way: a file the current
    # build no longer produces is an orphan whether or not anything was signed,
    # and the Debug product is normally built unsigned by script/build_and_run.sh
    # -- which is exactly where #555 was sitting.
    outer = subprocess.run(['codesign', '-dv', str(bundle)], capture_output=True, text=True)
    signed = (outer.returncode == 0 and 'Signature=' in outer.stderr
              and 'linker-signed' not in outer.stderr)
    checked = unsigned = orphans = 0
    for path in bundle.rglob('*'):
        if not path.is_file() or path.is_symlink() or not machO(path):
            continue
        checked += 1
        if signed:
            shown = subprocess.run(['codesign', '-dv', str(path)], capture_output=True, text=True)
            if shown.returncode != 0 or 'Signature=' not in shown.stderr:
                unsigned += 1
                failures.append('%s: %s is unsigned' % (label, path.relative_to(bundle)))
        # An embedded Swift runtime is back-deployment support for a macOS this
        # product no longer targets. Signed or not, it is left over from an older
        # deployment target: Xcode removes neither, and re-signs neither.
        if not embedsSwiftRuntime and swiftRuntime(path.name):
            orphans += 1
            failures.append('%s: %s is a Swift runtime this product minimum does not need'
                            % (label, path.relative_to(bundle)))
    if checked == 0:
        failures.append('%s: no Mach-O files found, so nothing was checked' % label)
    else:
        print('%s: %d Mach-O files, %d unsigned, %d orphaned Swift runtime%s'
              % (label, checked, unsigned, orphans,
                 '' if signed else ' (built without signing, signatures not checked)'))

if failures:
    print('FAIL:')
    for f in failures:
        print(' ', f)
    sys.exit(1)

# 5. And the override has to actually reach the build settings, both ways.
def resolved(extra=None, local=None):
    path = root / 'Config.local.xcconfig'
    wrote = False
    try:
        if local is not None:
            path.write_text('HOROS_DEVELOPMENT_TEAM = %s\n' % local)
            wrote = True
        command = ['xcodebuild', '-project', str(root / 'Horos.xcodeproj'), '-target', 'Horos',
                   '-configuration', 'Debug', '-showBuildSettings']
        if extra:
            command.append(extra)
        out = subprocess.run(command, capture_output=True, text=True, cwd=str(root)).stdout
        found = re.search(r'^\s+DEVELOPMENT_TEAM = (.*)$', out, re.M)
        return found.group(1).strip() if found else ''
    finally:
        if wrote:
            path.unlink()

if (root / 'Config.local.xcconfig').exists():
    print('SKIP: a Config.local.xcconfig is present; not disturbing it')
else:
    default, command_line, from_file = resolved(), resolved('HOROS_DEVELOPMENT_TEAM=ABCDE12345'), resolved(local='FGHIJ67890')
    if default:
        print('FAIL: a checkout with no override resolves a team: %r' % default); sys.exit(1)
    if command_line != 'ABCDE12345':
        print('FAIL: the command line override did not reach the build: %r' % command_line); sys.exit(1)
    if from_file != 'FGHIJ67890':
        print('FAIL: Config.local.xcconfig did not reach the build: %r' % from_file); sys.exit(1)

print('PASS: no team identifier is committed, the default resolves empty, both the command '
      'line and the untracked local config reach DEVELOPMENT_TEAM, and every executable in '
      'the bundles that exist is signed')
