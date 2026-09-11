#!/usr/bin/env python3
"""Verify local A295 native captures against independent patient geometry.

Uses only synthetic captures from capture-native-patient-crosshair.py. Read
docs/patient-crosshair-validation.md for the scenario, build phases and limits.
No UI events are generated here. Pixel buffers and identities remain local.
"""
import argparse
import json
import math
from pathlib import Path

GEOMETRY_EPSILON = 1e-4  # mm; declared before the native comparison
MPR_EPSILON = 0.50001   # half of the synthetic 1 mm reslice voxel
LABELS = (
    'baseline oblique-click oblique-drag hidden shown zoom pan flip-x flip-y '
    'rotation roi-length axial-click sagittal-click coronal-click frame-check-off '
    'mpr-source mpr-hidden mpr-receiver metal invalidated mpr-before-close '
    'mpr-closed planar-before-close planar-closed'
).split()
STUDY = '2.25.171473494598174573636010241172861156222'
COMMON_FRAME = '2.25.266143709534856121380824073041177203202'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def near(a, b, tolerance=GEOMETRY_EPSILON):
    return len(a) == len(b) and all(math.isfinite(x) and math.isfinite(y) and
                                  abs(x-y) <= tolerance for x, y in zip(a, b))


def dot(a, b):
    return sum(x*y for x, y in zip(a, b))


def viewer(state, name):
    matches = [v for v in state['viewers'] if v['title'].strip() == 'Crossref '+name]
    require(len(matches) == 1, 'Missing or duplicate viewer '+name)
    return matches[0]


def verify_capture(state, directory, label):
    point = state['point']
    if point is not None:
        require(len(point) == 3 and all(math.isfinite(v) for v in point), label+': finite point')
        require(state['pointIdentity']['study'] == STUDY and
                state['pointIdentity']['frame'] == COMMON_FRAME, label+': unexpected point identity')
        owners = [v['controller'] for v in state['viewers']]+[m['owner'] for m in state['mpr']]
        require(state['sourceOwner'] in owners, label+': orphaned source')
    else:
        require(state['sourceOwner'] == '0x0', label+': cleared point retains its source')
    marker_pixels = []
    max_error = 0
    for v in state['viewers']:
        context = label+'/'+v['title'].strip()
        require(v['count'] == 16 and v['dimensions'] == [32, 32] and
                v['spacing'] == [1, 1] and 0 <= v['index'] < 16, context+': fixture shape')
        row, col, normal = [v['orientation'][i:i+3] for i in (0, 3, 6)]
        cross = [row[1]*col[2]-row[2]*col[1], row[2]*col[0]-row[0]*col[2],
                 row[0]*col[1]-row[1]*col[0]]
        require(near(cross, normal) and abs(dot(row,col)) < GEOMETRY_EPSILON and
                all(abs(dot(axis,axis)-1) < GEOMETRY_EPSILON for axis in (row,col,normal)),
                context+': orthonormal DICOM basis')
        expected_marker = False
        if point is not None:
            delta = [p-o for p, o in zip(point, v['origin'])]
            projected = [dot(delta,row)+0.5, dot(delta,col)+0.5, dot(delta,normal)]
            require(near(projected, v['projectedSliceMM']), context+': patient projection')
            max_error = max(max_error, max(abs(a-b) for a,b in zip(projected,v['projectedSliceMM'])))
            admitted = not state['frameCheck'] or v['frameUID'] == state['pointIdentity']['frame']
            on_plane = abs(projected[2]) <= 0.5*max(abs(v['sliceInterval']), abs(v['sliceThickness']))+0.001
            expected_marker = state['visible'] and admitted and on_plane and all(0 <= x < 32 for x in projected[:2])
            if expected_marker:
                require(near(projected,v['markerSliceMM']), context+': drawn coordinate')
        require(v['markerVisible'] == expected_marker, context+': visibility/frame/plane policy')
        require(v['glError'] == 0 and not v['fallback'], context+': rendering error or fallback')
        w,h = v['bufferSize']
        require(w > 0 and h > 0 and w == int(w) and h == int(h), context+': buffer dimensions')
        filename = Path(v['bufferFile'])
        require(filename.name == str(filename), context+': nonlocal buffer path')
        data = (directory/filename).read_bytes()
        require(len(data) == w*h*4, context+': incomplete front buffer')
        if expected_marker:
            x,y = v['markerBacking']; count = 0
            for yy in range(max(0,int(y)-15),min(h,int(y)+16)):
                for xx in range(max(0,int(x)-15),min(w,int(x)+16)):
                    b,g,r,a = data[(yy*w+xx)*4:(yy*w+xx)*4+4]
                    count += 195 <= g <= 215 and 40 <= b <= 65 and r <= 5
            # Reference lines are drawn afterwards and can cover some arms.
            # This proves presence at the projected screen point; it is not
            # a claim that all 64 marker pixels remain unobscured.
            require(count > 0, context+': marker absent from front buffer')
            marker_pixels.append(count)
        else:
            # Grayscale phantoms and existing line colours contain no exact
            # crosshair colour. Scan the whole viewport to catch stale markers.
            require(data.count(bytes((51,204,0,255))) == 0, context+': stale marker pixels')
    return max_error, marker_pixels


def verify(directory):
    states = {}
    errors, pixels = [], []
    for label in LABELS:
        state = json.loads((directory/('final-'+label+'.json')).read_text())
        error, counts = verify_capture(state,directory,label)
        errors.append(error); pixels.extend(counts); states[label] = state
    # The final observer fix repeats the policy switch without another mouse
    # event, with the incompatible series already on the same geometric plane.
    for label in ('policy-on','policy-off','policy-restored'):
        state = json.loads((directory/(label+'.json')).read_text())
        error, counts = verify_capture(state,directory,label)
        errors.append(error); pixels.extend(counts); states[label] = state
    drag = states['oblique-drag']
    for label in ('hidden','shown','zoom','pan','flip-x','flip-y','rotation','roi-length'):
        state = states[label]
        require(state['point'] == drag['point'] and state['pointIdentity'] == drag['pointIdentity'],
                label+': patient point moved')
        for before, after in zip(drag['viewers'],state['viewers']):
            require(all(before[k] == after[k] for k in ('controller','pixList','roiList','index','series')),
                    label+': viewer identity or slice changed')
    require(not states['hidden']['visible'] and states['shown']['visible'], 'Visibility toggle not exercised')
    for label, name in (('oblique-click','Oblique (8)'),('oblique-drag','Oblique (8)'),
                        ('axial-click','Axial (1)'),('sagittal-click','Sagittal (2)'),('coronal-click','Coronal (3)')):
        state = states[label]; source = viewer(state,name)
        require(source['controller'] == state['sourceOwner'] and source['key'] and source['tool'] == 8,
                label+': input did not reach the intended source')
    require(not near(states['oblique-click']['point'],drag['point']), 'Drag did not move point')
    for label in ('oblique-click','oblique-drag','axial-click','sagittal-click'):
        state = states[label]
        require(sum(v['markerVisible'] and not v['key'] for v in state['viewers']) == 3,
                label+': three inactive compatible views must display markers')
        require(viewer(state,'Axial Pair C (7)')['index'] == 0, label+': incompatible control moved')
    original = viewer(drag,'Oblique (8)')
    require(viewer(states['zoom'],'Oblique (8)')['scale'] != original['scale'], 'Zoom not exercised')
    require(not near(viewer(states['pan'],'Oblique (8)')['markerOrCenterScreen'],
                     viewer(states['zoom'],'Oblique (8)')['markerOrCenterScreen']), 'Pan not exercised')
    require(viewer(states['flip-x'],'Oblique (8)')['xFlipped'] and
            viewer(states['flip-y'],'Oblique (8)')['yFlipped'] and
            viewer(states['rotation'],'Oblique (8)')['rotation'] == 90, 'Transform cases missing')
    rois = viewer(states['roi-length'],'Oblique (8)')['rois']
    lengths = [math.dist(r['points'][0],r['points'][1]) for r in rois if r['type'] == 5 and len(r['points']) == 2]
    # The native label shows 1.216 cm (0.01 mm displayed precision).
    require(len(lengths) == 1 and abs(lengths[0]-12.16) <= 0.005,
            'Native Length ROI did not survive mouse-up or disagrees with its label')
    require(not states['frame-check-off']['frameCheck'] and
            viewer(states['frame-check-off'],'Axial Pair C (7)')['markerVisible'], 'Explicit frame opt-out not exercised')
    for label, checked in (('policy-on',True),('policy-off',False),('policy-restored',True)):
        state = states[label]
        require(state['frameCheck'] == checked and state['point'] == states['policy-on']['point'], label+': preference/point')
        require(viewer(state,'Axial Pair C (7)')['markerVisible'] == (not checked), label+': immediate redraw')
    require(states['mpr-source']['sourceOwner'] == states['mpr-source']['mpr'][0]['owner'], 'MPR did not publish')
    require(not states['mpr-hidden']['visible'] and states['mpr-hidden']['point'] == states['mpr-source']['point'], 'MPR toggle changed point')
    receiver = states['mpr-receiver']; require(not receiver['mpr'][0]['key'], 'MPR receiver was not inactive')
    mpr_error = math.dist(receiver['point'],receiver['mpr'][0]['patient'])
    require(mpr_error <= MPR_EPSILON, 'MPR quantization exceeded half voxel')
    require(viewer(states['metal'],'Oblique (8)')['metal'] and states['metal']['point'] == receiver['point'], 'Metal changed point or did not run')
    for label in ('invalidated','mpr-closed','planar-closed'):
        require(states[label]['point'] is None, label+': stale source point')
    require(states['mpr-before-close']['point'] is not None and states['planar-before-close']['point'] is not None,
            'Close tests had no source point')
    require(not states['mpr-closed']['mpr'] and len(states['planar-closed']['viewers']) == 2, 'Close action did not complete')
    return {'captures':len(states),'maxProjectionErrorMM':max(errors),'mprErrorMM':mpr_error,
            'markerPixelCountRange':[min(pixels),max(pixels)],'nativeLengthMM':lengths[0]}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory',type=Path)
    args = parser.parse_args()
    try:
        print('PASS: '+json.dumps(verify(args.directory),sort_keys=True))
    except (ValueError,KeyError,IndexError,OSError) as error:
        parser.exit(1,'FAIL: '+str(error)+'\n')
