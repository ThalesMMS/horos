#!/usr/bin/env python3
"""Compare native 3D captures: the Metal render of the host's state against VTK's own pixels (#375).

Input: snapshots written by tools/capture-native-volume-metal.py. For every
label the tool reads the Metal BGRA render, VTK's 8-bit RGB screen capture
and, for projections, both scalar images, and reports:

- projections (MIP/MinIP/mean): on pixels both renderers consider inside,
  mean |Δ| and worst |Δ| of the scalar as a fraction of the volume's window
  range, plus the fraction of pixels whose inside/outside masks agree;
- composite: mean channel |Δ| over the pixels either renderer lit, the
  fraction of pixels whose lit/unlit state agrees, and the fraction of lit
  pixels within 32/255 on every channel;
- a downscaled side-by-side PPM (VTK left, Metal right) for a human look.

Tolerances, fixed before any comparison and written to the results file:
projections mean ≤ 1 % of range, worst ≤ 3 %, masks ≥ 98 %; composite mean
channel |Δ| ≤ 8/255, lit/unlit agreement ≥ 95 %, ≥ 90 % of lit pixels within
32/255 per channel (the two renderers sample the ray and correct opacity for
the step in their own way, so a tighter bound would be pretending).

    python3 tools/compare-native-volume-metal.py vr-mip vr-bone --results docs/volume-metal-results.json
"""
import argparse
import json
import struct
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('labels', nargs='+')
parser.add_argument('--directory', type=Path, default=Path('local-validation/issue-375-native'))
parser.add_argument('--results', type=Path, default=Path('docs/volume-metal-results.json'))
parser.add_argument('--preview-scale', type=int, default=4)
args = parser.parse_args()

TOLERANCES = {'projectionMean': 0.01, 'projectionWorst': 0.03, 'projectionMask': 0.98,
              'compositeMeanChannel': 8 / 255, 'compositeLitAgreement': 0.95, 'compositeWithin32': 0.90}


def load(label):
    base = args.directory / label
    state = json.loads((base.with_suffix('.json')).read_text())
    metal = (args.directory / (label + '.metal.bgra')).read_bytes()
    vtk = (args.directory / (label + '.vtk.rgb')).read_bytes()
    metal_scalar = vtk_scalar = None
    if (args.directory / (label + '.metal.full.f32')).exists():
        metal_scalar = (args.directory / (label + '.metal.full.f32')).read_bytes()
    if (args.directory / (label + '.vtk.f32')).exists():
        vtk_scalar = (args.directory / (label + '.vtk.f32')).read_bytes()
    return state, metal, vtk, metal_scalar, vtk_scalar


def preview(label, width, height, metal, vtk, vtk_width, vtk_height, spp):
    scale = args.preview_scale
    pw, ph = width // scale, height // scale
    rows = []
    for y in range(ph):
        row = bytearray()
        for x in range(pw):
            sx, sy = x * scale, y * scale
            if sx < vtk_width and sy < vtk_height:
                k = (sy * vtk_width + sx) * spp
                row += bytes(vtk[k:k + 3]) if spp >= 3 else bytes([vtk[k]] * 3)
            else:
                row += b'\0\0\0'
        for x in range(pw):
            k = (y * scale * width + x * scale) * 4
            row += bytes([metal[k + 2], metal[k + 1], metal[k]])
        rows.append(bytes(row))
    out = args.directory / (label + '.preview.ppm')
    out.write_bytes(b'P6\n%d %d\n255\n' % (pw * 2, ph) + b''.join(rows))
    return out


results = {'tolerances': TOLERANCES, 'captures': []}
failures = []
for label in args.labels:
    try:
        state, metal, vtk, metal_scalar, vtk_scalar = load(label)
    except FileNotFoundError as missing:
        state = json.loads((args.directory / (label + '.json')).read_text())
        failures.append('%s: no comparable render (%s; fallback %r)' % (label, Path(str(missing)).name, state.get('metalFallback')))
        results['captures'].append({'label': label, 'fallback': state.get('metalFallback'), 'note': 'no comparable render'})
        continue
    width, height = state['renderWidth'], state['renderHeight']
    vw, vh, spp = state['vtkWidth'], state['vtkHeight'], state['vtkSamplesPerPixel']
    entry = {'label': label, 'mode': state['renderingMode'], 'wl': state['wl'], 'ww': state['ww'],
             'clip': state['clippingRangeThicknessMm'] if state['clipRangeActivated'] else None,
             'shading': state['shading'], 'size': [width, height], 'vtkSize': [vw, vh],
             'metalMilliseconds': state['metalMilliseconds'], 'metalVolumeBytes': state['metalVolumeBytes'],
             'fallback': state['metalFallback'], 'footprintBytes': state['footprintBytes']}
    if state['metalFallback'] or len(metal) != width * height * 4:
        failures.append('%s: Metal did not render (%r)' % (label, state['metalFallback']))
        results['captures'].append(entry); continue
    if (vw, vh) != (width, height):
        entry['note'] = 'VTK capture size differs from the view; compared on the overlap'
    n = min(width, vw) * min(height, vh)
    entry['preview'] = str(preview(label, width, height, metal, vtk, vw, vh, spp))
    if state['renderingMode'] != 0 and metal_scalar and vtk_scalar:
        # VTK's full-depth image is at its own sample distance; Metal rendered
        # the same camera at that size, so the scalars compare pixel to pixel.
        width, height = state['vtkFullWidth'], state['vtkFullHeight']
        vs = struct.unpack('<%df' % (width * height), vtk_scalar)
        background_metal = background_vtk = state['snapshot'].get('scalarBackground', min(vs))
        span = max(1e-9, state['snapshot']['width'])
        # VTK rounds its ray-cast image origin to whole window pixels
        # (static_cast<int> in -[VRView getOrigin:...]); the capture rendered
        # eight half-pixel-shifted variants, and the best-aligned one is the
        # comparison, with the chosen shift recorded.
        candidates = [((0, 0), metal_scalar)]
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                shifted = args.directory / ('%s.metal.shift%d_%d.f32' % (label, dx, dy))
                if shifted.exists():
                    candidates.append(((dx * 0.5, dy * 0.5), shifted.read_bytes()))
        def score(raw):
            values = struct.unpack('<%df' % (width * height), raw)
            keep = [k for k in range(width * height) if values[k] != background_metal and vs[k] != background_vtk]
            return sum(abs(values[k] - vs[k]) for k in keep) / max(1, len(keep)), values
        best_shift, (best_mean, ms) = min(((shift, score(raw)) for shift, raw in candidates), key=lambda item: item[1][0])
        entry['alignmentShiftPixels'] = list(best_shift)
        inside = [k for k in range(width * height) if ms[k] != background_metal and vs[k] != background_vtk]
        agree = sum(1 for k in range(width * height) if (ms[k] == background_metal) == (vs[k] == background_vtk)) / (width * height)
        diffs = [abs(ms[k] - vs[k]) for k in inside]
        mean = (sum(diffs) / len(diffs) if diffs else 0) / span
        worst = (max(diffs) if diffs else 0) / span
        # Supplementary, not the tolerance: the same differences against the
        # volume's own value range, as the MPR comparison expressed them.
        value_span = max(1e-9, max(vs) - min(vs))
        entry.update({'kind': 'projection', 'inside': len(inside), 'meanOfRange': mean, 'worstOfRange': worst, 'maskAgreement': agree,
                      'meanOfValueRange': mean * span / value_span, 'worstOfValueRange': worst * span / value_span,
                      'medianAbsHU': sorted(diffs)[len(diffs) // 2] if diffs else 0})
        if mean > TOLERANCES['projectionMean'] or worst > TOLERANCES['projectionWorst'] or agree < TOLERANCES['projectionMask']:
            failures.append('%s: projection mean %.4f worst %.4f mask %.4f' % (label, mean, worst, agree))
        print('%s (%s, %dx%d): projection inside %d, mean %.5f worst %.5f of window, %.5f / %.5f of value range, median |Δ| %.1f, masks %.4f'
              % (label, ['VR', 'MIP', 'MinIP', 'mean'][state['renderingMode']], width, height, len(inside), mean, worst,
                 entry['meanOfValueRange'], entry['worstOfValueRange'], entry['medianAbsHU'], agree))
    else:
        lit_metal = lit_vtk = both = 0; channel = 0.0; within = 0
        for y in range(min(height, vh)):
            for x in range(min(width, vw)):
                km = (y * width + x) * 4; kv = (y * vw + x) * spp
                mr, mg, mb = metal[km + 2], metal[km + 1], metal[km]
                vr, vg, vb = (vtk[kv], vtk[kv + 1], vtk[kv + 2]) if spp >= 3 else (vtk[kv],) * 3
                lm = (mr + mg + mb) > 6; lv = (vr + vg + vb) > 6
                lit_metal += lm; lit_vtk += lv
                if lm or lv:
                    d = (abs(mr - vr) + abs(mg - vg) + abs(mb - vb)) / 3
                    channel += d
                if lm and lv:
                    both += 1
                    if max(abs(mr - vr), abs(mg - vg), abs(mb - vb)) <= 32:
                        within += 1
        either = lit_metal + lit_vtk - both
        mean_channel = (channel / either / 255) if either else 0
        agree = 1 - (either - both) / n
        within_fraction = within / both if both else 0
        entry.update({'kind': 'composite', 'litMetal': lit_metal, 'litVTK': lit_vtk, 'litBoth': both,
                      'meanChannel': mean_channel, 'litAgreement': agree, 'within32': within_fraction})
        if mean_channel > TOLERANCES['compositeMeanChannel'] or agree < TOLERANCES['compositeLitAgreement'] or within_fraction < TOLERANCES['compositeWithin32']:
            failures.append('%s: composite mean channel %.4f lit agreement %.4f within32 %.4f' % (label, mean_channel, agree, within_fraction))
        print('%s (VR, %dx%d): lit metal %d vtk %d both %d, mean channel %.4f, lit agreement %.4f, within 32/255 %.4f'
              % (label, width, height, lit_metal, lit_vtk, both, mean_channel, agree, within_fraction))
    results['captures'].append(entry)

results['failures'] = failures
args.results.write_text(json.dumps(results, indent=1) + '\n')
if failures:
    raise SystemExit('\n'.join(failures))
print('all %d captures within the tolerances fixed beforehand; results in %s' % (len(args.labels), args.results))
