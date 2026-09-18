#!/usr/bin/env python3
"""#373/A111: independent DICOM calibration/scalar oracle versus actual Metal.

Requires a synthetic fixture from tools/generate-planar-low-contrast-fixture.py
and pydicom/numpy. All derived arrays and detailed timings stay under that
external fixture. No UI or Xcode build. No speed threshold or legacy speed claim.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('fixture',nargs='?',type=Path)
parser.add_argument('--renderer-source',type=Path,default=ROOT/'Horos/Sources/PlanarMetalRenderer.swift')
parser.add_argument('--color-first-mutant',action='store_true',
                    help='negative control: compile a deliberately wrong color-first shader; expected to fail')
args = parser.parse_args()
if args.fixture is None:
    print('needs synthetic low-contrast fixture path and a Python with pydicom/numpy',file=sys.stderr)
    raise SystemExit(2)
import numpy as np
import pydicom

fixture = args.fixture.resolve()
assert fixture.is_relative_to((ROOT.parent/'DICOM_Example').resolve()), 'fixture must stay outside Git in ../DICOM_Example'
manifest = json.loads((fixture/'manifest.json').read_text())
assert manifest['version']==1 and manifest['synthetic'] is True
assert manifest['rows']==manifest['columns']==256 and manifest['output_size']==[512,512]
assert manifest['tolerances']=={'maximum_channel_error':1,'unexpected_clut_colors':0,'calibrated_pixel_error':0}
assert manifest['level']==2048 and manifest['width_window']==64
assert len(manifest['files'])==32
palette = np.array(manifest['palette'],dtype=np.uint8)
assert palette.shape==(8,3)
clut = np.concatenate((np.repeat(palette,32,axis=0),np.full((256,1),255,dtype=np.uint8)),axis=1)
rows, columns = np.ogrid[:256,:256]
# Independent scalar reference in float64: sample calibrated intensities at
# destination pixel centres, then quantize the window and index the discrete CLUT.
coordinate = (np.arange(512,dtype=np.float64)+0.5)/2-0.5
lower = np.floor(coordinate).astype(int)
fraction = coordinate-lower
lo, hi = np.clip(lower,0,255),np.clip(lower+1,0,255)
weights = [(1-fraction[:,None])*(1-fraction[None,:]),
           (1-fraction[:,None])*fraction[None,:],
           fraction[:,None]*(1-fraction[None,:]),fraction[:,None]*fraction[None,:]]


def neighbours(values):
    return [values[lo[:,None],lo[None,:]],values[lo[:,None],hi[None,:]],
            values[hi[:,None],lo[None,:]],values[hi[:,None],hi[None,:]]]


def window(values):
    return np.floor(np.clip((values-2016)/64,0,1)*255+0.5).astype(np.int64)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


results = fixture/'validation'
results.mkdir(exist_ok=True)
with tempfile.TemporaryDirectory(prefix='a111-',dir=results) as directory:
    work = Path(directory)
    (work/'clut.rgba').write_bytes(clut.tobytes())
    inputs, wrong_order_pixels, source_hashes = [],0,{}
    for record in manifest['files']:
        path = fixture/record['path']
        assert path.resolve().is_relative_to(fixture)
        source_hashes[path] = digest(path)
        assert source_hashes[path]==record['sha256'], f'fixture changed: {record["path"]}'
        ds = pydicom.dcmread(path)
        assert ds.PatientID=='QA-A111-ONLY' and ds.Modality==record['modality']
        assert ds.Rows==ds.Columns==256 and float(ds.WindowCenter)==2048 and float(ds.WindowWidth)==64
        slope,intercept = float(ds.RescaleSlope),float(ds.RescaleIntercept)
        assert (slope,intercept)==((0.25,-64) if ds.Modality=='PT' else (1,0))
        physical = ds.pixel_array.astype(np.float64).reshape(256,256)*slope+intercept
        # Analytic independent definition, not imported from the generator.
        expected_input = np.full((256,256),2048 + record['index']%4-1,dtype=np.float64)
        for cx,cy,radius,delta in [(80,80,20,8),(176,80,16,16),(80,176,12,-8),(176,176,8,-16)]:
            mask=(columns-cx)**2+(rows-cy)**2<=radius**2
            expected_input[mask]+=delta
            assert abs(delta/2048)<=0.0078125
        expected_input[:16,:]=np.where(columns%2==0,2032,2064)
        assert np.array_equal(physical,expected_input), 'stored values or calibration disagree with analytic phantom'
        interpolated = sum(w*v for w,v in zip(weights,neighbours(physical)))
        correct = clut[window(interpolated)]
        # Independent negative control: map each source sample first, then mix
        # its colors. Count output pixels where this wrong order is detectable.
        source_colors = clut[window(physical)].astype(np.float64)
        wrong = np.floor(sum(w[:,:,None]*v for w,v in zip(weights,neighbours(source_colors)))+0.5).astype(np.uint8)
        detectable = np.max(np.abs(correct.astype(int)-wrong.astype(int)),axis=2)>1
        wrong_order_pixels += int(detectable.sum())
        assert detectable[:30,:].sum()>12000, 'control strip does not distinguish interpolation order'
        name=f'{ds.Modality}-{record["index"]:02d}'
        physical.astype('<f4').tofile(work/f'{name}.f32')
        correct[:,:,[2,1,0,3]].tofile(work/f'{name}.bgra')
        inputs.append({'id':name,'pixels':f'{name}.f32','expected':f'{name}.bgra'})
    control={'width':256,'height':256,'output_width':512,'output_height':512,
             'level':2048,'width_window':64,'frames':inputs}
    (work/'input.json').write_text(json.dumps(control))
    renderer_source=args.renderer_source
    if args.color_first_mutant:
        source=renderer_source.read_text()
        correct='''        float normalized=clamp((sampled.r-minimum)/p.window.y,0.0,1.0);
        return float4(clut.read(uint2(uint(normalized*255.0+0.5),0)).rgb,1);'''
        wrong='''        float2 xy=pixel-0.5; int2 cell=int2(floor(xy)); float2 blend=fract(xy);
        float3 color=0;
        for(int j=0;j<2;j++)for(int i=0;i<2;i++) {
            float value=image.read(uint2(clamp(cell+int2(i,j),int2(0),int2(dimensions)-1))).r;
            float n=clamp((value-minimum)/p.window.y,0.0,1.0);
            color += clut.read(uint2(uint(n*255.0+0.5),0)).rgb
                * (i==0 ? 1-blend.x : blend.x) * (j==0 ? 1-blend.y : blend.y);
        }
        return float4(color,1);'''
        assert source.count(correct)==1, 'update negative control after shader changes'
        renderer_source=work/'ColorFirstMutant.swift'
        renderer_source.write_text(source.replace(correct,wrong))
    subprocess.run(['xcrun','swiftc','-O','-parse-as-library',
                    *[str(ROOT/'Horos/Sources'/name) for name in ['VolumeAllocation.swift','VolumeSession.swift',
                      'MPRMetalReslicer.swift','MetalPerformanceTrace.swift','MetalComputePipelineCache.swift',
                      'Metal4ComputeSubmitter.swift']],
                    str(renderer_source),str(ROOT/'tools/measure-planar-low-contrast.swift'),
                    '-o',str(work/'probe')],check=True)
    subprocess.run([str(work/'probe'),str(work)],check=True,timeout=90)
    report=json.loads((work/'gpu-results.json').read_text())
    assert all(digest(path)==value for path,value in source_hashes.items()), 'original DICOM changed'
    report['fixture_manifest_sha256']=digest(fixture/'manifest.json')
    report['renderer_sha256']=digest(args.renderer_source)
    report['host']=platform.platform()
    report['timestamp_utc']=datetime.now(timezone.utc).isoformat()
    report['harness_sha256']=digest(ROOT/'tools/measure-planar-low-contrast.swift')
    report['verifier_sha256']=digest(Path(__file__))
    report['generator_sha256']=digest(ROOT/'tools/generate-planar-low-contrast-fixture.py')
    report['source_base_commit']=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    report['decoder_versions']={'pydicom':pydicom.__version__,'numpy':np.__version__}
    report['swift_flags']=['-O','-parse-as-library']
    report['wrong_order_pixels_per_sequence']=wrong_order_pixels
    report['definitions']={'first_pass':'New renderer; first traversal of predecoded in-memory sequence. OS/driver/disk caches not flushed.',
        'repeat_passes':'Three identical traversals with same renderer; production update still allocates/uploads each frame.',
        'timing_excludes':'DICOM IO/decoding, reference calculation, readback, AppKit input, queue coalescing, composition and display. Readback/verification insert gaps between frames; this is not an input-to-display/FPS benchmark.',
        'gpu_ms':'Command-buffer gpuEndTime minus gpuStartTime; null when unavailable.',
        'frame_wall_ms':'Snapshot data copy + PlanarFrame construction + texture upload + output allocation + encode + submit/wait.',
        'claim':'No speedup comparison with legacy; no clinical detectability or complete #304 B acceptance.'}
    report['summary']={}
    for phase,predicate in [('first_pass',lambda s:s['pass']==0),('repeat_passes',lambda s:s['pass']>0)]:
        report['summary'][phase]={}
        samples=[s for s in report['samples'] if predicate(s)]
        for key in ['snapshot_ms','upload_ms','allocate_encode_ms','submit_wait_ms','frame_wall_ms','gpu_ms']:
            values=[s[key] for s in samples if s[key] is not None]
            report['summary'][phase][key]=({'count':len(values),'median':float(np.median(values)),
                'p95':float(np.percentile(values,95)),'maximum':max(values)} if values else None)
    # A unique report preserves earlier measurements; raw arrays are disposable.
    report_path=results/(work.name+'-results.json')
    report_path.write_text(json.dumps(report,indent=2)+'\n')
    print(f'PASS: 32 DICOM calibrations exact; color-first control differs in {wrong_order_pixels} pixels per sequence')
    print(f'Report: {report_path}')
    print(json.dumps(report['summary'],indent=2))
