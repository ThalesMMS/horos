#!/usr/bin/env python3
"""Synthetic CT plus Grayscale Softcopy Presentation State objects.

The destination must be empty. Nothing here is a clinical image. The GSPS files
exercise the documented subset in docs/gsps-subset.md: matching by SOP Instance
UID and frame, Softcopy VOI, displayed area, spatial transform, PIXEL/DISPLAY
annotations, a missing reference, and modules that must be flagged as
unsupported.
"""
import argparse
from pathlib import Path

import numpy
from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.sequence import Sequence
from pydicom.uid import (
    CTImageStorage,
    ExplicitVRLittleEndian,
    generate_uid,
)

GSPS = '1.2.840.10008.5.1.4.1.1.11.1'
COLOR_PS = '1.2.840.10008.5.1.4.1.1.11.2'


def meta(sop_class, instance):
    file_meta = FileMetaDataset()
    file_meta.MediaStorageSOPClassUID = sop_class
    file_meta.MediaStorageSOPInstanceUID = instance
    file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
    file_meta.ImplementationClassUID = generate_uid()
    return file_meta


def patient(dataset, study, series, instance, sop_class, modality, description):
    dataset.file_meta = meta(sop_class, instance)
    dataset.SpecificCharacterSet = 'ISO_IR 100'
    dataset.SOPClassUID = sop_class
    dataset.SOPInstanceUID = instance
    dataset.StudyInstanceUID = study
    dataset.SeriesInstanceUID = series
    dataset.PatientName = 'GSPS^SYNTHETIC'
    dataset.PatientID = 'GSPS-87'
    dataset.PatientBirthDate = '19700101'
    dataset.PatientSex = 'O'
    dataset.StudyDate = dataset.ContentDate = '20260101'
    dataset.StudyTime = dataset.ContentTime = '120000'
    dataset.AccessionNumber = 'GSPS87'
    dataset.StudyID = '87'
    dataset.Modality = modality
    dataset.StudyDescription = 'synthetic GSPS subset'
    dataset.SeriesDescription = description
    dataset.InstanceNumber = 1


def save(dataset, folder, name):
    path = folder / ('%s.dcm' % name)
    dataset.save_as(str(path), enforce_file_format=True)
    print('%-18s %s' % (name, dataset.SeriesDescription))


def referenced_image(sop_class, sop_instance, frames=None):
    item = Dataset()
    item.ReferencedSOPClassUID = sop_class
    item.ReferencedSOPInstanceUID = sop_instance
    if frames:
        item.ReferencedFrameNumber = frames
    return item


def referenced_series(series_uid, images):
    item = Dataset()
    item.SeriesInstanceUID = series_uid
    item.ReferencedImageSequence = Sequence(images)
    return item


def gsps_common(study, series, instance, description):
    dataset = Dataset()
    patient(dataset, study, series, instance, GSPS, 'PR', description)
    dataset.PresentationCreationDate = '20260101'
    dataset.PresentationCreationTime = '120000'
    dataset.ContentLabel = 'GSPS87'
    dataset.ContentDescription = description
    dataset.PresentationCreatorName = 'HOROS^TEST'
    return dataset


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('destination', type=Path, help='an empty directory for the files')
    arguments = parser.parse_args()
    arguments.destination.mkdir(parents=True, exist_ok=True)
    if any(arguments.destination.iterdir()):
        raise SystemExit('%s is not empty' % arguments.destination)

    study = generate_uid()
    ct_series = generate_uid()
    ct_sop = generate_uid()
    mf_series = generate_uid()
    mf_sop = generate_uid()

    ct = Dataset()
    patient(ct, study, ct_series, ct_sop, CTImageStorage, 'CT', 'referenced CT')
    ct.SeriesNumber = 1
    ct.Rows = ct.Columns = 32
    ct.SamplesPerPixel = 1
    ct.PhotometricInterpretation = 'MONOCHROME2'
    ct.BitsAllocated = ct.BitsStored = 16
    ct.HighBit = 15
    ct.PixelRepresentation = 0
    ct.WindowCenter = 2000
    ct.WindowWidth = 4000
    ct.PixelSpacing = [1.0, 1.0]
    ramp = numpy.tile(numpy.linspace(0, 4000, 32), (32, 1)).astype(numpy.uint16)
    ct.PixelData = ramp.tobytes()
    save(ct, arguments.destination, 'ct-ref')

    mf = Dataset()
    patient(mf, study, mf_series, mf_sop, CTImageStorage, 'CT', 'two-frame CT')
    mf.SeriesNumber = 2
    mf.NumberOfFrames = 2
    mf.Rows = mf.Columns = 16
    mf.SamplesPerPixel = 1
    mf.PhotometricInterpretation = 'MONOCHROME2'
    mf.BitsAllocated = mf.BitsStored = 16
    mf.HighBit = 15
    mf.PixelRepresentation = 0
    frames = numpy.stack([
        numpy.full((16, 16), 100, dtype=numpy.uint16),
        numpy.full((16, 16), 200, dtype=numpy.uint16),
    ])
    mf.PixelData = frames.tobytes()
    save(mf, arguments.destination, 'ct-multiframe')

    apply = gsps_common(study, generate_uid(), generate_uid(),
                        'VOI transform annotations')
    apply.SeriesNumber = 10
    apply.ReferencedSeriesSequence = Sequence([
        referenced_series(ct_series, [referenced_image(CTImageStorage, ct_sop, [1])]),
    ])
    apply.ImageRotation = 90
    apply.ImageHorizontalFlip = 'Y'
    voi = Dataset()
    voi.WindowCenter = 40
    voi.WindowWidth = 400
    apply.SoftcopyVOILUTSequence = Sequence([voi])
    area = Dataset()
    area.DisplayedAreaTopLeftHandCorner = [11, 11]
    area.DisplayedAreaBottomRightHandCorner = [20, 20]
    area.PresentationSizeMode = 'SCALE TO FIT'
    apply.DisplayedAreaSelectionSequence = Sequence([area])
    graphic = Dataset()
    graphic.GraphicAnnotationUnits = 'PIXEL'
    graphic.GraphicDimensions = 2
    graphic.NumberOfGraphicPoints = 2
    graphic.GraphicData = [10.0, 20.0, 30.0, 40.0]
    graphic.GraphicType = 'POLYLINE'
    display_point = Dataset()
    display_point.GraphicAnnotationUnits = 'DISPLAY'
    display_point.GraphicDimensions = 2
    display_point.NumberOfGraphicPoints = 1
    display_point.GraphicData = [0.5, 0.5]
    display_point.GraphicType = 'POINT'
    text = Dataset()
    text.AnchorPointAnnotationUnits = 'PIXEL'
    text.UnformattedTextValue = 'GSPS label'
    text.AnchorPoint = [10.0, 20.0]
    text.AnchorPointVisibility = 'Y'
    layer = Dataset()
    layer.ReferencedImageSequence = Sequence([referenced_image(CTImageStorage, ct_sop)])
    layer.GraphicObjectSequence = Sequence([graphic, display_point])
    layer.TextObjectSequence = Sequence([text])
    apply.GraphicAnnotationSequence = Sequence([layer])
    save(apply, arguments.destination, 'gsps-apply')

    missing = gsps_common(study, generate_uid(), generate_uid(),
                          'missing reference and unsupported modules')
    missing.SeriesNumber = 11
    missing.ReferencedSeriesSequence = Sequence([
        referenced_series(generate_uid(), [referenced_image(CTImageStorage, generate_uid())]),
    ])
    missing.ShutterShape = 'RECTANGULAR'
    missing.ShutterLeftVerticalEdge = 1
    missing.ShutterRightVerticalEdge = 8
    missing.ShutterUpperHorizontalEdge = 1
    missing.ShutterLowerHorizontalEdge = 8
    compound = Dataset()
    compound.CompoundGraphicInstanceID = 1
    compound.CompoundGraphicType = 'RECTANGLE'
    compound.CompoundGraphicUnits = 'PIXEL'
    missing.CompoundGraphicSequence = Sequence([compound])
    interpolated = Dataset()
    interpolated.GraphicAnnotationUnits = 'PIXEL'
    interpolated.GraphicDimensions = 2
    interpolated.NumberOfGraphicPoints = 2
    interpolated.GraphicData = [0.0, 0.0, 1.0, 1.0]
    interpolated.GraphicType = 'INTERPOLATED'
    layer = Dataset()
    layer.GraphicObjectSequence = Sequence([interpolated])
    missing.GraphicAnnotationSequence = Sequence([layer])
    save(missing, arguments.destination, 'gsps-missing')

    frame = gsps_common(study, generate_uid(), generate_uid(),
                        'frame 2 only')
    frame.SeriesNumber = 12
    frame.ReferencedSeriesSequence = Sequence([
        referenced_series(mf_series, [referenced_image(CTImageStorage, mf_sop, [2])]),
    ])
    voi = Dataset()
    voi.WindowCenter = 80
    voi.WindowWidth = 200
    frame.SoftcopyVOILUTSequence = Sequence([voi])
    save(frame, arguments.destination, 'gsps-frame')

    color = Dataset()
    patient(color, study, generate_uid(), generate_uid(), COLOR_PS, 'PR',
            'color presentation state')
    color.SeriesNumber = 13
    color.PresentationCreationDate = '20260101'
    color.PresentationCreationTime = '120000'
    color.ContentLabel = 'COLOR'
    color.ReferencedSeriesSequence = Sequence([
        referenced_series(ct_series, [referenced_image(CTImageStorage, ct_sop)]),
    ])
    save(color, arguments.destination, 'ps-color')

    print()
    print('study %s' % study)
    print('ct   %s' % ct_sop)
    print('mf   %s' % mf_sop)


if __name__ == '__main__':
    main()
