#!/usr/bin/env python3
"""Compare local synthetic native presentations with a scalar/CLUT oracle.

GPU readback is used as the renderer input, never as the expected output. The
oracle independently interpolates scalar samples in float64, quantizes the CLUT,
and composites fusion alpha. It also checks all calibrated source voxels against
the analytic phantom. Windowed transfer/filter inputs are separately compared
with host vImage resampling; that comparison does not validate the transfer curve.
"""
import argparse
import ctypes
import json
from pathlib import Path
import re
import uuid

import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def french_palette():
    """Read the named reference palette, independently of captured GL output."""
    text = (ROOT/'Horos/Sources/DefaultsOsiriX.m').read_bytes().decode('latin1')
    end = text.index('forKey:@"French"')
    start = text.rfind('int r[ 256]',0,end)
    tables = [np.fromstring(re.search(r'int '+channel+r'\[ 256\] = \{([^}]+)',text[start:end])[1],sep=',',dtype=np.uint8)
              for channel in ('b','g','r')]
    # The source deliberately assigns b[] to Red and r[] to Blue.
    return np.column_stack(tables)


def check_case(state, case):
    """Acceptance intent is supplied separately; observed flags cannot define it."""
    assert state['metalEnabled'] == (case != 'gray-control'), 'Wrong requested renderer'
    assert bool(state['fallback']) == (case != 'gray-control'), 'Missing/unexpected explicit fallback'
    assert state['blendingMode'] == 0
    is_fusion = case.startswith('fusion-')
    assert len(state['layers']) == (2 if is_fusion else 1), 'Wrong layer count'
    if is_fusion or case == 'gray-control':
        assert case in ('gray-control','fusion-gray','fusion-scalar','fusion-ct-window','fusion-pt-window')
        modalities = ['CT','PT'] if is_fusion else ['CT']
        level_width = [(300,1500) if case in ('fusion-ct-window','fusion-pt-window') else (100,200),
                       (650,256) if case == 'fusion-pt-window' else (600,400)]
        size,patient,namespace = 32,'LOCAL-FUSION-CT-PT','urn:horos:fusion-window:ct-pt:'
        mode = 'fusion'
    else:
        modality,mode = case.split('-',1)
        assert modality in ('nm','pt')
        assert mode in ('mean','mip','minip','logarithmic','logarithmic-roi','gaussian','gaussian-roi','shutter','shutter-shift')
        modalities,level_width = [modality.upper()],[(2048,64)]
        size,patient,namespace = 256,'QA-A111-ONLY','urn:horos:a111:low-contrast:v1:'
    for index,layer in enumerate(state['layers']):
        shutter = mode.startswith('shutter')
        expected = dict(modality=modalities[index],width=size,height=size,patient=patient,
                        curImage=0,stackMode={'mean':1,'mip':2,'minip':3}.get(mode,0),
                        stack=4 if mode in ('mean','mip','minip') else 1,stackDirection=0,
                        hasTransferFunction=mode.startswith('logarithmic'),hasFilter=mode.startswith('gaussian'),
                        hasSubtraction=False,shutterEnabled=shutter,isRGB=False,thickSlabVRActivated=False,
                        level=level_width[index][0],widthWindow=level_width[index][1],
                        xFlipped=False,yFlipped=False,rotation=0,
                        scalarDraw=not (index==0 and case in ('gray-control','fusion-gray')))
        for key,value in expected.items():
            assert layer[key] == value, f'{case}: {key} expected {value}, got {layer[key]}'
        name = f'series-{index+1}' if size==32 else ('shutter:' if shutter else '')+modalities[index]
        uid = '2.25.'+str(uuid.uuid5(uuid.NAMESPACE_URL,namespace+name).int)
        assert layer['series'].split()[-1] == uid, 'Wrong analytic fixture identity'
        if shutter:
            assert layer['shutterRect'] == [40,40,176,176]
        if mode.startswith('gaussian'):
            assert layer['kernelSize'] == 5 and layer['kernelNormalization'] == 52
            assert layer['kernel'] == [1,1,2,1,1,1,2,4,2,1,2,4,8,4,2,1,2,4,2,1,1,1,2,1,1]
        if mode.endswith('-roi'):
            assert layer['rois'] == [dict(type=9,mean=2055,min=2055,max=2055)], 'ROI must retain original intensity'
        else:
            assert layer['rois'] == [], 'Unexpected ROI annotations'


class Buffer(ctypes.Structure):
    _fields_ = [('data', ctypes.c_void_p), ('height', ctypes.c_size_t),
                ('width', ctypes.c_size_t), ('rowBytes', ctypes.c_size_t)]


def phantom(modality, width, height):
    yy, xx = np.mgrid[:height, :width]
    if width == height == 256 and modality in ('NM', 'PT'):
        volume = []
        for index in range(16):
            values = np.full((256, 256), 2048+index%4-1, dtype=np.float32)
            for cx, cy, radius, delta in [(80,80,20,8),(176,80,16,16),(80,176,12,-8),(176,176,8,-16)]:
                values[(xx-cx)**2+(yy-cy)**2 <= radius**2] += delta
            values[:16, :] = np.where(xx[:16, :] % 2 == 0, 2032, 2064)
            volume.append(values)
        return np.asarray(volume)
    if width == height == 32 and modality in ('CT', 'PT'):
        return np.asarray([xx+2*yy+3*z if modality == 'CT' else 500+3*xx+yy+5*z
                           for z in range(16)], dtype=np.float32)
    raise AssertionError('Unknown analytic phantom')


def coordinates(layer, width, height):
    yy, xx = np.mgrid[:height, :width]
    p = layer['screenToPixel']
    px = p[0]+(xx+.5)/width*(p[2]-p[0])+(yy+.5)/height*(p[4]-p[0])
    py = p[1]+(xx+.5)/width*(p[3]-p[1])+(yy+.5)/height*(p[5]-p[1])
    return px, py


def fixed_mask(layer, px, py):
    if layer['width'] == 256:
        strip = (px>8)&(px<248)&(py>4)&(py<14)&((px<120)|(px>136))
        body = (px>12)&(px<244)&(py>22)&(py<238)
        return strip | body
    return (px>3)&(px<29)&(py>3)&(py<29)


def interpolate(texture, px, py, image_width, image_height):
    th, tw = texture.shape
    x, y = px*tw/image_width-.5, py*th/image_height-.5
    x0, y0 = np.floor(x).astype(int), np.floor(y).astype(int)
    fx, fy = x-x0, y-y0
    def sample(dx, dy):
        return texture[np.clip(y0+dy,0,th-1),np.clip(x0+dx,0,tw-1)].astype(np.float64)
    return (sample(0,0)*(1-fx)*(1-fy)+sample(1,0)*fx*(1-fy)
            +sample(0,1)*(1-fx)*fy+sample(1,1)*fx*fy)


def interpolation_interval(texture, px, py, dx, dy, iw, ih):
    """Extrema include any texel-centre knot crossed by the interval.

    Between knots bilinear extrema are at corners. The declared coordinate
    interval is smaller than one texel, hence at most one interior knot per axis.
    """
    th, tw = texture.shape
    assert np.max(2*dx*tw/iw) < 1 and np.max(2*dy*th/ih) < 1
    knot_x = (np.ceil((px-dx)*tw/iw-.5)+.5)*iw/tw
    knot_y = (np.ceil((py-dy)*th/ih-.5)+.5)*ih/th
    xs = [px-dx, np.clip(knot_x,px-dx,px+dx), px+dx]
    ys = [py-dy, np.clip(knot_y,py-dy,py+dy), py+dy]
    values = [interpolate(texture,x,y,iw,ih) for x in xs for y in ys]
    return np.minimum.reduce(values), np.maximum.reduce(values)


def resample(source, shape):
    enlarged = np.empty(shape, dtype=source.dtype)
    lib = ctypes.CDLL('/System/Library/Frameworks/Accelerate.framework/Accelerate')
    scale = getattr(lib, 'vImageScale_Planar8' if source.dtype == np.uint8 else 'vImageScale_PlanarF')
    scale.argtypes = [ctypes.POINTER(Buffer), ctypes.POINTER(Buffer), ctypes.c_void_p, ctypes.c_uint32]
    scale.restype = ctypes.c_ssize_t
    src = Buffer(source.ctypes.data, *source.shape, source.strides[0])
    dst = Buffer(enlarged.ctypes.data, *enlarged.shape, enlarged.strides[0])
    assert scale(ctypes.byref(src),ctypes.byref(dst),None,0) == 0
    return enlarged


def convolve(source, layer):
    """Independent float64 spatial sum, with the host's documented edge policy."""
    size = layer['kernelSize']
    kernel = np.asarray(layer['kernel'],dtype=np.float64).reshape(size,size)
    if layer['kernelNormalization']:
        kernel /= layer['kernelNormalization']
    padded = np.pad(source,size//2,mode='edge').astype(np.float64)
    result = np.zeros(source.shape,dtype=np.float64)
    for y in range(size):
        for x in range(size):
            result += padded[y:y+source.shape[0],x:x+source.shape[1]]*kernel[y,x]
    # DCMPix replaces its first output row with the first source value.
    result[0] = source[0,0]
    return result.astype(np.float32)


def verify(path, case=None):
    state = json.loads(path.read_text())
    if case is not None:
        check_case(state,case)
    assert state['applicationActive'] and state['glError'] == 0
    assert not state['metalEnabled'] or state['fallback'], 'A special Metal mode needs explicit fallback'
    assert len(state['layers']) in (1, 2)
    w, h = map(int, state['viewSize'])
    actual = np.fromfile(path.with_suffix('.bgra'), dtype=np.uint8).reshape(h,w,4)[::-1,:,[2,1,0]]
    predicted = []
    mask = np.ones((h,w), dtype=bool)
    checked_voxels = 0
    for layer_index, layer in enumerate(state['layers']):
        assert not layer['legacyFailure']
        gray_primary = (not layer['scalarDraw'] and layer_index == 0
                        and layer['modality'] == 'CT'
                        and layer['textureFormat'] in (0x8040,0x804B))
        assert layer['scalarDraw'] or gray_primary, 'Unsupported non-scalar presentation'
        assert not layer['isRGB'] and not layer['thickSlabVRActivated']
        assert layer['textureCount'] == layer['textureRows'] == 1
        prefix = path.parent/layer['prefix']
        assert prefix.parent.resolve() == path.parent.resolve()
        iw, ih = layer['width'], layer['height']
        expected = phantom(layer['modality'], iw, ih)
        volume = np.fromfile(str(prefix)+'.volume.f32', dtype='<f4').reshape(expected.shape)
        assert np.array_equal(volume, expected), 'Calibrated source volume changed'
        raw = np.fromfile(str(prefix)+'.f32', dtype='<f4').reshape(ih,iw)
        assert np.array_equal(raw, expected[layer['curImage']]), 'Current source slice changed'
        checked_voxels += volume.size
        tw, th = layer['textureSize']
        texture = np.fromfile(str(prefix)+'.texture.f32', dtype='<f4').reshape(th,tw)
        assert np.isfinite(texture).all()
        if layer['textureFormat'] in (0x8040, 0x804B):  # GL_LUMINANCE8 / GL_INTENSITY8
            source = np.fromfile(str(prefix)+'.u8', dtype=np.uint8).reshape(ih,iw)
            if layer['shutterEnabled'] and not layer['hasTransferFunction']:
                minimum = layer['level']-layer['widthWindow']/2
                windowed = np.rint(np.clip((raw-minimum)/layer['widthWindow'],0,1)*255).astype(np.uint8)
                xx,yy = np.meshgrid(np.arange(iw),np.arange(ih))
                sx,sy,sw,sh = layer['shutterRect']
                windowed[~((xx>=sx)&(xx<sx+sw)&(yy>=sy)&(yy<sy+sh))] = 0
                assert np.array_equal(source,windowed), 'Analytic rectangular shutter differs'
            upload = resample(source, (th,tw)) if source.shape != texture.shape else source
            assert np.array_equal(np.rint(texture*255).astype(np.uint8), upload), 'Windowed upload differs'
            minimum, span = 0, 1
        else:
            assert layer['textureFormat'] in (0x8817, 0x8818)  # scalar float32
            minimum, span = layer['level']-layer['widthWindow']/2, layer['widthWindow']
            start, count = layer['curImage'], layer['stack']
            if layer['stackDirection']:
                slab = expected[max(0,start-count+1):start+1]
            else:
                slab = expected[start:min(start+count,len(expected))]
            mode = layer['stackMode']
            source = ({1:np.mean,2:np.max,3:np.min}[mode](slab,axis=0)
                      if mode in (1,2,3) else raw)
            if layer['hasFilter']:
                source = convolve(source, layer)
            upload = resample(source, (th,tw)) if source.shape != texture.shape else source
            # Convolution may sum in a different order in vImage.
            tolerance = np.abs(np.spacing(upload))*8 if layer['hasFilter'] else 0
            assert np.all(np.abs(texture-upload)<=tolerance), 'Physical scalar upload differs'
        px, py = coordinates(layer, w, h)
        mask &= fixed_mask(layer, px, py)
        value = interpolate(texture,px,py,iw,ih)
        # The host's coordinate conversion, GL vertices and texture varyings
        # are float32 too. Propagate their declared eight-ULP interval through
        # bilinear sampling instead of applying a bound only to final intensity.
        dx = np.abs(np.spacing((px*tw/iw).astype(np.float32)).astype(np.float64))*8*iw/tw
        dy = np.abs(np.spacing((py*th/ih).astype(np.float32)).astype(np.float64))*8*ih/th
        if 'subpixelBits' in state:
            # A reported raster subpixel quantum bounds snapping of the quad's
            # projected vertices. Propagate that screen-space interval through
            # the captured affine map; do not enlarge channel tolerance.
            bits = state['subpixelBits']
            assert 4 <= bits <= 32
            quantum = 2.0**-bits
            p = layer['screenToPixel']
            dx += quantum*(abs(p[2]-p[0])/w+abs(p[4]-p[0])/h)
            dy += quantum*(abs(p[3]-p[1])/w+abs(p[5]-p[1])/h)
        lower, upper = interpolation_interval(texture,px,py,dx,dy,iw,ih)
        slack = np.abs(np.spacing(value.astype(np.float32)).astype(np.float64))*8
        palette = np.fromfile(str(prefix)+'.rgba', dtype=np.uint8).reshape(256,4)
        if case is not None and not gray_primary:
            assert np.array_equal(palette[:,:3],french_palette()), 'Captured palette is not the expected French CLUT'
        if gray_primary:
            assert np.array_equal(palette[:,:3],np.repeat(np.arange(256,dtype=np.uint8)[:,None],3,axis=1)), 'Primary must use linear gray'
        if layer_index == 1:
            assert state['blendingMode'] == 0, 'Only source-over linear alpha is covered'
            factor = state['blendingFactor']
            assert np.isfinite(factor) and -256 <= factor <= 256
            entries = np.arange(256,dtype=np.float64)
            alpha = entries*(256+factor)/256 if factor <= 0 else entries*256/(256-factor) if factor < 256 else np.full(256,255)
            assert np.array_equal(palette[:,3],np.clip(alpha,0,255).astype(np.uint8)), 'Fusion alpha disagrees with factor'
        def entry(v):
            return np.floor(np.clip((v-minimum)/span,0,1)*255+.5).astype(int)
        if gray_primary:
            # This path has no discrete CLUT. Keep the continuous gray value;
            # primary framebuffer quantization and final blend quantization
            # together contribute at most .5*(1-alpha)+.5 <= one byte.
            predicted.append(('gray',np.clip(lower-slack,0,1)*255,
                              np.clip(upper+slack,0,1)*255))
        else:
            predicted.append((entry(lower-slack),entry(upper+slack),palette))
        if len(state['layers']) == 1:
            packed = actual[:,:,0].astype(np.uint32)*65536+actual[:,:,1].astype(np.uint32)*256+actual[:,:,2]
            entries = palette[:,0].astype(np.uint32)*65536+palette[:,1].astype(np.uint32)*256+palette[:,2]
            assert not (mask & ~np.isin(packed, entries)).any(), 'Colors outside the CLUT'
    assert mask.sum() > 1000, 'Insufficient unannotated image area'
    observed = actual[mask].astype(np.float64)
    error = np.full(observed.shape[0],np.inf)
    def candidates(prediction):
        if isinstance(prediction[0],str):
            _,low,high = prediction
            for gray in [low[mask],(low[mask]+high[mask])/2,high[mask]]:
                yield np.column_stack([gray,gray,gray,np.full(len(gray),255)]), np.ones(len(gray),dtype=bool)
            return
        low,high,palette = prediction
        low,high = low[mask],high[mask]
        # A CLUT need not be monotonic. Enumerate every admissible index;
        # comparing only endpoint colours is not an interval comparison.
        for offset in range(int(np.max(high-low))+1):
            index = low+offset
            yield palette[np.minimum(index,255)].astype(np.float64), index <= high
    for primary,valid_primary in candidates(predicted[0]):
        if len(predicted) == 1:
            difference = np.max(np.abs(observed-primary[:,:3]),axis=1)
            error = np.minimum(error,np.where(valid_primary,difference,np.inf))
        else:
            assert state['blendingMode'] == 0, 'Only source-over fusion is covered'
            for secondary,valid_secondary in candidates(predicted[1]):
                alpha = secondary[:,3:4]/255
                composite = secondary[:,:3]*alpha+primary[:,:3]*(1-alpha)
                difference = np.max(np.abs(observed-composite),axis=1)
                error = np.minimum(error,np.where(valid_primary&valid_secondary,difference,np.inf))
    assert not (error>1).any(), f'{(error>1).sum()} pixels disagree, max {error.max()}'
    print(f'{path.stem}: {mask.sum()} native pixels, {checked_voxels} exact calibrated voxels, max channel error {error.max():.3f}')
    return int(mask.sum()), checked_voxels


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('captures', type=Path, nargs='+')
    parser.add_argument('--case', help='Explicit expected mode, e.g. pt-mean or fusion-gray')
    args = parser.parse_args()
    results = [verify(path,args.case) for path in args.captures]
    print(f'PASS: {len(results)} captures, {sum(p for p,v in results)} pixels, {sum(v for p,v in results)} calibrated voxels')
