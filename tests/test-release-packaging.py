#!/usr/bin/env python3
"""script/build_release.sh keeps the previous artifact unless the new one is complete (#980).

The script compiles, signs the bundle ad hoc from the inside out, audits it with
tools/audit-release-bundle.py --strict --notices, writes BUILD-INFO.txt and
SHA256SUMS.txt beside it (script/release-metadata.py) and only then replaces
build/Release. This runs the real script in a scratch copy of the checkout with
xcodebuild replaced by a stand-in that either fails or "builds" a small bundle:

- a first good build leaves Isis DICOM Viewer.app, BUILD-INFO.txt and SHA256SUMS.txt; the
  sums verify with shasum, BUILD-INFO names the executable's SHA-256, says the
  bundle is not Developer ID signed nor notarized, and names no home folder;
- a failed build and a build whose bundle loads a library from outside itself
  or lacks a license notice fail and leave those three files as they were;
- a second good build replaces the three and keeps the previous ones under the
  same date.
"""
import private_tmpdir  # noqa: F401  - its own TMPDIR for the tools it runs (#803)
from pathlib import Path
import hashlib
import json
import plistlib
import os
import re
import shutil
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
failures = []


def report(ok, message):
    if not ok:
        failures.append(message)


if shutil.which('xcrun') is None:
    print('skipped: needs xcrun clang to make the test bundle', file=sys.stderr)
    sys.exit(2)

work = Path(tempfile.mkdtemp(prefix='release-packaging-')).resolve()
checkout = work / 'checkout'
checkout.mkdir()
subprocess.run(['/usr/bin/git', 'init', '-q', str(checkout)], check=True)
for relative in ('script/build_release.sh', 'script/release-metadata.py', 'tools/audit-release-bundle.py',
                 'Horos/Horos.entitlements', 'Decompress/Decompress.entitlements',
                 'Horos/Configuration/GitHub.xcconfig', 'FinderPreview/FinderPreview.entitlements',
                 'Horos/Scripts/DCMTK/PREPARATION.json'):
    (checkout / relative).parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(root / relative, checkout / relative)
# The strict notices audit reads the app's authoritative catalog as well as the
# fixture bundle. Keep that prerequisite with the isolated checkout.
(checkout / 'Horos/Sources').mkdir(parents=True)
shutil.copy2(root / 'Horos/Sources/LicenseAttribution.swift', checkout / 'Horos/Sources/LicenseAttribution.swift')
source_pin = json.loads((root / 'Horos/Scripts/external-sources.json').read_text())['OpenJPEG']
source_json = json.dumps(source_pin)
installed = checkout / 'build/Intermediates.noindex/Horos.build/Release/OpenJPEG.build/Install'
(installed / 'lib/pkgconfig').mkdir(parents=True)
(installed / 'lib/pkgconfig/libopenjp2.pc').write_text('Version: ' + source_pin['version'] + '\n')
(installed / 'share').mkdir()
(installed / 'share/source.json').write_text(source_json)
vtk_installed = checkout / 'build/Intermediates.noindex/Horos.build/Release/VTK.build/Install'
(vtk_installed/'include').mkdir(parents=True)
(vtk_installed/'include/vtkVersionMacros.h').write_text('#define VTK_VERSION "9.7.1"\n')
(vtk_installed/'share').mkdir()
vtk_pin = json.loads((root/'Horos/Scripts/external-sources.json').read_text())['VTK']
vtk_source_json = json.dumps(vtk_pin)
(vtk_installed/'share/source.json').write_text(vtk_source_json)
itk_installed = checkout / 'build/Intermediates.noindex/Horos.build/Release/ITK.build/Install'
(itk_installed/'include').mkdir(parents=True)
(itk_installed/'include/itkConfigure.h').write_text(
    '#define ITK_VERSION_MAJOR 5\n#define ITK_VERSION_MINOR 4\n#define ITK_VERSION_PATCH 7\n')
(itk_installed/'share').mkdir()
itk_pin = json.loads((root/'Horos/Scripts/external-sources.json').read_text())['ITK']
itk_source_json = json.dumps(itk_pin)
(itk_installed/'share/source.json').write_text(itk_source_json)
freetype_pin = json.loads((root/'Horos/Scripts/VTK/freetype-source.json').read_text())
vtk_adaptation = json.dumps({'source':freetype_pin,'method':'Mach-O alias, original symbol localized',
    'publicSymbol':'_vtkfreetype_FT_MulFix','localSymbol':'_FT_MulFix',
    'installedArchiveSha256':'1'*64,'recipeSha256':{'adapt-freetype.py':'2'*64}})
(vtk_installed/'share/freetype-host-adaptation.json').write_text(vtk_adaptation)

# The existing packaging stand-in has no Swift product initially; package cases
# below add a real Git checkout and a controlled public-tag response.
project = checkout / 'Horos.xcodeproj/project.pbxproj'
project.parent.mkdir(parents=True)
project.write_bytes(plistlib.dumps({'objects': {}}))

sources = work / 'sources'
sources.mkdir()


def clang(*arguments):
    subprocess.run(['xcrun', 'clang', '-arch', 'arm64', '-mmacosx-version-min=26.0',
                    '-Wl,-headerpad_max_install_names'] + list(arguments), check=True, capture_output=True)


def make_product(folder, outside=None, notices=True, marker='one'):
    app = folder / 'Isis DICOM Viewer.app'
    for sub in ('MacOS', 'Frameworks', 'Resources/Splash', 'Resources/ExternalLibraries/foo'):
        (app / 'Contents' / sub).mkdir(parents=True, exist_ok=True)
    (app / 'Contents/Info.plist').write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n<plist version="1.0"><dict>'
        '<key>CFBundleExecutable</key><string>Isis DICOM Viewer</string>'
        '<key>CFBundleIdentifier</key><string>test.release.packaging</string>'
        '<key>CFBundleShortVersionString</key><string>1.0</string>'
        '<key>CFBundleVersion</key><string>1</string>'
        '<key>LSMinimumSystemVersion</key><string>26.0</string>'
        '<key>CFBundlePackageType</key><string>APPL</string></dict></plist>\n')
    (sources / 'foo.c').write_text('int foo(void) { return 1; }\n')
    library = app / 'Contents/Frameworks/libfoo.1.dylib'
    clang('-dynamiclib', '-install_name', '@rpath/libfoo.1.dylib', str(sources / 'foo.c'), '-o', str(library))
    (sources / 'main.c').write_text('int foo(void); int main(void) { return foo() - 1; } /* %s */\n' % marker)
    link = [str(library)]
    if outside is not None:
        (sources / 'out.c').write_text('int out(void) { return 0; }\n')
        clang('-dynamiclib', '-install_name', str(outside), str(sources / 'out.c'), '-o', str(outside))
        link.append(str(outside))
    clang(str(sources / 'main.c'), '-o', str(app / 'Contents/MacOS/Isis DICOM Viewer'),
          '-Wl,-rpath,@executable_path/../Frameworks', *link)
    subprocess.run(['install_name_tool', '-change', '@rpath/libfoo.1.dylib',
                    '@loader_path/../Frameworks/libfoo.1.dylib', str(app / 'Contents/MacOS/Isis DICOM Viewer')],
                   check=True, capture_output=True)
    resources = app / 'Contents/Resources'
    names = ['LICENSE', 'COPYING.LESSER', 'NOTICE', 'Splash/about.html', 'Splash/licenses.html',
             'Splash/OpenSSL-LICENSE.txt', 'Splash/DICOM-Swift-LICENSE.txt']
    for name in names[:-1] if not notices else names:
        (resources / name).write_text('%s %s\n' % (name, marker))
    shutil.copytree(root / 'Binaries/Splash/ThirdParty', resources / 'Splash/ThirdParty')
    (resources / 'CompiledSources/OpenJPEG').mkdir(parents=True)
    (resources / 'CompiledSources/OpenJPEG/source.json').write_text(source_json)
    shutil.copyfile(root / 'Binaries/Splash/ThirdParty/Native/OpenJPEG/LICENSE',
                    resources / 'CompiledSources/OpenJPEG/LICENSE')
    (resources/'CompiledSources/ITK').mkdir()
    (resources/'CompiledSources/ITK/source.json').write_text(itk_source_json)
    for notice in ('LICENSE', 'NOTICE'):
        shutil.copyfile(root/'Binaries/Splash/ThirdParty/Native/ITK'/notice, resources/'CompiledSources/ITK'/notice)
    (resources/'CompiledSources/VTK').mkdir()
    (resources/'CompiledSources/VTK/source.json').write_text(vtk_source_json)
    shutil.copyfile(root/'Binaries/Splash/ThirdParty/Native/VTK/Copyright.txt',
                    resources/'CompiledSources/VTK/Copyright.txt')
    (resources/'CompiledSources/VTK/freetype-host-adaptation.json').write_text(vtk_adaptation)
    (resources / 'ExternalLibraries/embedded-libraries.txt').write_text(
        '# test\nfoo 1.0 arm64_tahoe %s libfoo.1.dylib\n' % ('0' * 64))
    (resources / 'ExternalLibraries/foo/LICENSE').write_text('license of foo\n')
    import importlib.util
    spec = importlib.util.spec_from_file_location('feedback_prepare', root / 'Horos/Scripts/FeedbackReporter/prepare.py')
    selector = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(selector)
    with tempfile.TemporaryDirectory(prefix='packaging-feedback-') as temporary:
        prepared = selector.prepare(root / 'FeedbackReporter', Path(temporary) / 'prepared')
        framework = app / 'Contents/Frameworks/FeedbackReporter.framework'
        version = framework / 'Versions/A'
        target = version / 'Resources'
        target.mkdir(parents=True, exist_ok=True)
        (framework / 'Versions/Current').symlink_to('A')
        (framework / 'Resources').symlink_to('Versions/Current/Resources')
        (framework / 'FeedbackReporter').symlink_to('Versions/Current/FeedbackReporter')
        (sources / 'feedback.c').write_text('int feedback_metadata_fixture(void) { return 0; }\n')
        clang('-dynamiclib', '-install_name', '@rpath/FeedbackReporter.framework/Versions/A/FeedbackReporter',
              str(sources / 'feedback.c'), '-o', str(version / 'FeedbackReporter'))
        import plistlib
        (target / 'Info.plist').write_bytes(plistlib.dumps({
            'CFBundleExecutable': 'FeedbackReporter', 'CFBundleIdentifier': 'test.release.feedback',
            'CFBundlePackageType': 'FMWK', 'CFBundleVersion': '1'}))
        shutil.copyfile(prepared / 'BuildSource.json', target / 'BuildSource.json')
    return folder


products = work / 'products'
good = make_product(products / 'good')
second = make_product(products / 'second', marker='two')
external = make_product(products / 'external', outside=work / 'libout.1.dylib')
unnoticed = make_product(products / 'unnoticed', notices=False)
empty_notice = make_product(products / 'empty-notice')
(empty_notice / 'Isis DICOM Viewer.app/Contents/Resources/Splash/ThirdParty/Native/ITK/NOTICE').write_bytes(b'')
missing_transitive = make_product(products / 'missing-transitive')
(missing_transitive / 'Isis DICOM Viewer.app/Contents/Resources/Splash/ThirdParty/Native/VTK/ThirdParty/freetype/vtkfreetype/docs/FTL.TXT').unlink()
wrong_source = make_product(products / 'wrong-source')
(wrong_source / 'Isis DICOM Viewer.app/Contents/Resources/CompiledSources/OpenJPEG/source.json').write_text('{}\n')


stub = work / 'bin'
stub.mkdir()
(stub / 'xcodebuild').write_text('''#!/bin/sh
if [ "$1" = "-version" ]; then echo "Xcode 99.0"; echo "Build version 99A1"; exit 0; fi
if [ -n "$STUB_FAIL" ]; then
    echo "$STUB_FAIL" >&2
    i=0
    while [ "$i" -lt 80 ]; do echo "note: interrupted parallel task"; i=$((i + 1)); done
    exit 65
fi
case " $* " in *" -disableAutomaticPackageResolution "*) ;; *) echo "error: automatic package resolution allowed" >&2; exit 1;; esac
case " $* " in *" -onlyUsePackageVersionsFromResolvedFile "*) ;; *) echo "error: resolved pins not required" >&2; exit 1;; esac
case " $* " in *" COMPILATION_CACHE_CAS_PATH=$PWD/build/CompilationCache.noindex "*) ;; *) echo "error: compilation cache is not local to the checkout" >&2; exit 1;; esac
if [ -n "$STUB_MUTATE_LOCK" ]; then printf 'changed lockfile' >> "$STUB_MUTATE_LOCK"; fi
for argument; do case "$argument" in SYMROOT=*) symroot="${argument#SYMROOT=}" ;; esac; done
mkdir -p "$symroot/Release"
rm -rf "$symroot/Release/Isis DICOM Viewer.app"
/usr/bin/ditto "$STUB_PRODUCT/Isis DICOM Viewer.app" "$symroot/Release/Isis DICOM Viewer.app"
''')
(stub / 'xcodebuild').chmod(0o755)

output = checkout / 'build/Release'
ITEMS = ('Isis DICOM Viewer.app', 'BUILD-INFO.txt', 'SHA256SUMS.txt')


def build(product=None, fail=False, mutate_lock=False, public_ref=None):
    environment = dict(os.environ, PATH='%s:%s' % (stub, os.environ.get('PATH', '/usr/bin:/bin')))
    environment['GIT_ALLOW_PROTOCOL'] = 'file'
    environment.pop('HOROS_PUBLIC_SOURCE_REF', None)
    if public_ref is not None:
        environment['HOROS_PUBLIC_SOURCE_REF'] = public_ref
    environment.pop('STUB_FAIL', None)
    environment.pop('STUB_MUTATE_LOCK', None)
    if mutate_lock:
        environment['STUB_MUTATE_LOCK'] = str(checkout / 'Horos.xcodeproj/project.xcworkspace/xcshareddata/swiftpm/Package.resolved')
    if fail:
        environment['STUB_FAIL'] = fail if isinstance(fail, str) else 'error: stub: build failed'
    if product is not None:
        environment['STUB_PRODUCT'] = str(product)
    return subprocess.run(['/bin/bash', str(checkout / 'script/build_release.sh')], env=environment,
                          capture_output=True, text=True, cwd=str(checkout))


def state():
    """What build/Release holds: each item's digest (the app by its executable)."""
    result = {}
    for item in ITEMS:
        path = output / item
        if item == 'Isis DICOM Viewer.app':
            path = path / 'Contents/MacOS/Isis DICOM Viewer'
        result[item] = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
    return result


first = build(good)
report(first.returncode == 0, 'the first good build failed: %s' % (first.stdout + first.stderr)[-1500:])
before = state()
report(all(before.values()), 'the first build did not leave all of %s: %s' % (ITEMS, before))
if all(before.values()):
    check = subprocess.run(['shasum', '-a', '256', '-c', 'SHA256SUMS.txt'], cwd=str(output),
                           capture_output=True, text=True)
    report(check.returncode == 0 and 'FAILED' not in check.stdout,
           'SHA256SUMS.txt does not verify: %s' % check.stdout[-500:])
    listed = (output / 'SHA256SUMS.txt').read_text()
    report('Isis DICOM Viewer.app/Contents/MacOS/Isis DICOM Viewer' in listed and 'BUILD-INFO.txt' in listed
           and 'Isis DICOM Viewer.app/Contents/Frameworks/libfoo.1.dylib' in listed,
           'SHA256SUMS.txt does not list the bundle and BUILD-INFO')
    info = (output / 'BUILD-INFO.txt').read_text()
    report(not re.search(r'^\s+GDCM\s', info, re.M),
           'BUILD-INFO.txt still lists the retired GDCM dependency')
    report(before['Isis DICOM Viewer.app'] in info, 'BUILD-INFO.txt does not carry the executable\'s SHA-256')
    report('NOT signed with Developer ID, NOT notarized' in info, 'BUILD-INFO.txt does not say what the artifact is not')
    report('foo 1.0 (arm64_tahoe)' in info and 'libfoo.1.dylib' in info,
           'BUILD-INFO.txt does not list the embedded libraries')
    report(source_pin['sha256'] in info and source_pin['revision'] in info,
           'BUILD-INFO.txt does not identify the OpenJPEG archive consumed by this build')
    report(itk_pin['sha256'] in info and itk_pin['revision'] in info,
           'BUILD-INFO.txt does not identify the ITK archive consumed by this build')
    report(freetype_pin['treeSha256'] in info and '_vtkfreetype_FT_MulFix' in info and
           'source patches: none in FreeType' in info,
           'BUILD-INFO.txt does not distinguish original FreeType source from its host ABI adaptation')
    report('ad hoc' in info and 'disable-library-validation' in info, 'BUILD-INFO.txt does not describe the signature')
    report('Xcode 99.0' in info, 'BUILD-INFO.txt does not name the toolchain')
    report('FeedbackReporter upstream 92230feade69e1298cd5a8cbc0c8ddd2dc939934' in info
           and 'host source selection:' in info, 'FeedbackReporter metadata omits built source selection')
    report('DCMTK compiled from the unmodified checkout' in info and 'prepared source differs from base' not in info,
           'DCMTK metadata does not say that the pinned source is compiled unmodified')
    report('libarchive headers source 3.7.4' in info and 'runtime supplied by macOS' in info,
           'libarchive metadata confuses header version with runtime')
    report('/Users/' not in info and str(Path.home()) not in info and str(work) not in info,
           'BUILD-INFO.txt names a local path')
    signed = subprocess.run(['codesign', '-dv', str(output / 'Isis DICOM Viewer.app')], capture_output=True, text=True).stderr
    report('flags=0x10002(adhoc,runtime)' in signed, 'the app is not signed ad hoc with the hardened runtime')

for label, arguments, expected in (('a failed build', {'fail': True}, 'stub: build failed'),
                                   ('a broken submodule', {'fail': "fatal: could not get a repository handle for submodule 'FeedbackReporter'"},
                                    "fatal: could not get a repository handle for submodule 'FeedbackReporter'"),
                                   ('a bundle loading from outside', {'product': external}, 'from outside the bundle'),
                                   ('a bundle without a notice', {'product': unnoticed}, 'DICOM-Swift-LICENSE.txt'),
                                   ('an empty native notice', {'product': empty_notice}, 'Native/ITK/NOTICE'),
                                   ('a missing transitive notice', {'product': missing_transitive}, 'FTL.TXT'),
                                   ('a different bundled source record', {'product': wrong_source}, 'compiled source record')):
    signing_log = checkout / 'build/logs/release-signing.log'
    signing_before = signing_log.read_bytes() if signing_log.exists() else None
    outcome = build(**arguments)
    if 'notice' in label:
        report(signing_log.read_bytes() == signing_before, label + ' reached signing before notice audit')
    report(outcome.returncode != 0, '%s was accepted' % label)
    report(expected in outcome.stdout + outcome.stderr,
           '%s failed for another reason: %s' % (label, (outcome.stdout + outcome.stderr)[-800:]))
    report(state() == before, '%s changed the previous artifact' % label)
    report(not list(output.glob('*.previous-*')), '%s left a backup behind' % label)

again = build(second)
report(again.returncode == 0, 'the second good build failed: %s' % (again.stdout + again.stderr)[-1500:])
after = state()
report(after['Isis DICOM Viewer.app'] != before['Isis DICOM Viewer.app'] and all(after.values()), 'the second build did not replace the artifact')
kept = sorted(p.name for p in output.glob('*.previous-*'))
stamps = {re.sub(r'^.*\.previous-(.*?)\.(app|txt)$', r'\1', name) for name in kept}
report(len(kept) == 3 and len(stamps) == 1, 'the previous artifact was not kept as three files of one date: %s' % kept)
if len(kept) == 3:
    previous_app = next(output.glob('Isis DICOM Viewer.previous-*.app'))
    report(hashlib.sha256((previous_app / 'Contents/MacOS/Isis DICOM Viewer').read_bytes()).hexdigest() == before['Isis DICOM Viewer.app'],
           'the kept app is not the previous one')

# Pin approval is checked against effective state and Git, not merely copied
# from Package.resolved into BUILD-INFO. No network or source compilation stand-in
# is counted as functional app validation here.
package_url = 'https://github.com/ThalesMMS/DICOM-Swift.git'
package_path = checkout / 'build/SourcePackages'
package_checkout = package_path / 'checkouts/DICOM-Swift'
package_checkout.mkdir(parents=True)
subprocess.run(['/usr/bin/git', 'init', '-q', str(package_checkout)], check=True)
(package_checkout / 'Package.swift').write_text('// synthetic packaging input\n')
# Package license snapshots are real public materials; the small source checkout
# and network responses remain synthetic packaging stand-ins.
import importlib.util
spec = importlib.util.spec_from_file_location('release_metadata', root / 'script/release-metadata.py')
release_metadata = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release_metadata)
for source_path, bundle_path in release_metadata.PACKAGE_NOTICE_PATHS.items():
    target = package_checkout / source_path
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(root / 'Binaries' / bundle_path, target)

for arguments in (['add', '.'], ['-c', 'user.name=Test', '-c', 'user.email=test@example.invalid',
                   'commit', '-qm', 'Synthetic package'], ['remote', 'add', 'origin', package_url]):
    subprocess.run(['/usr/bin/git', '-C', str(package_checkout), *arguments], check=True, capture_output=True)
revision = subprocess.check_output(['/usr/bin/git', '-C', str(package_checkout), 'rev-parse', 'HEAD'], text=True).strip()
(stub / 'git').write_text('#!/bin/sh\ncase " $* " in *" ls-remote "*) '
                         + 'printf "' + revision + '\trefs/tags/0.0.0-test\n"; exit 0;; esac\n'
                         + 'exec /usr/bin/git "$@"\n')
(stub / 'git').chmod(0o755)
objects = {
    'remote': {'isa': 'XCRemoteSwiftPackageReference', 'repositoryURL': package_url,
               'requirement': {'kind': 'exactVersion', 'version': '0.0.0-test'}},
    'product': {'isa': 'XCSwiftPackageProductDependency', 'package': 'remote', 'productName': 'DicomWebClient'},
    'target': {'isa': 'PBXNativeTarget', 'name': 'Horos', 'packageProductDependencies': ['product']},
}
project.write_bytes(plistlib.dumps({'objects': objects}))
lock = checkout / 'Horos.xcodeproj/project.xcworkspace/xcshareddata/swiftpm/Package.resolved'
lock.parent.mkdir(parents=True)
approved_state = {'revision': revision, 'version': '0.0.0-test'}
approved_lock = json.dumps({'version': 3, 'pins': [{'identity': 'dicom-swift', 'kind': 'remoteSourceControl',
                           'location': package_url, 'state': approved_state}]})
lock.write_text(approved_lock)
dependency = {'packageRef': {'identity': 'dicom-swift', 'kind': 'remoteSourceControl', 'location': package_url},
              'state': {'name': 'sourceControlCheckout', 'checkoutState': approved_state}, 'subpath': 'DICOM-Swift'}
workspace_state = package_path / 'workspace-state.json'
def save_state():
    workspace_state.write_text(json.dumps({'version': 6, 'object': {'dependencies': [dependency], 'artifacts': []}}))
save_state()
pinned = build(good)
report(pinned.returncode == 0, 'the approved effective package failed: ' + (pinned.stdout + pinned.stderr)[-800:])
pinned_before = state()
if pinned.returncode == 0:
    metadata = (output / 'BUILD-INFO.txt').read_text()
    report('DicomWebClient' in metadata and revision in metadata and 'tag: 0.0.0-test' in metadata,
           'metadata lacks the effective product/tag/public revision')
    report(hashlib.sha256(lock.read_bytes()).hexdigest() in metadata,
           'metadata lacks the approved lockfile hash')
    for source_path, bundled in release_metadata.PACKAGE_NOTICE_PATHS.items():
        source_bytes = (package_checkout / source_path).read_bytes()
        report((output / 'Isis DICOM Viewer.app/Contents/Resources' / bundled).read_bytes() == source_bytes,
               'bundled package notice differs from effective source: ' + source_path)
        report(hashlib.sha256(source_bytes).hexdigest() in metadata,
               'metadata lacks effective package notice hash: ' + source_path)

def rejected(label, expected, **arguments):
    outcome = build(good, **arguments)
    report(outcome.returncode != 0 and expected in outcome.stdout + outcome.stderr,
           label + ' was accepted or failed for another reason: ' + (outcome.stdout + outcome.stderr)[-600:])
    report(state() == pinned_before, label + ' replaced the previous artifact')

dependency['state'] = {'name': 'fileSystem', 'path': str(work)}
save_state()
rejected('a local package override', 'local override')
dependency['state'] = {'name': 'sourceControlCheckout', 'checkoutState': approved_state}
save_state()
(package_checkout / 'Package.swift').write_text('// locally changed input\n')
rejected('modified package source', 'local changes')
subprocess.run(['/usr/bin/git', '-C', str(package_checkout), 'checkout', '--', 'Package.swift'], check=True)
subprocess.run(['/usr/bin/git', '-C', str(package_checkout), 'remote', 'set-url', 'origin', str(work)], check=True)
rejected('a rewritten package origin', 'origin was rewritten')
subprocess.run(['/usr/bin/git', '-C', str(package_checkout), 'remote', 'set-url', 'origin', package_url], check=True)
# A lockfile/state that agree with each other can still lie about the checkout.
false_state = {'revision': '0' * 40, 'version': '0.0.0-test'}
false_lock = json.loads(approved_lock)
false_lock['pins'][0]['state'] = false_state
lock.write_text(json.dumps(false_lock))
dependency['state']['checkoutState'] = false_state
save_state()
rejected('a false resolved revision', 'checkout revision differs')
lock.write_text(approved_lock)
dependency['state']['checkoutState'] = approved_state
save_state()
public_response = (stub / 'git').read_text()
(stub / 'git').write_text(public_response.replace(revision, '0' * 40))
rejected('a tag pointing at another revision', 'does not match its public tag')
(stub / 'git').write_text(public_response)
subprocess.run(['/usr/bin/git', '-C', str(package_checkout), 'remote', 'set-url', 'origin',
                package_url.removesuffix('.git')], check=True)
equivalent = build(good)
report(equivalent.returncode == 0, 'the public URL without .git was refused: '
       + (equivalent.stdout + equivalent.stderr)[-800:])
pinned_before = state()
subprocess.run(['/usr/bin/git', '-C', str(package_checkout), 'remote', 'set-url', 'origin',
                'https://github.com/unapproved/DICOM-Swift.git'], check=True)
rejected('another public package origin', 'origin was rewritten')
subprocess.run(['/usr/bin/git', '-C', str(package_checkout), 'remote', 'set-url', 'origin', package_url], check=True)
# Real Xcode working copies point to a bare cache whose origin is public.
cache = package_path / 'repositories/DICOM-Swift-test.git'
cache.parent.mkdir()
subprocess.run(['/usr/bin/git', 'clone', '--bare', str(package_checkout), str(cache)], check=True, capture_output=True)
subprocess.run(['/usr/bin/git', '-C', str(cache), 'remote', 'set-url', 'origin', package_url], check=True)
subprocess.run(['/usr/bin/git', '-C', str(package_checkout), 'remote', 'set-url', 'origin', str(cache)], check=True)
cached = build(good)
report(cached.returncode == 0, 'a public Xcode bare-cache origin was refused: ' + (cached.stdout + cached.stderr)[-800:])
subprocess.run(['/usr/bin/git', '-C', str(cache), 'remote', 'set-url', 'origin',
                package_url.removesuffix('.git')], check=True)
equivalent_cache = build(good)
report(equivalent_cache.returncode == 0, 'the public Xcode cache URL without .git was refused: '
       + (equivalent_cache.stdout + equivalent_cache.stderr)[-800:])
pinned_before = state()
subprocess.run(['/usr/bin/git', '-C', str(cache), 'remote', 'set-url', 'origin', str(work)], check=True)
rejected('a rewritten Xcode cache origin', 'origin was rewritten')
subprocess.run(['/usr/bin/git', '-C', str(cache), 'remote', 'set-url', 'origin', package_url], check=True)
subprocess.run(['/usr/bin/git', '-C', str(package_checkout), 'remote', 'set-url', 'origin', package_url], check=True)
objects['remote']['requirement']['kind'] = 'upToNextMajorVersion'
project.write_bytes(plistlib.dumps({'objects': objects}))
rejected('a floating package requirement', 'Exact Version')
objects['remote']['requirement']['kind'] = 'exactVersion'
project.write_bytes(plistlib.dumps({'objects': objects}))
objects['local'] = {'isa': 'XCLocalSwiftPackageReference', 'relativePath': str(work)}
project.write_bytes(plistlib.dumps({'objects': objects}))
rejected('a local project package reference', 'local Swift package')
del objects['local']
project.write_bytes(plistlib.dumps({'objects': objects}))
canonical_workspace = checkout / 'Horos.xcodeproj/project.xcworkspace/contents.xcworkspacedata'
canonical_workspace.write_text('<Workspace><FileRef location="self:"/><FileRef location="group:local-package"/></Workspace>')
rejected('a canonical workspace override', 'additional workspace references')
canonical_workspace.write_text('<Workspace><FileRef location="self:"/></Workspace>')
rejected('a lockfile mutated by the build', 'alterou o lockfile', mutate_lock=True)
lock.write_text(approved_lock)

# Verify the optional mapping to the public Horos source. A private checkout's
# commit is never automatically emitted as public source provenance.
subprocess.run(['/usr/bin/git', 'init', '-q', str(checkout)], check=True)
for arguments in (['add', 'Horos.xcodeproj', 'script', 'tools', 'Horos', 'FinderPreview'],
                  ['-c', 'user.name=Test', '-c', 'user.email=test@example.invalid',
                   'commit', '-qm', 'Synthetic Horos source']):
    subprocess.run(['/usr/bin/git', '-C', str(checkout), *arguments], check=True, capture_output=True)
horos_revision = subprocess.check_output(['/usr/bin/git', '-C', str(checkout), 'rev-parse', 'HEAD'], text=True).strip()
(stub / 'git').write_text('#!/bin/sh\ncase " $* " in\n'
                         + '*" ls-remote "*"ThalesMMS/horos.git"*) printf "' + horos_revision + '\trefs/heads/main\n"; exit 0;;\n'
                         + '*" ls-remote "*) printf "' + revision + '\trefs/tags/0.0.0-test\n"; exit 0;; esac\n'
                         + 'exec /usr/bin/git "$@"\n')
local_source = build(good)
report(local_source.returncode == 0, 'a local source build failed')
if local_source.returncode == 0:
    local_metadata = (output / 'BUILD-INFO.txt').read_text()
    report(horos_revision not in local_metadata and 'no public revision is asserted' in local_metadata,
           'private source commit was represented as public source')
public_source = build(good, public_ref='refs/heads/main')
report(public_source.returncode == 0, 'a verified public source mapping failed: '
       + (public_source.stdout + public_source.stderr)[-800:])
if public_source.returncode == 0:
    public_metadata = (output / 'BUILD-INFO.txt').read_text()
    report('verified public revision: ' + horos_revision in public_metadata,
           'the verified public Horos source mapping was not recorded')
pinned_before = state()
entitlements_source = checkout / 'Horos/Horos.entitlements'
entitlements_source.write_bytes(entitlements_source.read_bytes() + b'\n<!-- changed local source -->\n')
rejected('unpublished Horos source', 'do not match', public_ref='refs/heads/main')

# Exercise the missing local repository with real Git and a disposable upstream.
upstream = work / 'submodule-source'
subprocess.run(['/usr/bin/git', 'init', '-q', str(upstream)], check=True)
(upstream / 'source.txt').write_text('pinned source\n')
for arguments in (['add', 'source.txt'], ['-c', 'user.name=Test', '-c', 'user.email=test@example.invalid',
                                       'commit', '-qm', 'Synthetic dependency']):
    subprocess.run(['/usr/bin/git', '-C', str(upstream), *arguments], check=True, capture_output=True)
submodule_revision = subprocess.check_output(['/usr/bin/git', '-C', str(upstream), 'rev-parse', 'HEAD'], text=True).strip()
subprocess.run(['/usr/bin/git', '-C', str(checkout), '-c', 'protocol.file.allow=always',
                'submodule', 'add', '-q', str(upstream), 'SyntheticDependency'], check=True)
dependency_tree = checkout / 'SyntheticDependency'
original_gitfile = (dependency_tree / '.git').read_bytes()
(dependency_tree / 'local-note.txt').write_text('preserve local work\n')
shutil.rmtree(checkout / '.git/modules/SyntheticDependency')
recovered = build(good)
report(recovered.returncode == 0, 'missing submodule metadata did not recover: '
       + (recovered.stdout + recovered.stderr)[-800:])
backups = list((checkout / 'build/recovery').glob('submodules-*/SyntheticDependency'))
report(len(backups) == 1, 'submodule recovery did not preserve exactly one worktree')
if len(backups) == 1:
    report((backups[0] / '.git').read_bytes() == original_gitfile
           and (backups[0] / 'local-note.txt').read_text() == 'preserve local work\n'
           and (backups[0] / 'source.txt').read_bytes() == (upstream / 'source.txt').read_bytes(),
           'submodule recovery changed the preserved worktree')
if recovered.returncode == 0:
    restored_revision = subprocess.check_output(['/usr/bin/git', '-C', str(dependency_tree), 'rev-parse', 'HEAD'], text=True).strip()
    report(restored_revision == submodule_revision, 'submodule recovery selected a different pin')
    repeated = build(good)
    report(repeated.returncode == 0 and list((checkout / 'build/recovery').glob('submodules-*/SyntheticDependency')) == backups,
           'a healthy submodule was not reused on the next build')

shutil.rmtree(checkout / '.git/modules/SyntheticDependency')
subprocess.run(['/usr/bin/git', '-C', str(checkout), 'config', '-f', '.gitmodules',
                'submodule.SyntheticDependency.url', str(work / 'missing-upstream')], check=True)
before_acquisition_failure = state()
acquisition_failure = build(good)
report(acquisition_failure.returncode != 0 and 'fatal:' in acquisition_failure.stderr
       and 'o Xcode não foi iniciado' in acquisition_failure.stderr,
       'a failed submodule acquisition did not report its original error before Xcode')
report(state() == before_acquisition_failure, 'a failed submodule acquisition replaced the previous artifact')

shutil.rmtree(work, ignore_errors=True)
for failure in failures:
    print('FAIL: %s' % failure)
if failures:
    sys.exit(1)
print('ok: build_release.sh writes the app, BUILD-INFO.txt and SHA256SUMS.txt together, which verify and name '
      'no local path; a failed build, an external library and a missing notice leave the previous artifact; '
      'a new one keeps the previous three under one date')
