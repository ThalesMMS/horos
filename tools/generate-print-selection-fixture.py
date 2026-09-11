#!/usr/bin/env python3
"""Synthetic #384 A series, RGB multiframe, three-page encapsulated PDF and long SR.

Requires pydicom and numpy. Destination must be empty and outside this repository.
No real patient, network service or previous fixture is read. Originals have SHA-256
entries for checking after import/printing. Use --images 240 for a long selection.
"""
import argparse
import hashlib
import json
import uuid
from pathlib import Path

import numpy as np
from pydicom.dataset import Dataset, FileDataset, FileMetaDataset
from pydicom.uid import (ExplicitVRLittleEndian, SecondaryCaptureImageStorage,
                        MultiFrameTrueColorSecondaryCaptureImageStorage,
                        EncapsulatedPDFStorage, BasicTextSRStorage)


def uid(name):
    return '2.25.' + str(uuid.uuid5(uuid.NAMESPACE_URL, 'horos-print-384-' + name).int)


def pdf_fixture():
    objects = [b'<< /Type /Catalog /Pages 2 0 R >>',
               b'<< /Type /Pages /Kids [4 0 R 6 0 R 8 0 R] /Count 3 >>',
               b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>']
    for index, color in enumerate(['1 0 0', '0 1 0', '0 0 1']):
        content = f'{color} rg 80 100 300 420 re f\n0 0 0 rg 80 100 30 40 re f\n'
        if index < 2:
            content += f'BT /F1 24 Tf 60 730 Td (PRINT384-PDF-{index + 1}) Tj ET\n'
        content = content.encode('ascii')
        objects.append(f'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 3 0 R >> >> /Contents {5 + index*2} 0 R >>'.encode())
        objects.append(f'<< /Length {len(content)} >>\nstream\n'.encode() + content + b'endstream')
    result = b'%PDF-1.4\n'
    offsets = [0]
    for number, value in enumerate(objects, 1):
        offsets.append(len(result))
        result += f'{number} 0 obj\n'.encode() + value + b'\nendobj\n'
    xref = len(result)
    result += f'xref\n0 {len(objects)+1}\n0000000000 65535 f \n'.encode()
    result += b''.join(f'{offset:010} 00000 n \n'.encode() for offset in offsets[1:])
    return result + f'trailer\n<< /Size {len(objects)+1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n'.encode()


def code(value, scheme, meaning):
    item = Dataset()
    item.CodeValue = value; item.CodingSchemeDesignator = scheme; item.CodeMeaning = meaning
    return item


def generate(destination, images=8):
    destination = destination.resolve()
    root = Path(__file__).resolve().parents[1]
    if destination == root or root in destination.parents:
        raise ValueError('Generate fixtures outside the repository')
    if images < 1 or images > 1000:
        raise ValueError('--images must be between 1 and 1000')
    destination.mkdir(parents=True, exist_ok=True)
    if any(destination.iterdir()):
        raise ValueError('Use an empty output directory')
    paths = []
    def base(name, sop, number, description, modality):
        path = destination / 'import' / f'{name}.dcm'
        path.parent.mkdir(exist_ok=True)
        meta = FileMetaDataset()
        meta.MediaStorageSOPClassUID = sop; meta.MediaStorageSOPInstanceUID = uid(name)
        meta.TransferSyntaxUID = ExplicitVRLittleEndian
        ds = FileDataset(str(path), {}, file_meta=meta, preamble=b'\0' * 128)
        ds.SOPClassUID = sop; ds.SOPInstanceUID = uid(name)
        ds.StudyInstanceUID = uid('study'); ds.SeriesInstanceUID = uid('series-' + str(number))
        ds.PatientName = 'SYNTHETIC^PRINT384'; ds.PatientID = 'LOCAL-PRINT-384'
        ds.PatientBirthDate = ''; ds.PatientSex = 'O'
        ds.StudyDate = ds.ContentDate = '20260912'; ds.StudyTime = ds.ContentTime = '120000'
        ds.StudyID = 'PRINT384'; ds.AccessionNumber = 'LOCAL384'
        ds.StudyDescription = 'Synthetic print package A'
        ds.SeriesNumber = number; ds.SeriesDescription = description; ds.Modality = modality
        ds.SpecificCharacterSet = 'ISO_IR 100'; ds.InstanceNumber = 1
        ds.ReferringPhysicianName = ''
        ds.Manufacturer = 'Synthetic generator'
        return path, ds
    def save(path, ds):
        ds.save_as(path, enforce_file_format=True)
        paths.append(dict(path=path.relative_to(destination).as_posix(),
                          sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                          series=int(ds.SeriesNumber), instance=int(ds.InstanceNumber),
                          frames=int(getattr(ds, 'NumberOfFrames', 1))))
    y, x = np.indices((96, 64))
    for index in range(images):
        path, ds = base(f'gray-{index:04}', SecondaryCaptureImageStorage, 1, 'Print ordered grayscale', 'OT')
        ds.InstanceNumber = index + 1; ds.Rows = 96; ds.Columns = 64
        ds.SamplesPerPixel = 1; ds.PhotometricInterpretation = 'MONOCHROME2'
        ds.BitsAllocated = ds.BitsStored = 8; ds.HighBit = 7; ds.PixelRepresentation = 0
        ds.PixelSpacing = [1, 1]; ds.ConversionType = 'WSD'; ds.ImageType = ['DERIVED', 'SECONDARY']
        ds.WindowCenter = 128; ds.WindowWidth = 256
        pixels = np.where((x < 32) & (y < 48), 30 + index % 180,
                          np.where(x >= 32, 210, 90)).astype('u1')
        pixels[3:20, 1:25:2] = 0
        ds.PixelData = pixels.tobytes(); save(path, ds)
    path, ds = base('rgb-multiframe', MultiFrameTrueColorSecondaryCaptureImageStorage, 2, 'Print RGB four frames pixel ratio 2', 'OT')
    ds.Rows = 96; ds.Columns = 64; ds.NumberOfFrames = 4
    ds.SamplesPerPixel = 3; ds.PhotometricInterpretation = 'RGB'; ds.PlanarConfiguration = 0
    ds.BitsAllocated = ds.BitsStored = 8; ds.HighBit = 7; ds.PixelRepresentation = 0
    ds.PixelSpacing = [2, 1]; ds.FrameTime = 100; ds.FrameIncrementPointer = [0x00181063]
    ds.ConversionType = 'WSD'; ds.ImageType = ['DERIVED', 'SECONDARY']
    colors = [(240, 17, 17), (17, 240, 17), (17, 17, 240), (240, 240, 17)]
    frames = []
    for color in colors:
        rgb = np.empty((96, 64, 3), dtype='u1'); rgb[:] = color
        rgb[3:20, 1:25:2] = 0; rgb[65:90, 40:60] = (255, 255, 255); frames.append(rgb.tobytes())
    ds.PixelData = b''.join(frames); save(path, ds)
    pdf = pdf_fixture()
    (destination / 'reference-three-pages.pdf').write_bytes(pdf)
    path, ds = base('encapsulated-pdf', EncapsulatedPDFStorage, 3, 'Print PDF three pages', 'DOC')
    ds.MIMETypeOfEncapsulatedDocument = 'application/pdf'; ds.EncapsulatedDocument = pdf
    ds.DocumentTitle = 'Synthetic print report'; ds.BurnedInAnnotation = 'YES'
    ds.ConceptNameCodeSequence = []; save(path, ds)
    path, ds = base('structured-report', BasicTextSRStorage, 4, 'Print SR long report', 'SR')
    ds.ValueType = 'CONTAINER'; ds.ContinuityOfContent = 'SEPARATE'
    ds.CompletionFlag = 'COMPLETE'; ds.VerificationFlag = 'UNVERIFIED'
    ds.ConceptNameCodeSequence = [code('18748-4', 'LN', 'Diagnostic imaging study')]
    content = []
    for index in range(60):
        text = Dataset(); text.RelationshipType = 'CONTAINS'; text.ValueType = 'TEXT'
        text.ConceptNameCodeSequence = [code('121106', 'DCM', 'Comment')]
        text.TextValue = f'PRINT384-SR-{index:03} Synthetic paragraph for page order and completion. ' * 3
        content.append(text)
    ds.ContentSequence = content
    ds.ReferencedPerformedProcedureStepSequence = []; ds.PerformedProcedureCodeSequence = []
    save(path, ds)
    manifest = dict(synthetic=True, patientID='LOCAL-PRINT-384', instances=paths,
                    expectations=dict(grayPages=images, rgbFrames=4, pdfPages=3,
                                      pdfText=['PRINT384-PDF-1', 'PRINT384-PDF-2'],
                                      pdfLastPage='blue rectangle, no text',
                                      srTokens=[f'PRINT384-SR-{i:03}' for i in range(60)],
                                      sourceRGBSize=[64, 96], displayRGBSize=[64, 192]))
    (destination / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--images', type=int, default=8)
    arguments = parser.parse_args()
    result = generate(arguments.output, arguments.images)
    print(f'Generated {len(result["instances"])} synthetic DICOMs; import only output/import; preserve manifest and originals')
