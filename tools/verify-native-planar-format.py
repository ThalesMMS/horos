#!/usr/bin/env python3
"""Independent fixture decoder and native-buffer oracle for the planar matrix.

The generated source files must match their pre-import hashes. RGB padding is
not a DICOM channel. Scalar buffers are calibrated values, never display bytes.
Presentation comparison uses the declared central image rectangle, with no
masking based on differences. Use --presentation only for supported Metal with
software interpolation off (the separate A111 oracle covers enlargement).
"""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pydicom


def expected(ds):
    raw = ds.pixel_array
    if ds.PhotometricInterpretation == 'PALETTE COLOR':
        entries, first, bits = map(int, ds.RedPaletteColorLookupTableDescriptor)
        entries = entries or 65536
        index = np.clip(raw.astype('i8')-first, 0, entries-1)
        channels = []
        for name in ('Red', 'Green', 'Blue'):
            table = np.frombuffer(getattr(ds, name+'PaletteColorLookupTableData'),
                                  dtype='u1' if bits == 8 else '<u2')[:entries]
            # The historical narrow 16-bit table fixture intentionally holds
            # eight-bit entries. The wide table uses the high eight bits.
            if bits == 16 and table.max() > 255:
                table = table >> 8
            channels.append(table[index])
        return np.stack(channels, axis=-1).astype('u1'), True
    if ds.SamplesPerPixel == 3:
        return raw, True
    return (raw.astype('f8')*float(ds.get('RescaleSlope', 1))
            + float(ds.get('RescaleIntercept', 0))).astype('<f4'), False


def verify(path, manifest, presentation=False, expected_frame=None, backend="metal", roi=False,
           expected_movie=None, temporal_roi=False, scroll_catalog=False):
    state = json.loads(path.read_text())
    assert state['applicationActive'] and state['glError'] == 0, 'inactive application or GL error'
    assert state['metalEnabled'] == (backend == 'metal'), 'wrong rendering backend'
    assert state['frames'] and len(state['frames']) <= (1300 if scroll_catalog else 256)
    if scroll_catalog:
        assert all(r['patient'] in {'LOCAL-SCROLL-CT', 'LOCAL-SCROLL-MR'} for r in manifest['files'])
    sources = {r['sop']: r for r in manifest['files']}
    decoded, seen, samples = {}, set(), 0
    for frame in state['frames']:
        sop, number = frame['sop'], frame['frame']
        assert (sop, number) not in seen, 'duplicate frame'
        seen.add((sop, number))
        record = sources[sop]
        if sop not in decoded:
            source = Path(manifest['root'])/record['path']
            assert hashlib.sha256(source.read_bytes()).hexdigest() == record['sha256'], 'fixture changed'
            ds = pydicom.dcmread(source)
            decoded[sop] = (ds, *expected(ds))
        ds, pixels, color = decoded[sop]
        assert frame['width'] == ds.Columns and frame['height'] == ds.Rows, 'dimensions changed'
        assert frame['isRGB'] == color, 'color mode changed'
        if 'PixelSpacing' in ds:
            assert np.allclose(frame['spacing'], list(reversed(ds.PixelSpacing)), rtol=0, atol=1e-7), 'pixel spacing changed'
        for tag, key in [('ImagePositionPatient','position'),('ImageOrientationPatient','orientation')]:
            if tag in ds:
                assert np.allclose(frame[key], ds[tag].value, rtol=0, atol=1e-6), 'geometry changed'
        count = int(ds.get('NumberOfFrames', 1))
        assert 0 <= number < count, 'frame number out of range'
        plane = pixels[number] if count > 1 else pixels
        raw = np.fromfile(path.parent/frame['file'], dtype='u1' if color else '<f4')
        actual = raw.reshape(ds.Rows, ds.Columns, 4)[:,:,1:] if color else raw.reshape(ds.Rows, ds.Columns)
        assert np.array_equal(actual, plane), 'native sample mismatch: '+record['path']+' frame '+str(number)
        samples += plane.size
    expected_ids = {(r['sop'], f) for r in manifest['files'] if r['series'] == state['series']
                    for f in range(r['frames'])}
    # A 4D viewer holds multiple series. Each must be present in full, and
    # temporal association is checked separately against its fixture metadata.
    if state['movies'] > 1:
        series = {sources[f['sop']]['series'] for f in state['frames']}
        expected_ids = {(r['sop'], f) for r in manifest['files'] if r['series'] in series
                        for f in range(r['frames'])}
        for f in state['frames']:
            ds = decoded[f['sop']][0]
            assert f['movie'] == int(ds.TemporalPositionIdentifier)-1, 'temporal association changed'
    assert seen == expected_ids, 'missing or unexpected frames'
    current = next(f for f in state['frames'] if f['movie'] == state['currentMovie'] and f['index'] == state['currentImage'])
    if expected_frame is not None:
        assert current['frame'] == expected_frame, 'wrong displayed frame'
    if expected_movie is not None:
        assert state['currentMovie'] == expected_movie, 'wrong displayed time'
        assert state['movies'] == 3 and len(state['frames']) == 24, 'incomplete temporal volume'
        assert {(f['movie'], f['index']) for f in state['frames']} == {
            (time, index) for time in range(3) for index in range(8)}, 'missing temporal slice'
    report = dict(frames=len(seen), samples=samples, sampleErrors=0, currentFrame=current['frame'],
                  currentMovie=state['currentMovie'], fallback=state['fallback'])
    if roi:
        ds = decoded[current['sop']][0]
        assert ds.PatientID == 'S373-FORMATS' and sources[current['sop']]['path'] == 'formats/mono1-calibrated.dcm', 'wrong ROI fixture'
        rois = current['rois']
        assert len(rois) == 1 and rois[0]['name'] == 'S373-MONO1-F'+str(current['frame']) and rois[0]['type'] == 6, 'ROI association changed'
        step = 202*current['frame']
        assert [rois[0][k] for k in ('mean','min','max')] == [-2004+step,-2052+step,-1956+step], 'ROI calibration changed'
        report['roi'] = rois[0]
    if temporal_roi:
        ds = decoded[current['sop']][0]
        assert ds.PatientID == 'MPR-4D-226' and current['index'] == 0, 'wrong temporal ROI fixture'
        rois = current['rois']
        assert len(rois) == 1 and rois[0]['type'] == 6, 'temporal ROI association changed'
        value = 50 + 100 * (int(ds.TemporalPositionIdentifier) - 1)
        assert [rois[0][k] for k in ('mean', 'min', 'max')] == [value]*3, 'temporal ROI calibration changed'
        report['roi'] = rois[0]
    if presentation:
        assert not state['fallback'], 'unexpected fallback'
        assert not state['softwareInterpolation'], 'software enlargement needs the A111 oracle'
        ds, pixels, color = decoded[current['sop']]
        plane = pixels[current['frame']] if int(ds.get('NumberOfFrames',1)) > 1 else pixels
        sw, sh = map(int, state['viewSize'])
        yy, xx = np.mgrid[:sh,:sw]
        transform = np.array(state['screenToPixel']).reshape(3,2)
        points = transform[0] + ((xx+.5)/sw)[:,:,None]*(transform[1]-transform[0]) + ((yy+.5)/sh)[:,:,None]*(transform[2]-transform[0])
        px, py = points[:,:,0], points[:,:,1]
        mask = (px>=ds.Columns/4)&(px<ds.Columns*3/4)&(py>=ds.Rows/4)&(py<ds.Rows*3/4)
        assert mask.sum() >= 128, 'image too small for the fixed mask'
        x, y = px[mask]-.5, py[mask]-.5
        if state['nearest']:
            values = plane[np.floor(py[mask]).astype(int),np.floor(px[mask]).astype(int)]
        else:
            ix, iy = np.floor(x).astype(int), np.floor(y).astype(int)
            fx, fy = x-ix, y-iy
            if color: fx,fy=fx[:,None],fy[:,None]
            values = ((plane[iy,ix]*(1-fx)+plane[iy,ix+1]*fx)*(1-fy)
                      +(plane[iy+1,ix]*(1-fx)+plane[iy+1,ix+1]*fx)*fy)
        clut = np.fromfile(path.with_suffix('.clut'),dtype='u1').reshape(256,4)
        inverted = ds.PhotometricInterpretation == 'MONOCHROME1'
        assert current.get('displayInverted', False) == inverted, 'presentation polarity changed'
        span = -state['widthWindow'] if inverted else state['widthWindow']
        minimum = state['level']-span/2
        normalized = np.clip((values-minimum)*255/(int(span) if color else span),0,255)
        indices = np.floor(normalized if color else normalized+.5).astype(int)
        rgb = np.stack([clut[indices[:,c],c] for c in range(3)],axis=-1) if color else clut[indices,:3]
        actual = np.fromfile(path.with_suffix('.bgra'),dtype='u1').reshape(sh,sw,4)[::-1][:,:,[2,1,0]][mask]
        error = np.abs(actual.astype(int)-rgb.astype(int))
        assert error.max() <= 1, 'presentation mismatch: max channel error '+str(error.max())+', pixels '+str(np.count_nonzero(error.max(axis=1)>1))
        report.update(presentationPixels=int(mask.sum()), maximumChannelError=int(error.max()))
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('capture', type=Path)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--presentation', action='store_true')
    parser.add_argument('--expected-frame', type=int)
    parser.add_argument('--backend', choices=('metal','original'), default='metal')
    parser.add_argument('--roi', action='store_true')
    parser.add_argument('--expected-movie', type=int)
    parser.add_argument('--temporal-roi', action='store_true')
    parser.add_argument('--scroll-catalog', action='store_true')
    args = parser.parse_args()
    print(json.dumps(verify(args.capture, json.loads(args.manifest.read_text()),
                            args.presentation, args.expected_frame, args.backend, args.roi,
                            args.expected_movie, args.temporal_roi, args.scroll_catalog), indent=2))
