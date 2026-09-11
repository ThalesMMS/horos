#!/usr/bin/env python3
"""Every prebuilt binary the app ships is audited against the architecture it builds for.

The project builds a single architecture (Config.xcconfig ARCHS). A prebuilt
dependency that lacks it either fails to load, or — for a helper launched as a
process — needs Rosetta on Apple Silicon. Both are silent at build time.
"""
import re, subprocess, sys, zipfile, tempfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
config = (root / 'Config.xcconfig').read_text()
match = re.search(r'^\s*ARCHS\s*=\s*(.+?)\s*$', config, re.M)
if not match:
    print('FAIL: Config.xcconfig no longer declares ARCHS'); sys.exit(1)
target = match.group(1).split()
print('project builds for: %s' % ' '.join(target))

MACHO = (b'\xcf\xfa\xed\xfe', b'\xce\xfa\xed\xfe', b'\xca\xfe\xba\xbe', b'\xbe\xba\xfe\xca')

def archs(path):
    result = subprocess.run(['lipo', '-archs', str(path)], capture_output=True, text=True)
    return result.stdout.split()

def audit(label, path):
    with open(path, 'rb') as handle:
        if handle.read(4) not in MACHO:
            return None
    return (label, archs(path))

found = []
for path in sorted((root / 'Binaries').rglob('*')):
    if path.is_file() and not path.is_symlink() and path.suffix != '.zip':
        entry = audit(str(path.relative_to(root)), path)
        if entry:
            found.append(entry)
# Archived dependencies are unpacked into the bundle at build time.
for archive in sorted((root / 'Binaries').glob('*.zip')):
    with zipfile.ZipFile(archive) as z, tempfile.TemporaryDirectory(prefix='horos-arch-') as folder:
        for name in z.namelist():
            if name.endswith('/'):
                continue
            extracted = Path(z.extract(name, folder))
            if extracted.is_file() and extracted.stat().st_size > 4:
                entry = audit('%s!%s' % (archive.name, name), extracted)
                if entry:
                    found.append(entry)

if not found:
    print('FAIL: no prebuilt binaries were inspected'); sys.exit(1)

missing = [(label, a) for label, a in found if not set(target) & set(a)]
print('inspected %d prebuilt binaries, %d lack every target architecture' % (len(found), len(missing)))
for label, a in missing:
    print('   %-58s %s' % (label, ' '.join(a) or '(none)'))

# Known and accounted for. Anything else is a new problem.
accepted = {
    # Weakly linked with a NULL guard around InstallConnexionHandlers, so the
    # SpaceNavigator feature is absent on this architecture rather than breaking
    # the launch. The linker reports ignoring it.
    '3DconnexionClient': 'weakly linked, guarded, feature absent',
    # Compiled out: every call site sits behind #if defined(USEHOMEPHONE), which
    # this project does not define. The linker reports ignoring it.
    'homephone': 'not referenced, USEHOMEPHONE undefined',
    # Listed in the Decompress target but no symbol from them is referenced, so
    # the link succeeds without them.
    'libmingOsiriX': 'unreferenced', 'libgifOsiriX': 'unreferenced',
    'libfreetypeOsiriX': 'unreferenced', 'libpng12OsiriX': 'unreferenced',
    # Stale payload: the project has no reference to this archive, and the HTTP
    # server builds SSCrypto from source under cocoahttpserver/.
    'SSCrypto': 'archive never unpacked, built from source instead',
}
dciodvfy = [(label, a) for label, a in found if 'dciodvfy' in label]
if not dciodvfy:
    print('FAIL: dciodvfy is no longer shipped in Binaries/')
    sys.exit(1)
if any('arm64' not in a for _, a in dciodvfy):
    print('FAIL: shipped dciodvfy must be arm64, got', dciodvfy)
    sys.exit(1)

unexpected = [m for m in missing if not any(name in m[0] for name in accepted)]
if unexpected:
    print('FAIL: prebuilt binaries without a target architecture and without a documented reason:')
    for label, a in unexpected:
        print(' ', label, a)
    sys.exit(1)

# Each accepted name has to still be present; a rename should fail this test
# rather than silently widen the exemption.
for name in accepted:
    if not any(name in label for label, _ in found):
        print('FAIL: %s is no longer shipped; drop it from the accepted list' % name)
        sys.exit(1)

print('PASS: every prebuilt binary either carries a target architecture or is one of the '
      '%d documented exceptions' % len(accepted))
for name, reason in sorted(accepted.items()):
    print('   %-20s %s' % (name, reason))
