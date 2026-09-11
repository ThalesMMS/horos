#!/usr/bin/env python3
"""Tumour-segmentation job contract is compiled into the app target."""
from pathlib import Path
import sys

root = Path(__file__).resolve().parents[1]
pbx = (root / 'Horos.xcodeproj/project.pbxproj').read_text(encoding='utf-8')
source = root / 'Horos/Sources/TumorSegmentationJob.swift'
helper = root / 'tools/metal3d_tumor_segmentation_mock.py'
contract = root / 'docs/tumor-segmentation-contract.md'

if 'TumorSegmentationJob.swift' not in pbx:
    print('FAIL: TumorSegmentationJob.swift is not in the app target')
    sys.exit(1)
if 'TumorSegmentationJob.swift in Sources' not in pbx:
    print('FAIL: TumorSegmentationJob.swift is not in a Sources build phase')
    sys.exit(1)
if not source.is_file():
    print('FAIL: Horos/Sources/TumorSegmentationJob.swift is missing')
    sys.exit(1)
text = source.read_text(encoding='utf-8')
if 'helper --job' not in text and '["--job"' not in text:
    print('FAIL: the job type no longer launches with --job')
    sys.exit(1)
if 'shape-resize' not in source.read_text(encoding='utf-8') and 'resize' not in text:
    print('FAIL: resize fallback is no longer refused as registration')
    sys.exit(1)
if not helper.is_file():
    print('FAIL: mock helper is missing')
    sys.exit(1)
mock = helper.read_text(encoding='utf-8')
if '--job' not in mock or 'mock-threshold' not in mock:
    print('FAIL: mock helper is not the --job smoke backend')
    sys.exit(1)
if 'ystarrev' in mock.lower() and '23722fb552d96fa2d60c7f58a6d4ac2c27950f86' not in mock:
    print('FAIL: mock helper must cite the ystarrev SHA it was adapted from')
    sys.exit(1)
if not contract.is_file():
    print('FAIL: docs/tumor-segmentation-contract.md is missing')
    sys.exit(1)
doc = contract.read_text(encoding='utf-8')
if 'float32' not in doc or 'z, y, x' not in doc:
    print('FAIL: contract doc must record float32 little-endian z/y/x order')
    sys.exit(1)
if 'mock' not in doc.lower() or 'nnunet' not in doc.lower():
    print('FAIL: contract doc must distinguish mock, candidate and nnU-Net')
    sys.exit(1)
print('PASS: tumour-segmentation job is in the app target with a versioned mock helper')
