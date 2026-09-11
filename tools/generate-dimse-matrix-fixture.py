#!/usr/bin/env python3
"""Synthetic upstream-DIMSE study: native, compressed, multiframe, SR and SEG.

Requires pydicom, numpy and imagecodecs. Use an empty directory outside Git.
The manifest records the source and decoded-pixel hashes, without patient data.
"""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
import imagecodecs
from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.encaps import encapsulate
from pydicom.uid import (generate_uid, ExplicitVRLittleEndian, ImplicitVRLittleEndian,
    ExplicitVRBigEndian, CTImageStorage, MRImageStorage, UltrasoundMultiFrameImageStorage,
    BasicTextSRStorage, SegmentationStorage, JPEGLSLossless, JPEG2000Lossless, RLELossless)

def code(value, scheme, meaning):
    item = Dataset(); item.CodeValue = value; item.CodingSchemeDesignator = scheme; item.CodeMeaning = meaning
    return item

def generate(folder, include_jpeg2000=False):
    folder.mkdir(parents=True, exist_ok=True)
    if any(folder.iterdir()): raise ValueError('Use an empty fixture directory')
    study, frame = generate_uid(), generate_uid()
    entries = []
    def base(name, sop, modality):
        ds = Dataset(); ds.file_meta = FileMetaDataset()
        ds.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
        ds.SOPClassUID = sop; ds.SOPInstanceUID = generate_uid()
        ds.StudyInstanceUID = study; ds.SeriesInstanceUID = generate_uid()
        ds.SpecificCharacterSet = 'ISO_IR 192'
        ds.PatientName = 'SYNTHETIC^DIMSE'; ds.PatientID = 'LOCAL-371'
        ds.PatientBirthDate = '19700101'; ds.PatientSex = 'O'
        ds.StudyDate = ds.ContentDate = '20260912'; ds.StudyTime = ds.ContentTime = '120000'
        ds.StudyID = '371'; ds.AccessionNumber = 'LOCAL371'; ds.StudyDescription = 'Synthetic DIMSE matrix'
        ds.SeriesDescription = name; ds.Modality = modality; ds.InstanceNumber = 1
        ds.SeriesNumber = len(entries) + 1; ds.Manufacturer = 'Synthetic generator'
        return ds
    def save(name, ds, expected=None):
        path = folder / (name + '.dcm'); ds.save_as(path, enforce_file_format=True)
        entries.append(dict(file=path.name, sopClass=str(ds.SOPClassUID), uid=str(ds.SOPInstanceUID),
            frames=int(getattr(ds, 'NumberOfFrames', 1)), syntax=str(ds.file_meta.TransferSyntaxUID),
            sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            pixelSHA256=hashlib.sha256(expected.astype('<u2').tobytes()).hexdigest() if expected is not None else None))
    specs = [('ct-explicit', CTImageStorage, 'CT', ExplicitVRLittleEndian, 1),
             ('ct-implicit', CTImageStorage, 'CT', ImplicitVRLittleEndian, 1),
             ('ct-big', CTImageStorage, 'CT', ExplicitVRBigEndian, 1),
             ('mr-rle', MRImageStorage, 'MR', RLELossless, 1),
             ('ct-jpegls', CTImageStorage, 'CT', JPEGLSLossless, 1),
             ('us-multiframe', UltrasoundMultiFrameImageStorage, 'US', ExplicitVRLittleEndian, 4)]
    if include_jpeg2000:
        specs += [('ct-jpeg2000', CTImageStorage, 'CT', JPEG2000Lossless, 1),
                  ('us-jpeg2000', UltrasoundMultiFrameImageStorage, 'US', JPEG2000Lossless, 4)]
    for number, (name, sop, modality, syntax, frames) in enumerate(specs, 1):
        ds = base(name, sop, modality)
        pixels = (np.arange(frames * 32 * 33, dtype=np.uint16).reshape(frames, 32, 33) * number) % 4096
        if frames == 1: pixels = pixels[0]
        ds.Rows = 32; ds.Columns = 33; ds.SamplesPerPixel = 1
        ds.PhotometricInterpretation = 'MONOCHROME2'; ds.BitsAllocated = 16
        ds.BitsStored = 12; ds.HighBit = 11; ds.PixelRepresentation = 0
        ds.PixelSpacing = [1, 1]; ds.SliceThickness = 1
        ds.ImagePositionPatient = [0, 0, number]; ds.ImageOrientationPatient = [1, 0, 0, 0, 1, 0]
        ds.FrameOfReferenceUID = frame; ds.ImageType = ['ORIGINAL', 'PRIMARY']
        ds.RescaleIntercept = 0; ds.RescaleSlope = 1
        if frames > 1: ds.NumberOfFrames = frames; ds.FrameTime = 100
        ds.PixelData = pixels.astype('<u2').tobytes()
        if syntax == RLELossless: ds.compress(syntax, generate_instance_uid=False)
        elif syntax == JPEGLSLossless:
            ds.PixelData = encapsulate([imagecodecs.jpegls_encode(pixels)])
            ds['PixelData'].is_undefined_length = True; ds.file_meta.TransferSyntaxUID = syntax
        elif syntax == JPEG2000Lossless:
            ds.PixelData = encapsulate([imagecodecs.jpeg2k_encode(frame, level=0, reversible=True, codecformat='J2K', bitspersample=12)
                for frame in pixels.reshape(frames, 32, 33)])
            ds['PixelData'].is_undefined_length = True; ds.file_meta.TransferSyntaxUID = syntax
        else:
            ds.file_meta.TransferSyntaxUID = syntax
            if syntax == ExplicitVRBigEndian: ds.PixelData = pixels.astype('>u2').tobytes()
        save(name, ds, pixels)
    ds = base('sr-text', BasicTextSRStorage, 'SR')
    ds.CompletionFlag = 'COMPLETE'; ds.VerificationFlag = 'UNVERIFIED'; ds.PreliminaryFlag = 'FINAL'
    ds.ValueType = 'CONTAINER'; ds.ContinuityOfContent = 'SEPARATE'
    ds.ConceptNameCodeSequence = [code('18748-4', 'LN', 'Diagnostic imaging study')]
    text = Dataset(); text.RelationshipType = 'CONTAINS'; text.ValueType = 'TEXT'
    text.ConceptNameCodeSequence = [code('121106', 'DCM', 'Comment')]
    text.TextValue = 'Synthetic report: comunicação íntegra.'; ds.ContentSequence = [text]
    save('sr-text', ds)
    ds = base('seg-fractional', SegmentationStorage, 'SEG')
    ds.FrameOfReferenceUID = frame; ds.Rows = 32; ds.Columns = 33; ds.NumberOfFrames = 2
    ds.SamplesPerPixel = 1; ds.PhotometricInterpretation = 'MONOCHROME2'
    ds.BitsAllocated = ds.BitsStored = 8; ds.HighBit = 7; ds.PixelRepresentation = 0
    ds.ImageType = ['DERIVED', 'PRIMARY']; ds.SegmentationType = 'FRACTIONAL'
    ds.SegmentationFractionalType = 'PROBABILITY'; ds.MaximumFractionalValue = 255
    ds.ContentLabel = 'SYNTHETIC'; ds.ContentDescription = 'Synthetic mask'
    ds.ContentCreatorName = 'LOCAL^TEST'; ds.SegmentsOverlap = 'NO'
    segment = Dataset(); segment.SegmentNumber = 1; segment.SegmentLabel = 'Mask'
    segment.SegmentAlgorithmType = 'MANUAL'
    segment.SegmentedPropertyCategoryCodeSequence = [code('T-D0050', 'SRT', 'Tissue')]
    segment.SegmentedPropertyTypeCodeSequence = [code('T-D0050', 'SRT', 'Tissue')]
    ds.SegmentSequence = [segment]
    shared = Dataset(); spacing = Dataset(); spacing.PixelSpacing = [1, 1]; spacing.SliceThickness = 1
    shared.PixelMeasuresSequence = [spacing]; orientation = Dataset(); orientation.ImageOrientationPatient = [1, 0, 0, 0, 1, 0]
    shared.PlaneOrientationSequence = [orientation]; ds.SharedFunctionalGroupsSequence = [shared]
    groups = []
    for z in range(2):
        group = Dataset(); position = Dataset(); position.ImagePositionPatient = [0, 0, z]
        group.PlanePositionSequence = [position]; reference = Dataset(); reference.ReferencedSegmentNumber = 1
        group.SegmentIdentificationSequence = [reference]; groups.append(group)
    ds.PerFrameFunctionalGroupsSequence = groups
    pixels = np.zeros((2, 32, 33), np.uint8); pixels[:, 7:20, 5:17] = 255
    ds.PixelData = pixels.tobytes(); save('seg-fractional', ds, pixels)
    manifest = dict(study=study, patient='LOCAL-371', instances=entries)
    (folder/'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    return manifest

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('output', type=Path)
    parser.add_argument('--jpeg2000', action='store_true', help='Include independent single/multiframe JPEG2000 sources')
    args = parser.parse_args()
    print(json.dumps(generate(args.output, args.jpeg2000), indent=2))
