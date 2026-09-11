#!/usr/bin/env python3
"""What the legacy viewer's print leaves behind, on the running build (#384 A).

Two steps, each one lldb attach, nothing modal:

- `spool` runs the real `preparePrintSpoolDirectory`, `writePrintPage:index:into:`
  and `discardPrintSpoolDirectory` of the viewer in front, with the frames the
  viewer actually draws: it reports where the pages went, who can read them,
  what they are called, whether the shared `/tmp/print` was touched, and
  whether anything survived the job;
- `annotations` captures the same frame with the annotations shown and hidden,
  writes both, and measures the top band where the patient's name is drawn, so
  a page printed with identifiers hidden can be shown not to carry them;
- `renderers` prepares one print page with the legacy OpenGL drawing and one
  with the optional Metal planar drawing of #373, separately, and reports which
  renderer actually drew and what the page came out as.

    python3 tools/exercise-native-viewer-print.py --pid N spool|annotations|renderers
"""
import argparse
import json
from pathlib import Path
import re
import subprocess
import uuid

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--pid', type=int, required=True)
parser.add_argument('step', choices=['spool', 'annotations', 'renderers'])
parser.add_argument('--pages', type=int, default=4)
parser.add_argument('--series', default=None, help='pick the viewer by series name instead of the front one')
parser.add_argument('--label', default=None)
parser.add_argument('--output', type=Path, default=Path('local-validation/issue-384-native'))
args = parser.parse_args()
args.label = args.label or ('print-' + args.step)
if args.pid <= 0 or not re.fullmatch('[a-z0-9-]+', args.label) or args.pages < 1:
    parser.error('positive PID, positive page count and a lowercase label')
args.output.mkdir(parents=True, exist_ok=True)
out_dir = args.output.resolve()
report = out_dir / (args.label + '.json')
staged = report.with_name(report.name + '.' + uuid.uuid4().hex + '.partial')

preamble = r'''
NSMutableDictionary *p384 = [NSMutableDictionary dictionary];
id v384 = nil;
NSString *wanted384 = SERIES;
if ([wanted384 length])
  for (id c384 in (NSArray*)[(Class)objc_getClass("ViewerController") get2DViewers])
    if ([(NSString*)[(NSObject*)[c384 currentSeries] valueForKey:@"name"] isEqualToString: wanted384]) { v384 = c384; break; }
if (!v384) v384 = (id)[(Class)objc_getClass("ViewerController") frontMostDisplayed2DViewer];
p384[@"viewer"] = @(v384 != nil);
p384[@"series"] = (NSString*)[(NSObject*)[v384 currentSeries] valueForKey:@"name"] ?: @"";
p384[@"fused"] = @((id)[v384 blendingController] != nil);
NSFileManager *fm384 = [NSFileManager defaultManager];
'''.replace('SERIES', json.dumps(args.series or ''))

steps = {
    'spool': r'''
p384[@"sharedPathBefore"] = @((BOOL)[fm384 fileExistsAtPath: @"/tmp/print"]);
if (v384) {
  p384[@"prepared"] = @((BOOL)[v384 preparePrintSpoolDirectory]);
  NSString *dir384 = (NSString*)[(NSObject*)v384 valueForKey: @"printSpoolDirectory"];
  p384[@"directory"] = dir384 ?: @"";
  p384[@"insideTemporary"] = @((BOOL)[dir384 hasPrefix: NSTemporaryDirectory()]);
  p384[@"ownedByPolicy"] = @((BOOL)[(Class)objc_getClass("HorosPrintSelection") isSpoolDirectory: dir384]);
  NSDictionary *attrs384 = (NSDictionary*)[fm384 attributesOfItemAtPath: dir384 error: nil];
  p384[@"permissions"] = [NSString stringWithFormat: @"%o", (unsigned)[(NSNumber*)attrs384[NSFilePosixPermissions] unsignedShortValue]];
  NSMutableArray *files384 = [NSMutableArray array];
  long written384 = 0;
  for (long i384 = 0; i384 < PAGES; i384++) {
    NSImage *cap384 = (NSImage*)[(id)[v384 imageView] nsimage: NO];
    if ((BOOL)[v384 writePrintPage: cap384 index: (int)i384 into: files384]) written384++;
  }
  p384[@"written"] = @(written384);
  NSMutableArray *names384 = [NSMutableArray array];
  NSMutableArray *sizes384 = [NSMutableArray array];
  for (NSString *path384 in files384) {
    (void)[names384 addObject: [path384 lastPathComponent]];
    (void)[sizes384 addObject: @((long)[(NSNumber*)[fm384 attributesOfItemAtPath: path384 error: nil][NSFileSize] longLongValue])];
  }
  p384[@"pageNames"] = names384;
  p384[@"pageSizes"] = sizes384;
  NSString *patient384 = (NSString*)[(NSObject*)v384 valueForKeyPath: @"currentStudy.name"] ?: @"";
  NSString *identifier384 = (NSString*)[(NSObject*)v384 valueForKeyPath: @"currentStudy.patientID"] ?: @"";
  p384[@"patient"] = @([patient384 length] > 0);
  BOOL leaks384 = NO;
  for (NSString *name384 in names384)
    if ((BOOL)[(Class)objc_getClass("HorosPrintSelection") temporaryNameLeaksIdentifiers: name384 patientName: patient384 patientID: identifier384]) leaks384 = YES;
  p384[@"namesLeakIdentifiers"] = @(leaks384);
  long present384 = 0;
  for (NSString *path384 in files384) if ([fm384 fileExistsAtPath: path384]) present384++;
  p384[@"pagesOnDiskDuringJob"] = @(present384);
  (void)[v384 discardPrintSpoolDirectory];
  long after384 = 0;
  for (NSString *path384 in files384) if ([fm384 fileExistsAtPath: path384]) after384++;
  p384[@"pagesOnDiskAfterJob"] = @(after384);
  p384[@"directoryAfterJob"] = @((BOOL)[fm384 fileExistsAtPath: dir384]);
  p384[@"remembersAfterJob"] = @((id)[(NSObject*)v384 valueForKey: @"printSpoolDirectory"] != nil);
}
p384[@"sharedPathAfter"] = @((BOOL)[fm384 fileExistsAtPath: @"/tmp/print"]);
''',
    'annotations': r'''
if (v384) {
  NSUserDefaults *d384 = [NSUserDefaults standardUserDefaults];
  long previous384 = (long)[d384 integerForKey: @"ANNOTATIONS"];
  p384[@"annotationsBefore"] = @(previous384);
  NSMutableArray *measures384 = [NSMutableArray array];
  long levels384[2] = {3, 0};
  for (long k384 = 0; k384 < 2; k384++) {
    (void)[d384 setInteger: levels384[k384] forKey: @"ANNOTATIONS"];
    (void)[(NSView*)[v384 imageView] setNeedsDisplay: YES];
    (void)[(NSView*)[v384 imageView] display];
    NSImage *cap384 = (NSImage*)[(id)[v384 imageView] nsimage: NO];
    CGImageRef cg384 = (CGImageRef)[(Class)objc_getClass("HorosRegisteredGIF") sRGBImageForImage: cap384];
    NSBitmapImageRep *rep384 = [[NSBitmapImageRep alloc] initWithCGImage: cg384];
    NSData *png384 = (NSData*)[rep384 representationUsingType: (NSBitmapImageFileType)4 properties: @{}];
    (void)[png384 writeToFile: (NSString*)[(NSString*)OUTDIR stringByAppendingPathComponent:
        [NSString stringWithFormat: @"annotations-%ld.png", levels384[k384]]] atomically: YES];
    long wide384 = (long)[rep384 pixelsWide], high384 = (long)[rep384 pixelsHigh];
    long band384 = high384 / 8; if (band384 < 8) band384 = high384;
    double sum384 = 0, sumsq384 = 0; long n384 = 0, bright384 = 0;
    for (long y384 = 0; y384 < band384; y384++)
      for (long x384 = 0; x384 < wide384; x384++) {
        NSUInteger px384[4] = {0,0,0,0};
        (void)[rep384 getPixel: px384 atX: x384 y: y384];
        double value384 = (double)px384[0];
        sum384 += value384; sumsq384 += value384 * value384; n384++;
        if (value384 > 40) bright384++;
      }
    double mean384 = n384 ? sum384 / (double)n384 : 0;
    double variance384 = n384 ? (sumsq384 / (double)n384) - mean384 * mean384 : 0;
    (void)[measures384 addObject: @{@"level": @(levels384[k384]), @"size": @[@(wide384), @(high384)],
                                    @"bandRows": @(band384), @"mean": @(mean384),
                                    @"stddev": @(variance384 > 0 ? sqrt(variance384) : 0),
                                    @"litPixels": @(bright384), @"bandPixels": @(n384)}];
  }
  p384[@"bands"] = measures384;
  (void)[d384 setInteger: previous384 forKey: @"ANNOTATIONS"];
  (void)[(NSView*)[v384 imageView] setNeedsDisplay: YES];
  (void)[(NSView*)[v384 imageView] display];
  p384[@"annotationsRestored"] = @((long)[d384 integerForKey: @"ANNOTATIONS"] == previous384);
}
''',
    'renderers': r'''
if (v384) {
  BOOL wasMetal384 = (BOOL)[v384 horosPlanarMetalEnabled];
  p384[@"metalBefore"] = @(wasMetal384);
  NSMutableArray *rows384 = [NSMutableArray array];
  for (long k384 = 0; k384 < 2; k384++) {
    BOOL want384 = (k384 == 1);
    if ((BOOL)[v384 horosPlanarMetalEnabled] != want384) (void)[v384 togglePlanarMetal: nil];
    (void)[(NSView*)[v384 imageView] setNeedsDisplay: YES];
    (void)[(NSView*)[v384 imageView] display];
    (void)[v384 preparePrintSpoolDirectory];
    NSMutableArray *files384 = [NSMutableArray array];
    NSImage *cap384 = (NSImage*)[(id)[v384 imageView] nsimage: NO];
    BOOL wrote384 = (BOOL)[v384 writePrintPage: cap384 index: 0 into: files384];
    CGImageRef cg384 = (CGImageRef)[(Class)objc_getClass("HorosRegisteredGIF") sRGBImageForImage: cap384];
    NSBitmapImageRep *rep384 = [[NSBitmapImageRep alloc] initWithCGImage: cg384];
    NSData *png384 = (NSData*)[rep384 representationUsingType: (NSBitmapImageFileType)4 properties: @{}];
    (void)[png384 writeToFile: (NSString*)[(NSString*)OUTDIR stringByAppendingPathComponent:
        [NSString stringWithFormat: @"renderer-%@.png", want384 ? @"metal" : @"opengl"]] atomically: YES];
    double sum384 = 0; long n384 = 0, lit384 = 0;
    for (long y384 = 0; y384 < (long)[rep384 pixelsHigh]; y384 += 2)
      for (long x384 = 0; x384 < (long)[rep384 pixelsWide]; x384 += 2) {
        NSUInteger px384[4] = {0,0,0,0};
        (void)[rep384 getPixel: px384 atX: x384 y: y384];
        sum384 += (double)px384[0]; n384++; if (px384[0] > 8) lit384++;
      }
    (void)[rows384 addObject: @{@"metal": @(want384),
        @"drewWithMetal": @((double)[(id)[v384 imageView] horosPlanarLastCommandMilliseconds] >= 0),
        @"fallbackReason": (NSString*)[(id)[v384 imageView] horosPlanarFallbackReason] ?: @"",
        @"pageWritten": @(wrote384),
        @"pageBytes": @([files384 count] ? (long)[(NSNumber*)[fm384 attributesOfItemAtPath: [files384 lastObject] error: nil][NSFileSize] longLongValue] : 0),
        @"size": @[@((long)[rep384 pixelsWide]), @((long)[rep384 pixelsHigh])],
        @"mean": @(n384 ? sum384 / (double)n384 : -1),
        @"litFraction": @(n384 ? (double)lit384 / (double)n384 : -1)}];
    (void)[v384 discardPrintSpoolDirectory];
  }
  p384[@"renderers"] = rows384;
  if ((BOOL)[v384 horosPlanarMetalEnabled] != wasMetal384) (void)[v384 togglePlanarMetal: nil];
  p384[@"metalRestored"] = @((BOOL)[v384 horosPlanarMetalEnabled] == wasMetal384);
  (void)[(NSView*)[v384 imageView] display];
}
''',
}

expression = preamble + steps[args.step].replace('OUTDIR', json.dumps(str(out_dir))).replace('PAGES', str(args.pages))
expression += '(void)[[NSJSONSerialization dataWithJSONObject:p384 options:3 error:nil] writeToFile:@' + json.dumps(str(staged)) + ' atomically:YES];\n'
commands = out_dir / (args.label + '.lldb')
commands.write_text('expression -l objc++ -- @import AppKit\n'
                    'expression -l objc++ -- { ' + ' '.join(expression.splitlines()) + ' }\nprocess detach\n')
result = subprocess.run(['xcrun', 'lldb', '--batch', '-p', str(args.pid), '-s', str(commands)], capture_output=True, text=True)
(out_dir / (args.label + '.log')).write_text(result.stdout + result.stderr)
if result.returncode or not staged.exists():
    raise SystemExit('lldb step failed; inspect ' + str(out_dir / (args.label + '.log')))
staged.replace(report)
print(json.dumps(json.loads(report.read_text()), indent=1)[:2200])
