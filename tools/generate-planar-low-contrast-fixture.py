#!/usr/bin/env python3
"""Generate synthetic NM/PT low-contrast inputs for #373/A111, outside Git.

The two series have identical calibrated intensities but distinct stored values:
NM counts are direct; PT BQML = stored*0.25-64. This is a numerical display
phantom, not a clinical acquisition or a measurement of diagnostic performance.
"""
import argparse
import hashlib
import json
from pathlib import Path
import uuid

import numpy as np
from pydicom.dataset import Dataset, FileDataset, FileMetaDataset
from pydicom.tag import Tag
from pydicom.uid import ExplicitVRLittleEndian, NuclearMedicineImageStorage, PositronEmissionTomographyImageStorage

ROOT = Path(__file__).resolve().parents[1]
PALETTE = [[0,0,64], [0,0,255], [0,128,255], [0,255,255],
           [255,255,0], [255,128,0], [255,0,0], [128,0,0]]


def uid(name):
    return '2.25.' + str(uuid.uuid5(uuid.NAMESPACE_URL, 'urn:horos:a111:low-contrast:v1:' + name).int)


def generate(output, shutter=False):
    output = output.resolve()
    examples = (ROOT.parent/'DICOM_Example').resolve()
    if not examples.is_dir() or not output.is_relative_to(examples):
        raise ValueError('Output must be inside the existing ../DICOM_Example directory')
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        raise ValueError('Use an empty output directory; preserve previous fixtures')
    rows, columns = np.ogrid[:256, :256]
    records = []
    def fixture_uid(name):
        return uid(('shutter:' if shutter else '') + name)
    for modality, sop, slope, intercept in [('NM', NuclearMedicineImageStorage, 1, 0),
                                           ('PT', PositronEmissionTomographyImageStorage, 0.25, -64)]:
        folder = output/modality
        folder.mkdir()
        for index in range(16):
            shift = index % 4 - 1
            physical = np.full((256,256), 2048 + shift, dtype=np.float32)
            for cx, cy, radius, delta in [(80,80,20,8), (176,80,16,16),
                                          (80,176,12,-8), (176,176,8,-16)]:
                mask = (columns-cx)**2 + (rows-cy)**2 <= radius**2
                physical[mask] += delta
            # A separate control strip, well away from the low-contrast disks:
            # adjacent 2032/2064 samples straddle the discrete blue/yellow CLUT.
            physical[:16,:] = np.where(columns % 2 == 0, 2032, 2064)
            stored = ((physical - intercept)/slope).astype('<u2')
            path = folder/f'{index:02d}.dcm'
            meta = FileMetaDataset()
            meta.MediaStorageSOPClassUID = sop
            meta.MediaStorageSOPInstanceUID = fixture_uid(f'{modality}-{index}')
            meta.TransferSyntaxUID = ExplicitVRLittleEndian
            ds = FileDataset(str(path), {}, file_meta=meta, preamble=b'\0'*128)
            ds.SOPClassUID = sop; ds.SOPInstanceUID = meta.MediaStorageSOPInstanceUID
            ds.StudyInstanceUID = fixture_uid('study'); ds.SeriesInstanceUID = fixture_uid(modality)
            ds.FrameOfReferenceUID = fixture_uid('frame')
            ds.PatientName = 'SYNTHETIC^A111 LOW CONTRAST'; ds.PatientID = 'QA-A111-ONLY'
            ds.PatientBirthDate = ''; ds.PatientSex = ''; ds.StudyID = 'A111'
            ds.StudyDescription = 'Synthetic planar interpolation acceptance'
            ds.SeriesDescription = f'A111 {modality} low contrast numerical phantom'
            if shutter:
                ds.SeriesDescription += ' shutter'
                ds.ShutterShape = 'RECTANGULAR'
                ds.ShutterLeftVerticalEdge = ds.ShutterUpperHorizontalEdge = 40
                ds.ShutterRightVerticalEdge = ds.ShutterLowerHorizontalEdge = 216
                ds.ShutterPresentationValue = 0
            ds.StudyDate = ds.SeriesDate = ds.ContentDate = '20260913'
            ds.StudyTime = ds.SeriesTime = ds.ContentTime = '120000'
            ds.AccessionNumber = ''; ds.ReferringPhysicianName = ''
            ds.Modality = modality; ds.SeriesNumber = 1 if modality == 'NM' else 2
            ds.InstanceNumber = index+1
            ds.ImageType = ['ORIGINAL','PRIMARY','STATIC'] if modality == 'NM' else ['ORIGINAL','PRIMARY']
            ds.Rows = ds.Columns = 256; ds.PixelSpacing = [2,2]; ds.SliceThickness = 4
            ds.ImageOrientationPatient = [1,0,0,0,1,0]
            ds.ImagePositionPatient = [-256,-256,index*4]
            ds.SamplesPerPixel = 1; ds.PhotometricInterpretation = 'MONOCHROME2'
            ds.BitsAllocated = ds.BitsStored = 16; ds.HighBit = 15; ds.PixelRepresentation = 0
            ds.RescaleSlope = slope; ds.RescaleIntercept = intercept
            ds.WindowCenter = 2048; ds.WindowWidth = 64
            ds.PatientPosition = 'HFS'; ds.Manufacturer = 'Horos Synthetic QA'
            if modality == 'PT':
                ds.Units = 'BQML'; ds.SeriesType = ['STATIC','IMAGE']; ds.DecayCorrection = 'NONE'
                ds.CountsSource = 'EMISSION'; ds.CorrectedImage = []; ds.ActualFrameDuration = 1000
                ds.NumberOfSlices = 16; ds.RescaleType = 'BQML'
                ds.RadiopharmaceuticalInformationSequence = []
            else:
                ds.NumberOfFrames = 1; ds.NumberOfEnergyWindows = 1; ds.NumberOfDetectors = 1
                ds.FrameIncrementPointer = [Tag(0x00540010),Tag(0x00540020)]
                ds.EnergyWindowVector = [1]; ds.DetectorVector = [1]
                detector = Dataset(); detector.ImageOrientationPatient = ds.ImageOrientationPatient
                detector.ImagePositionPatient = ds.ImagePositionPatient
                ds.DetectorInformationSequence = [detector]
                ds.EnergyWindowInformationSequence = [Dataset()]
            ds.PixelData = stored.tobytes()
            ds.save_as(path, enforce_file_format=True)
            records.append({'path':str(path.relative_to(output)), 'modality':modality, 'index':index,
                            'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
    manifest = {'version':1, 'synthetic':True, 'shutter':shutter, 'rows':256, 'columns':256, 'frames_per_series':16,
                'level':2048, 'width_window':64, 'output_size':[512,512], 'palette':PALETTE,
                'tolerances':{'maximum_channel_error':1,'unexpected_clut_colors':0,
                              'calibrated_pixel_error':0},
                'lesions':[[80,80,20,8],[176,80,16,16],[80,176,12,-8],[176,176,8,-16]],
                'files':records}
    (output/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    (output/'README.md').write_text('Synthetic A111 data only. Import NM or PT separately.\n'
        'The discrete display CLUT is in manifest.json; DICOM remains MONOCHROME2.\n'
        'PT uses BQML=stored*0.25-64, NM direct counts. Disks have ±8/±16 over 2048.\n'
        'Rows 0..15 are an interpolation-order control, not part of the low-contrast disks.\n'
        'No diagnostic claims, photon noise simulation, SUV or acquisition conformance certification.\n')
    print(f'Generated 32 synthetic DICOM instances at {output}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output',type=Path)
    parser.add_argument('--shutter',action='store_true',help='Distinct series UIDs with a rectangular DICOM shutter')
    args = parser.parse_args()
    generate(args.output, args.shutter)
