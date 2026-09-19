#!/usr/bin/env python3
"""Physical Length JSON uses version 2 and series/phase identity, never coplanarity."""
from pathlib import Path
import subprocess,tempfile
root=Path(__file__).resolve().parents[1]
code=r'''
import Foundation
import AppKit
let series=ROIInterchangeSeries(); series.seriesInstanceUID="series";series.frameOfReferenceUID="frame"
let image=ROIInterchangeImage();image.rows=32;image.columns=32;image.pixelSpacingX=1;image.pixelSpacingY=2
image.imagePosition=[0,0,0];image.imageOrientation=[1,0,0,0,1,0];image.temporalIndex=1
let roi=ROIInterchangeROI();roi.name="Length";roi.typeCode=5;roi.points=[NSValue(point:.zero),NSValue(point:NSPoint(x:3,y:2))];roi.patientPoints=[[0,0,0],[3,4,12]]
let reference:[String:Any] = ["sopInstanceUID":"sop","frame":0,"generated":NSNumber(value:0),"imagePositionPatient":[0,0,0],"imageOrientationPatient":[1,0,0,0,1,0],"pixelSpacing":[1,2]]
roi.volumeLength=["version":1,"id":"uuid","series":"series","frameOfReference":"frame","temporalIndex":1,"a":[0,0,0],"b":[3,4,12],"referenceA":reference,"referenceB":reference]
image.rois=[roi];series.images=[image]
let data=try ROIInterchange.encode(series,generator:nil)
let root=try JSONSerialization.jsonObject(with:data) as! [String:Any];precondition(root["version"] as! Int==2)
let decoded=try ROIInterchange.decode(data);let physical=decoded.images[0].rois[0].volumeLength!
precondition(physical["a"] as! [Double] == [0,0,0] && physical["b"] as! [Double] == [3,4,12])
precondition(physical["id"] as! String == "uuid")
let target=ROIInterchangeSeries();target.seriesInstanceUID="series";target.frameOfReferenceUID="frame"
let plane=ROIInterchangeImage();plane.temporalIndex=1;plane.rows=32;plane.columns=32;plane.pixelSpacingX=1;plane.pixelSpacingY=1;plane.imagePosition=[0,7,0];plane.imageOrientation=[1,0,0,0,0,1];target.images=[plane]
precondition(ROIAssociation.plan(document:decoded,against:target).canApply) // endpoints deliberately not coplanar with this coronal slice
plane.temporalIndex=0;precondition(!ROIAssociation.plan(document:decoded,against:target).canApply);plane.temporalIndex=1
target.seriesInstanceUID="other";precondition(!ROIAssociation.plan(document:decoded,against:target).canApply);target.seriesInstanceUID="series"
target.frameOfReferenceUID="other";precondition(!ROIAssociation.plan(document:decoded,against:target).canApply)
var invalid=root;invalid["version"]=1
var refused=false;do{_ = try ROIInterchange.decode(JSONSerialization.data(withJSONObject:invalid))}catch{refused=true};precondition(refused)
roi.volumeLength!["b"]=[0,0,0];refused=false;do{_=try ROIInterchange.encode(series,generator:nil)}catch{refused=true};precondition(refused)
roi.volumeLength=nil;roi.patientPoints=[[0,0,0],[3,4,0]]
let legacy=try ROIInterchange.encode(series,generator:nil);let old=try JSONSerialization.jsonObject(with:legacy) as! [String:Any];precondition(old["version"] as! Int==1)
precondition(try ROIInterchange.decode(legacy).images[0].rois[0].volumeLength==nil)
print("PASS: archive BOOL normalization, version 2, endpoints, identity/phase, noncoplanar import, invalid and legacy payloads")
'''.replace('precondition(try ROIInterchange.decode(legacy).images[0].rois[0].volumeLength==nil)','let oldDecoded=try ROIInterchange.decode(legacy);precondition(oldDecoded.images[0].rois[0].volumeLength==nil)')
with tempfile.TemporaryDirectory(prefix='horos-length-json-') as d:
 p=Path(d);(p/'main.swift').write_text(code)
 subprocess.run(['xcrun','swiftc',*[str(root/'Horos/Sources'/n) for n in ['ROIIntersliceGeometry.swift','ROIInterchange.swift','ROIArchiveFormat.swift','ROIAssociation.swift']],str(p/'main.swift'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
