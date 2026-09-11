#!/usr/bin/env python3
"""Verify local A111 native GL/Metal captures, without driving the application.

Requires numpy and macOS Accelerate. All 32 calibrated slices must match the
analytic NM/PT phantom exactly. The pixel oracle uses host vImage resampling,
then independently computes bilinear interpolation/window/CLUT in float64.
Allow one colour byte, with adjacent CLUT entries only within eight float32
ULPs of an intensity quantization boundary. Exclude host annotations by the
same fixed masks in every capture; never derive a mask from pixel differences.
"""
import argparse
import ctypes
import hashlib
import json
from pathlib import Path
import numpy as np


class Buffer(ctypes.Structure):
    _fields_ = [('data', ctypes.c_void_p), ('height', ctypes.c_size_t),
                ('width', ctypes.c_size_t), ('rowBytes', ctypes.c_size_t)]


def verify(folder, fixture, post_scroll=False):
    manifest = json.loads((fixture/'manifest.json').read_text())
    assert manifest['synthetic'] and len(manifest['files']) == 32
    for record in manifest['files']:
        path = fixture/record['path']
        assert path.resolve().is_relative_to(fixture.resolve())
        assert hashlib.sha256(path.read_bytes()).hexdigest() == record['sha256']
    yy, xx = np.mgrid[:256, :256]
    expected_volume = []
    for index in range(16):
        values = np.full((256, 256), 2048+index%4-1, dtype=np.float32)
        for cx, cy, radius, delta in [(80,80,20,8),(176,80,16,16),(80,176,12,-8),(176,176,8,-16)]:
            values[(xx-cx)**2+(yy-cy)**2 <= radius**2] += delta
        values[:16, :] = np.where(xx[:16, :] % 2 == 0, 2032, 2064)
        expected_volume.append(values)
    expected_volume = np.asarray(expected_volume)
    library = ctypes.CDLL('/System/Library/Frameworks/Accelerate.framework/Accelerate')
    scale = library.vImageScale_PlanarF
    scale.argtypes = [ctypes.POINTER(Buffer), ctypes.POINTER(Buffer), ctypes.c_void_p, ctypes.c_uint32]
    scale.restype = ctypes.c_ssize_t

    def capture(name):
        state = json.loads((folder/(name+'.json')).read_text())
        assert state['width'] == state['height'] == 256 and state['curImage'] == 0
        assert state['level'] == 2048 and state['widthWindow'] == 64
        assert state['glError'] == 0 and not state['fallback'] and not state.get('legacyFailure')
        assert state['softwareInterpolation'] and state['scaleValue'] > 2
        volume = np.fromfile(folder/(name+'.volume.f32'), dtype='<f4').reshape(16,256,256)
        assert np.array_equal(volume, expected_volume), f'{name}: calibrated volume changed'
        source = np.fromfile(folder/(name+'.f32'), dtype='<f4').reshape(256,256)
        assert np.array_equal(source, expected_volume[0])
        w, h = map(int, state['viewSize'])
        bgra = np.fromfile(folder/(name+'.bgra'), dtype=np.uint8).reshape(h,w,4)[::-1]
        table = np.fromfile(folder/(name+'.rgba'), dtype=np.uint8).reshape(256,4)
        y, x = np.mgrid[:h,:w]
        p = state['screenToPixel']
        px = p[0]+(x+0.5)/w*(p[2]-p[0])+(y+0.5)/h*(p[4]-p[0])
        py = p[1]+(x+0.5)/w*(p[3]-p[1])+(y+0.5)/h*(p[5]-p[1])
        strip = (px>8)&(px<248)&(py>4)&(py<14)&((px<120)|(px>136))
        body = (px>12)&(px<244)&(py>22)&(py<238)
        return state, source, bgra[:,:,[2,1,0]], table[:,:3], px, py, strip, body

    before = capture('a111-nm-before')
    def forbidden(rgb, table, mask):
        packed = rgb[:,:,0].astype(np.uint32)*65536+rgb[:,:,1].astype(np.uint32)*256+rgb[:,:,2]
        entries = table[:,0].astype(np.uint32)*65536+table[:,1].astype(np.uint32)*256+table[:,2]
        return int((mask & ~np.isin(packed, entries)).sum())
    old_forbidden = forbidden(before[2], before[3], before[6])
    assert old_forbidden > 20000, 'historical capture no longer reproduces the colour-first defect'
    checked = boundaries = 0
    renderers = ([(f'release-{modality}-{backend}', backend == 'metal')
                  for modality in ('nm', 'pt') for backend in ('gl', 'metal')]
                 if post_scroll else
                 [('a111-nm-gl-corrected',False), ('a111-nm-metal-corrected',True),
                  ('a111-pt-gl-corrected',False), ('a111-pt-metal-corrected',True)])
    for name, enabled in renderers:
        state, source, rgb, table, px, py, strip, body = capture(name)
        assert state['metalEnabled'] == enabled and not state['rois']
        assert not state.get('hasTransferFunction', False)
        assert np.array_equal(table, before[3]), f'{name}: different CLUT'
        mask = strip | body
        assert forbidden(rgb, table, mask) == 0, f'{name}: colours outside CLUT'
        enlarged = np.empty((768,768), dtype=np.float32)
        src = Buffer(source.ctypes.data,256,256,256*4)
        dst = Buffer(enlarged.ctypes.data,768,768,768*4)
        assert scale(ctypes.byref(src),ctypes.byref(dst),None,0) == 0
        x, y = px*3-0.5, py*3-0.5
        x0, y0 = np.floor(x).astype(int), np.floor(y).astype(int)
        fx, fy = x-x0, y-y0
        def sample(dx,dy):
            return enlarged[np.clip(y0+dy,0,767),np.clip(x0+dx,0,767)].astype(np.float64)
        value = (sample(0,0)*(1-fx)*(1-fy)+sample(1,0)*fx*(1-fy)
                 +sample(0,1)*(1-fx)*fy+sample(1,1)*fx*fy)
        slack = np.spacing(value.astype(np.float32)).astype(np.float64)*8
        def entry(intensity):
            return np.floor(np.clip((intensity-2016)/64,0,1)*255+0.5).astype(int)
        lo, hi, mid = entry(value-slack), entry(value+slack), entry(value)
        errors = np.maximum.reduce(np.abs(rgb.astype(int)-table[mid].astype(int)), axis=2)
        allowed = np.minimum(np.max(np.abs(rgb.astype(int)-table[lo].astype(int)),axis=2),
                             np.max(np.abs(rgb.astype(int)-table[hi].astype(int)),axis=2))
        failures = mask & (allowed>1)
        assert not failures.any(), f'{name}: {failures.sum()} pixels disagree with scalar oracle; max error {allowed[mask].max()}'
        boundary = int((mask & (errors>1)).sum())
        checked += int(mask.sum()); boundaries += boundary
        print(f'{name}: {mask.sum()} pixels; zero forbidden colours; {boundary} float32 boundary pixels')
    if not post_scroll:
        for name, enabled in [('a111-nm-metal-roi',True),('a111-nm-gl-roi',False),
                              ('a111-pt-metal-roi',True),('a111-pt-gl-roi',False)]:
            state = capture(name)[0]
            assert state['metalEnabled'] == enabled
            assert state['rois'] == [{'type':6,'name':'Unnamed','mean':2055,'min':2055,'max':2055}]
    print(f'PASS: {checked} native pixels, {boundaries} float32 boundary pixels; '
          f'{old_forbidden} baseline colours outside CLUT eliminated; 2097152 calibrated NM/PT voxels exact; '
          + ('post-scroll captures (no new ROI measurement); ' if post_scroll else 'ROIs retain 2055; ')
          + '32 original DICOM hashes intact')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('snapshots', type=Path)
    parser.add_argument('fixture', type=Path)
    parser.add_argument('--post-scroll', action='store_true',
                        help='Validate release-{nm,pt}-{gl,metal} captures after the native scroll runs')
    args = parser.parse_args()
    verify(args.snapshots, args.fixture, args.post_scroll)
