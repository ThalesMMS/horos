#!/usr/bin/env python3
"""Verify a locally generated #157 report against the synthetic merge template.

The expected JSON object contains name, patientID, studyName, accessionNumber
and modality as they were exported from the selected synthetic Study. This
checks saved bytes, not Word windows, consent, or the database association.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET
import zipfile


def verify(report, template, expected):
    spec = importlib.util.spec_from_file_location(
        'word_fixture', Path(__file__).with_name('generate-word-merge-template.py'))
    fixture = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fixture)
    with zipfile.ZipFile(template) as package:
        image = package.read('word/media/image1.png')
    data = report.read_bytes()
    if data.startswith(b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1'):
        text = subprocess.run(['/usr/bin/textutil', '-convert', 'txt', '-stdout', str(report)],
                              check=True, capture_output=True).stdout.decode('utf-8')
        image_found = image in data
        format_name = 'Word 97-2004 DOC'
    elif zipfile.is_zipfile(report):
        with zipfile.ZipFile(report) as package:
            ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
            document = ET.fromstring(package.read('word/document.xml'))
            text = '\n'.join(''.join(p.itertext()) for p in document.findall('.//w:p', ns))
            image_found = any(package.read(name) == image for name in package.namelist()
                              if name.startswith('word/media/'))
        format_name = 'Office Open XML DOCX'
    else:
        raise ValueError('Report is neither a DOC compound file nor a DOCX package')
    lines = text.splitlines()
    required = [fixture.TITLE, *fixture.PARAGRAPHS]
    required.extend(f'{field}: {expected[field]}' for field in fixture.FIELDS)
    for line in set(required):
        if lines.count(line) != required.count(line):
            raise ValueError('Saved report has missing, duplicated or incorrect merge content')
    if not image_found:
        raise ValueError('The exact synthetic template PNG is missing from the saved report')
    return {'format': format_name, 'bytes': len(data),
            'sha256': hashlib.sha256(data).hexdigest(),
            'mergeFields': len(fixture.FIELDS), 'repeatedNameCount': 2,
            'portugueseAndRussian': True, 'exactTemplateImage': True}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('report', type=Path)
    parser.add_argument('--template', type=Path, required=True, help='Original generated DOCX fixture')
    parser.add_argument('--expected', type=Path, required=True, help='Synthetic Study values as JSON')
    args = parser.parse_args()
    print(json.dumps(verify(args.report, args.template, json.loads(args.expected.read_text())), indent=2))
