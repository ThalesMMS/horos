#!/usr/bin/env python3
"""Read, and optionally drive, the host's 3D viewer and its Metal twin in a running Horos (#375).

Attaches LLDB to the development process, finds the visible VRController
(the one the user opened, not the hidden one behind the 3D MPR), optionally
changes its state through the controller's and view's own methods, then
writes one JSON snapshot plus: the Metal render of that state at the view's
drawable size (BGRA and, for projections, the scalar image), the VTK pixels
the view itself reports (`getRawPixels`, 8-bit RGB) and, for projections,
VTK's full-depth scalar image. See docs/volume-metal-validation.md.

    python3 tools/capture-native-volume-metal.py vr-mip --pid 123 --mode 1
    python3 tools/capture-native-volume-metal.py vr-bone --pid 123 --preset 'Bone CT:0'
    python3 tools/capture-native-volume-metal.py vr-clip --pid 123 --clip 5 --rotate 30
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
parser.add_argument('--mode', type=int, choices=[0, 1, 2, 3], help='0 volume rendering, 1 MIP, 2 MinIP, 3 mean')
parser.add_argument('--wl', type=float); parser.add_argument('--ww', type=float)
parser.add_argument('--clip', help='clipping range thickness in mm, or "off"')
parser.add_argument('--engine', type=int, choices=[0, 2], help='switch the view to this engine first. A switch keeps the crop '
                    'in place, a camera\'s (--crop) included (#668)')
parser.add_argument('--crop', help='SHRINK[,THIN[,DEGREES]]: the uncropped camera\'s six crop planes moved inward by SHRINK of '
                    'the box on every side (THIN more on the pair along z), turned DEGREES about the box centre around z, '
                    'applied through setCamera: as a saved camera applies them; 0 restores the uncropped planes (#664)')
parser.add_argument('--rotate', type=float, help='azimuth the camera by this many degrees about the view-up axis')
parser.add_argument('--elevate', type=float, help='elevate the camera by this many degrees')
parser.add_argument('--preset', help='GROUP:INDEX from the 3D presets, applied through the controller\'s own steps')
parser.add_argument('--shading', choices=['on', 'off'])
parser.add_argument('--projection', choices=['parallel', 'perspective'])
parser.add_argument('--comparison', action='store_true', help='open the Compare in Metal (3D) window before reading')
parser.add_argument('--drag', help='DX,DY in view points: a synthetic left-button drag from the view centre through the view\'s own mouse handlers (rotate tool)')
parser.add_argument('--debug-crash', action='store_true', help='keep the process stopped at a crash inside the expression and log a backtrace')
parser.add_argument('--output', type=Path, default=Path('local-validation/issue-375-native'))
args = parser.parse_args()
if args.pid <= 0 or not re.fullmatch('[a-z0-9-]+', args.label):
    parser.error('Use a positive PID and a lowercase snapshot label')
args.output.mkdir(parents=True, exist_ok=True)
base = (args.output / args.label).resolve()
staged = Path(str(base) + '.json.' + uuid.uuid4().hex + '.partial')

actions = ''
if args.engine is not None:
    actions += '(void)[f375V setEngine:(long)%d showWait:(BOOL)0];\n' % args.engine
if args.preset:
    group, index = args.preset.rsplit(':', 1)
    if not re.fullmatch(r'[A-Za-z0-9 _-]+', group):
        parser.error('preset group must be plain text')
    actions += ('{ NSArray *f375L = (NSArray *)[f375C find3DSettingsForGroupName:@"%s"]; NSDictionary *f375P = (NSDictionary *)[f375L objectAtIndex:%d];'
                ' (void)[f375C ApplyCLUTString:(NSString *)[f375P objectForKey:@"CLUT"]]; (void)[f375C ApplyOpacityString:(NSString *)[f375P objectForKey:@"opacity"]];'
                ' (void)[f375C setWLWW:(float)[(NSNumber *)[f375P objectForKey:@"wl"] floatValue] :(float)[(NSNumber *)[f375P objectForKey:@"ww"] floatValue]];'
                ' if ([(NSNumber *)[f375P objectForKey:@"useShading"] boolValue]) { NSString *f375SN = (NSString *)[f375P objectForKey:@"shading"]; id f375AC = (id)[(NSObject *)f375C valueForKey:@"shadingsPresetsController"];'
                ' for (NSDictionary *f375D in (NSArray *)[f375AC arrangedObjects]) { if ([(NSString *)[f375D valueForKey:@"name"] isEqualToString:f375SN]) { (void)[f375AC setSelectedObjects:@[f375D]]; break; } }'
                ' (void)[f375C applyShading:f375C]; (void)[f375V activateShading:(BOOL)1]; } else { (void)[f375V activateShading:(BOOL)0]; }'
                ' f375S[@"presetName"] = (NSString *)[f375P objectForKey:@"name"] ?: @""; }\n' % (group, int(index)))
if args.mode is not None:
    if args.mode in (0, 1):
        actions += '(void)[f375C setModeIndex:(long)%d];\n' % args.mode
    else:
        # MinIP and mean are not in the window's matrix; the view takes them.
        actions += '(void)[f375V setMode:(long)%d]; (void)[f375V setBlendingMode:(long)%d];\n' % (args.mode, args.mode)
    # The mean is a mode of the view's own mapper, which setMode: sets (#665).
if args.wl is not None and args.ww is not None:
    actions += '(void)[f375C setWLWW:(float)%g :(float)%g];\n' % (args.wl, args.ww)
if args.clip is not None:
    if args.clip == 'off':
        actions += '(void)[f375V setClipRangeActivated:(BOOL)0];\n'
    else:
        actions += '(void)[f375V setClipRangeActivated:(BOOL)1]; (void)[f375V setClippingRangeThicknessInMm:(double)%g];\n' % float(args.clip)
if args.projection:
    actions += '(void)[f375V setProjectionMode:(int)%d];\n' % (1 if args.projection == 'parallel' else 0)
if args.crop is not None:
    shrink, thin, degrees = (list(map(float, args.crop.split(','))) + [0.0, 0.0])[:3]
    # The first planes seen are the uncropped box; they are kept on the view so a
    # later capture builds its crop from them, and --crop 0 puts them back.
    actions += ('{ id f375Cam = (id)[f375V cameraWithThumbnail:(BOOL)0]; NSMutableArray *f375Pl = (NSMutableArray *)[f375Cam croppingPlanes];'
                ' NSArray *f375Base = (NSArray *)objc_getAssociatedObject((id)f375V, (const void *)@selector(horosRayCastImageRegion));'
                ' if (!f375Base) { f375Base = [f375Pl copy]; (void)objc_setAssociatedObject((id)f375V, (const void *)@selector(horosRayCastImageRegion), (id)f375Base, (objc_AssociationPolicy)1); }'
                ' double f375B[6][6], f375O[6][6], f375Cx = 0, f375Cy = 0;'
                ' for (int i = 0; i < 6; ++i) { (void)[(NSValue *)[f375Base objectAtIndex:i] getValue:f375B[i]]; f375Cx += f375B[i][0] / 6; f375Cy += f375B[i][1] / 6; }'
                ' for (int i = 0; i < 6; ++i) { int j = 0; double best = 2; for (int k = 0; k < 6; ++k) { double dot = f375B[i][3]*f375B[k][3] + f375B[i][4]*f375B[k][4] + f375B[i][5]*f375B[k][5]; if (dot < best) { best = dot; j = k; } }'
                '  double d = f375B[i][3]*(f375B[j][0]-f375B[i][0]) + f375B[i][4]*(f375B[j][1]-f375B[i][1]) + f375B[i][5]*(f375B[j][2]-f375B[i][2]);'
                '  double f = %g + (fabs(f375B[i][5]) > 0.9 ? %g : 0.0);'
                '  double px = f375B[i][0] + f*d*f375B[i][3], py = f375B[i][1] + f*d*f375B[i][4], pz = f375B[i][2] + f*d*f375B[i][5];'
                '  double a = %g * M_PI / 180.0, ca = cos(a), sa = sin(a);'
                '  f375O[i][0] = f375Cx + ca*(px-f375Cx) - sa*(py-f375Cy); f375O[i][1] = f375Cy + sa*(px-f375Cx) + ca*(py-f375Cy); f375O[i][2] = pz;'
                '  f375O[i][3] = ca*f375B[i][3] - sa*f375B[i][4]; f375O[i][4] = sa*f375B[i][3] + ca*f375B[i][4]; f375O[i][5] = f375B[i][5]; }'
                ' for (int i = 0; i < 6; ++i) (void)[f375Pl replaceObjectAtIndex:(NSUInteger)i withObject:[NSValue valueWithBytes:f375O[i] objCType:"{N3Plane={N3Vector=ddd}{N3Vector=ddd}}"]];'
                ' (void)[f375V setCamera:f375Cam]; }\n' % (shrink, thin, degrees))
if args.shading:
    actions += '(void)[f375V activateShading:(BOOL)%d];\n' % (1 if args.shading == 'on' else 0)
if args.rotate is not None or args.elevate is not None:
    # Through the same Camera object the host saves and restores: azimuth
    # about the view-up axis, then elevation about the right axis, both
    # around the focal point.
    actions += ('{ id f375Cam = (id)[f375V cameraWithThumbnail:(BOOL)0]; id f375P = (id)[f375Cam position]; id f375F = (id)[f375Cam focalPoint]; id f375U = (id)[f375Cam viewUp];'
                ' double px = (double)(float)[f375P x] - (double)(float)[f375F x], py = (double)(float)[f375P y] - (double)(float)[f375F y], pz = (double)(float)[f375P z] - (double)(float)[f375F z];'
                ' double ux = (double)(float)[f375U x], uy = (double)(float)[f375U y], uz = (double)(float)[f375U z]; double ul = sqrt(ux*ux+uy*uy+uz*uz); ux /= ul; uy /= ul; uz /= ul;'
                ' double a = %g * M_PI / 180.0, ca = cos(a), sa = sin(a);'
                ' double rx = px*ca + (uy*pz - uz*py)*sa + ux*(ux*px+uy*py+uz*pz)*(1-ca), ry = py*ca + (uz*px - ux*pz)*sa + uy*(ux*px+uy*py+uz*pz)*(1-ca), rz = pz*ca + (ux*py - uy*px)*sa + uz*(ux*px+uy*py+uz*pz)*(1-ca);'
                ' double e = %g * M_PI / 180.0, ce = cos(e), se = sin(e);'
                ' double fx = -rx, fy = -ry, fz = -rz; double fl = sqrt(fx*fx+fy*fy+fz*fz); fx /= fl; fy /= fl; fz /= fl;'
                ' double kx = fy*uz - fz*uy, ky = fz*ux - fx*uz, kz = fx*uy - fy*ux; double kl = sqrt(kx*kx+ky*ky+kz*kz); kx /= kl; ky /= kl; kz /= kl;'
                ' double qx = rx*ce + (ky*rz - kz*ry)*se + kx*(kx*rx+ky*ry+kz*rz)*(1-ce), qy = ry*ce + (kz*rx - kx*rz)*se + ky*(kx*rx+ky*ry+kz*rz)*(1-ce), qz = rz*ce + (kx*ry - ky*rx)*se + kz*(kx*rx+ky*ry+kz*rz)*(1-ce);'
                ' double vx = ux*ce + (ky*uz - kz*uy)*se + kx*(kx*ux+ky*uy+kz*uz)*(1-ce), vy = uy*ce + (kz*ux - kx*uz)*se + ky*(kx*ux+ky*uy+kz*uz)*(1-ce), vz = uz*ce + (kx*uy - ky*ux)*se + kz*(kx*ux+ky*uy+kz*uz)*(1-ce);'
                ' (void)[f375Cam setPosition:(id)[(id)objc_getClass("Point3D") pointWithX:(float)((double)(float)[f375F x] + qx) y:(float)((double)(float)[f375F y] + qy) z:(float)((double)(float)[f375F z] + qz)]];'
                ' (void)[f375Cam setViewUp:(id)[(id)objc_getClass("Point3D") pointWithX:(float)vx y:(float)vy z:(float)vz]];'
                ' (void)[f375V setCamera:f375Cam]; }\n' % (args.rotate or 0.0, args.elevate or 0.0))
if args.drag:
    dx, dy = (float(v) for v in args.drag.split(','))
    actions += ('{ NSView *f375NV = (NSView *)f375V; NSRect f375R = [f375NV bounds]; NSPoint f375P0 = { (CGFloat)NSMidX(f375R), (CGFloat)NSMidY(f375R) };'
                ' NSPoint f375W0 = [f375NV convertPoint:f375P0 toView:nil]; NSPoint f375W1 = { (CGFloat)(f375W0.x + %g), (CGFloat)(f375W0.y + %g) };'
                ' NSWindow *f375Win = [f375NV window]; NSInteger f375N = [f375Win windowNumber]; NSTimeInterval f375T = [[NSProcessInfo processInfo] systemUptime];'
                ' NSEvent *f375D = [NSEvent mouseEventWithType:NSEventTypeLeftMouseDown location:f375W0 modifierFlags:0 timestamp:f375T windowNumber:f375N context:nil eventNumber:1 clickCount:1 pressure:1];'
                ' (void)[f375NV mouseDown:f375D];'
                ' for (int f375I = 1; f375I <= 8; ++f375I) { NSPoint f375Pi = { (CGFloat)(f375W0.x + (f375W1.x - f375W0.x) * f375I / 8.0), (CGFloat)(f375W0.y + (f375W1.y - f375W0.y) * f375I / 8.0) };'
                ' NSEvent *f375G = [NSEvent mouseEventWithType:NSEventTypeLeftMouseDragged location:f375Pi modifierFlags:0 timestamp:f375T + 0.01 * f375I windowNumber:f375N context:nil eventNumber:1 + f375I clickCount:1 pressure:1];'
                ' (void)[f375NV mouseDragged:f375G]; }'
                ' NSEvent *f375U = [NSEvent mouseEventWithType:NSEventTypeLeftMouseUp location:f375W1 modifierFlags:0 timestamp:f375T + 0.1 windowNumber:f375N context:nil eventNumber:10 clickCount:1 pressure:0];'
                ' (void)[f375NV mouseUp:f375U]; }\n' % (dx, dy))
if args.comparison:
    actions += '(void)[f375C openVolumeMetalComparison:nil];\n'

# Note: the expression is joined into one line, so it must not contain line comments.
expression = r'''
id f375C = nil;
for (NSWindow *f375W in (id)[(NSApplication*)NSApp windows]) {
  id wc = (id)[f375W windowController];
  if (wc && (BOOL)[wc isKindOfClass:(Class)objc_getClass("VRController")] && (BOOL)[f375W isVisible] && ![(NSString *)[wc style] isEqualToString:@"noNib"]) { f375C = wc; break; }
}
NSMutableDictionary *f375S = [NSMutableDictionary dictionary];
if (!f375C) { f375S[@"error"] = @"no visible VRController"; }
else {
id f375V = (id)[f375C view];
ACTIONS
(void)[f375V render];
NSDictionary *f375Snap = (NSDictionary *)[f375C horosVolumeSnapshot];
NSMutableDictionary *f375Public = [NSMutableDictionary dictionaryWithDictionary:f375Snap];
[f375Public removeObjectForKey:@"volume"]; [f375Public removeObjectForKey:@"clut"];
f375S[@"snapshot"] = f375Public;
f375S[@"clutHash"] = @((unsigned long)[(NSData *)[f375Snap objectForKey:@"clut"] hash]);
f375S[@"controller"] = [NSString stringWithFormat:@"%p", f375C];
f375S[@"style"] = (NSString *)[f375C style] ?: @"";
f375S[@"renderingMode"] = @((long)[f375V renderingMode]);
f375S[@"projectionMode"] = @((int)[f375V projectionMode]);
f375S[@"factor"] = @((float)[f375V factor]);
f375S[@"engine"] = @((int)[f375V engine]);
f375S[@"lod"] = @((float)[f375V lodDisplayed]);
NSRect f375B = [(NSView *)f375V bounds];
NSRect f375Backing = [(NSView *)f375V convertRectToBacking:f375B];
f375S[@"viewWidth"] = @((long)f375Backing.size.width); f375S[@"viewHeight"] = @((long)f375Backing.size.height);
float f375WL = 0, f375WW = 0; (void)[f375V getWLWW:&f375WL :&f375WW];
f375S[@"wl"] = @(f375WL); f375S[@"ww"] = @(f375WW);
f375S[@"shading"] = @((long)[f375V shading]);
f375S[@"clipRangeActivated"] = @((BOOL)[f375V clipRangeActivated]);
f375S[@"clippingRangeThicknessMm"] = @((double)[f375V getClippingRangeThicknessInMm]);
long f375RW = 0, f375RH = 0, f375SPP = 0, f375BPP = 0;
unsigned char *f375Raw = (unsigned char *)[f375V getRawPixels:&f375RW :&f375RH :&f375SPP :&f375BPP :(BOOL)0 :(BOOL)0];
f375S[@"vtkWidth"] = @(f375RW); f375S[@"vtkHeight"] = @(f375RH); f375S[@"vtkSamplesPerPixel"] = @(f375SPP); f375S[@"vtkBitsPerSample"] = @(f375BPP);
if (f375Raw) { (void)[[NSData dataWithBytesNoCopy:f375Raw length:(NSUInteger)(f375RW * f375RH * f375SPP * (f375BPP / 8)) freeWhenDone:NO] writeToFile:VTK atomically:YES]; free(f375Raw); }
long f375Width = f375RW > 0 ? f375RW : (long)f375Backing.size.width, f375Height = f375RH > 0 ? f375RH : (long)f375Backing.size.height;
f375S[@"renderWidth"] = @(f375Width); f375S[@"renderHeight"] = @(f375Height);
float f375O[3] = {0, 0, 0}, f375Cos[9] = {0, 0, 0, 0, 0, 0, 0, 0, 0};
(void)[f375V getOrigin:f375O windowCentered:(BOOL)0 sliceMiddle:(BOOL)1];
(void)[f375V getOrientation:f375Cos];
double f375Pitch = (double)[f375V getResolution] * (double)(float)[f375V imageSampleDistance];
double f375T = (BOOL)[f375V clipRangeActivated] ? (double)[f375V getClippingRangeThicknessInMm] : 0;
double f375Ext = 4.0 * (double)[f375V getResolution] * 1000.0;
/* getOrigin: hands back the upper-left corner of VTK's ray-cast image (it rounds the image origin to window pixels), so the centre of pixel (0,0) is half a pitch further along both axes: the alignment search converged on (+0.5, +0.5) in every capture. */
double f375Cx = f375O[0] + ((double)f375Width * 0.5) * f375Pitch * f375Cos[0] + ((double)f375Height * 0.5) * f375Pitch * f375Cos[3];
double f375Cy = f375O[1] + ((double)f375Width * 0.5) * f375Pitch * f375Cos[1] + ((double)f375Height * 0.5) * f375Pitch * f375Cos[4];
double f375Cz = f375O[2] + ((double)f375Width * 0.5) * f375Pitch * f375Cos[2] + ((double)f375Height * 0.5) * f375Pitch * f375Cos[5];
/* getOrientation: returns the view matrix rows: right, minus up, minus direction of projection; the eye sits behind the plane along that third row. */
double f375Back = f375T > 0 ? f375T * 0.5 : f375Ext;
NSArray *f375Cam = @[@(f375Cx + f375Cos[6] * f375Back), @(f375Cy + f375Cos[7] * f375Back), @(f375Cz + f375Cos[8] * f375Back),
                     @(f375Cx), @(f375Cy), @(f375Cz), @(-f375Cos[3]), @(-f375Cos[4]), @(-f375Cos[5]), @1, @((double)f375Height * f375Pitch * 0.5), @30];
f375S[@"derivedCamera"] = f375Cam; f375S[@"pitch"] = @(f375Pitch); f375S[@"imageOrigin"] = @[@(f375O[0]), @(f375O[1]), @(f375O[2])];
/* A projection samples from VTK's near plane (#659); the derived camera has its own eye, so the planes are re-expressed from it. */
double f375Near = 0.0, f375Far = f375T > 0 ? f375T : -1.0;
if ([(NSNumber *)[f375Snap objectForKey:@"anchoredProjection"] boolValue]) {
  NSArray *f375VC = (NSArray *)[f375Snap objectForKey:@"camera"];
  double f375Dx = [(NSNumber *)f375VC[3] doubleValue] - [(NSNumber *)f375VC[0] doubleValue], f375Dy = [(NSNumber *)f375VC[4] doubleValue] - [(NSNumber *)f375VC[1] doubleValue], f375Dz = [(NSNumber *)f375VC[5] doubleValue] - [(NSNumber *)f375VC[2] doubleValue];
  double f375Dl = sqrt(f375Dx * f375Dx + f375Dy * f375Dy + f375Dz * f375Dz); f375Dx /= f375Dl; f375Dy /= f375Dl; f375Dz /= f375Dl;
  double f375VN = [(NSNumber *)[f375Snap objectForKey:@"near"] doubleValue], f375VF = [(NSNumber *)[f375Snap objectForKey:@"far"] doubleValue];
  f375Near = ([(NSNumber *)f375VC[0] doubleValue] + f375Dx * f375VN - [(NSNumber *)f375Cam[0] doubleValue]) * f375Dx
           + ([(NSNumber *)f375VC[1] doubleValue] + f375Dy * f375VN - [(NSNumber *)f375Cam[1] doubleValue]) * f375Dy
           + ([(NSNumber *)f375VC[2] doubleValue] + f375Dz * f375VN - [(NSNumber *)f375Cam[2] doubleValue]) * f375Dz;
  f375Far = f375Near + (f375VF - f375VN);
}
f375S[@"derivedNear"] = @(f375Near); f375S[@"derivedFar"] = @(f375Far);
NSMutableData *f375Scalar = [NSMutableData data];
NSError *f375E = nil;
NSData *f375Metal = (NSData *)[f375C horosVolumeMetalRenderWithCamera:f375Cam near:f375Near far:f375Far width:(long)f375Width height:(long)f375Height scalarOut:f375Scalar error:&f375E];
f375S[@"metalBytes"] = @((long)[f375Metal length]);
f375S[@"metalMilliseconds"] = @((double)[f375C horosVolumeMetalLastMilliseconds]);
f375S[@"metalVolumeBytes"] = @((long)[f375C horosVolumeMetalBytes]);
f375S[@"metalFallback"] = (NSString *)[f375C horosVolumeMetalFallbackReason] ?: @"";
if (f375Metal) { (void)[f375Metal writeToFile:METAL atomically:YES]; }
if ([f375Scalar length] > 0) { (void)[f375Scalar writeToFile:METALSCALAR atomically:YES]; (void)[f375Scalar writeToFile:METALFULL atomically:YES];
  for (int f375Dy = -1; f375Dy <= 1; ++f375Dy) for (int f375Dx = -1; f375Dx <= 1; ++f375Dx) { if (f375Dx == 0 && f375Dy == 0) continue;
    double f375Sx = 0.5 * f375Dx * f375Pitch, f375Sy = 0.5 * f375Dy * f375Pitch;
    NSArray *f375ShiftCam = @[@([(NSNumber *)f375Cam[0] doubleValue] + f375Sx * f375Cos[0] + f375Sy * f375Cos[3]), @([(NSNumber *)f375Cam[1] doubleValue] + f375Sx * f375Cos[1] + f375Sy * f375Cos[4]), @([(NSNumber *)f375Cam[2] doubleValue] + f375Sx * f375Cos[2] + f375Sy * f375Cos[5]),
                              @([(NSNumber *)f375Cam[3] doubleValue] + f375Sx * f375Cos[0] + f375Sy * f375Cos[3]), @([(NSNumber *)f375Cam[4] doubleValue] + f375Sx * f375Cos[1] + f375Sy * f375Cos[4]), @([(NSNumber *)f375Cam[5] doubleValue] + f375Sx * f375Cos[2] + f375Sy * f375Cos[5]),
                              f375Cam[6], f375Cam[7], f375Cam[8], f375Cam[9], f375Cam[10], f375Cam[11]];
    NSMutableData *f375ShiftScalar = [NSMutableData data]; NSError *f375ShiftE = nil;
    NSData *f375ShiftMetal = (NSData *)[f375C horosVolumeMetalRenderWithCamera:f375ShiftCam near:f375Near far:f375Far width:(long)f375Width height:(long)f375Height scalarOut:f375ShiftScalar error:&f375ShiftE];
    if (f375ShiftMetal && [f375ShiftScalar length] > 0) { (void)[f375ShiftScalar writeToFile:[NSString stringWithFormat:@"%@.shift%d_%d.f32", METALBASE, f375Dx, f375Dy] atomically:YES]; }
  }
}
NSMutableData *f375ViewScalar = [NSMutableData data]; NSError *f375EV = nil;
NSData *f375MetalView = (NSData *)[f375C horosVolumeMetalRenderWithWidth:(long)f375Backing.size.width height:(long)f375Backing.size.height scalarOut:f375ViewScalar error:&f375EV];
f375S[@"metalViewMilliseconds"] = @((double)[f375C horosVolumeMetalLastMilliseconds]);
if (f375MetalView) { (void)[f375MetalView writeToFile:METALVIEW atomically:YES]; }
if ((long)[f375V renderingMode] != 0) {
  (void)[f375V prepareFullDepthCapture]; (void)[f375V render];
  long f375FW = 0, f375FH = 0; BOOL f375RGB = 0;
  float *f375Full = (float *)[f375V imageInFullDepthWidth:&f375FW height:&f375FH isRGB:&f375RGB];
  NSArray *f375Grid = (NSArray *)[f375V horosRayCastImageRegion];
  (void)[f375V restoreFullDepthCapture]; (void)[f375V render];
  /* The grid VTK just ray-cast, rendered in Metal as the hook renders it: the snapshot's own camera, planes and step (#659). */
  if (f375Grid.count == 6) {
    f375S[@"vtkGrid"] = f375Grid;
    NSMutableData *f375GridScalar = [NSMutableData data]; NSError *f375GridE = nil;
    NSData *f375GridMetal = (NSData *)[f375C horosVolumeMetalRenderWithCamera:(NSArray *)nil near:(double)0.0 far:(double)-1.0 width:(long)[(NSNumber *)f375Grid[4] longValue] height:(long)[(NSNumber *)f375Grid[5] longValue] imageRegion:(NSArray *)[f375Grid subarrayWithRange:NSMakeRange(0, 4)] scalarOut:f375GridScalar error:&f375GridE];
    if (f375GridMetal && [f375GridScalar length] > 0) { (void)[f375GridScalar writeToFile:METALGRID atomically:YES]; }
    f375S[@"gridFallback"] = (NSString *)[f375C horosVolumeMetalFallbackReason] ?: @"";
  }
  f375S[@"vtkFullWidth"] = @(f375FW); f375S[@"vtkFullHeight"] = @(f375FH); f375S[@"vtkFullRGB"] = @(f375RGB);
  if (f375Full && !f375RGB) { (void)[[NSData dataWithBytesNoCopy:f375Full length:(NSUInteger)(f375FW * f375FH * 4) freeWhenDone:NO] writeToFile:VTKSCALAR atomically:YES]; }
  if (f375Full) free(f375Full);
}
f375S[@"comparisonOpen"] = @((BOOL)[(id)objc_getClass("HorosVolumeComparison") isOpenForSource:f375C]);
struct task_vm_info f375Info; mach_msg_type_number_t f375Count = TASK_VM_INFO_COUNT;
(void)task_info(mach_task_self(), TASK_VM_INFO, (task_info_t)&f375Info, &f375Count);
f375S[@"footprintBytes"] = @((unsigned long long)f375Info.phys_footprint);
}
(void)[[NSJSONSerialization dataWithJSONObject:f375S options:3 error:nil] writeToFile:OUTPUT atomically:YES];
'''.replace('ACTIONS', actions).replace('OUTPUT', '@' + json.dumps(str(staged)))
for token, suffix in (('METALGRID', '.metal.grid.f32'), ('METALSCALAR', '.metal.f32'), ('METALFULL', '.metal.full.f32'), ('METALVIEW', '.metal.view.bgra'), ('METALBASE', '.metal'), ('VTKSCALAR', '.vtk.f32'), ('METAL', '.metal.bgra'), ('VTK', '.vtk.rgb')):
    expression = expression.replace(token, '@' + json.dumps(str(base) + suffix))
commands = args.output / (args.label + '.lldb')
commands.write_text('expression -l objc++ -- @import AppKit\n'
                    'expression -l objc++ -- @import Darwin\n'
                    'expression -l objc++ ' + ('-u false ' if args.debug_crash else '') + '-- { ' + ' '.join(expression.splitlines()) + ' }\n'
                    + ('bt 16\n' if args.debug_crash else '')
                    + 'process detach\n')
result = subprocess.run(['xcrun', 'lldb', '--batch', '-p', str(args.pid), '-s', str(commands)],
                        capture_output=True, text=True)
(args.output / (args.label + '.log')).write_text(result.stdout + result.stderr)
if result.returncode or not staged.exists():
    raise SystemExit('Capture failed; inspect the local LLDB log')
staged.replace(Path(str(base) + '.json'))
state = json.loads(Path(str(base) + '.json').read_text())
if 'error' in state:
    raise SystemExit(state['error'])
snap = state['snapshot']
print('%s: mode %s wl/ww %.0f/%.0f clip %s (%.2f mm) shading %s render %dx%d (view %dx%d) metal %.3f ms volume %d fallback=%r vtk spp %d'
      % (args.label, state['renderingMode'], state['wl'], state['ww'], state['clipRangeActivated'], state['clippingRangeThicknessMm'],
         state['shading'], state['renderWidth'], state['renderHeight'], state['viewWidth'], state['viewHeight'], state['metalMilliseconds'],
         state['metalVolumeBytes'], state['metalFallback'], state['vtkSamplesPerPixel']))
if 'error' not in snap:
    print('  camera %s parallel=%s scale %.3f angle %.1f near/far %s/%s' % (['%.2f' % v for v in snap['camera'][:9]], snap['camera'][9], snap['camera'][10], snap['camera'][11], snap['near'], snap['far']))
