#!/usr/bin/env python3
"""License texts, credits and bundle notices stay complete and are not a blind origin replace."""
from pathlib import Path
import hashlib
import json
import os
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
snap = root / 'docs/third-party/donor-horos-23722fb552d96fa2d60c7f58a6d4ac2c27950f86'
# The donor checkout is a read-only reference that no clone provides. Point
# HOROS_DONOR_CHECKOUT at it to run the byte-for-byte comparison; without it
# the snapshot is still checked against its pinned hashes.
_donor = os.environ.get('HOROS_DONOR_CHECKOUT')
origin = Path(_donor).expanduser() if _donor else None
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
    fail('MANIFEST revision is not the documented donor SHA')
if sha256(snap / 'LICENSE') != origin_license_sha:
    fail('snapshotted LICENSE hash drifted')
if sha256(snap / 'COPYING.LESSER') != origin_copying_sha:
    fail('snapshotted COPYING.LESSER hash drifted')
if sha256(root / 'COPYING.LESSER') != origin_copying_sha:
    fail('root COPYING.LESSER no longer matches the origin snapshot')

if origin is not None and origin.is_dir():
    # The origin is a read-only reference whose working tree may sit on any
    # revision: the Delta-3 phase reads three later commits from the same clone.
    # Compare the snapshot with the blobs of the pinned revision, which is what
    # it claims to be a copy of, instead of with whatever HEAD happens to be.
    try:
        subprocess.run(['git', '-C', str(origin), 'cat-file', '-e', revision + '^{commit}'],
                       check=True, capture_output=True)
    except subprocess.CalledProcessError:
        fail('the donor checkout does not contain the snapshotted revision %s' % revision)
    for name in ('LICENSE', 'COPYING.LESSER'):
        blob = subprocess.run(['git', '-C', str(origin), 'show', '%s:%s' % (revision, name)],
                              check=True, capture_output=True).stdout
        if blob != (snap / name).read_bytes():
            fail('snapshot %s is not a byte-for-byte copy of %s at %s' % (name, name, revision[:12]))
        # The later revisions this phase adopts must not have changed the terms
        # without the snapshot being renewed.
        for adopted in ('8a37f4b3a46832ce0c0343f35ec57ece78235a47',
                        '8be8b977f8574877118cf9e6b3470baf7bf7ba2f',
                        'e2acd36ed1f25ea94f0b6e5cfc7359fd95e262d9'):
            present = subprocess.run(['git', '-C', str(origin), 'cat-file', '-e', adopted + '^{commit}'],
                                     capture_output=True)
            if present.returncode != 0:
                continue
            later = subprocess.run(['git', '-C', str(origin), 'show', '%s:%s' % (adopted, name)],
                                   check=True, capture_output=True).stdout
            if later != blob:
                fail('%s changed between %s and %s; renew the snapshot before adopting it'
                     % (name, revision[:12], adopted[:12]))

workbench_license = (root / 'LICENSE').read_text(encoding='utf-8')
origin_license = (snap / 'LICENSE').read_text(encoding='utf-8')
if workbench_license == origin_license:
    fail('root LICENSE is a blind replacement of the origin file')
if 'Purview' not in workbench_license or 'HorosCloud' not in workbench_license:
    fail('root LICENSE dropped the Purview/HorosCloud notice')
if 'Yves Starreveld' not in workbench_license:
    fail('root LICENSE does not credit Yves Starreveld')
# Nothing links Grok since #617: LICENSE and NOTICE must not say it does.
if 'Grok' in workbench_license:
    fail('root LICENSE still says Horos is linked against Grok')
if 'Lesser General Public License' not in workbench_license:
    fail('root LICENSE dropped the Horos LGPLv3 terms')

notice = (root / 'NOTICE').read_text(encoding='utf-8')
readme = (root / 'README.md').read_text(encoding='utf-8')
about = (root / 'Binaries/Splash/about.html').read_text(encoding='utf-8')
licenses_html = (root / 'Binaries/Splash/licenses.html').read_text(encoding='utf-8')
for text, label in ((notice, 'NOTICE'), (readme, 'README.md'), (about, 'about.html'),
                    (licenses_html, 'licenses.html')):
    if 'Yves Starreveld' not in text:
        fail('%s does not credit Yves Starreveld' % label)
    if 'OsiriX' not in text:
        fail('%s dropped OsiriX credit' % label)

if 'HorosCloud' not in notice or 'Do not import that removal' not in notice and 'not imported' not in notice:
    if 'not imported' not in notice.lower() and 'not import' not in notice:
        fail('NOTICE does not keep the HorosCloud/Purview disposition')
if 'Grok' in notice:
    fail('NOTICE still lists Grok')
if 'Do not treat the tree as uniformly LGPL' not in notice:
    fail('NOTICE no longer says the tree is not uniformly LGPL')
if 'ONNX' not in notice:
    fail('NOTICE does not record that model weights were not imported')

code = r'''
import Foundation

precondition(LicenseAttribution.donorRevision == "23722fb552d96fa2d60c7f58a6d4ac2c27950f86")
precondition(LicenseAttribution.donorAuthor == "Yves Starreveld")
precondition(LicenseAttribution.catalogID == "L368")
precondition(LicenseAttribution.originLicenseSHA256 == "d885acd3300b5464fe5e6774610b35fb2d83192f272be3325d69b89d2d666f38")
precondition(LicenseAttribution.originCopyingLesserSHA256 == "c9f740e3eddbb3a01de0d3924a9afd17782567e20c28e55d0e2436376b5c9000")
precondition(!LicenseAttribution.treatsAllComponentsAsLGPL())

let components = LicenseAttribution.components()
let ids = Set(components.map(\.identifier))
for needed in ["horos", "osirix", "donor", "dcmtk", "itk", "vtk", "gdcm",
               "openjpeg", "openssl", "charls", "horoscloud", "weights"] {
    precondition(ids.contains(needed), "missing \(needed)")
}

precondition(!ids.contains("grok"), "Grok is listed, but nothing links it since #617")
let openssl = components.first { $0.identifier == "openssl" }!
precondition(openssl.license == "Apache-2.0")
precondition(openssl.sourcePath == "OpenSSL/upstream/LICENSE.txt")

let donor = components.first { $0.identifier == "donor" }!
precondition(donor.incorporated)
precondition(donor.origin == "adapted-source")
precondition(donor.name.contains("Yves Starreveld"))

let cloud = components.first { $0.identifier == "horoscloud" }!
precondition(cloud.incorporated)
precondition(cloud.origin == "local-workbench")

let weights = components.first { $0.identifier == "weights" }!
precondition(!weights.incorporated)

precondition(LicenseAttribution.preservesPurviewNotice(in: workbenchLicense))
precondition(LicenseAttribution.creditsDonor(in: workbenchLicense))
precondition(!LicenseAttribution.isBlindOriginReplacement(originLicense: originLicense,
                                                        workbenchLicense: workbenchLicense))
precondition(LicenseAttribution.creditsDonor(in: LicenseAttribution.aboutCreditsHTML()))
precondition(LicenseAttribution.aboutCreditsHTML().contains("AGPLv3"))
precondition(LicenseAttribution.materialQuestions().count >= 3)

let package = URL(fileURLWithPath: packageRoot)
precondition(LicenseAttribution.missingNotices(inDirectory: package).isEmpty)

let incomplete = URL(fileURLWithPath: incompleteRoot)
precondition(LicenseAttribution.missingNotices(inDirectory: incomplete).contains("NOTICE"))
precondition(LicenseAttribution.missingNotices(inDirectory: incomplete).contains("Splash/licenses.html"))
precondition(LicenseAttribution.missingNotices(inDirectory: incomplete).contains("Splash/OpenSSL-LICENSE.txt"))

print("PASS: license catalog, Purview, donor credit, AGPL split, bundle notices")
'''

with tempfile.TemporaryDirectory(prefix='horos-license-') as d:
    package = Path(d) / 'Resources'
    (package / 'Splash').mkdir(parents=True)
    for name in ('LICENSE', 'COPYING.LESSER', 'NOTICE'):
        (package / name).write_bytes((root / name).read_bytes())
    (package / 'Splash/about.html').write_bytes((root / 'Binaries/Splash/about.html').read_bytes())
    (package / 'Splash/licenses.html').write_bytes((root / 'Binaries/Splash/licenses.html').read_bytes())
    (package / 'Splash/OpenSSL-LICENSE.txt').write_bytes((root / 'Binaries/Splash/OpenSSL-LICENSE.txt').read_bytes())
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
