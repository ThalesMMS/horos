#!/usr/bin/env python3
"""Synthetic Horos Cloud report DICOM objects for association tests.

Four objects, no service and no credentials:

  image                 CT-like instance of the target study
  report-same-uid       Encapsulated PDF whose StudyInstanceUID is the study
  report-referenced     Encapsulated PDF with a new StudyInstanceUID that
                        references the study and the image SOP Instance UID
  report-name-only      Encapsulated PDF with a new StudyInstanceUID, the same
                        patient name, and no references

The destination must be empty. Nothing here is a real Cloud payload.
"""
from __future__ import annotations

import argparse
import json
import uuid
from pathlib import Path

PDF = b'%PDF-1.1\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n'
PDF_SOP = '1.2.840.10008.5.1.4.1.1.104.1'
CT_SOP = '1.2.840.10008.5.1.4.1.1.2'
EXPLICIT_LE = '1.2.840.10008.1.2.1'


def uid(name: str) -> str:
    return '2.25.' + str(uuid.uuid5(uuid.NAMESPACE_URL, 'horos-cloud-report-' + name).int)


STUDY = uid('study')
SERIES = uid('series')
IMAGE = uid('image')
REPORT_SAME = uid('report-same')
REPORT_REF = uid('report-referenced')
REPORT_NAME = uid('report-name')
CLOUD_STUDY_REF = uid('cloud-study')
CLOUD_STUDY_NAME = uid('cloud-study-name')
PATIENT_NAME = 'CLOUD^REPORT'
PATIENT_ID = 'CLOUD-160'


def even(value: bytes, vr: str) -> bytes:
    if len(value) % 2:
        return value + (b'\x00' if vr == 'UI' else b' ')
    return value


def element(group: int, element_number: int, vr: str, value: bytes) -> bytes:
    value = even(value, vr)
    tag = group.to_bytes(2, 'little') + element_number.to_bytes(2, 'little') + vr.encode('ascii')
    if vr in {'OB', 'OD', 'OF', 'OL', 'OW', 'SQ', 'UC', 'UN', 'UR', 'UT'}:
        return tag + b'\x00\x00' + len(value).to_bytes(4, 'little') + value
    return tag + len(value).to_bytes(2, 'little') + value


def ui(group: int, element_number: int, value: str) -> bytes:
    return element(group, element_number, 'UI', value.encode('ascii'))


def lo(group: int, element_number: int, value: str) -> bytes:
    return element(group, element_number, 'LO', value.encode('ascii'))


def cs(group: int, element_number: int, value: str) -> bytes:
    return element(group, element_number, 'CS', value.encode('ascii'))


def pn(group: int, element_number: int, value: str) -> bytes:
    return element(group, element_number, 'PN', value.encode('ascii'))


def sh(group: int, element_number: int, value: str) -> bytes:
    return element(group, element_number, 'SH', value.encode('ascii'))


def da(group: int, element_number: int, value: str) -> bytes:
    return element(group, element_number, 'DA', value.encode('ascii'))


def tm(group: int, element_number: int, value: str) -> bytes:
    return element(group, element_number, 'TM', value.encode('ascii'))


def us(group: int, element_number: int, value: int) -> bytes:
    return element(group, element_number, 'US', value.to_bytes(2, 'little'))


def is_(group: int, element_number: int, value: int) -> bytes:
    return element(group, element_number, 'IS', str(value).encode('ascii'))


def ob(group: int, element_number: int, value: bytes) -> bytes:
    return element(group, element_number, 'OB', value)


def sq(group: int, element_number: int, items: list[bytes]) -> bytes:
    body = b''
    for item in items:
        body += b'\xfe\xff\x00\xe0' + len(item).to_bytes(4, 'little') + item
    return element(group, element_number, 'SQ', body)


def meta(sop_class: str, sop_instance: str) -> bytes:
    body = (
        ob(0x0002, 0x0001, b'\x00\x01')
        + ui(0x0002, 0x0002, sop_class)
        + ui(0x0002, 0x0003, sop_instance)
        + ui(0x0002, 0x0010, EXPLICIT_LE)
        + ui(0x0002, 0x0012, '1.2.826.0.1.3680043.8.498.1')
    )
    return element(0x0002, 0x0000, 'UL', len(body).to_bytes(4, 'little')) + body


def common(sop_class: str, sop_instance: str, study: str, series: str,
          modality: str, series_description: str, manufacturer: str,
          patient_name: str = PATIENT_NAME) -> bytes:
    return (
        ui(0x0008, 0x0016, sop_class)
        + ui(0x0008, 0x0018, sop_instance)
        + da(0x0008, 0x0020, '20260101')
        + tm(0x0008, 0x0030, '120000')
        + cs(0x0008, 0x0060, modality)
        + lo(0x0008, 0x0070, manufacturer)
        + lo(0x0008, 0x1030, 'Cloud report association')
        + lo(0x0008, 0x103E, series_description)
        + pn(0x0010, 0x0010, patient_name)
        + lo(0x0010, 0x0020, PATIENT_ID)
        + ui(0x0020, 0x000D, study)
        + ui(0x0020, 0x000E, series)
        + sh(0x0020, 0x0010, '160')
        + is_(0x0020, 0x0011, 1)
        + is_(0x0020, 0x0013, 1)
    )


def write_part10(path: Path, sop_class: str, sop_instance: str, dataset: bytes) -> None:
    path.write_bytes(b'\x00' * 128 + b'DICM' + meta(sop_class, sop_instance) + dataset)


def image_dataset() -> bytes:
    pixels = bytes([i % 256 for i in range(64)])
    return common(CT_SOP, IMAGE, STUDY, SERIES, 'CT', 'Synthetic CT', 'Horos QA') + (
        us(0x0028, 0x0002, 1)
        + cs(0x0028, 0x0004, 'MONOCHROME2')
        + us(0x0028, 0x0010, 8)
        + us(0x0028, 0x0011, 8)
        + us(0x0028, 0x0100, 8)
        + us(0x0028, 0x0101, 8)
        + us(0x0028, 0x0102, 7)
        + us(0x0028, 0x0103, 0)
        + ob(0x7FE0, 0x0010, pixels)
    )


def report_dataset(sop_instance: str, study: str, series: str, references: bool,
                   manufacturer: str = 'Horos Cloud') -> bytes:
    referenced_study = (
        ui(0x0008, 0x1150, '1.2.840.10008.3.1.2.3.1')
        + ui(0x0008, 0x1155, STUDY)
    )
    referenced_sop = (
        ui(0x0008, 0x1150, CT_SOP)
        + ui(0x0008, 0x1155, IMAGE)
    )
    referenced_series = ui(0x0020, 0x000E, SERIES) + sq(0x0008, 0x1199, [referenced_sop])
    evidence = ui(0x0020, 0x000D, STUDY) + sq(0x0008, 0x1115, [referenced_series])
    extra = b''
    if references:
        extra = (
            sq(0x0008, 0x1110, [referenced_study])
            + sq(0x0040, 0xA375, [evidence])
        )
    return common(PDF_SOP, sop_instance, study, series, 'DOC',
                  'Horos Cloud Report', manufacturer) + extra + (
        cs(0x0028, 0x0301, 'YES')
        + lo(0x0042, 0x0012, 'application/pdf')
        + ob(0x0042, 0x0011, PDF)
    )


def generate(output: Path) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        raise ValueError('Use an empty output directory')
    write_part10(output / 'image.dcm', CT_SOP, IMAGE, image_dataset())
    write_part10(output / 'report-same-uid.dcm', PDF_SOP, REPORT_SAME,
                  report_dataset(REPORT_SAME, STUDY, uid('report-same-series'), False))
    write_part10(output / 'report-referenced.dcm', PDF_SOP, REPORT_REF,
                  report_dataset(REPORT_REF, CLOUD_STUDY_REF, uid('report-ref-series'), True))
    write_part10(output / 'report-name-only.dcm', PDF_SOP, REPORT_NAME,
                  report_dataset(REPORT_NAME, CLOUD_STUDY_NAME, uid('report-name-series'), False))
    manifest = {
        'study': STUDY,
        'series': SERIES,
        'image': IMAGE,
        'report_same': REPORT_SAME,
        'report_referenced': REPORT_REF,
        'report_name_only': REPORT_NAME,
        'cloud_study_referenced': CLOUD_STUDY_REF,
        'cloud_study_name_only': CLOUD_STUDY_NAME,
        'patient_name': PATIENT_NAME,
        'patient_id': PATIENT_ID,
        'files': {
            'image': 'image.dcm',
            'report_same_uid': 'report-same-uid.dcm',
            'report_referenced': 'report-referenced.dcm',
            'report_name_only': 'report-name-only.dcm',
        },
    }
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    arguments = parser.parse_args()
    generate(arguments.output)
    print('study', STUDY)
    print('image', IMAGE)
    print('report-same-uid', REPORT_SAME)
    print('report-referenced', REPORT_REF, 'study', CLOUD_STUDY_REF)
    print('report-name-only', REPORT_NAME, 'study', CLOUD_STUDY_NAME)
