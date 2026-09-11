#!/usr/bin/env python3
"""License texts, credits and bundle notices stay complete and are not a blind origin replace."""
from pathlib import Path
import hashlib
import json
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
snap = root / 'docs/third-party/ystarrev-horos-23722fb552d96fa2d60c7f58a6d4ac2c27950f86'
origin = root.parent / 'ystarrev/horos'
revision = '23722fb552d96fa2d60c7f58a6d4ac2c27950f86'
origin_license_sha = 'd885acd3300b5464fe5e6774610b35fb2d83192f272be3325d69b89d2d666f38'
origin_copying_sha = 'c9f740e3eddbb3a01de0d3924a9afd17782567e20c28e55d0e2436376b5c9000'


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fail(message):
    print('FAIL:', message, file=sys.stderr)
    sys.exit(1)


manifest = json.loads((snap / 'MANIFEST.json').read_text())
if manifest['revision'] != revision:
    fail('MANIFEST revision is not the documented ystarrev SHA')
if sha256(snap / 'LICENSE') != origin_license_sha:
    fail('snapshotted LICENSE hash drifted')
if sha256(snap / 'COPYING.LESSER') != origin_copying_sha:
    fail('snapshotted COPYING.LESSER hash drifted')
if sha256(root / 'COPYING.LESSER') != origin_copying_sha:
    fail('root COPYING.LESSER no longer matches the origin snapshot')

if origin.is_dir():
    if (origin / 'LICENSE').read_bytes() != (snap / 'LICENSE').read_bytes():
        fail('snapshot LICENSE is not a byte-for-byte copy of ../ystarrev/horos/LICENSE')
    if (origin / 'COPYING.LESSER').read_bytes() != (snap / 'COPYING.LESSER').read_bytes():
        fail('snapshot COPYING.LESSER is not a byte-for-byte copy of the origin file')
    head = subprocess.check_output(['git', '-C', str(origin), 'rev-parse', 'HEAD'], text=True).strip()
    if head != revision:
        fail('ystarrev/horos HEAD is %s, snapshot is %s' % (head, revision))

workbench_license = (root / 'LICENSE').read_text(encoding='utf-8')
origin_license = (snap / 'LICENSE').read_text(encoding='utf-8')
if workbench_license == origin_license:
    fail('root LICENSE is a blind replacement of the origin file')
if 'Purview' not in workbench_license or 'HorosCloud' not in workbench_license:
    fail('root LICENSE dropped the Purview/HorosCloud notice')
if 'Yves Starreveld' not in workbench_license or 'ystarrev/horos' not in workbench_license:
    fail('root LICENSE does not credit ystarrev/horos and Yves Starreveld')
if 'GNU Affero General Public License' not in workbench_license:
    fail('root LICENSE dropped the Grok AGPLv3 notice')
if 'Lesser General Public License' not in workbench_license:
    fail('root LICENSE dropped the Horos LGPLv3 terms')

notice = (root / 'NOTICE').read_text(encoding='utf-8')
readme = (root / 'README.md').read_text(encoding='utf-8')
about = (root / 'Binaries/Splash/about.html').read_text(encoding='utf-8')
licenses_html = (root / 'Binaries/Splash/licenses.html').read_text(encoding='utf-8')
for text, label in ((notice, 'NOTICE'), (readme, 'README.md'), (about, 'about.html'),
                    (licenses_html, 'licenses.html')):
    if 'Yves Starreveld' not in text or 'ystarrev/horos' not in text:
        fail('%s does not credit ystarrev/horos and Yves Starreveld' % label)
    if 'OsiriX' not in text:
        fail('%s dropped OsiriX credit' % label)

if 'HorosCloud' not in notice or 'Do not import that removal' not in notice and 'not imported' not in notice:
    if 'not imported' not in notice.lower() and 'not import' not in notice:
        fail('NOTICE does not keep the HorosCloud/Purview disposition')
if 'AGPLv3' not in notice or 'not LGPL' not in notice:
    fail('NOTICE does not flag Grok AGPLv3 as distinct from LGPL')
if 'ONNX' not in notice:
    fail('NOTICE does not record that model weights were not imported')

code = r'''
import Foundation

precondition(LicenseAttribution.ystarrevRevision == "23722fb552d96fa2d60c7f58a6d4ac2c27950f86")
precondition(LicenseAttribution.ystarrevRepository == "ystarrev/horos")
precondition(LicenseAttribution.ystarrevAuthor == "Yves Starreveld")
precondition(LicenseAttribution.catalogID == "L368")
precondition(LicenseAttribution.originLicenseSHA256 == "d885acd3300b5464fe5e6774610b35fb2d83192f272be3325d69b89d2d666f38")
precondition(LicenseAttribution.originCopyingLesserSHA256 == "c9f740e3eddbb3a01de0d3924a9afd17782567e20c28e55d0e2436376b5c9000")
precondition(!LicenseAttribution.treatsAllComponentsAsLGPL())

let components = LicenseAttribution.components()
let ids = Set(components.map(\.identifier))
for needed in ["horos", "osirix", "ystarrev", "grok", "dcmtk", "itk", "vtk", "gdcm",
               "openjpeg", "openssl", "charls", "horoscloud", "weights"] {
    precondition(ids.contains(needed), "missing \(needed)")
}

let grok = components.first { $0.identifier == "grok" }!
precondition(grok.license == "AGPLv3")
precondition(grok.incorporated)
precondition(grok.license != "LGPLv3")

let ystarrev = components.first { $0.identifier == "ystarrev" }!
precondition(ystarrev.incorporated)
precondition(ystarrev.origin == "adapted-source")
precondition(ystarrev.name.contains("Yves Starreveld"))

let cloud = components.first { $0.identifier == "horoscloud" }!
precondition(cloud.incorporated)
precondition(cloud.origin == "local-workbench")

let weights = components.first { $0.identifier == "weights" }!
precondition(!weights.incorporated)

precondition(LicenseAttribution.preservesPurviewNotice(in: workbenchLicense))
precondition(LicenseAttribution.creditsYstarrev(in: workbenchLicense))
precondition(!LicenseAttribution.isBlindOriginReplacement(originLicense: originLicense,
                                                        workbenchLicense: workbenchLicense))
precondition(LicenseAttribution.creditsYstarrev(in: LicenseAttribution.aboutCreditsHTML()))
precondition(LicenseAttribution.aboutCreditsHTML().contains("AGPLv3"))
precondition(LicenseAttribution.materialQuestions().count >= 3)

let package = URL(fileURLWithPath: packageRoot)
precondition(LicenseAttribution.missingNotices(inDirectory: package).isEmpty)

let incomplete = URL(fileURLWithPath: incompleteRoot)
precondition(LicenseAttribution.missingNotices(inDirectory: incomplete).contains("NOTICE"))
precondition(LicenseAttribution.missingNotices(inDirectory: incomplete).contains("Splash/licenses.html"))

print("PASS: license catalog, Purview, ystarrev credit, AGPL split, bundle notices")
'''

with tempfile.TemporaryDirectory(prefix='horos-license-') as d:
    package = Path(d) / 'Resources'
    (package / 'Splash').mkdir(parents=True)
    for name in ('LICENSE', 'COPYING.LESSER', 'NOTICE'):
        (package / name).write_bytes((root / name).read_bytes())
    (package / 'Splash/about.html').write_bytes((root / 'Binaries/Splash/about.html').read_bytes())
    (package / 'Splash/licenses.html').write_bytes((root / 'Binaries/Splash/licenses.html').read_bytes())
    incomplete = Path(d) / 'Incomplete'
    (incomplete / 'Splash').mkdir(parents=True)
    (incomplete / 'LICENSE').write_bytes((root / 'LICENSE').read_bytes())
    (incomplete / 'COPYING.LESSER').write_bytes((root / 'COPYING.LESSER').read_bytes())
    (incomplete / 'Splash/about.html').write_bytes((root / 'Binaries/Splash/about.html').read_bytes())

    swift = Path(d) / 'main.swift'
    swift.write_text(
        'let workbenchLicense = """\n%s\n"""\n'
        'let originLicense = """\n%s\n"""\n'
        'let packageRoot = "%s"\n'
        'let incompleteRoot = "%s"\n'
        '%s' % (
            workbench_license.replace('\\', '\\\\'),
            origin_license.replace('\\', '\\\\'),
            str(package),
            str(incomplete),
            code,
        )
    )
    subprocess.run([
        'xcrun', 'swiftc',
        str(root / 'Horos/Sources/LicenseAttribution.swift'),
        str(swift), '-o', str(Path(d) / 'test'),
    ], check=True)
    subprocess.run([str(Path(d) / 'test')], check=True)

print('PASS: origin snapshots, consolidated LICENSE, credits, catalog L368')
