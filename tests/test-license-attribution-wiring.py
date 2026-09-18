#!/usr/bin/env python3
"""License catalog is in the app target and the About path loads bundled notices."""
from pathlib import Path
import sys

root = Path(__file__).resolve().parents[1]
pbx = (root / 'Horos.xcodeproj/project.pbxproj').read_text(encoding='utf-8')
splash = (root / 'Horos/Sources/SplashScreen.m').read_text(encoding='latin1')
about = (root / 'Binaries/Splash/about.html').read_text(encoding='utf-8')
licenses = (root / 'Binaries/Splash/licenses.html').read_text(encoding='utf-8')
readme = (root / 'README.md').read_text(encoding='utf-8')
notice = (root / 'NOTICE').read_text(encoding='utf-8')
docs = (root / 'docs/license-attribution.md').read_text(encoding='utf-8')
xcconfig = (root / 'Horos/Horos.xcconfig').read_text(encoding='utf-8')
catalog = (root / 'docs/host-localization-catalog-contract.md').read_text(encoding='utf-8')


def fail(message):
    print('FAIL:', message, file=sys.stderr)
    sys.exit(1)


needed_pbx = [
    'LicenseAttribution.swift in Sources',
    'NOTICE in Resources',
    'LICENSE in Resources',
    'COPYING.LESSER in Resources',
    'Splash in Resources',
]
missing = [item for item in needed_pbx if item not in pbx]
if missing:
    fail('pbxproj is missing ' + ', '.join(missing))

if 'Horos-Swift.h' not in splash:
    fail('SplashScreen.m does not import Horos-Swift.h')
if 'HorosLicenseAttribution missingNoticesIn:' not in splash:
    fail('SplashScreen.m does not consult HorosLicenseAttribution for bundled notices')
if 'Splash/about.html' not in splash:
    fail('SplashScreen.m no longer loads Splash/about.html')
if 'licenses.html' not in about:
    fail('about.html does not link to licenses.html')
if 'OpenSSL-LICENSE.txt' not in licenses:
    fail('licenses.html does not link to the bundled OpenSSL license')
if (root / 'Binaries/Splash/OpenSSL-LICENSE.txt').read_bytes() != (root / 'OpenSSL/upstream/LICENSE.txt').read_bytes():
    fail('the bundled OpenSSL license differs from the pinned upstream text')

for name in ('Horos Project', 'OsiriX', 'Yves Starreveld',
             'Horos Cloud', 'DCMTK', 'ITK', 'VTK', 'OpenJPEG', 'CharLS'):
    if name not in licenses:
        fail('licenses.html is missing ' + name)
for text, label in ((licenses, 'licenses.html'), (about, 'about.html')):
    if 'Grok' in text:
        fail(label + ' still credits Grok, which nothing links since #617')

if 'DICOMweb' not in notice:
    fail('NOTICE dropped the DICOMweb preservation note')
if 'Yves Starreveld' not in readme:
    fail('README.md no longer credits the donor author')
if 'L368' not in docs:
    fail('docs/license-attribution.md is missing catalog ID L368')
if 'test-license-attribution.py' not in docs:
    fail('docs/license-attribution.md does not point at the tests for #367/#385')
if 'Yves Starreveld' not in xcconfig:
    fail('HUMAN_READABLE_COPYRIGHT no longer credits the donor author')
if 'L368' not in catalog:
    fail('host localization catalog contract does not point at L368')

# The origin removal of HorosCloud must not appear as an instruction to delete it.
if 'remove HorosCloud' in notice.lower() or 'delete HorosCloud' in notice.lower():
    fail('NOTICE tells the reader to remove HorosCloud')

print('PASS: About path, pbx resources, README/NOTICE/docs catalog L368')
