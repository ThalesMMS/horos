#!/usr/bin/env python3
"""Read A295 geometry from the isolated synthetic cross-reference study.

This attaches LLDB only to read model/presentation state; all interaction is
performed through the native UI. Captures and debugger logs must remain local.
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
parser.add_argument('--pixels', action='store_true', help='Read GL front buffers for drawn-marker verification')
parser.add_argument('--output', type=Path, default=Path('local-validation/patient-crosshair'))
args = parser.parse_args()
if args.pid <= 0 or not re.fullmatch('[a-z0-9-]+', args.label):
    parser.error('Use a positive PID and a lowercase snapshot label')
args.output.mkdir(parents=True, exist_ok=True)
output = (args.output / (args.label + '.json')).resolve()
staged = output.with_name(output.name + '.' + uuid.uuid4().hex + '.partial')
expression = r'''
NSArray *a295Viewers=(id)[(id)objc_getClass("ViewerController") get2DViewers];
BOOL a295Synthetic=a295Viewers.count > 0;
for (id a295Vc in a295Viewers) {
 if (!(BOOL)[(id)[(NSObject *)a295Vc valueForKeyPath:@"currentStudy.patientID"] isEqualToString:@"LOCAL-CROSS-REFERENCE"]) a295Synthetic=NO;
}
if (a295Synthetic) {
NSMutableDictionary *a295State=[NSMutableDictionary dictionary];
id a295Crosshair=(id)[(id)objc_getClass("HorosPatientCrosshairController") shared];
id a295Point=(id)[a295Crosshair currentPoint];
a295State[@"point"] = a295Point ? (id)[a295Point coordinates] : (id)[NSNull null];
a295State[@"pointIdentity"]=a295Point ? @{@"study":[(NSObject *)a295Point valueForKeyPath:@"identity.studyInstanceUID"],@"series":[(NSObject *)a295Point valueForKeyPath:@"identity.seriesInstanceUID"],@"frame":[(NSObject *)a295Point valueForKeyPath:@"identity.frameOfReferenceUID"],@"generation":[(NSObject *)a295Point valueForKeyPath:@"identity.generation"]} : (id)[NSNull null];
a295State[@"sourceOwner"]=[NSString stringWithFormat:@"%p",(id)[a295Crosshair sourceOwner]];
a295State[@"visible"]=@((BOOL)[a295Crosshair isVisible]);
a295State[@"frameCheck"]=@([[NSUserDefaults standardUserDefaults] boolForKey:@"UseFrameofReferenceUID"]);
a295State[@"applicationActive"]=@([(NSApplication*)NSApp isActive]);
a295State[@"keyWindow"]=[(NSApplication*)NSApp keyWindow].title ?: @"";
NSMutableArray *a295ViewerStates=[NSMutableArray array];
for (id a295Vc in a295Viewers) {
 id a295View=(id)[a295Vc imageView]; id a295Pix=(id)[a295View curDCM]; NSWindow *a295Window=(id)[a295Vc window];
 float a295Coords[3]={0,0,0}; BOOL drawn=(BOOL)[a295View getPatientCrosshairSliceCoordinates:a295Coords];
 float a295Projection[3]={0,0,0};
 if (a295Point) {
  NSArray *a295PatientValues=(id)[a295Point coordinates];
  float a295PatientPoint[3]={(float)[a295PatientValues[0] floatValue],(float)[a295PatientValues[1] floatValue],(float)[a295PatientValues[2] floatValue]};
  (void)[a295Pix convertDICOMCoords:a295PatientPoint toSliceCoords:a295Projection pixelCenter:YES];
 }
 double a295Origin[3]={ (double)[[(NSObject *)a295Pix valueForKey:@"originX"] doubleValue], (double)[[(NSObject *)a295Pix valueForKey:@"originY"] doubleValue], (double)[[(NSObject *)a295Pix valueForKey:@"originZ"] doubleValue] };
 float a295Orientation[9]; (void)[a295Pix orientation:a295Orientation];
 NSMutableArray *a295Basis=[NSMutableArray array]; for(int i=0;i<9;i++) [a295Basis addObject:@(a295Orientation[i])];
 NSRect a295Frame=a295Window.frame;
 NSMutableDictionary *a295V=[NSMutableDictionary dictionaryWithDictionary:@{
  @"title":a295Window.title, @"controller":[NSString stringWithFormat:@"%p",a295Vc],
  @"pixList":[NSString stringWithFormat:@"%p",(id)[a295Vc pixList]],
  @"roiList":[NSString stringWithFormat:@"%p",(id)[a295Vc roiList]],
  @"index":[(NSObject *)a295View valueForKey:@"curImage"], @"count":@([(NSArray *)(id)[a295Vc pixList] count]),
  @"key":@(a295Window.isKeyWindow), @"visible":@(a295Window.isVisible),
  @"frame":@[@(a295Frame.origin.x),@(a295Frame.origin.y),@(a295Frame.size.width),@(a295Frame.size.height)],
  @"series":[(NSObject *)a295Vc valueForKeyPath:@"currentSeries.seriesInstanceUID"],
  @"frameUID":(id)[a295Pix frameofReferenceUID] ?: @"", @"origin":@[@(a295Origin[0]),@(a295Origin[1]),@(a295Origin[2])],
  @"orientation":a295Basis, @"spacing":@[[(NSObject *)a295Pix valueForKey:@"pixelSpacingX"],[(NSObject *)a295Pix valueForKey:@"pixelSpacingY"]],
  @"dimensions":@[[(NSObject *)a295Pix valueForKey:@"pwidth"],[(NSObject *)a295Pix valueForKey:@"pheight"]],
  @"sliceInterval":[(NSObject *)a295Pix valueForKey:@"sliceInterval"], @"sliceThickness":[(NSObject *)a295Pix valueForKey:@"sliceThickness"],
  @"projectedSliceMM":@[@(a295Projection[0]),@(a295Projection[1]),@(a295Projection[2])],
  @"markerVisible":@(drawn), @"markerSliceMM":@[@(a295Coords[0]),@(a295Coords[1]),@(a295Coords[2])],
  @"scale":[(NSObject *)a295View valueForKey:@"scaleValue"], @"rotation":[(NSObject *)a295View valueForKey:@"rotation"],
  @"xFlipped":[(NSObject *)a295View valueForKey:@"xFlipped"], @"yFlipped":[(NSObject *)a295View valueForKey:@"yFlipped"], @"flippedData":[(NSObject *)a295View valueForKey:@"flippedData"],
  @"tool":[(NSObject *)a295View valueForKey:@"currentTool"], @"metal":@((BOOL)[a295Vc horosPlanarMetalEnabled]),
  @"fallback":(id)[a295View horosPlanarFallbackReason] ?: @"",
  @"mousePixel":@[[(NSObject *)a295View valueForKey:@"mouseXPos"],[(NSObject *)a295View valueForKey:@"mouseYPos"]]
 }];
 NSMutableArray *a295Rois=[NSMutableArray array];
 for (NSArray *a295Slice in (id)[a295Vc roiList]) for(id a295Roi in a295Slice) {
  NSMutableArray *a295RoiPoints=[NSMutableArray array];
  for (NSObject *a295RoiPoint in (NSArray *)(id)[a295Roi points])
   [a295RoiPoints addObject:@[[a295RoiPoint valueForKey:@"x"],[a295RoiPoint valueForKey:@"y"]]];
  [a295Rois addObject:@{@"type":@((long)[a295Roi type]),@"name":(id)[a295Roi name] ?: @"",@"mode":@((long)[a295Roi ROImode]),@"points":a295RoiPoints}];
 }
 a295V[@"rois"]=a295Rois;
 NSPoint a295Pixel={0,0}, a295Screen={0,0}; a295Pixel.x=a295Point ? a295Projection[0]/(double)[[(NSObject *)a295Pix valueForKey:@"pixelSpacingX"] doubleValue] : 16; a295Pixel.y=a295Point ? a295Projection[1]/(double)[[(NSObject *)a295Pix valueForKey:@"pixelSpacingY"] doubleValue] : 16;
 SEL a295Sel=NSSelectorFromString(@"ConvertFromGL2Screen:");
 NSInvocation *a295Inv=[NSInvocation invocationWithMethodSignature:(NSMethodSignature *)[a295View methodSignatureForSelector:a295Sel]];
 [a295Inv setTarget:a295View]; [a295Inv setSelector:a295Sel]; [a295Inv setArgument:&a295Pixel atIndex:2]; [a295Inv invoke]; [a295Inv getReturnValue:&a295Screen];
 a295V[@"markerOrCenterScreen"]=@[@(a295Screen.x),@(a295Screen.y)];
 PIXEL_CAPTURE
 [a295ViewerStates addObject:a295V];
}
a295State[@"viewers"]=a295ViewerStates;
NSMutableArray *a295Mprs=[NSMutableArray array];
for (NSWindow *a295Window in [(NSApplication*)NSApp windows]) {
 id a295Owner=a295Window.windowController;
 if ((BOOL)[a295Owner isKindOfClass:(Class)objc_getClass("OrthogonalMPRViewer")] && a295Window.isVisible &&
 (BOOL)[(id)[(NSObject *)a295Owner valueForKeyPath:@"currentStudy.patientID"] isEqualToString:@"LOCAL-CROSS-REFERENCE"]) {
  id a295Controller=(id)[a295Owner controller]; float a295Patient[3];
  (void)[(id)[a295Controller xReslicedView] getCrossPositionDICOMCoords:a295Patient];
  [a295Mprs addObject:@{@"title":a295Window.title,@"owner":[NSString stringWithFormat:@"%p",a295Owner],@"key":@(a295Window.isKeyWindow),
    @"patient":@[@(a295Patient[0]),@(a295Patient[1]),@(a295Patient[2])],@"tool":@((int)[a295Controller currentTool])}];
 }
}
a295State[@"mpr"]=a295Mprs;
[[NSJSONSerialization dataWithJSONObject:a295State options:3 error:nil]writeToFile:OUTPUT atomically:YES];
}
'''.replace('OUTPUT', '@' + json.dumps(str(staged)))

pixel_capture = r"""
NSRect a295Bounds=[(NSView*)a295View convertRectToBacking:[(NSView*)a295View bounds]];
NSPoint a295WindowPoint=[a295Window convertPointFromScreen:a295Screen];
NSPoint a295ViewPoint=[(NSView*)a295View convertPoint:a295WindowPoint fromView:nil];
NSPoint a295Backing=[(NSView*)a295View convertPointToBacking:a295ViewPoint];
a295V[@"markerBacking"]=@[@(a295Backing.x),@(a295Backing.y)];
a295V[@"bufferSize"]=@[@(a295Bounds.size.width),@(a295Bounds.size.height)];
NSOpenGLContext *a295Previous=[NSOpenGLContext currentContext];
NSOpenGLContext *a295Context=(id)[a295View openGLContext]; [a295Context makeCurrentContext];
int a295ReadBuffer=0;
glPushClientAttrib(GL_CLIENT_PIXEL_STORE_BIT); glGetIntegerv(GL_READ_BUFFER,&a295ReadBuffer);
glReadBuffer(GL_FRONT); glPixelStorei(GL_PACK_ALIGNMENT,1); glPixelStorei(GL_PACK_ROW_LENGTH,0);
glPixelStorei(GL_PACK_SKIP_PIXELS,0); glPixelStorei(GL_PACK_SKIP_ROWS,0);
NSMutableData *a295Pixels=[NSMutableData dataWithLength:(NSUInteger)a295Bounds.size.width*(NSUInteger)a295Bounds.size.height*4];
glReadPixels(0,0,(int)a295Bounds.size.width,(int)a295Bounds.size.height,GL_BGRA,GL_UNSIGNED_BYTE,[a295Pixels mutableBytes]);
a295V[@"glError"]=@(glGetError()); glReadBuffer(a295ReadBuffer); glPopClientAttrib();
if(a295Previous) [a295Previous makeCurrentContext]; else [NSOpenGLContext clearCurrentContext];
NSString *a295PixelFile=[NSString stringWithFormat:@"%@-view-%lu.bgra",PIXEL_PREFIX,(unsigned long)a295ViewerStates.count];
[a295Pixels writeToFile:a295PixelFile atomically:YES]; a295V[@"bufferFile"]=a295PixelFile.lastPathComponent;
""".replace('PIXEL_PREFIX', '@' + json.dumps(str(output.with_suffix(''))))
expression = expression.replace('PIXEL_CAPTURE', pixel_capture if args.pixels else '')

commands = args.output / (args.label + '.lldb')
commands.write_text('expression -l objc++ -- @import AppKit\nexpression -l objc++ -- @import OpenGL.GL\n'
                    'expression -l objc++ -- { ' + ' '.join(expression.splitlines()) + ' }\n'
                    'process detach\n')
result = subprocess.run(['xcrun', 'lldb', '--batch', '-p', str(args.pid), '-s', str(commands)],
                        capture_output=True, text=True)
(args.output / (args.label + '.log')).write_text(result.stdout + result.stderr)
if result.returncode or not staged.exists():
    raise SystemExit('Capture failed or viewers were not the synthetic study; inspect the local LLDB log')
state = json.loads(staged.read_text())
staged.replace(output)
print(args.label + ': ' + json.dumps({k:state[k] for k in ('point','visible','frameCheck','mpr')}))
for v in state['viewers']:
    print(v['title'].strip(), 'index',v['index'],'marker',v['markerVisible'],v['markerSliceMM'],'screen',v['markerOrCenterScreen'])
