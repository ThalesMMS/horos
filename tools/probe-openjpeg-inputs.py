#!/usr/bin/env python3
"""Validate JPEG2000 EOF handling through the built object and Decompress helper.

Requires pydicom, numpy and imagecodecs. OUTPUT must be empty and outside Git.
Creates synthetic JP2/J2K controls, malformed inputs and disposable conversions.
"""
import argparse
import copy
import hashlib
import importlib.util
import json
import plistlib
from pathlib import Path
import subprocess
import time

import imagecodecs
import numpy as np
import pydicom
from pydicom.encaps import encapsulate
from pydicom.uid import JPEG2000Lossless, ExplicitVRLittleEndian

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('output', type=Path)
args = parser.parse_args()
if not __debug__:
    parser.error('Run without -O so validation assertions remain enabled')
output = args.output.resolve()
if output.is_relative_to(ROOT):
    parser.error('Keep generated fixtures outside the checkout')
if output.exists() and (not output.is_dir() or any(output.iterdir())):
    parser.error('Use an empty output directory')
output.mkdir(parents=True, exist_ok=True)
helper = ROOT/'build/Development/HorosDevelopment.app/Contents/Resources/Decompress'
build = ROOT/'build/Build/Intermediates.noindex/Horos.build/Debug'
obj = build/'Decompress.build/Objects-normal/arm64/OPJSupport.o'
archive = build/'OpenJPEG.build/Install/lib/libopenjp2.a'
assert all(p.is_file() for p in (helper, obj, archive)), 'Build with script/build_and_run.sh --verify first'

driver = r'''
#include "OPJSupport.h"
#include <fstream>
#include <vector>
#include <cstdlib>
int main(int argc,char**argv) {
    if(argc!=3)return 2;
    std::ifstream in(argv[1],std::ios::binary);
    std::vector<char> data((std::istreambuf_iterator<char>(in)),{});
    long size=0;int color=-1;OPJSupport codec;
    void* pixels=codec.decompressJPEG2K(data.data(),data.size(),&size,&color);
    if(!pixels)return 1;
    std::ofstream result(argv[2],std::ios::binary);result.write((char*)pixels,size);
    free(pixels);return result?0:3;
}
'''
(output/'probe.cc').write_text(driver)
subprocess.run(['xcrun','clang++','-std=c++11','-I'+str(ROOT/'Horos/Sources'),
    str(output/'probe.cc'),str(obj),str(archive),'-o',str(output/'probe')],check=True)
spec = importlib.util.spec_from_file_location('fixture', ROOT/'tools/generate-dimse-matrix-fixture.py')
fixture = importlib.util.module_from_spec(spec);spec.loader.exec_module(fixture)
fixture.generate(output/'source')
single = pydicom.dcmread(output/'source/ct-explicit.dcm')
multi = pydicom.dcmread(output/'source/us-multiframe.dcm')
settings = output/'settings.plist'
settings.write_bytes(plistlib.dumps({'DecompressMoveIfFail':False}))
results = []
raw_controls = {}
pixels = single.pixel_array
for container in ('J2K','JP2'):
    for bits in (12,16):
        name = f'{container}-{bits}'
        encoded = imagecodecs.jpeg2k_encode(pixels,level=0,reversible=True,
            codecformat=container,bitspersample=bits)
        raw_controls[name] = encoded
        source = output/(name+'.j2k');source.write_bytes(encoded)
        destination = output/(name+'.raw')
        started = time.monotonic()
        subprocess.run([str(output/'probe'),str(source),str(destination)],
            check=True,capture_output=True,timeout=5)
        assert destination.read_bytes() == pixels.astype('<u2').tobytes(), name
        results.append(dict(case=name,route='built-object',pixelsMatch=True,
            seconds=round(time.monotonic()-started,3)))

malformed = {'jp2-signature-only':raw_controls['JP2-12'][:12],
    'jp2-header-truncated':raw_controls['JP2-12'][:40],
    'j2k-header-truncated':raw_controls['J2K-12'][:16]}
for name, encoded in malformed.items():
    source = output/(name+'.j2k');source.write_bytes(encoded)
    destination = output/(name+'.raw')
    result = subprocess.run([str(output/'probe'),str(source),str(destination)],
        capture_output=True,timeout=5)
    assert result.returncode == 1 and not destination.exists(), name
    results.append(dict(case=name,route='built-object',rejected=True))

for name, template, container, invalid in [
    ('single-j2k',single,'J2K',None),('single-jp2',single,'JP2',None),
    ('multi-j2k',multi,'J2K',None),('multi-jp2',multi,'JP2',None),
    *[(name,single,None,encoded) for name,encoded in malformed.items()]]:
    case = output/name;case.mkdir()
    pixels = template.pixel_array
    frames = pixels.reshape(-1,int(template.Rows),int(template.Columns))
    ds = copy.deepcopy(template)
    ds.file_meta = template.file_meta.copy()
    ds.file_meta.TransferSyntaxUID = JPEG2000Lossless
    encoded = [invalid] if invalid is not None else [imagecodecs.jpeg2k_encode(frame,
        codecformat=container,bitspersample=12,level=0,reversible=True) for frame in frames]
    ds.PixelData = encapsulate(encoded);ds['PixelData'].is_undefined_length = True
    ds['PixelData'].VR = 'OB'
    source = case/'input.dcm';ds.save_as(source,enforce_file_format=True)
    original = source.read_bytes()
    destination = case/'destination';destination.mkdir();target = destination/source.name
    target.write_bytes(b'previous destination')
    started = time.monotonic()
    result = subprocess.run([str(helper),str(destination),'SettingsPlist',str(settings),
        'decompressList',str(source)],capture_output=True,timeout=5)
    if invalid is not None:
        assert result.returncode == 1, (name, result.returncode, result.stderr)
        diagnostic = b'Could not convert pixel Data to ExplicitVRLittleEndian'
        assert diagnostic in result.stdout + result.stderr, (name, result.stdout, result.stderr)
        assert source.read_bytes() == original and target.read_bytes() == b'previous destination', name
        verdict = dict(rejected=True,sourcePreserved=True,destinationPreserved=True,
            exitCode=result.returncode,diagnostic=diagnostic.decode())
    else:
        assert result.returncode == 0, (name,result.stderr)
        actual = pydicom.dcmread(target)
        assert actual.file_meta.TransferSyntaxUID == ExplicitVRLittleEndian
        assert actual.SOPInstanceUID == template.SOPInstanceUID
        assert int(getattr(actual,'NumberOfFrames',1)) == len(frames)
        assert np.array_equal(actual.pixel_array,pixels), name
        verdict = dict(frames=len(frames),pixelsMatch=True)
    (case/'helper-stderr.txt').write_bytes(result.stderr)
    (case/'helper-stdout.txt').write_bytes(result.stdout)
    results.append(dict(case=name,route='helper',seconds=round(time.monotonic()-started,3),**verdict))

for entry in json.loads((output/'source/manifest.json').read_text())['instances']:
    assert hashlib.sha256((output/'source'/entry['file']).read_bytes()).hexdigest() == entry['sha256']
(output/'results.json').write_text(json.dumps(results,indent=2)+'\n')
for result in results: print(json.dumps(result),flush=True)
print('PASS: built decoder and helper terminate, preserve failures, and retain independent pixels/frames')
