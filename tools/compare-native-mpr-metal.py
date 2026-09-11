#!/usr/bin/env python3
"""Compare native 3D MPR captures: Metal versus VTK versus an independent oracle (#374).

Input: pairs of snapshots written by tools/capture-native-mpr-metal.py for the
same camera, slab mode and thickness, one with Use Metal in MPR off (VTK
pixels) and one with it on, plus the raw volume the capture dumped. The
oracle is the pure-Python trilinear reslice from tests/test-mpr-metal-reslicer.py,
run on the volume the application itself handed to both renderers, in the
host's local frame (voxel (i, j, k) at (i·sx, j·sy, k·dz)).

Tolerances, fixed before any comparison and expressed on the volume's value
range, so a low-contrast phantom is judged as strictly as a CT:

- geometry: the Metal capture must report the same plane origin, orientation,
  spacing, size and slab thickness as the VTK capture (the host keeps the
  geometry; Metal only replaces pixels), to 1e-4;
- Metal versus oracle, interior pixels: worst |Δ| ≤ 0.1 % of range (the
  engine is exact to float rounding; anything larger is a frame or convention
  error in the host adapter);
- Metal versus VTK, interior pixels: mean |Δ| ≤ 1 % of range and worst
  |Δ| ≤ 3 % of range (VTK quantises to 16 bits and samples the slab at its
  own step);
- inside/outside masks: VTK stops at the voxel-centre box, the engine covers
  the half-voxel rim around it (its documented clamp-to-edge convention), so
  a pixel may differ only if Metal is inside and it lies within that rim;
  every other disagreement counts, and ≥ 98 % of pixels must agree.

    python3 tools/compare-native-mpr-metal.py --volume vtk-mip1 vtk-mip1:metal-mip1 vtk-mean4:metal-mean4
"""
import argparse
import importlib.util
import json
import struct
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('reslicer_test', root / 'tests/test-mpr-metal-reslicer.py')
reslicer_test = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reslicer_test)

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('pairs', nargs='+', metavar='VTK:METAL', help='snapshot labels of a VTK capture and its Metal twin')
parser.add_argument('--volume', required=True, help='label whose .vol dump is the volume (any capture of the same series)')
parser.add_argument('--directory', type=Path, default=Path('local-validation/issue-374-native'))
parser.add_argument('--results', type=Path, default=Path('docs/mpr-metal-reslice-results.json'))
args = parser.parse_args()

GEOMETRY_TOLERANCE = 1e-4
METAL_ORACLE_WORST = 0.001
METAL_VTK_MEAN = 0.01
METAL_VTK_WORST = 0.03
MASK_AGREEMENT = 0.98


def load(label):
    state = json.loads((args.directory / (label + '.json')).read_text())
    raw = (args.directory / (label + '.f32')).read_bytes()
    planes = []
    for view in state['views']:
        n = view['width'] * view['height']
        planes.append(struct.unpack('<%df' % n, raw[view['offset']:view['offset'] + 4 * n]))
    return state, planes


volume_state, _ = load(args.volume)
W, H = volume_state['volume']['width'], volume_state['volume']['height']
sx, sy = volume_state['volume']['spacingX'], volume_state['volume']['spacingY']
dz = abs(volume_state['volume']['sliceInterval'] or volume_state['volume']['sliceThickness'])
raw_volume = (args.directory / (args.volume + '.vol')).read_bytes()
D = len(raw_volume) // (W * H * 4)
# The viewer's buffer may be larger than the stack; the slice count is what the
# original pix list has, which the capture records through maxMovieIndex-free
# means: trust the DICOM-derived depth from the first capture's volume block.
D = volume_state['volume'].get('depth', D)
values = struct.unpack('<%df' % (W * H * D), raw_volume[:W * H * D * 4])
lowest, highest = min(values), max(values)
value_range = max(1e-9, highest - lowest)
voxel = lambda i, j, k: values[(k * H + j) * W + i]
transform = [[sx, 0, 0, 0], [0, sy, 0, 0], [0, 0, dz, 0], [0, 0, 0, 1]]
world_to_voxel = reslicer_test.invert(transform)


try:
    import numpy
except ImportError:  # the pure-Python oracle below is the reference; numpy only makes large planes tractable
    numpy = None


def oracle_numpy(view, background):
    """Same conventions as reslicer_test.oracle, vectorised for CT-sized planes."""
    c, sp = view['orientation'], view['spacing']
    grid = numpy.asarray(values, dtype=numpy.float64).reshape(D, H, W)
    xs, ys = numpy.meshgrid(numpy.arange(view['width']), numpy.arange(view['height']))
    origin = numpy.asarray(view['origin'])
    row = numpy.asarray(c[0:3]) * sp
    col = numpy.asarray(c[3:6]) * sp
    normal = numpy.cross(row, col); normal /= numpy.linalg.norm(normal)
    thickness, step = view['sliceThickness'], min(sx, sy, dz)
    count = max(2, int(numpy.ceil(thickness / step - 1e-9)) + 1) if thickness > 0 else 1
    slab = normal * (thickness / (count - 1)) if count > 1 else numpy.zeros(3)
    centre = origin[None, None, :] + xs[..., None] * row[None, None, :] + ys[..., None] * col[None, None, :]
    inverse = numpy.linalg.inv(numpy.asarray(transform, dtype=numpy.float64))
    accumulated = None
    counted = numpy.zeros(xs.shape, dtype=numpy.int64)
    for s in range(count):
        world = centre + slab[None, None, :] * (s - (count - 1) / 2)
        homogeneous = numpy.concatenate([world, numpy.ones(world.shape[:2] + (1,))], axis=-1)
        v = homogeneous @ inverse.T
        vx, vy, vz = v[..., 0], v[..., 1], v[..., 2]
        inside = (vx >= -0.5) & (vx <= W - 0.5) & (vy >= -0.5) & (vy <= H - 0.5) & (vz >= -0.5) & (vz <= D - 0.5)
        base = numpy.floor(numpy.stack([vx, vy, vz], axis=-1))
        w = numpy.stack([vx, vy, vz], axis=-1) - base
        base = base.astype(numpy.int64)
        def at(di, dj, dk):
            i = numpy.clip(base[..., 0] + di, 0, W - 1); j = numpy.clip(base[..., 1] + dj, 0, H - 1); k = numpy.clip(base[..., 2] + dk, 0, D - 1)
            return grid[k, j, i]
        x00 = at(0, 0, 0) * (1 - w[..., 0]) + at(1, 0, 0) * w[..., 0]
        x10 = at(0, 1, 0) * (1 - w[..., 0]) + at(1, 1, 0) * w[..., 0]
        x01 = at(0, 0, 1) * (1 - w[..., 0]) + at(1, 0, 1) * w[..., 0]
        x11 = at(0, 1, 1) * (1 - w[..., 0]) + at(1, 1, 1) * w[..., 0]
        value = (x00 * (1 - w[..., 1]) + x10 * w[..., 1]) * (1 - w[..., 2]) + (x01 * (1 - w[..., 1]) + x11 * w[..., 1]) * w[..., 2]
        if accumulated is None:
            accumulated = numpy.where(inside, value, 0.0)
        elif view['projection'] == 1:
            accumulated = numpy.where(inside, numpy.where(counted > 0, numpy.maximum(accumulated, value), value), accumulated)
        elif view['projection'] == 2:
            accumulated = numpy.where(inside, numpy.where(counted > 0, numpy.minimum(accumulated, value), value), accumulated)
        else:
            accumulated = numpy.where(inside, accumulated + value, accumulated)
        counted += inside
    if view['projection'] == 3:
        result = numpy.where(counted > 0, accumulated / numpy.maximum(counted, 1), background)
    else:
        result = numpy.where(counted > 0, accumulated, background)
    return [float(x) for x in result.reshape(-1)]


def oracle(view, background):
    if numpy is not None:
        return oracle_numpy(view, background)
    c, sp = view['orientation'], view['spacing']
    plane = {'origin': view['origin'], 'rowStep': [c[0] * sp, c[1] * sp, c[2] * sp],
             'columnStep': [c[3] * sp, c[4] * sp, c[5] * sp], 'width': view['width'], 'height': view['height'],
             'thickness': view['sliceThickness'], 'sampleStep': min(sx, sy, dz),
             'projection': view['projection'], 'background': background}
    return reslicer_test.oracle(voxel, (W, H, D), world_to_voxel, plane)


results = {'volume': {'width': W, 'height': H, 'depth': D, 'spacing': [sx, sy, dz], 'range': [lowest, highest]},
           'tolerances': {'geometry': GEOMETRY_TOLERANCE, 'metalOracleWorst': METAL_ORACLE_WORST,
                          'metalVTKMean': METAL_VTK_MEAN, 'metalVTKWorst': METAL_VTK_WORST, 'maskAgreement': MASK_AGREEMENT},
           'pairs': []}
failures = []
for pair in args.pairs:
    vtk_label, metal_label = pair.split(':')
    vtk, vtk_planes = load(vtk_label)
    metal, metal_planes = load(metal_label)
    entry = {'vtk': vtk_label, 'metal': metal_label, 'mode': metal['clippingRangeMode'],
             'thicknessMm': metal['thicknessMm'], 'metalMilliseconds': metal['lastMilliseconds'],
             'volumeBytes': metal['volumeBytes'], 'fallback': metal['fallbackReason'], 'views': []}
    if not metal['metalEnabled'] or metal['fallbackReason']:
        failures.append('%s: Metal was not active (%r)' % (metal_label, metal['fallbackReason']))
    if vtk['metalEnabled']:
        failures.append('%s: the VTK capture had Metal on' % vtk_label)
    if vtk['clippingRangeMode'] != metal['clippingRangeMode'] or abs(vtk['thicknessMm'] - metal['thicknessMm']) > GEOMETRY_TOLERANCE:
        failures.append('%s: mode or thickness differ between the captures' % pair)
    for index, (a, b) in enumerate(zip(vtk['views'], metal['views'])):
        for key in ('width', 'height'):
            if a[key] != b[key]:
                failures.append('%s view %d: %s differs' % (pair, index + 1, key))
        for key in ('origin', 'orientation'):
            if max(abs(x - y) for x, y in zip(a[key], b[key])) > GEOMETRY_TOLERANCE:
                failures.append('%s view %d: %s differs' % (pair, index + 1, key))
        for key in ('spacing', 'sliceThickness'):
            if abs(a[key] - b[key]) > GEOMETRY_TOLERANCE:
                failures.append('%s view %d: %s differs' % (pair, index + 1, key))
        if b['fallback']:
            failures.append('%s view %d: fallback %r' % (pair, index + 1, b['fallback']))
        b = dict(b, projection=metal['clippingRangeMode'])
        expected = oracle(b, lowest)
        got_metal, got_vtk = metal_planes[index], vtk_planes[index]
        n = len(expected)
        interior = [k for k in range(n) if expected[k] != lowest and got_vtk[k] != lowest]
        worst_oracle = max((abs(expected[k] - got_metal[k]) for k in interior), default=0) / value_range
        diffs = [abs(got_metal[k] - got_vtk[k]) for k in interior]
        mean_vtk = (sum(diffs) / len(diffs) if diffs else 0) / value_range
        worst_vtk = (max(diffs) if diffs else 0) / value_range
        rim = 0
        disagreements = 0
        c, sp, o = b['orientation'], b['spacing'], b['origin']
        for k in range(n):
            if (got_metal[k] == lowest) == (got_vtk[k] == lowest):
                continue
            x, y = k % b['width'], k // b['width']
            world = [o[axis] + x * c[axis] * sp + y * c[3 + axis] * sp for axis in range(3)]
            v = world_to_voxel(world)
            in_rim = all(-0.5 - 1e-6 <= v[axis] <= (W, H, D)[axis] - 0.5 + 1e-6 for axis in range(3))
            if got_metal[k] != lowest and in_rim:
                rim += 1
            else:
                disagreements += 1
        agreement = 1 - disagreements / n
        view_result = {'width': a['width'], 'height': a['height'], 'interior': len(interior),
                       'metalOracleWorst': worst_oracle, 'metalVTKMean': mean_vtk, 'metalVTKWorst': worst_vtk,
                       'maskAgreement': agreement, 'rimOnlyPixels': rim}
        entry['views'].append(view_result)
        if worst_oracle > METAL_ORACLE_WORST:
            failures.append('%s view %d: Metal differs from the oracle by %.4f of range' % (pair, index + 1, worst_oracle))
        if mean_vtk > METAL_VTK_MEAN or worst_vtk > METAL_VTK_WORST:
            failures.append('%s view %d: Metal versus VTK mean %.4f worst %.4f of range' % (pair, index + 1, mean_vtk, worst_vtk))
        if agreement < MASK_AGREEMENT:
            failures.append('%s view %d: masks agree on %.3f of pixels' % (pair, index + 1, agreement))
        print('%s view %d (%dx%d, %d interior): oracle worst %.5f, VTK mean %.5f worst %.5f, mask %.4f (%d rim-only)'
              % (pair, index + 1, a['width'], a['height'], len(interior), worst_oracle, mean_vtk, worst_vtk, agreement, rim))
    results['pairs'].append(entry)

results['failures'] = failures
args.results.write_text(json.dumps(results, indent=1) + '\n')
if failures:
    raise SystemExit('\n'.join(failures))
print('all %d pairs within the tolerances fixed beforehand; results in %s' % (len(args.pairs), args.results))
