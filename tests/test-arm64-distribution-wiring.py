#!/usr/bin/env python3
"""arm64-only publication is declared, plugins are diagnosed before load, helpers are not Rosetta."""
from pathlib import Path
import sys

root = Path(__file__).resolve().parents[1]
failures = []


def check(condition, message):
    if not condition:
        failures.append(message)


def body(path, signature):
    source = path.read_bytes().decode('latin1')
    at = 0
    while True:
        at = source.find(signature, at)
        if at < 0:
            return ''
        brace = source.find('{', at)
        semi = source.find(';', at)
        if brace >= 0 and (semi < 0 or brace < semi):
            break
        at += len(signature)
    depth, index = 0, brace
    while index < len(source):
        if source[index] == '{':
            depth += 1
        elif source[index] == '}':
            depth -= 1
            if depth == 0:
                return source[brace:index + 1]
        index += 1
    return ''


config = (root / 'Config.xcconfig').read_text(encoding='utf-8')
swift = (root / 'Horos/Sources/HorosArchitectureAudit.swift').read_text(encoding='utf-8')
pbx = (root / 'Horos.xcodeproj/project.pbxproj').read_text(encoding='utf-8')
manager = root / 'Horos/Sources/PluginManager.m'
xml = root / 'Horos/Sources/XMLController.m'
nitrogen = (root / 'Nitrogen/Nitrogen.xcodeproj/project.pbxproj').read_text(encoding='utf-8')

check('ARCHS = arm64' in config, 'Config.xcconfig must keep ARCHS = arm64')
check('EXCLUDED_ARCHS[sdk=macosx*] = x86_64 i386 ppc ppc64' in config,
      'Config.xcconfig must exclude Intel and PowerPC slices')
check('arm64 or x86_64' not in config, 'Config.xcconfig must not promise an Intel product')
check('Apple Silicon only' in config or 'arm64-only' in config.lower() or 'Apple Silicon' in config,
      'Config.xcconfig must say the product is Apple Silicon')
check('MACOSX_DEPLOYMENT_TARGET = 26.0' in config,
      'deployment target must match the macOS 26 minimum owned by #369')
check('DEVELOPMENT_TEAM = TPT6TVH8UY' not in config,
      'do not copy ystarrev DEVELOPMENT_TEAM')

check('@objc(HorosArchitectureAudit)' in swift, 'Swift auditor must stay @objc')
check('pluginDiagnosisAtPath:' in swift, 'plugins are diagnosed by path')
check('helperDiagnosisAtPath:' in swift, 'helpers are diagnosed by path')
check('not launched under Rosetta' in swift, 'Intel helpers must not use Rosetta as the product path')
check('HorosArchitectureAudit.swift in Sources' in pbx, 'auditor must be in the Horos target')

load = body(manager, '+ (void) loadPluginBundle:(NSString*) path\n')
check('pluginDiagnosisAtPath' in load, 'loadPluginBundle must consult HorosArchitectureAudit before NSBundle')
bundle_at = load.find('bundleWithPath')
diag_at = load.find('pluginDiagnosisAtPath')
check(diag_at >= 0 and (bundle_at < 0 or diag_at < bundle_at),
      'Intel-only plugins must be named before NSBundle opens them')
check('Incompatible' in load, 'Intel-only plugins remain Incompatible, not silently skipped')

install = body(manager, '+ (void) installPluginFromPath: (NSString*) path\n')
check('pluginDiagnosisAtPath' in install, 'install must refuse Intel-only plugins before touching the install')
preflight_at = install.find('preflightAndReturnError')
install_diag = install.find('pluginDiagnosisAtPath')
check(install_diag >= 0 and (preflight_at < 0 or install_diag < preflight_at),
      'install must diagnose architecture before NSBundle preflight')

verify = body(xml, '- (IBAction) verify:(id) sender\n')
check('helperDiagnosisAtPath' in verify, 'DICOM validator must consult helperDiagnosis before launch')
task_at = verify.find('HorosRunBoundedTask')
help_at = verify.find('helperDiagnosisAtPath')
check(help_at >= 0 and (task_at < 0 or help_at < task_at),
      'do not launch an Intel leftover under Rosetta; diagnose first')
check('dciodvfy' in verify, 'the validator command must remain; do not delete it to pass the audit')

import re
nitrogen_archs = re.findall(r'ARCHS = \((.*?)\);', nitrogen, re.S)
check(nitrogen_archs, 'Nitrogen leftover project must still declare ARCHS')
for block in nitrogen_archs:
    check('x86_64' not in block and 'i386' not in block and 'ppc' not in block,
          'Nitrogen leftover project must not publish Intel or PowerPC')
    check('arm64' in block, 'Nitrogen leftover project follows the arm64 product')

if failures:
    for item in failures:
        print('FAIL:', item, file=sys.stderr)
    sys.exit(1)
print('PASS: arm64-only Config, plugin diagnosis before load, validator command kept')
