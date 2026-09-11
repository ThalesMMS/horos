#!/usr/bin/env python3
"""Generate a synthetic CT plus matching binary SEG for native #377 surface validation."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import numpy as np
import pydicom
from pydicom.dataset import FileDataset, FileMetaDataset
from pydicom.uid import CTImageStorage, ExplicitVRLittleEndian, generate_uid

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('output', type=Path)
parser.add_argument('--latency', type=int, metavar='SIZE', default=0,
                    help='write a SIZE x SIZE x SIZE/2 CT with one sphere and one shell SEG for import latency instead of the topology phantom')
args = parser.parse_args()
out = args.output.resolve()
if out == root or root in out.parents:
    raise SystemExit('output must be outside the repository')
if out.exists() and any(out.iterdir()):
    raise SystemExit('output must be empty')
out.mkdir(parents=True, exist_ok=True)
(out/'source-ct').mkdir()
rows = columns = args.latency or 32
frames = (args.latency // 2) if args.latency else 16
study, series, frame_uid = generate_uid(), generate_uid(), generate_uid()
refs = [generate_uid() for _ in range(frames)]
z, y, x = np.indices((frames, rows, columns))
if args.latency:
    radius = rows / 2.0 - 2
    distance = np.sqrt((x + 0.5 - columns / 2.0) ** 2 + (y + 0.5 - rows / 2.0) ** 2 + (2 * (z + 0.5) - frames) ** 2)
    masks = [distance <= radius * 0.55, (distance <= radius) & (distance > radius * 0.8)]
else:
  masks = [
    (x >= 1) & (x < 8) & (y >= 1) & (y < 8) & (z < 5),
    (x >= 10) & (x < 20) & (y >= 2) & (y < 12) & ~((x >= 13) & (x < 17) & (y >= 5) & (y < 9)),
    (x >= 22) & (x < 30) & (y >= 2) & (y < 10) & (z >= 3) & (z < 13)
        & ~((x >= 24) & (x < 28) & (y >= 4) & (y < 8) & (z >= 5) & (z < 11)),
    ((x >= 1) & (x < 5) & (y >= 20) & (y < 24) & (z >= 3) & (z < 7))
        | ((x >= 9) & (x < 13) & (y >= 25) & (y < 29) & (z >= 10) & (z < 14))]
for index, sop in enumerate(refs):
    meta = FileMetaDataset()
    meta.MediaStorageSOPClassUID = CTImageStorage
    meta.MediaStorageSOPInstanceUID = sop
    meta.TransferSyntaxUID = ExplicitVRLittleEndian
    path = out/'source-ct'/f'{index+1:03}.dcm'
    image = FileDataset(str(path), {}, file_meta=meta, preamble=b'\0'*128)
    image.SOPClassUID = CTImageStorage; image.SOPInstanceUID = sop
    image.StudyInstanceUID = study; image.SeriesInstanceUID = series; image.FrameOfReferenceUID = frame_uid
    image.PatientName = 'SEG^SURFACE^SYNTHETIC'; image.PatientID = 'SYNTHETIC-377' + ('-LATENCY' if args.latency else '')
    image.StudyDate = '20260913'; image.StudyTime = '120000'; image.Modality = 'CT'
    image.StudyDescription = 'Synthetic SEG topology'; image.SeriesDescription = 'Surface latency CT' if args.latency else 'Surface source CT'
    image.SeriesNumber = 1; image.InstanceNumber = index + 1
    image.Rows = rows; image.Columns = columns; image.PixelSpacing = [1, 1]
    image.SliceThickness = 2; image.SpacingBetweenSlices = 2
    image.ImageOrientationPatient = [1, 0, 0, 0, 1, 0]
    image.ImagePositionPatient = [-rows/2, -rows/2, -frames + 2*index]
    image.SamplesPerPixel = 1; image.PhotometricInterpretation = 'MONOCHROME2'
    image.BitsAllocated = 16; image.BitsStored = 16; image.HighBit = 15; image.PixelRepresentation = 1
    image.RescaleSlope = 1; image.RescaleIntercept = 0; image.WindowCenter = 300; image.WindowWidth = 1200
    pixels = np.full((rows, columns), -700, dtype='<i2')
    for number, mask in enumerate(masks): pixels[mask[index]] = 200 + number*200
    image.PixelData = pixels.tobytes()
    image.save_as(path, enforce_file_format=True)

with tempfile.TemporaryDirectory(prefix='horos-seg-generator-') as folder:
    tmp = Path(folder)
    for index, mask in enumerate(masks): (tmp/f'{index}.mask').write_bytes(mask.astype('uint8').tobytes())
    driver = r'''
import Foundation
let args = CommandLine.arguments
let refs = args[5].components(separatedBy: ",")
let rows = Int(args[6])!, frames = Int(args[7])!, count = Int(args[8])!
let plane = rows * rows
let geometry = DicomSEGGeometry(rows:rows, columns:rows, frames:frames,
    spacingRow:1, spacingCol:1, sliceThickness:2, origin:[-Double(rows)/2,-Double(rows)/2,-Double(frames)],
    orientation:[1,0,0,0,1,0], frameOfReferenceUID:args[4],
    frameOrigins:(0..<frames).map { [-Double(rows)/2,-Double(rows)/2,Double(-frames + 2*$0)] })
let names = count == 4 ? ["Border solid", "Through tube", "Internal cavity", "Separate components"] : ["Large sphere", "Large shell"]
let colors:[(Double,Double,Double)] = [(1,0.2,0.1),(0.1,1,0.2),(0.2,0.4,1),(1,0.8,0.1)]
var segments:[DicomSEGSegment] = []
for i in 0..<count {
    let data = try Data(contentsOf:URL(fileURLWithPath:args[1]).appendingPathComponent("\(i).mask"))
    segments.append(DicomSEGSegment(number:UInt16(i+1),label:names[i],trackingUID:DicomSEGCodec.makeUID(),
        color:colors[i],visible:true,kind:.binary,algorithm:"MANUAL",provenance:"synthetic topology phantom",
        referencedSOPInstanceUIDs:refs,frames:(0..<frames).map { data.subdata(in:$0*plane..<($0+1)*plane) },maximumFractionalValue:1))
}
let identity = DicomSEGIdentity(sopInstanceUID:DicomSEGCodec.makeUID(),seriesInstanceUID:DicomSEGCodec.makeUID(),
    studyInstanceUID:args[3],frameOfReferenceUID:args[4],sourceSOPInstanceUIDs:refs)
let document = DicomSEGDocument(identity:identity,geometry:geometry,kind:.binary,segments:segments,diagnoses:[],sourceBytes:nil)
try DicomSEGCodec.encode(document).write(to:URL(fileURLWithPath:args[2]))
'''
    (tmp/'main.swift').write_text(driver)
    subprocess.run(['xcrun','swiftc',str(root/'Horos/Sources/DicomSEG.swift'),str(tmp/'main.swift'),'-o',str(tmp/'generate')],check=True)
    subprocess.run([str(tmp/'generate'),str(tmp),str(out/'surfaces.dcm'),study,frame_uid,','.join(refs),str(rows),str(frames),str(len(masks))],check=True)
seg = pydicom.dcmread(out/'surfaces.dcm')
assert np.array_equal(seg.pixel_array, np.concatenate(masks,axis=0).astype('uint8'))
files = {str(p.relative_to(out)): hashlib.sha256(p.read_bytes()).hexdigest() for p in out.rglob('*.dcm')}
(out/'manifest.json').write_text(json.dumps({'synthetic':True,'rows':rows,'columns':columns,'frames':frames,
    'volumeMm3':[int(m.sum())*2 for m in masks],'sha256':files},indent=2)+'\n')
print(json.dumps({'output':str(out),'sourceSlices':frames,'segments':len(masks),'volumeMm3':[int(m.sum())*2 for m in masks]}))
