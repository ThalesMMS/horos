#!/usr/bin/env python3
"""The manifest of this adoption phase, for a later incorporation (#610).

Writes `docs/donor-delta3-manifest.json`: which origin commits were read,
which workbench commits carry the adoption, what each delivery decided, and
which tests and documents stand behind it. Nothing is pushed anywhere - this
records what would be offered, and to whom, if somebody later asks for it.

    python3 tools/write-delta3-manifest.py [--check]

`--check` regenerates into memory and fails when the file on disk differs, so
the manifest cannot drift from the repository it describes.
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument('--check', action='store_true')
arguments = parser.parse_args()

ORIGIN_COMMITS = [
    ('8a37f4b3a46832ce0c0343f35ec57ece78235a47', 'APIs, caches, progressive retrieval, navigation, drag export'),
    ('8be8b977f8574877118cf9e6b3470baf7bf7ba2f', 'Bonjour browsing, ROIs in context, recoverable slice failures'),
    ('e2acd36ed1f25ea94f0b6e5cfc7359fd95e262d9', 'Bonjour/transport, Metal 4, preview windowing, planar print'),
]
BASELINE = '23722fb552d96fa2d60c7f58a6d4ac2c27950f86'
GATE = 'afc2ab2db'

DELIVERIES = [
    ('603', 'file revision as the cache key', 'adapted',
     ['Horos/Sources/FileRevision.swift', 'Horos/Sources/DCMPix.h', 'Horos/Sources/DCMPix.m'],
     ['tests/test-file-revision.py', 'tests/test-dcmpix-parsed-file-cache.py'],
     'docs/issue-603-cache-invalidation-map.md'),
    ('604', 'progressive retrieve and view', 'adapted',
     ['Horos/Sources/RetrieveViewing.swift', 'Horos/Sources/QueryController.mm'],
     ['tests/test-retrieve-viewing.py', 'tests/test-retrieve-viewing-wiring.py',
      'tests/test-unreadable-slice-navigation.py'],
     'docs/issue-604-progressive-retrieve.md'),
    ('605', 'batch drag export', 'adapted',
     ['Horos/Sources/DatabaseDragExport.swift', 'Horos/Sources/BrowserController.m'],
     ['tests/test-database-drag-export.py', 'tests/test-database-drag-export-wiring.py',
      'tests/test-non-pixel-import-triage.py'],
     'docs/issue-605-batch-drag-export.md'),
    ('606', 'native Bonjour discovery and publication', 'adapted',
     ['Horos/Sources/BonjourDiscovery.swift', 'Horos/Sources/BonjourPublisher.m'],
     ['tests/test-bonjour-discovery.py', 'tests/test-bonjour-discovery-wiring.py'],
     'docs/issue-606-native-bonjour.md'),
    ('607', 'shared-database client on NWConnection', 'adapted',
     ['Horos/Sources/DatabaseTransport.swift', 'Horos/Sources/RemoteDicomDatabase.mm'],
     ['tests/test-database-transport.py', 'tests/test-shared-database-client-wiring.py'],
     'docs/issue-607-shared-database-client.md'),
    ('608', 'preview window sources and shared decode', 'adapted',
     ['Horos/Sources/PreviewWindowing.swift', 'Horos/Sources/PreviewView.h',
      'Horos/Sources/PreviewView.m', 'Horos/Sources/BrowserController.m'],
     ['tests/test-preview-window-policy.py', 'tests/test-preview-windowing-wiring.py'],
     'docs/issue-608-preview-windowing.md'),
    ('609', 'Metal 4 planar submission pilot', 'measured: keep opt-in, not adopted by default',
     ['Horos/Sources/PlanarMetal4Renderer.swift', 'Horos/Sources/PlanarHostRenderer.swift'],
     ['tests/test-planar-metal4-pilot.py', 'tests/test-planar-backend-selection.py'],
     'docs/issue-609-planar-metal4-pilot.md'),
    ('610', 'integration, planar print, provenance and rollback', 'evidence, plus three residues fixed',
     ['Horos/Sources/QueryController.mm', 'Horos/Sources/PreviewWindowing.swift',
      'Horos/Sources/PreviewView.m'],
     ['tests/test-planar-print-responder.py', 'tests/test-retrieve-viewing-wiring.py'],
     'docs/issue-610-delta3-integration.md'),
]

EXCLUDED = [
    ('macOS 27 deployment target', 'the workbench stays on 26.0; every API used is available there'),
    ('retired database accessors and the DCMTK bridge loader', 'public API consumed by plugins'),
    ('vendored SBJSON, N2UserDefaults, NSWindow+N2 removals', 'nothing is removed to simplify a build or a test'),
    ('global inertial scrolling', 'changes clinical behaviour; a wheel is not an acceptance condition'),
    ('3D volume quality toggle and artefact fix', 'belongs to a Metal viewer tree this workbench does not have'),
    ('MetalViewerLauncher, SwiftDICOMReader, MetalStudyROI, HorosPhoneVolumeExporter',
     'parallel loaders, caches and viewers, which #602 forbids'),
    ('origin Scripts/test_*.py', 'the local suite covers the same contracts with its own fixtures'),
]
CONDITIONAL = [
    ('Metal 4 for MPR, volume rendering, registration, surface picking, shared volume preparation, CPU readback',
     'later candidates conditioned on a profile; #609 measured the planar path and found no gain'),
]


def revision(spec):
    try:
        return subprocess.check_output(['git', '-C', str(root), 'rev-parse', spec], text=True).strip()
    except subprocess.CalledProcessError:
        return ''


def commit_for(issue):
    """The commit that introduced a delivery: the oldest one naming the issue.

    Newest-first would move every time a later commit mentions the same issue -
    a documentation follow-up, for instance - and the manifest would never
    match the tree it describes.
    """
    try:
        history = subprocess.check_output(
            ['git', '-C', str(root), 'log', '--format=%H %s', '%s..HEAD' % GATE], text=True)
    except subprocess.CalledProcessError:
        return ''
    matches = [entry.split()[0] for entry in history.splitlines() if ('(#%s)' % issue) in entry]
    return matches[-1] if matches else''


manifest = {
    'phase': 'donor delta 3',
    'purpose': 'record what was adopted, for a possible later incorporation into ThalesMMS/horos',
    'published': False,
    'origin': {
        'repository': 'donor fork of Horos (credited in NOTICE)',
        'baseline': BASELINE,
        'commits': [{'sha': sha, 'subject': subject} for sha, subject in ORIGIN_COMMITS],
    },
    'workbench': {
        'repository': 'ThalesMMS/horos-workbench',
        'branch': 'issues',
        # The gate and the per-delivery commits identify the phase. HEAD does
        # not belong here: it would move with the commit that writes this file.
        'gate': revision(GATE) or GATE,
    },
    'deliveries': [
        {'issue': int(issue), 'subject': subject, 'decision': decision,
         'commit': commit_for(issue), 'sources': sources, 'tests': tests, 'document': document}
        for issue, subject, decision, sources, tests, document in DELIVERIES
    ],
    'excluded': [{'item': item, 'reason': reason} for item, reason in EXCLUDED],
    'conditionalCandidates': [{'item': item, 'reason': reason} for item, reason in CONDITIONAL],
    'optIns': {
        'HorosProgressiveRetrieveViewing': 'progressive retrieve and view (#604)',
        'HorosPlanarMetal4Pilot': 'Metal 4 planar submission pilot (#609), off by default',
        'HorosPlanarPerformanceTrace': 'opt-in planar signposts (#373)',
    },
    'environment': {
        'os': 'macOS 26.6.2', 'sdk': '26.5', 'deploymentTarget': '26.0',
        'architecture': 'arm64', 'device': 'Apple M4', 'intelMacs': 'out of scope',
    },
}

text = json.dumps(manifest, indent=2, sort_keys=True) + '\n'
target = root / 'docs/donor-delta3-manifest.json'
if arguments.check:
    current = target.read_text() if target.exists() else ''
    if current != text:
        print('FAIL: the manifest on disk does not match the repository it describes')
        raise SystemExit(1)
    print('ok: the delta manifest matches the repository')
else:
    target.write_text(text)
    print('wrote', target)
