#!/usr/bin/env python3
"""Volume rendering draws MIP, MinIP and mean in Metal, as VTK draws them (#659).

The VR host used to refuse every projection (`renderingMode != 0`), so a MIP drew
with VTK's CPU ray caster. It now draws in Metal, and two things had to follow
VTK for the picture to be the same, both checked here:

* where the samples fall: the snapshot hands the renderer the mapper's own
  SampleDistance and the camera's clipping planes, in millimetres, and asks for
  anchored sampling (the rule itself is measured against an oracle in
  `tests/test-volume-metal-renderer.py`);
* how a reduced value is painted: `VTKKWRCHelper_LookupColorMax` writes the
  colour of the value premultiplied by the scalar opacity at that value, in 15
  bits, and the opacity table is not corrected for the step outside composite.
  `HorosVolumeRenderer.projectionPicture` is compared here, entry by entry,
  with an independent Python rendering of VTK's functions: the colour from
  `BuildFunctionFromTable` with 255 entries over the window, the opacity from
  the curve's points with VTK's added end points, clamped outside, and the
  fixed-point premultiplication. A ray with no sample stays at zero.

Also checked in the sources: the hook paints projections with that picture
instead of taking the scalar for an opacity, VTK's cropping regions are still
refused (the crop box itself is #664's), MIP and MinIP leap bricks that cannot change them and an anchored
projection samples through the hardware filter (without both, the Release
campaign measured Metal slower than VTK's CPU MIP), and the capture tool keeps a
projection's sample phase on VTK's near plane when it renders from its derived
camera.

`<git revision>` as an optional argument reads the sources from that revision,
the negative control.
"""
from pathlib import Path
import json
import math
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
revision = sys.argv[1] if len(sys.argv) > 1 else None


def read(path):
    if revision:
        return subprocess.check_output(['git', '-C', str(root), 'show', revision + ':' + path]).decode('utf-8')
    return (root / path).read_text()


failures = []
bridge = read('Horos/Sources/VRHostBridge.mm')
renderer = read('Horos/Sources/VolumeMetalRenderer.swift')
capture = read('tools/capture-native-volume-metal.py')

hook = bridge[bridge.index('- (BOOL)horosRenderMetalImageForMapper:'):bridge.index('- (NSDictionary *)horosVolumeSnapshot')]
if 'renderingMode != 0) reason' in hook or 'This projection uses the original renderer.' in hook:
    failures.append('the VR hook still refuses projections')
if 'mapper->GetCropping()' not in hook:
    failures.append('the VR hook no longer refuses VTK cropping regions, which the renderer does not reproduce')
# The picture is painted by a helper the comparison window shares (#671).
picture = bridge[bridge.index('static NSData *HorosVolumePicture('):bridge.index('static NSData *HorosComposedBGRA(')]
if 'projectionPictureWithScalar:' not in picture or 'HorosVolumePicture(pixels, opacity, renderingMode == 0 ? nil :' not in hook:
    failures.append('the VR hook paints a projection with its scalar as an opacity, not with VTK\'s colour and opacity')
snapshot = bridge[bridge.index('- (NSDictionary *)horosVolumeSnapshot'):]
# The camera, and a projection's near and far planes, come from a helper both volumes share (#671).
camera = bridge[bridge.index('- (NSDictionary *)horosVolumeCameraSnapshot {'):bridge.index('- (NSDictionary *)horosVolumeSnapshot')]
if 'aCamera->GetClippingRange(range)' not in camera or '[self horosVolumeCameraSnapshot]' not in snapshot:
    failures.append('the VR snapshot does not hand a projection the camera\'s clipping planes')
for needle, why in [('volumeMapper->GetSampleDistance() / factor', 'the mapper\'s sample distance'),
                    ('@"anchoredProjection": @(projection)', 'anchored sampling'),
                    ('@"projectionOpacity": projectionOpacity', 'the unscaled opacity curve')]:
    if needle not in snapshot:
        failures.append('the VR snapshot does not hand a projection %s' % why)
if 'anchoredProjection:[snapshot[@"anchoredProjection"] boolValue]' not in bridge:
    failures.append('the bridge does not pass anchored sampling to the renderer')
if 'if (anchored) tStart = tNear + (floor((max(tEntry, tNear) - tNear) / p.clip.w) + 1.0) * p.clip.w;' not in renderer:
    failures.append('the renderer does not anchor a projection\'s samples on the near plane')
if 'unchanged = mode == 1 ? values.y <= reduced : values.x >= reduced;' not in renderer:
    failures.append('MIP and MinIP do not leap bricks that cannot change them, as VTK\'s MIP leaps cells; the Release campaign measured the renderer slower than VTK without it')
if 'sampleVolume(volume, v, inside, mode == 0 || anchored)' not in renderer:
    failures.append('an anchored projection does not take the hardware filter; the Release campaign measured it slower than VTK without it')
if 'f375Near' not in capture or 'anchoredProjection' not in capture:
    failures.append('the capture tool renders projections from its derived eye, not from VTK\'s near plane')
if 'projectionPicture(' not in renderer:
    failures.append('the renderer facade has no projection picture')
if failures:
    for failure in failures:
        print('FAIL:', failure)
    raise SystemExit(1)

# --- the picture, against an independent rendering of VTK's functions ---------
CASES = []
clut_ramp = [[i, (i * 3) % 256, 255 - i] for i in range(256)]
clut_steps = [[0, 0, 255] if i < 100 else ([255, 255, 0] if i < 200 else [255, 0, 0]) for i in range(256)]
curves = [[], [[0, 0], [256, 1]], [[40, 0], [120, 0.3], [200, 0.9]], [[0, 0.25], [128, 0.5]], [[64, 0.8], [192, 0.2], [256, 1]]]
values = [-3000.0, -1024.0, -1.0, 0.0, 0.5, 13.25, 99.9, 100.0, 250.0, 399.0, 400.0, 401.0, 555.5, 5000.0]
for curve in curves:
    for clut in (clut_ramp, clut_steps):
        for level, width in ((200.0, 400.0), (-50.5, 1000.0)):
            CASES.append({'curve': curve, 'clut': clut, 'level': level, 'width': width,
                          'values': values + [-4000.0], 'background': -4000.0})


def vtk_picture(case):
    level, width = case['level'], case['width']
    start, end = level - width / 2, level + width / 2
    # VRView setOpacity: points over the window; (start, 0) unless the first is
    # at 0; (end, 1) unless the last is at 256; vtkPiecewiseFunction clamps.
    points = [(p[0], p[1]) for p in case['curve']]
    function = []
    if not points or points[0][0] != 0:
        function.append((start, 0.0))
    function += [(start + p[0] / 256 * (end - start), p[1]) for p in points]
    if not points or points[-1][0] != 256:
        function.append((end, 1.0))
    function.sort(key=lambda p: p[0])

    def opacity(value):
        if value <= function[0][0]:
            return function[0][1]
        for a, b in zip(function, function[1:]):
            if value <= b[0]:
                return a[1] + (b[1] - a[1]) * (value - a[0]) / (b[0] - a[0]) if b[0] > a[0] else b[1]
        return function[-1][1]

    def colour(value, channel):
        # BuildFunctionFromTable(start, end, 255, table): entries 0..254 evenly
        # over the window, linear between them, clamped outside.
        position = min(254.0, max(0.0, (value - start) / (end - start) * 254))
        lower = int(math.floor(position)); upper = min(254, lower + 1); weight = position - lower
        return (case['clut'][lower][channel] * (1 - weight) + case['clut'][upper][channel] * weight) / 255

    out = []
    for value in case['values']:
        if value == case['background']:
            out += [0, 0, 0, 0]; continue
        alpha = int(min(1.0, max(0.0, opacity(value))) * 32767 + 0.5)
        out += [(int(colour(value, c) * 32767 + 0.5) * alpha + 0x7fff) >> 15 for c in range(3)] + [alpha]
    return out


DRIVER = r'''
import Foundation
@main struct Check {
    static func main() throws {
        let cases = try JSONSerialization.jsonObject(with: Data(contentsOf: URL(fileURLWithPath: CommandLine.arguments[1]))) as! [[String: Any]]
        var pictures = [[Int]]()
        for c in cases {
            let values = (c["values"] as! [Double]).map { Float($0) }
            let clut = (c["clut"] as! [[Int]]).flatMap { entry -> [UInt8] in [UInt8(entry[0]), UInt8(entry[1]), UInt8(entry[2]), 255] }
            let points = (c["curve"] as! [[Double]]).flatMap { $0 }.map { NSNumber(value: $0) }
            let picture = VolumeRendererBridge.projectionPicture(scalar: values.withUnsafeBytes { Data($0) } as NSData,
                level: c["level"] as! Double, width: c["width"] as! Double, clut: Data(clut) as NSData,
                opacityPoints: points, background: c["background"] as! Double) as Data
            pictures.append(picture.withUnsafeBytes { $0.bindMemory(to: UInt16.self).map { Int($0) } })
        }
        print(String(data: try JSONSerialization.data(withJSONObject: pictures), encoding: .utf8)!)
    }
}
'''

with tempfile.TemporaryDirectory(prefix='horos-volume-projection-') as name:
    work = Path(name)
    sources = ['VolumeAllocation.swift', 'VolumeSession.swift', 'MPRMetalReslicer.swift', 'VolumeMetalRenderer.swift',
               'MetalPerformanceTrace.swift', 'MetalComputePipelineCache.swift', 'Metal4ComputeSubmitter.swift']
    for source in sources:
        (work / source).write_text(read('Horos/Sources/' + source))
    (work / 'Check.swift').write_text(DRIVER)
    (work / 'cases.json').write_text(json.dumps(CASES))
    build = subprocess.run(['xcrun', 'swiftc', '-O', '-parse-as-library', '-suppress-warnings',
                            *[str(work / source) for source in sources], str(work / 'Check.swift'), '-o', str(work / 'check')])
    if build.returncode:
        print('FAIL: the renderer does not build with the projection picture driver')
        raise SystemExit(1)
    run = subprocess.run([str(work / 'check'), str(work / 'cases.json')], capture_output=True, text=True, timeout=60)
    if run.returncode:
        print(run.stdout + run.stderr)
        print('FAIL: the projection picture driver failed')
        raise SystemExit(1)
    pictures = json.loads(run.stdout)

compared = 0
for case, picture in zip(CASES, pictures):
    expected = vtk_picture(case)
    if picture != expected:
        index = next(i for i in range(len(expected)) if picture[i] != expected[i])
        print('FAIL: value %r, curve %r, window %r/%r: channel %d is %d, VTK writes %d'
              % (case['values'][index // 4], case['curve'], case['level'], case['width'], index % 4, picture[index], expected[index]))
        raise SystemExit(1)
    compared += len(case['values'])
print('PASS: %d projected values painted as VTK paints them (%d curves, 2 CLUTs, 2 windows, no-sample rays at zero); '
      'the hook, the snapshot and the capture tool sample and paint projections as VTK' % (compared, len(curves)))
