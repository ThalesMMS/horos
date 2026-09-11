#!/usr/bin/env python3
"""HVRVOL02 stays a host exporter: not DICOM, not DICOMweb, not a copied team."""
from pathlib import Path
import sys

root = Path(__file__).resolve().parents[1]
failures = []


def text(relative):
    return (root / relative).read_bytes().decode('latin1')


def require(condition, message):
    if not condition:
        failures.append(message)


source = text('Horos/Sources/HorosHVRVOL02.swift')
project = text('Horos.xcodeproj/project.pbxproj')
copy = text('Horos/Sources/BrowserController+Sources+Copy.m')
config = text('Config.xcconfig')
docs = text('docs/hvrvol02-export-validation.md')
browser = text('Horos/Sources/BrowserController.m')

require('HorosHVRVOL02.swift' in project, 'the exporter is not in the application target')
require('HVRVOL02' in source, 'the exporter does not name the HVRVOL02 contract')
require('_horosiphone._tcp' in source, 'Bonjour discovery type is missing')
require('explicitlyAuthorized' in source, 'authorization is not distinct from discovery')
require('DICOM_LPS_mm' in source and 'float32' in source, 'patient-space float32 contract is missing')

require('copyImagesToRemoteBrowserSourceThread' in copy,
        'remote database copy was removed to make room for the phone exporter')
require('SendController.h' in browser,
        'DICOM SendController is no longer imported by the browser')
web = text('Horos/Sources/DICOMwebClient.swift')
require('QIDO' in web and 'WADO' in web, 'DICOMweb client lost QIDO/WADO')

require('TPT6TVH8UY' not in config, 'ystarrev DEVELOPMENT_TEAM was copied into Config.xcconfig')
require('HOROS_DEVELOPMENT_TEAM' in config, 'local signing override was dropped')

require('native gap' in docs.lower() or 'gap nativo' in docs.lower(),
        'the validation record does not keep the native iPhone receptor as a gap')
require('iPhone' in docs, 'the validation record does not mention the iPhone receptor')
require('HVRVOL02' in docs, 'the validation record does not name the contract')
require('26.6' in docs or 'arm64' in docs, 'the validation record omits the measured host')

if failures:
    print('FAIL:')
    for item in failures:
        print(' ', item)
    sys.exit(1)
print('PASS: HVRVOL02 wiring preserves DICOM, DICOMweb and local signing')
