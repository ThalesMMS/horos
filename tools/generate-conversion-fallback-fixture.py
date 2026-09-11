#!/usr/bin/env python3
"""Generate a valid MPEG-2 DICOM without a helper decoder and a truncated input.

Requires pydicom and ffmpeg. The existing JPEG-series generator supplies the
synthetic metadata template; no historical images are read.
"""
import argparse
import hashlib
import json
import runpy
import subprocess
from pathlib import Path

from pydicom.encaps import encapsulate
from pydicom.uid import MPEG2MPML, VideoPhotographicImageStorage

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('destination', type=Path)
args = parser.parse_args()
out = args.destination
out.mkdir(parents=True, exist_ok=True)
if any(out.iterdir()):
    parser.error('Use an empty destination')
template = runpy.run_path(str(Path(__file__).with_name('generate-jpeg-series-fixture.py')))
stream = out / 'stream.m2v'
subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'testsrc2=size=64x64:rate=25',
                '-frames:v', '4', '-c:v', 'mpeg2video', '-f', 'mpeg2video', str(stream)], check=True)
path = out / 'unsupported-video.dcm'
ds = template['dataset'](path, 'conversion-video', True)
ds.SOPClassUID = ds.file_meta.MediaStorageSOPClassUID = VideoPhotographicImageStorage
ds.file_meta.TransferSyntaxUID = MPEG2MPML
ds.PatientID = 'LOCAL-CONVERSION'
ds.PatientName = 'QA^ConversionFallback'
ds.Modality = 'XC'
ds.NumberOfFrames = 4
ds.FrameTime = 40
ds.FrameIncrementPointer = [0x00181063]
ds.SamplesPerPixel = 3
ds.PhotometricInterpretation = 'YBR_PARTIAL_420'
ds.PlanarConfiguration = 0
ds.LossyImageCompression = '01'
ds.PixelData = encapsulate([stream.read_bytes()])
ds['PixelData'].is_undefined_length = True
ds.save_as(path, enforce_file_format=True)
(out / 'truncated.dcm').write_bytes(path.read_bytes()[:180])
manifest = {p.name: {'bytes': p.stat().st_size, 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}
            for p in out.glob('*.dcm')}
(out / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
print(json.dumps(manifest, indent=2))
