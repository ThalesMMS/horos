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

for name in ('Horos Project', 'OsiriX', 'Yves Starreveld', 'ystarrev/horos',
             'Grok', 'AGPLv3', 'Horos Cloud', 'DCMTK', 'ITK', 'VTK'):
    if name not in licenses:
        fail('licenses.html is missing ' + name)

if 'DICOMweb' not in notice:
    fail('NOTICE dropped the DICOMweb preservation note')
if 'docs/license-attribution.md' not in readme:
    fail('README.md does not point at the attribution document')
if 'L368' not in docs:
    fail('docs/license-attribution.md is missing catalog ID L368')
if 'test-license-attribution.py' not in docs:
    fail('docs/license-attribution.md does not point at the tests for #367/#385')
if 'Yves Starreveld' not in xcconfig:
    fail('HUMAN_READABLE_COPYRIGHT no longer credits ystarrev')
if 'L368' not in catalog:
    fail('host localization catalog contract does not point at L368')

# The origin removal of HorosCloud must not appear as an instruction to delete it.
if 'remove HorosCloud' in notice.lower() or 'delete HorosCloud' in notice.lower():
    fail('NOTICE tells the reader to remove HorosCloud')

print('PASS: About path, pbx resources, README/NOTICE/docs catalog L368')
