#!/usr/bin/env python3
"""Create a known spline ROI for the synthetic Crossref Axial acceptance image."""
import argparse,json,uuid
from pathlib import Path
import pydicom

def generate(image,output,anisotropic_image=None):
    if output.exists() or (anisotropic_image and anisotropic_image.exists()):
        raise FileExistsError('Use new output paths')
    ds=pydicom.dcmread(image,stop_before_pixels=anisotropic_image is None)
    if str(ds.PatientID)!='LOCAL-CROSS-REFERENCE' or str(ds.SeriesDescription)!='Crossref Axial':
        raise ValueError('Use the synthetic Crossref Axial fixture, not patient data')
    if anisotropic_image:
        def uid(value):
            return '2.25.'+str(uuid.uuid5(uuid.NAMESPACE_URL,'urn:horos:roi-length-anisotropic:'+value).int)
        ds.SeriesInstanceUID=uid(str(ds.SeriesInstanceUID))
        ds.SOPInstanceUID=uid(str(ds.SOPInstanceUID))
        ds.file_meta.MediaStorageSOPInstanceUID=ds.SOPInstanceUID
        ds.SeriesDescription='Crossref Axial Anisotropic'
        ds.SeriesNumber=101
        ds.PixelSpacing=[2,0.5]
        ds.save_as(anisotropic_image,enforce_file_format=True)
    document={
        'format':'org.horosproject.roi-interchange','version':1,
        'coordinateSystems':{'pixel':'Top-left pixel corner, x right and y down','patient':'DICOM LPS millimetres'},
        'series':{'studyInstanceUID':str(ds.StudyInstanceUID),'seriesInstanceUID':str(ds.SeriesInstanceUID),'frameOfReferenceUID':str(ds.FrameOfReferenceUID)},
        'images':[{'index':int(ds.InstanceNumber)-1,'sopInstanceUID':str(ds.SOPInstanceUID),'frame':0,
                   'rows':int(ds.Rows),'columns':int(ds.Columns),'pixelSpacing':[float(ds.PixelSpacing[1]),float(ds.PixelSpacing[0])],
                   'imagePositionPatient':[float(x) for x in ds.ImagePositionPatient],
                   'imageOrientationPatient':[float(x) for x in ds.ImageOrientationPatient],
                   'rois':[{'name':'QA Spline Length','type':'openPolygon','isSpline':True,
                            'points':[[5,5],[10,22],[20,7],[26,22]],'color':[1,1,0],'thickness':2}]}]
    }
    with output.open('x') as f:json.dump(document,f,indent=2)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('image',type=Path);p.add_argument('output',type=Path)
    p.add_argument('--anisotropic-image',type=Path,help='Also create a synthetic DICOM with x=0.5 mm, y=2 mm and distinct series/instance UIDs')
    a=p.parse_args();generate(a.image,a.output,a.anisotropic_image)
