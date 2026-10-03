#!/usr/bin/env python3
"""Audit every executable a built bundle ships (#385 release gate, #979).

Reports, for each Mach-O inside the bundle, the architectures it carries,
whether it is signed, its entitlements, and where each library it loads comes
from; and, for the bundle itself, the minimum system version, the update feed
and the code-signing flags. Reads only; it signs nothing and changes nothing.

Every load command is resolved the way dyld would: @loader_path from the
binary's folder, @executable_path from the executable of its process (the
application's, a helper's own, or an extension's), @rpath through the binary's
LC_RPATH and, for a library, its executable's. A library is one of:

- system:    /usr/lib or /System, provided by the macOS;
- bundle:    a file inside the bundle;
- external:  anything else that exists, such as the build directory or
             /opt/homebrew (the bundle would work only on this Mac);
- missing:   nothing at any of the candidate paths (a weak link is reported
             but tolerated).

An LC_RPATH that points outside the bundle is reported as well.

    python3 tools/audit-release-bundle.py path/to/Isis DICOM Viewer.app [--json OUT] [--strict] [--notices]

With --strict the exit status is 1 when a binary lacks the expected
architecture, is unsigned, loads something external or missing, carries an
outside LC_RPATH, or when `codesign --verify --deep --strict` rejects the
bundle; the reasons are printed. --notices adds the license texts and notices:
LICENSE, COPYING.LESSER, NOTICE, the Splash pages and licenses, and for each
library embedded in Frameworks its record and its bottle's license texts.
"""
import argparse
import json
import os
import plistlib
import re
import subprocess
import sys
from html.parser import HTMLParser
from pathlib import Path

MACHO = (b'\xcf\xfa\xed\xfe', b'\xce\xfa\xed\xfe', b'\xca\xfe\xba\xbe', b'\xbe\xba\xfe\xca')
SYSTEM = ('/usr/lib/', '/System/')
LOADS = ('LC_LOAD_DYLIB', 'LC_LOAD_WEAK_DYLIB', 'LC_REEXPORT_DYLIB', 'LC_LOAD_UPWARD_DYLIB')

def missing_bundle_notices(bundle):
    resources = bundle / 'Contents/Resources'
    required = {'LICENSE', 'COPYING.LESSER', 'NOTICE', 'Splash/about.html',
                'Splash/licenses.html', 'Splash/OpenSSL-LICENSE.txt',
                'Splash/DICOM-Swift-LICENSE.txt', 'Splash/ThirdParty/licenses.html'}
    catalog = Path(__file__).resolve().parents[1] / 'Horos/Sources/LicenseAttribution.swift'
    source = catalog.read_text(encoding='utf-8')
    declaration = re.search(r'requiredThirdPartyResourceNames = \[(.*?)\]', source, re.S)
    if not declaration:
        raise SystemExit('catalog has no required third-party notices')
    required.update('Splash/ThirdParty/' + name for name in re.findall(r'"([^"]+)"', declaration.group(1)))
    index = resources / 'Splash/ThirdParty/licenses.html'
    try:
        index_text = index.read_text(encoding='utf-8')
    except (OSError, UnicodeError):
        index_text = ''
    for link in re.findall(r'href="([^"]+)"', index_text):
        if ':' not in link and not link.startswith('#'):
            required.add('Splash/ThirdParty/' + link)
    missing_notices = []
    for name in sorted(required):
        try:
            if not (resources / name).is_file() or not (resources / name).read_bytes().strip():
                missing_notices.append(name)
        except OSError:
            missing_notices.append(name)
    class LicenseReader(HTMLParser):
        def __init__(self):
            super().__init__()
            self.in_pre = False
            self.text = ''
        def handle_starttag(self, tag, attrs):
            if tag == 'pre': self.in_pre = True
        def handle_endtag(self, tag):
            if tag == 'pre': self.in_pre = False
        def handle_data(self, data):
            if self.in_pre: self.text += data
    for original in re.findall(r'<link rel="license" href="([^"]+)">', index_text):
        page = resources / 'Splash/ThirdParty' / ('Rendered/' + original + '.html')
        try:
            html = page.read_bytes().decode('utf-8')
            encoding = re.search(r'<meta name="license-text-encoding" content="([^"]+)">', html)
            reader = LicenseReader()
            reader.feed(html)
            if not encoding or reader.text.encode(encoding.group(1)) != (index.parent / original).read_bytes():
                missing_notices.append(str(page.relative_to(resources)))
        except (OSError, UnicodeError, LookupError):
            missing_notices.append(str(page.relative_to(resources)))
    embedded_files = sorted(p.name for p in (bundle / 'Contents/Frameworks').glob('*.dylib')
                            if p.is_file() and not p.is_symlink())
    record = resources / 'ExternalLibraries/embedded-libraries.txt'
    recorded = {}
    if record.is_file():
        for line in record.read_text().splitlines():
            fields = line.split()
            if len(fields) >= 5 and not line.startswith('#'):
                for name in fields[4:]:
                    recorded[name] = fields[0]
    elif embedded_files:
        missing_notices.append('ExternalLibraries/embedded-libraries.txt')
    for name in embedded_files:
        bottle = recorded.get(name)
        if bottle is None:
            missing_notices.append('ExternalLibraries: no record of %s' % name)
        elif not any((resources / 'ExternalLibraries' / bottle).glob('*')):
            missing_notices.append('ExternalLibraries/%s (license of %s)' % (bottle, name))
    return missing_notices


parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument('bundle', type=Path)
parser.add_argument('--json', type=Path, default=None)
parser.add_argument('--expect-arch', default='arm64')
parser.add_argument('--channel', choices=('github', 'appstore'))
parser.add_argument('--store-distribution', action='store_true',
                    help='require App Store distribution entitlements and provisioning')
parser.add_argument('--strict', action='store_true',
                    help='exit 1 when the bundle is not self-contained, signed and of the expected architecture')
parser.add_argument('--notices', action='store_true',
                    help='also require the license texts and notices the application ships (#980)')
parser.add_argument('--notices-only', action='store_true',
                    help='check required notices before signing; do not inspect binaries or signatures')
args = parser.parse_args()
if args.store_distribution and args.channel != 'appstore':
    parser.error('--store-distribution requires --channel appstore')
if not (args.bundle / 'Contents').is_dir():
    parser.error('not an application bundle: ' + str(args.bundle))
bundle = args.bundle.resolve()

if args.notices_only:
    missing = missing_bundle_notices(bundle)
    result = {'missingNotices': missing, 'problems': ['the bundle lacks ' + name for name in missing]}
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(result, indent=1) + '\n')
    print(json.dumps(result, indent=1))
    sys.exit(1 if missing else 0)

info = plistlib.loads((bundle / 'Contents/Info.plist').read_bytes())
report = {
    'bundle': str(args.bundle),
    'identifier': info.get('CFBundleIdentifier', ''),
    'version': info.get('CFBundleShortVersionString', ''),
    'minimumSystemVersion': info.get('LSMinimumSystemVersion', ''),
    'updateFeed': info.get('SUFeedURL', ''),
    'automaticChecks': info.get('SUEnableAutomaticChecks', None),
    'binaries': [],
}
main_executable = bundle / 'Contents/MacOS' / info.get('CFBundleExecutable', '')


def archs(path):
    result = subprocess.run(['lipo', '-archs', str(path)], capture_output=True, text=True)
    return result.stdout.split()


def signature(path):
    result = subprocess.run(['codesign', '-dvv', str(path)], capture_output=True, text=True)
    text = result.stdout + result.stderr
    if 'code object is not signed' in text:
        return {'signed': False, 'authority': '', 'flags': '', 'entitlements': []}
    authority = re.search(r'^Authority=(.+)$', text, re.M)
    flags = re.search(r'^CodeDirectory .*flags=(\S+)', text, re.M)
    shown = subprocess.run(['codesign', '-d', '--entitlements', '-', '--xml', str(path)],
                           capture_output=True)
    entitlements = []
    start = shown.stdout.find(b'<?xml')
    if start >= 0:
        try:
            entitlements = sorted(plistlib.loads(shown.stdout[start:]))
        except Exception:
            entitlements = ['(unreadable)']
    return {'signed': True,
            'authority': authority.group(1) if authority else ('adhoc' if 'adhoc' in text else ''),
            'flags': flags.group(1) if flags else '',
            'linkerSigned': 'linker-signed' in text,
            'entitlements': entitlements}


def load_commands(path):
    """(filetype, [(command, name)], [rpath]) of the first architecture."""
    listing = subprocess.run(['otool', '-hvl', '-arch', args.expect_arch, str(path)],
                             capture_output=True, text=True).stdout
    if 'Load command' not in listing:
        listing = subprocess.run(['otool', '-hvl', str(path)], capture_output=True, text=True).stdout
    filetype = None
    header = re.search(r'^MH_\S+\s+\S+\s+\S+\s+0x[0-9a-f]+\s+(\S+)', listing, re.M)
    if header:
        filetype = header.group(1)
    loads, rpaths, command = [], [], None
    for line in listing.splitlines():
        line = line.strip()
        if line.startswith('cmd '):
            command = line.split()[1]
        elif line.startswith('name ') and command in LOADS:
            loads.append((command, line.split()[1]))
        elif line.startswith('path ') and command == 'LC_RPATH':
            rpaths.append(line.split()[1])
    return filetype, loads, rpaths


def executable_folder(path, filetype):
    """The folder @executable_path means for code in `path`."""
    if filetype == 'EXECUTE':
        return path.parent
    for parent in path.parents:
        if parent.suffix in ('.appex', '.app') and parent != bundle:
            return parent / 'Contents/MacOS'
        if parent == bundle:
            break
    return main_executable.parent


def expand(reference, loader_folder, executable_folder_):
    if reference.startswith('@loader_path/'):
        return loader_folder / reference[len('@loader_path/'):]
    if reference.startswith('@executable_path/'):
        return executable_folder_ / reference[len('@executable_path/'):]
    return Path(reference)


def inside(path):
    try:
        Path(os.path.realpath(path)).relative_to(bundle)
        return True
    except ValueError:
        return False


main_rpaths = load_commands(main_executable)[2] if main_executable.is_file() else []


def classify(reference, binary, filetype, rpaths):
    loader = binary.parent
    executable = executable_folder(binary, filetype)
    if reference.startswith(SYSTEM):
        return 'system', reference
    if reference.startswith('@rpath/'):
        tail = reference[len('@rpath/'):]
        # dyld also searches the rpaths of the images that loaded this one;
        # the executable's stand for them.
        searched = list(rpaths) + ([] if filetype == 'EXECUTE' else main_rpaths)
        candidates = []
        for rpath in searched:
            base = expand(rpath, loader, executable if not rpath.startswith('@loader_path') else loader)
            candidates.append(base / tail)
    else:
        candidates = [expand(reference, loader, executable)]
    for candidate in candidates:
        if candidate.exists():
            return ('bundle' if inside(candidate) else 'external'), str(candidate)
    return 'missing', ', '.join(str(c) for c in candidates) or '(no rpath)'


problems = []
for path in sorted(bundle.rglob('*')):
    if not path.is_file() or path.is_symlink():
        continue
    try:
        with path.open('rb') as handle:
            head = handle.read(4)
    except OSError:
        continue
    if head not in MACHO:
        continue
    relative = str(path.relative_to(bundle))
    found = archs(path)
    filetype, loads, rpaths = load_commands(path)
    links = []
    for command, reference in loads:
        kind, where = classify(reference, path, filetype, rpaths)
        weak = command == 'LC_LOAD_WEAK_DYLIB'
        links.append({'name': reference, 'kind': kind, 'resolved': where, 'weak': weak})
        if kind == 'external':
            problems.append('%s loads %s from outside the bundle (%s)' % (relative, reference, where))
        elif kind == 'missing' and not weak:
            problems.append('%s loads %s, which is nowhere in the bundle (%s)' % (relative, reference, where))
    outside_rpaths = [r for r in rpaths if not r.startswith(('@loader_path', '@executable_path'))
                      and not r.startswith(SYSTEM)]
    for rpath in outside_rpaths:
        problems.append('%s searches %s, outside the bundle' % (relative, rpath))
    entry = {
        'path': relative,
        'archs': found,
        'type': filetype,
        'hasExpected': args.expect_arch in found,
        'foreignOnly': bool(found) and args.expect_arch not in found,
        'links': links,
        'rpaths': rpaths,
        **signature(path),
    }
    if not entry['hasExpected']:
        problems.append('%s has no %s (%s)' % (relative, args.expect_arch, ' '.join(found) or 'no slice'))
    if not entry['signed']:
        problems.append('%s is not signed' % relative)
    report['binaries'].append(entry)

# The notices the application must carry (LicenseAttribution's required
# resources) and, for each library embedded loose in Frameworks, its line in the
# record of embedded-external-inputs.py and the license texts of its bottle.
missing_notices = missing_bundle_notices(bundle) if args.notices else []
for name in missing_notices:
    problems.append('the bundle lacks %s' % name)
report['missingNotices'] = missing_notices

verify = subprocess.run(['codesign', '--verify', '--deep', '--strict', str(bundle)],
                        capture_output=True, text=True)
report['signatureValid'] = verify.returncode == 0
if verify.returncode:
    problems.append('codesign --verify --deep --strict: ' + (verify.stderr.strip() or 'failed'))
report['bundleSignature'] = signature(bundle)

if args.channel:
    def entitlement_values(path):
        result = subprocess.run(['codesign', '-d', '--entitlements', ':-', str(path)], capture_output=True)
        start = result.stdout.find(b'<?xml')
        return plistlib.loads(result.stdout[start:]) if start >= 0 else {}

    app_entitlements = entitlement_values(bundle)
    store = args.channel == 'appstore'
    if bool(app_entitlements.get('com.apple.security.app-sandbox')) != store:
        problems.append('the main app sandbox does not match the distribution channel')
    if store:
        for key in ('com.apple.security.network.client', 'com.apple.security.network.server',
                    'com.apple.security.files.user-selected.read-write',
                    'com.apple.security.files.bookmarks.app-scope'):
            if app_entitlements.get(key) is not True:
                problems.append('the store app lacks ' + key)
        for entry in report['binaries']:
            if entry['type'] != 'EXECUTE' or not entry['path'].startswith('Contents/Resources/'):
                continue
            values = entitlement_values(bundle / entry['path'])
            if not values.get('com.apple.security.app-sandbox') or not values.get('com.apple.security.inherit'):
                problems.append(entry['path'] + ' does not inherit the app sandbox')
        with (bundle / 'Contents/Info.plist').open('rb') as source:
            executable = plistlib.load(source)['CFBundleExecutable']
        symbols = subprocess.check_output(['nm', '-g', str(bundle / 'Contents/MacOS' / executable)], text=True)
        for name in ('_OBJC_CLASS_$_HorosUpdateInstaller', '_OBJC_CLASS_$_HorosUpdateFeedClient',
                     'PluginPackageDownload'):
            if name in symbols:
                problems.append('the store executable still contains ' + name)
    if args.store_distribution:
        if not store:
            problems.append('store distribution validation requires the appstore channel')
        for entry in report['binaries'] + [report['bundleSignature']]:
            for key in ('com.apple.security.cs.disable-library-validation', 'com.apple.security.get-task-allow',
                        'com.apple.security.cs.allow-dyld-environment-variables'):
                if key in entry['entitlements']:
                    problems.append('store distribution contains the local entitlement ' + key)
        if report['bundleSignature']['authority'] in ('', 'adhoc'):
            problems.append('store distribution requires a certificate signature')
        if not (bundle / 'Contents/embedded.provisionprofile').is_file():
            problems.append('store distribution requires an embedded provisioning profile')

        # Embedded metadata must agree with the expanded bundle plist.
        layout = subprocess.check_output(['otool', '-l', str(main_executable)], text=True)
        section = re.search(r'sectname __info_plist\s+segname __TEXT.*?size (0x[0-9a-f]+)\s+offset (\d+)',
                            layout, re.S)
        if section:
            size, offset = int(section.group(1), 16), int(section.group(2))
            with main_executable.open('rb') as executable_file:
                executable_file.seek(offset)
                metadata = executable_file.read(size).rstrip(b'\0')
            try:
                embedded_info = plistlib.loads(metadata)
                for key in ('CFBundleIdentifier', 'CFBundleShortVersionString', 'CFBundleVersion'):
                    if embedded_info.get(key) != info.get(key):
                        problems.append('the executable has inconsistent embedded ' + key)
            except Exception:
                problems.append('the executable has an invalid embedded Info.plist')

        for framework in (bundle / 'Contents/Frameworks').glob('*.framework'):
            current = framework / 'Versions/Current'
            if not current.is_dir():
                continue
            framework_info = plistlib.loads((current / 'Resources/Info.plist').read_bytes())
            name = framework_info.get('CFBundleExecutable')
            if name:
                link = framework / name
                if not link.is_symlink() or os.readlink(link) != 'Versions/Current/' + name:
                    problems.append(framework.name + ' lacks the canonical executable symlink')

        # Resource bundles may remain unsigned, but a retained development
        # signature is not a distribution signature and is rejected by Apple.
        for resource in (bundle / 'Contents/Resources').rglob('*.bundle'):
            resource_info = resource / 'Contents/Info.plist'
            if not resource_info.is_file():
                continue
            if plistlib.loads(resource_info.read_bytes()).get('CFBundleExecutable'):
                continue
            resource_signature = signature(resource)
            if (resource_signature['signed'] and
                    resource_signature['authority'] != report['bundleSignature']['authority']):
                problems.append(resource.name + ' retains a different signing authority')
    report['channel'] = args.channel

report['binaryCount'] = len(report['binaries'])
report['withExpectedArch'] = sum(item['hasExpected'] for item in report['binaries'])
report['foreignOnly'] = [item['path'] for item in report['binaries'] if item['foreignOnly']]
report['unsigned'] = [item['path'] for item in report['binaries'] if not item['signed']]
report['architectures'] = sorted({arch for item in report['binaries'] for arch in item['archs']})
report['external'] = sorted({'%s -> %s' % (item['path'], link['name'])
                             for item in report['binaries'] for link in item['links']
                             if link['kind'] == 'external'})
report['missing'] = sorted({'%s -> %s' % (item['path'], link['name'])
                            for item in report['binaries'] for link in item['links']
                            if link['kind'] == 'missing'})
report['embeddedLibraries'] = sorted({os.path.relpath(link['resolved'], bundle)
                                      for item in report['binaries'] for link in item['links']
                                      if link['kind'] == 'bundle' and link['resolved'].endswith('.dylib')})
report['problems'] = problems

if args.json:
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(report, indent=1) + '\n')
print(json.dumps({k: v for k, v in report.items() if k not in ('binaries', 'bundleSignature')}, indent=1))
if args.notices and missing_notices and not args.strict:
    sys.exit(1)
if args.strict and problems:
    print('FAIL: the bundle is not self-contained, signed and %s:' % args.expect_arch, file=sys.stderr)
    for problem in problems:
        print('  ' + problem, file=sys.stderr)
    sys.exit(1)
