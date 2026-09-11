#!/usr/bin/env python3
"""Read, and optionally drive, the host's 3D MPR in a running Horos (#374).

Attaches LLDB to the development process (which needs get-task-allow), finds
the first MPRController, optionally changes its state through the very
methods the menu and toolbar call, then writes one JSON snapshot and the raw
float pixels of the three planes. Used for the Metal-versus-VTK comparison;
see docs/mpr-metal-reslice-validation.md. Snapshots and logs stay local.

    python3 tools/capture-native-mpr-metal.py vtk-mip --pid 123
    python3 tools/capture-native-mpr-metal.py metal-mip --pid 123 --metal on
    python3 tools/capture-native-mpr-metal.py metal-mean --pid 123 --mode 3 --thickness 4
"""
import argparse
import json
from pathlib import Path
import re
import subprocess
import uuid

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('label')
parser.add_argument('--pid', type=int, required=True)
parser.add_argument('--metal', choices=['on', 'off'], help='set Use Metal in MPR before reading')
parser.add_argument('--mode', type=int, choices=[0, 1, 2, 3], help='clipping range mode: 0 VR, 1 MIP, 2 MinIP, 3 mean')
parser.add_argument('--thickness', type=float, help='slab thickness in mm')
parser.add_argument('--rotate', type=float, help='rotate the first view camera by this many degrees before reading')
parser.add_argument('--kernel', choices=['on', 'off'], help='A216: put a 3x3 sharpen kernel on the first view\'s pix, or remove it')
parser.add_argument('--roi', action='store_true', help='draw an oval ROI on the target view, in pixel units, before reading')
parser.add_argument('--movie-index', type=int, help='4D: select this phase through the controller before reading')
parser.add_argument('--view', type=int, choices=[1, 2, 3], default=1, help='which MPR view --rotate, --kernel and --roi act on')
parser.add_argument('--output', type=Path, default=Path('local-validation/issue-374-native'))
args = parser.parse_args()
if args.pid <= 0 or not re.fullmatch('[a-z0-9-]+', args.label):
    parser.error('Use a positive PID and a lowercase snapshot label')
args.output.mkdir(parents=True, exist_ok=True)
output = (args.output / (args.label + '.json')).resolve()
staged = output.with_name(output.name + '.' + uuid.uuid4().hex + '.partial')
pixels = (args.output / (args.label + '.f32')).resolve()
volume_file = (args.output / (args.label + '.vol')).resolve()

actions = ''
if args.metal:
    actions += ('if ((BOOL)[m374C horosMPRMetalEnabled] != (BOOL)%d) { (void)[m374C toggleMPRMetal:nil]; }\n'
                % (1 if args.metal == 'on' else 0))
if args.mode is not None:
    actions += '(void)[m374C setClippingRangeMode:(int)%d];\n' % args.mode
if args.thickness is not None:
    actions += '(void)[m374C setClippingRangeThickness:(float)%g];\n' % args.thickness
if args.rotate is not None:
    # Roll the first view's camera about its own viewing direction, through
    # the same Camera object the host restores before each reconstruction.
    actions += ('{ id v = (id)[m374C mprViewN]; id cam = (id)[v camera]; id up = (id)[cam viewUp]; id pos = (id)[cam position]; id foc = (id)[cam focalPoint];'
                ' double dx = (double)(float)[foc x] - (double)(float)[pos x], dy = (double)(float)[foc y] - (double)(float)[pos y], dz = (double)(float)[foc z] - (double)(float)[pos z];'
                ' double l = sqrt(dx*dx+dy*dy+dz*dz); dx /= l; dy /= l; dz /= l;'
                ' double ux = (double)(float)[up x], uy = (double)(float)[up y], uz = (double)(float)[up z];'
                ' double cx = dy*uz - dz*uy, cy = dz*ux - dx*uz, cz = dx*uy - dy*ux;'
                ' double a = %g * M_PI / 180.0, ca = cos(a), sa = sin(a);'
                ' (void)[cam setViewUp:(id)[(id)objc_getClass("Point3D") pointWithX:(float)(ca*ux + sa*cx) y:(float)(ca*uy + sa*cy) z:(float)(ca*uz + sa*cz)]];'
                ' (void)[v restoreCamera]; (void)[cam setForceUpdate:YES]; (void)[v updateViewMPR]; }\n' % args.rotate)
if args.movie_index is not None:
    actions += '(void)[m374C setCurMovieIndex:(int)%d];\n' % args.movie_index
if args.kernel is not None:
    if args.kernel == 'on':
        actions += ('{ id p = (id)[(id)[m374C mprViewN] pix]; float k[9] = {0,-1,0,-1,5,-1,0,-1,0}; (void)[p setConvolutionKernel:k :3 :1.0f];'
                    ' (void)[(id)[m374C mprViewN] setNeedsDisplay:YES]; }\n')
    else:
        actions += ('{ id p = (id)[(id)[m374C mprViewN] pix]; (void)[p setConvolutionKernel:(float*)0 :0 :0.0f];'
                    ' (void)[(id)[m374C mprViewN] setNeedsDisplay:YES]; }\n')
if args.roi:
    actions += ('{ id v = (id)[m374C mprViewN]; id p = (id)[v pix]; NSPoint io; io.x = (CGFloat)(double)[p originX]; io.y = (CGFloat)(double)[p originY];'
                ' id r = (id)[[(id)objc_getClass("ROI") alloc] initWithType:(long)9 :(float)[p pixelSpacingX] :(float)[p pixelSpacingY] :io];'
                ' NSRect rr; rr.origin.x = (CGFloat)((double)[p pwidth]*0.5-12); rr.origin.y = (CGFloat)((double)[p pheight]*0.5-8); rr.size.width = 24; rr.size.height = 16;'
                ' (void)[r setROIRect:rr]; (void)[r setName:@"f374"];'
                ' (void)[(NSMutableArray*)[v curRoiList] addObject:r]; (void)[r setPix:p]; (void)[r recompute]; (void)[v setNeedsDisplay:YES]; }\n')

actions = actions.replace('mprViewN', 'mprView%d' % args.view)

expression = r'''
id m374C = nil;
for (NSWindow *m374W in (id)[(NSApplication*)NSApp windows]) {
  id wc = (id)[m374W windowController];
  if (wc && (BOOL)[wc isKindOfClass:(Class)objc_getClass("MPRController")]) { m374C = wc; break; }
}
if (!m374C) { (void)printf("no MPRController\n"); }
else {
ACTIONS
NSMutableDictionary *m374S = [NSMutableDictionary dictionary];
m374S[@"controller"] = [NSString stringWithFormat:@"%p", m374C];
m374S[@"metalEnabled"] = @((BOOL)[m374C horosMPRMetalEnabled]);
m374S[@"fallbackReason"] = (id)[m374C horosMPRFallbackReason] ?: @"";
m374S[@"lastMilliseconds"] = @((double)[m374C horosMPRLastMilliseconds]);
m374S[@"volumeBytes"] = @((long)[m374C horosMPRVolumeBytes]);
m374S[@"clippingRangeMode"] = @((int)[m374C clippingRangeMode]);
m374S[@"clippingRangeThickness"] = @((float)[m374C clippingRangeThickness]);
m374S[@"thicknessMm"] = @((float)[m374C getClippingRangeThicknessInMm]);
m374S[@"movieIndex"] = @((int)[m374C curMovieIndex]);
m374S[@"maxMovieIndex"] = @((int)[m374C maxMovieIndex]);
id m374O = (id)[m374C originalPix];
m374S[@"volume"] = @{@"width": @((long)[m374O pwidth]), @"height": @((long)[m374O pheight]),
  @"spacingX": @((double)[m374O pixelSpacingX]), @"spacingY": @((double)[m374O pixelSpacingY]),
  @"sliceInterval": @((double)[m374O sliceInterval]), @"sliceThickness": @((double)[m374O sliceThickness]),
  @"originX": @((double)[m374O originX]), @"originY": @((double)[m374O originY]), @"originZ": @((double)[m374O originZ]),
  @"depth": @((long)[(NSArray*)[(id)[(NSArray*)[(id)objc_getClass("ViewerController") get2DViewers] firstObject] pixList] count])};
NSMutableArray *m374Views = [NSMutableArray array];
NSMutableData *m374Pixels = [NSMutableData data];
for (id m374V in @[(id)[m374C mprView1], (id)[m374C mprView2], (id)[m374C mprView3]]) {
  id p = (id)[m374V pix];
  float m374Cos[9]; (void)[p orientation:m374Cos];
  long w = (long)[p pwidth], h = (long)[p pheight];
  NSMutableDictionary *d = [NSMutableDictionary dictionary];
  d[@"width"] = @(w); d[@"height"] = @(h);
  double m374Sp = (double)[p pixelSpacingX]; d[@"spacing"] = isfinite(m374Sp) ? @(m374Sp) : (id)@"non-finite";
  double m374Or[3] = {(double)[p originX], (double)[p originY], (double)[p originZ]};
  d[@"origin"] = @[isfinite(m374Or[0]) ? @(m374Or[0]) : (id)@"non-finite", isfinite(m374Or[1]) ? @(m374Or[1]) : (id)@"non-finite", isfinite(m374Or[2]) ? @(m374Or[2]) : (id)@"non-finite"];
  d[@"orientation"] = @[@(m374Cos[0]),@(m374Cos[1]),@(m374Cos[2]),@(m374Cos[3]),@(m374Cos[4]),@(m374Cos[5]),@(m374Cos[6]),@(m374Cos[7]),@(m374Cos[8])];
  d[@"sliceThickness"] = @((double)[p sliceThickness]);
  d[@"wl"] = @((float)[m374V curWL]); d[@"ww"] = @((float)[m374V curWW]);
  d[@"scale"] = @((float)[m374V scaleValue]);
  d[@"fallback"] = (id)[m374V horosPlanarFallbackReason] ?: @"";
  d[@"convolution"] = @((BOOL)[p horosPlanarHasPresentationFilter]);
  d[@"roiCount"] = @((long)[(NSArray*)[m374V curRoiList] count]);
  NSMutableArray *rois = [NSMutableArray array];
  for (id r in (NSArray*)[m374V curRoiList]) { float m374Mean=0, m374Total=0, m374Dev=0, m374Min=0, m374Max=0; (void)[p computeROI:r :&m374Mean :&m374Total :&m374Dev :&m374Min :&m374Max];
    (void)[rois addObject:@{@"name": (id)[r name] ?: @"", @"mean": @(m374Mean), @"max": @(m374Max), @"min": @(m374Min), @"dev": @(m374Dev), @"pixels": @(m374Total), @"type": @((long)[r type])}]; }
  d[@"rois"] = rois;
  d[@"offset"] = @((long)[m374Pixels length]);
  float *f = (float*)[p fImage];
  if (f) (void)[m374Pixels appendBytes:f length:(NSUInteger)(w*h*4)];
  (void)[m374Views addObject:d];
}
m374S[@"views"] = m374Views;
(void)[m374Pixels writeToFile:PIXELS atomically:YES];
(void)[(NSData*)[(id)[(NSArray*)[(id)objc_getClass("ViewerController") get2DViewers] firstObject] volumeData] writeToFile:VOLUME atomically:YES];
(void)[[NSJSONSerialization dataWithJSONObject:m374S options:3 error:nil] writeToFile:OUTPUT atomically:YES];
}
'''.replace('ACTIONS', actions).replace('OUTPUT', '@' + json.dumps(str(staged))).replace('PIXELS', '@' + json.dumps(str(pixels))).replace('VOLUME', '@' + json.dumps(str(volume_file))).replace('EXCEPTION', '@' + json.dumps(str(args.output.resolve() / (args.label + '.exception.txt'))))
commands = args.output / (args.label + '.lldb')
commands.write_text('expression -l objc++ -- @import AppKit\n'
                    'expression -l objc++ -- { ' + ' '.join(expression.splitlines()) + ' }\n'
                    'process detach\n')
result = subprocess.run(['xcrun', 'lldb', '--batch', '-p', str(args.pid), '-s', str(commands)],
                        capture_output=True, text=True)
(args.output / (args.label + '.log')).write_text(result.stdout + result.stderr)
if result.returncode or not staged.exists():
    raise SystemExit('Capture failed; inspect the local LLDB log')
staged.replace(output)
state = json.loads(output.read_text())
print('%s: metal=%s mode=%d thickness=%.2f mm ms=%.3f bytes=%d fallback=%r' % (
    args.label, state['metalEnabled'], state['clippingRangeMode'], state['thicknessMm'],
    state['lastMilliseconds'], state['volumeBytes'], state['fallbackReason']))
for index, view in enumerate(state['views']):
    print('  view %d: %dx%d spacing %.4f origin %s thickness %.2f fallback=%r' % (
        index + 1, view['width'], view['height'], view['spacing'],
        ['%.3f' % v for v in view['origin']], view['sliceThickness'], view['fallback']))
