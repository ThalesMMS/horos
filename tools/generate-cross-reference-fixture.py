#!/usr/bin/env python3
"""Generate orthogonal MR planes plus an incompatible-frame control series.

`--parallel-pair` emits a different set: three **axial** series over the same
geometry, series 5, 6 and 7 of the same study. A and B share a frame of
reference; C has a different one.

`--oblique` adds series 8, tilted 45 degrees around patient Y. Its middle plane
contains patient point (8, 8, 8), also covered by the orthogonal and parallel
sets. Pixel values sample 256 + X + 2Y + 3Z in patient millimetres, rounded to
unsigned 16-bit integers; the offset keeps the oblique extent nonnegative.

The orthogonal set cannot demonstrate slice-to-slice synchronisation, because
moving an axial slice along Z correctly leaves a sagittal series where it is; a
pair that varies along the same axis is what shows two viewers following each
other (#373, criterion A294). Nor can it demonstrate the frame-of-reference
refusal (A295): a series that would stay put for a geometric reason proves
nothing about the frame. C exists so that geometry is held constant and only the
frame differs.
"""
import argparse, math, uuid
from pathlib import Path
from pydicom.dataset import FileDataset, FileMetaDataset
from pydicom.uid import MRImageStorage, ExplicitVRLittleEndian

def uid(value):
    return '2.25.' + str(uuid.uuid5(uuid.NAMESPACE_URL, 'urn:horos:cross-reference:' + value).int)

ORTHOGONAL = [('Crossref Axial','axial','common'), ('Crossref Sagittal','sagittal','common'),
              ('Crossref Coronal','coronal','common'), ('Crossref Unrelated','sagittal','unrelated')]
# Same axis, same frame: the pair that can show two viewers following each other.
# Pair C is the control for the refusal: identical geometry, different frame of
# reference, so only the frame can explain a viewer that does not follow. The
# orthogonal control cannot play that part, because its slices vary along
# another axis and would stay put for a geometric reason anyway.
PARALLEL = [('Crossref Axial Pair A','axial','common'),
            ('Crossref Axial Pair B','axial','common'),
            ('Crossref Axial Pair C','axial','unrelated')]
OBLIQUE = [('Crossref Oblique','oblique','common')]

def generate(output, parallel=False, oblique=False):
    if parallel and oblique: raise ValueError('Choose one fixture set')
    output.mkdir(parents=True,exist_ok=True)
    if any(output.iterdir()): raise ValueError('Use an empty output directory')
    series = OBLIQUE if oblique else (PARALLEL if parallel else ORTHOGONAL)
    first = 8 if oblique else (5 if parallel else 1)
    for number,(name,plane,frame) in enumerate(series,first):
        for index in range(16):
            meta=FileMetaDataset();meta.MediaStorageSOPClassUID=MRImageStorage
            meta.MediaStorageSOPInstanceUID=uid(f'image-{number}-{index}');meta.TransferSyntaxUID=ExplicitVRLittleEndian
            ds=FileDataset(str(output/f'{number:02d}-{index:02d}.dcm'),{},file_meta=meta,preamble=b'\0'*128)
            ds.SOPClassUID=MRImageStorage;ds.SOPInstanceUID=meta.MediaStorageSOPInstanceUID
            ds.StudyInstanceUID=uid('study');ds.SeriesInstanceUID=uid(f'series-{number}');ds.FrameOfReferenceUID=uid(frame)
            ds.PatientName='QA^Cross Reference';ds.PatientID='LOCAL-CROSS-REFERENCE';ds.StudyID='CROSSREF'
            ds.StudyDescription='Cross Reference Acceptance';ds.SeriesDescription=name
            ds.StudyDate=ds.SeriesDate=ds.ContentDate='20260907';ds.StudyTime=ds.SeriesTime=ds.ContentTime='120000'
            ds.Modality='MR';ds.SeriesNumber=number;ds.InstanceNumber=index+1
            ds.ImageType=['ORIGINAL','PRIMARY','OTHER'];ds.Rows=ds.Columns=32
            ds.PixelSpacing=[1,1];ds.SliceThickness=1;ds.SpacingBetweenSlices=1
            if plane=='oblique':
                diagonal=math.sqrt(0.5)
                row=(diagonal,0,-diagonal);column=(0,1,0);normal=(diagonal,0,diagonal)
                position=tuple(8-15.5*row[i]-15.5*column[i]+(index-8)*normal[i] for i in range(3))
                ds.ImageOrientationPatient=[format(v,'.12g') for v in (*row,*column)]
                ds.ImagePositionPatient=[format(v,'.12g') for v in position]
                ds.SliceLocation=format(sum(position[i]*normal[i] for i in range(3)),'.12g')
                points=(tuple(position[i]+x*row[i]+y*column[i] for i in range(3))
                        for y in range(32) for x in range(32))
            elif plane=='axial':
                ds.ImageOrientationPatient=[1,0,0,0,1,0];ds.ImagePositionPatient=[0,0,index];ds.SliceLocation=index
                points=((x,y,index) for y in range(32) for x in range(32))
            elif plane=='sagittal':
                ds.ImageOrientationPatient=[0,1,0,0,0,1];ds.ImagePositionPatient=[index,0,0];ds.SliceLocation=index
                points=((index,x,y) for y in range(32) for x in range(32))
            else:
                ds.ImageOrientationPatient=[1,0,0,0,0,1];ds.ImagePositionPatient=[0,index,0];ds.SliceLocation=-index
                points=((x,index,y) for y in range(32) for x in range(32))
            ds.SamplesPerPixel=1;ds.PhotometricInterpretation='MONOCHROME2';ds.PixelRepresentation=0
            ds.BitsAllocated=ds.BitsStored=16;ds.HighBit=15;ds.WindowCenter=304 if oblique else 100;ds.WindowWidth=200
            ds.PixelData=b''.join(round((256 if oblique else 0)+x+2*y+3*z).to_bytes(2,'little') for x,y,z in points)
            ds.save_as(ds.filename,enforce_file_format=True)
    if oblique:
        print('Generated 16 oblique MR images sharing the common frame, with patient landmark (8, 8, 8).')
    elif parallel:
        print('Generated 48 MR images: two parallel axial series sharing a frame of reference, '
              'plus a third with the same geometry and a different frame.')
    else:
        print('Generated 64 MR images: axial, sagittal, coronal, and different-frame sagittal control.')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__,
                              formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('output',type=Path)
    group=p.add_mutually_exclusive_group()
    group.add_argument('--parallel-pair',action='store_true',
                       help='three parallel axial series instead of the orthogonal set')
    group.add_argument('--oblique',action='store_true',
                       help='one oblique series sharing the common frame')
    a=p.parse_args()
    generate(a.output, parallel=a.parallel_pair, oblique=a.oblique)
