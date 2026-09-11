#!/usr/bin/env python3
"""Stage B of #304: identical phase inputs and actual GL/Metal GPU commands.

This extends the established offscreen phase methodology, not a native viewer
or compositor measurement. Every catalog slice is rendered on both backends.
Use native PlanarPerformance traces separately for application input/latency.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time

import numpy as np
from scroll_baseline import (_phase_times, _windowed_bytes, catalog_plan,
                             gesture_walk, host_context, measure_mpr_control, summarize,
                             same_frame_of_reference, sync_destination_index)

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('fixtures', type=Path)
p.add_argument('--output', type=Path, required=True)
p.add_argument('--gl-probe', type=Path, required=True)
p.add_argument('--metal-probe', type=Path, required=True)
a = p.parse_args()
if a.output.exists() and any(a.output.iterdir()):
    p.error('output must be empty; preserve previous evidence')
a.output.mkdir(parents=True, exist_ok=True)
plan = catalog_plan()
plan.update(tolerances={'calibratedSamples':0,'channelBytes':1},
            cache={'cold':'no decoded dataset array; filesystem cache is not purged',
                   'warm':'decoded input arrays and initialized renderer; passes 1 through 3'},
            endpoint='offscreen command completion; not application event or compositor',
            source=host_context())
(a.output/'plan.json').write_text(json.dumps(plan,indent=2)+'\n')
manifest = {str(f.relative_to(a.fixtures)):hashlib.sha256(f.read_bytes()).hexdigest()
            for s in plan['series'] for f in sorted((a.fixtures/s['name']).glob('*.dcm'))}
assert len(manifest)==3900, 'incomplete catalog'
(a.output/'originals-before.json').write_text(json.dumps(manifest,indent=2)+'\n')
all_results=[]
for spec in plan['series']:
    name=spec['name'];folder=a.output/name;folder.mkdir()
    files=sorted((a.fixtures/name).glob('*.dcm'))
    assert len(files)==spec['slices']
    entries=[];cold=[];warm=[]
    for index,path in enumerate(files):
        phase,ds=_phase_times(path)
        assert str(ds.SeriesInstanceUID)==spec['series_uid'] and int(ds.InstanceNumber)==index+1
        assert list(map(float,ds.ImageOrientationPatient))==spec['orientation']
        assert float(ds.ImagePositionPatient[2])==index*0.5
        level=float(ds.WindowCenter);width=float(ds.WindowWidth)
        pixels=ds.pixel_array
        calibrated=(pixels.astype('f4')*float(ds.RescaleSlope)+float(ds.RescaleIntercept)).astype('<f4')
        yy,xx=np.mgrid[:ds.Rows,:ds.Columns]
        analytic=((xx+yy+index*3)%4096)+(-1024 if spec['modality']=='CT' else 0)
        assert np.array_equal(calibrated,analytic), 'calibration mismatch'
        started=time.perf_counter()
        warm_scalar=pixels.astype('f4')*float(ds.RescaleSlope)+float(ds.RescaleIntercept)
        scalar_ms=(time.perf_counter()-started)*1000
        started=time.perf_counter()
        legacy=_windowed_bytes(pixels,float(ds.RescaleIntercept),float(ds.RescaleSlope),level,width)
        legacy_ms=(time.perf_counter()-started)*1000
        expected=np.floor(np.clip((analytic-(level-width/2))*255/width,0,255)+0.5).astype('u1')
        bgra=np.repeat(expected[:,:,None],4,axis=2);bgra[:,:,3]=255
        entry={'id':str(ds.SOPInstanceUID),'pixels':f'{index}.f32',
               'legacy':f'{index}.u8','expected':f'{index}.bgra'}
        calibrated.tofile(folder/entry['pixels']);(folder/entry['legacy']).write_bytes(legacy)
        bgra.tofile(folder/entry['expected']);entries.append(entry);cold.append(phase)
        warm.append({'scalar_ms':scalar_ms,'legacy_ms':legacy_ms})
    clut=np.repeat(np.arange(256,dtype='u1')[:,None],4,axis=1);clut[:,3]=255
    clut.tofile(folder/'clut.rgba')
    input={'width':spec['size'],'height':spec['size'],'output_width':spec['size'],
           'output_height':spec['size'],'level':level,'width_window':width,'frames':entries}
    (folder/'input.json').write_text(json.dumps(input)+'\n')
    result={'name':name,'slices':len(files),'omittedSlices':0,'coldPhases':cold,'warmPhases':warm,
            'wheel':gesture_walk(len(files),precise=False),'trackpad':gesture_walk(len(files),precise=True),
            'mprControl':measure_mpr_control(a.fixtures/name),'backends':{}}
    # Alternate the order by series, and use a fresh process for every backend.
    backends=['gl','metal'] if len(all_results)%2==0 else ['metal','gl']
    for backend in backends:
        command=[str(a.gl_probe.resolve()),'--dataset',str(folder.resolve())] if backend=='gl' else [str(a.metal_probe.resolve()),str(folder.resolve())]
        with (folder/(backend+'-time.txt')).open('w') as err, (folder/(backend+'-run.txt')).open('w') as out:
            subprocess.run(['/usr/bin/time','-l','-p',*command],stdout=out,stderr=err,check=True)
        gpu=json.loads((folder/('gl-results.json' if backend=='gl' else 'gpu-results.json')).read_text())
        assert gpu['maximum_channel_error']<=1 and gpu['pixels_checked']==len(files)*spec['size']**2*4
        assert {(s['pass'],s['frame']) for s in gpu['samples']}=={(p,i) for p in range(4) for i in range(len(files))}
        for s in gpu['samples']:
            assert s['id']==entries[s['frame']]['id']
            # The existing baseline is additive phase timing. Metal does not
            # pay the CPU 8-bit window operation that the GL upload consumes.
            i=s['frame'];c=cold[i];w=warm[i]
            s['phase_cold_ms']=sum(c[k] for k in ('input_ms','io_ms','decode_ms','prepare_ms'))+s['frame_wall_ms']+(c['present_ms'] if backend=='gl' else 0)
            s['phase_warm_ms']=c['input_ms']+s['frame_wall_ms']+(w['legacy_ms'] if backend=='gl' else w['scalar_ms'])
        timings=(folder/(backend+'-time.txt')).read_text()
        gpu['process']={k:float(re.search(r'^'+k+r'\s+([\d.]+)',timings,re.M)[1]) for k in ('real','user','sys')}
        gpu['process']['maximumRSSBytes']=int(re.search(r'(\d+)\s+maximum resident set size',timings)[1])
        gpu['summary']={'cold':summarize([s['phase_cold_ms'] for s in gpu['samples'] if s['pass']==0]),
                        'warm':summarize([s['phase_warm_ms'] for s in gpu['samples'] if s['pass']>0]),
                        'frame':summarize([s['frame_wall_ms'] for s in gpu['samples']]),
                        'gpu':summarize([s['gpu_ms'] for s in gpu['samples'] if s['gpu_ms'] is not None])}
        if backend=='metal':
            gpu['summary']['allocatedBytes']=summarize([s['metal_allocated_bytes'] for s in gpu['samples']])
        result['backends'][backend]=gpu
    all_results.append(result)
    (folder/'paired-results.json').write_text(json.dumps(result,indent=2)+'\n')
    print(name,'PASS',len(files),'slices, four passes per backend',flush=True)
after={str(f.relative_to(a.fixtures)):hashlib.sha256(f.read_bytes()).hexdigest()
       for s in plan['series'] for f in sorted((a.fixtures/s['name']).glob('*.dcm'))}
assert after==manifest,'original files changed'
summary={'series':all_results,'originalFiles':len(manifest),'omittedSlices':0,
         'renderedFrames':sum(len(s['backends'][b]['samples']) for s in all_results for b in ('gl','metal')),
         'originalHashesPreserved':True,'scope':plan['endpoint']}
source,destination=a.fixtures/'sync-a-100',a.fixtures/'sync-b-100'
assert same_frame_of_reference(source,destination)
mapping=[sync_destination_index(source,destination,index) for index in range(100)]
assert mapping==list(range(100))
summary['sync']={'indices':100,'maximumIndexError':0,'mapping':mapping,
                 'scope':'existing SliceLocation model; native two-viewer interaction is A294'}
(a.output/'results.json').write_text(json.dumps(summary,indent=2)+'\n')
print('PASS:',summary['renderedFrames'],'GPU frames, 3900 preserved originals',flush=True)
