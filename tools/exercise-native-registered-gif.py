#!/usr/bin/env python3
"""Capture the registered comparison from the running build (#384 B).

Three steps, each one lldb attach to the development build, nothing modal:

- `static` moves the host's fusion blend to each stop, captures what the viewer
  draws, normalises it to sRGB and writes one PNG per stop;
- `gif` calls the viewer's own panel-free capture, writes the animation, and
  writes each decoded frame as a PNG beside the static ones, with the frame
  durations, the loop count and the size the animation declares;
- `clipboard` copies the animation to the general pasteboard and reads it back,
  reporting whether the bytes survived and how many frames came back.

`tools/compare-native-registered-gif.py` then compares the two sets of PNGs.

    python3 tools/exercise-native-registered-gif.py --pid N static|gif|clipboard
"""
import argparse
import json
from pathlib import Path
import re
import subprocess
import uuid

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--pid', type=int, required=True)
parser.add_argument('step', choices=['static', 'gif', 'clipboard'])
parser.add_argument('--stops', default='0,1', help='blend stops, 0 (base) to 1 (companion)')
parser.add_argument('--delay', type=float, default=0.5)
parser.add_argument('--label', default=None)
parser.add_argument('--output', type=Path, default=Path('local-validation/issue-384-native'))
args = parser.parse_args()
args.label = args.label or ('gif-' + args.step)
if args.pid <= 0 or not re.fullmatch('[a-z0-9-]+', args.label):
    parser.error('positive PID and a lowercase label')
stops = [float(value) for value in args.stops.split(',')]
if not stops or not all(0 <= value <= 1 for value in stops):
    parser.error('blend stops are fractions between 0 and 1')
args.output.mkdir(parents=True, exist_ok=True)
out_dir = args.output.resolve()
report = out_dir / (args.label + '.json')
staged = report.with_name(report.name + '.' + uuid.uuid4().hex + '.partial')
stop_literal = ', '.join('@%r' % value for value in stops)

preamble = r'''
NSMutableDictionary *g384 = [NSMutableDictionary dictionary];
id v384 = nil;
for (id c384 in (NSArray*)[(Class)objc_getClass("ViewerController") get2DViewers])
  if ((id)[c384 blendingController] != nil) { v384 = c384; break; }
if (!v384) v384 = (id)[(Class)objc_getClass("ViewerController") frontMostDisplayed2DViewer];
g384[@"viewer"] = @(v384 != nil);
g384[@"series"] = (NSString*)[(NSObject*)[v384 currentSeries] valueForKey:@"name"] ?: @"";
g384[@"companionSeries"] = (NSString*)[(NSObject*)[(id)[v384 blendingController] currentSeries] valueForKey:@"name"] ?: @"";
NSArray *stops384 = @[STOPS];
'''.replace('STOPS', stop_literal)

steps = {
    'static': r'''
if (v384) {
  id session384 = (id)[v384 horosRegistrationSession];
  g384[@"sessionKey"] = (NSString*)[(Class)objc_getClass("HorosRegisteredGIF") sessionKeyForSession:session384];
  g384[@"companions"] = @((long)[(NSArray*)[session384 companions] count]);
  id fused384 = (id)[v384 blendingController];
  g384[@"fused"] = @(fused384 != nil);
  NSSlider *s384 = (NSSlider*)[v384 blendingSlider];
  double prev384 = (double)[s384 doubleValue], lo384 = (double)[s384 minValue], hi384 = (double)[s384 maxValue];
  g384[@"sliderRange"] = @[@(lo384), @(hi384)];
  NSMutableArray *means384 = [NSMutableArray array];
  for (NSNumber *stop384 in stops384) {
    (void)[s384 setDoubleValue: lo384 + [stop384 doubleValue] * (hi384 - lo384)];
    (void)[v384 blendingSlider: s384];
    (void)[(NSView*)[v384 imageView] display];
    NSImage *cap384 = (NSImage*)[(id)[v384 imageView] nsimage: NO];
    CGImageRef cg384 = (CGImageRef)[(Class)objc_getClass("HorosRegisteredGIF") sRGBImageForImage: cap384];
    NSBitmapImageRep *rep384 = [[NSBitmapImageRep alloc] initWithCGImage: cg384];
    NSData *png384 = (NSData*)[rep384 representationUsingType: (NSBitmapImageFileType)4 properties: @{}];
    (void)[png384 writeToFile: (NSString*)[(NSString*)OUTDIR stringByAppendingPathComponent:
        [NSString stringWithFormat: @"static-%02ld.png", (long)[stops384 indexOfObject: stop384]]] atomically: YES];
    double sum384 = 0; long n384 = 0;
    for (long y384 = 0; y384 < (long)[rep384 pixelsHigh]; y384 += 4)
      for (long x384 = 0; x384 < (long)[rep384 pixelsWide]; x384 += 4) {
        NSUInteger px384[4] = {0,0,0,0};
        (void)[rep384 getPixel: px384 atX: x384 y: y384];
        sum384 += (double)px384[0]; n384++;
      }
    (void)[means384 addObject: @(n384 ? sum384 / (double)n384 : -1)];
    if ([stop384 isEqualToNumber: [stops384 objectAtIndex: 0]]) g384[@"size"] = @[@((long)[rep384 pixelsWide]), @((long)[rep384 pixelsHigh])];
  }
  g384[@"staticMeans"] = means384;
  (void)[s384 setDoubleValue: prev384];
  (void)[v384 blendingSlider: s384];
  (void)[(NSView*)[v384 imageView] display];
  g384[@"blendRestored"] = @((double)[s384 doubleValue] == prev384);
}
''',
    'gif': r'''
if (v384) {
  NSString *refusal384 = nil;
  id result384 = (id)[v384 horosRegisteredComparisonGIFWithBlendStops: stops384 delaySeconds: DELAY refusal: &refusal384];
  g384[@"refusal"] = refusal384 ?: @"";
  g384[@"usable"] = @((BOOL)[result384 isUsable]);
  NSData *data384 = (NSData*)[result384 data];
  g384[@"bytes"] = @((long)[data384 length]);
  if (data384) {
    (void)[data384 writeToFile: (NSString*)[(NSString*)OUTDIR stringByAppendingPathComponent: @"comparison.gif"] atomically: YES];
    g384[@"frameCount"] = @((long)[(Class)objc_getClass("HorosRegisteredGIF") frameCountInData: data384]);
    g384[@"delays"] = (NSArray*)[(Class)objc_getClass("HorosRegisteredGIF") frameDelaysInData: data384];
    g384[@"loopCount"] = @((long)[(Class)objc_getClass("HorosRegisteredGIF") loopCountInData: data384]);
    g384[@"size"] = @[@((long)[result384 width]), @((long)[result384 height])];
    NSMutableArray *means384 = [NSMutableArray array];
    for (long i384 = 0; i384 < (long)[(Class)objc_getClass("HorosRegisteredGIF") frameCountInData: data384]; i384++) {
      NSBitmapImageRep *rep384 = (NSBitmapImageRep*)[(Class)objc_getClass("HorosRegisteredGIF") frameBitmapInData: data384 atIndex: i384];
      NSData *png384 = (NSData*)[rep384 representationUsingType: (NSBitmapImageFileType)4 properties: @{}];
      (void)[png384 writeToFile: (NSString*)[(NSString*)OUTDIR stringByAppendingPathComponent:
          [NSString stringWithFormat: @"frame-%02ld.png", i384]] atomically: YES];
      double sum384 = 0; long n384 = 0;
      for (long y384 = 0; y384 < (long)[rep384 pixelsHigh]; y384 += 4)
        for (long x384 = 0; x384 < (long)[rep384 pixelsWide]; x384 += 4) {
          NSUInteger px384[4] = {0,0,0,0};
          (void)[rep384 getPixel: px384 atX: x384 y: y384];
          sum384 += (double)px384[0]; n384++;
        }
      (void)[means384 addObject: @(n384 ? sum384 / (double)n384 : -1)];
    }
    g384[@"frameMeans"] = means384;
  }
  NSSlider *s384 = (NSSlider*)[v384 blendingSlider];
  g384[@"blendAfter"] = @((double)[s384 doubleValue]);
}
''',
    'clipboard': r'''
if (v384) {
  NSString *refusal384 = nil;
  id result384 = (id)[v384 horosRegisteredComparisonGIFWithBlendStops: stops384 delaySeconds: DELAY refusal: &refusal384];
  NSData *data384 = (NSData*)[result384 data];
  g384[@"usable"] = @((BOOL)[result384 isUsable]);
  NSPasteboard *pb384 = [NSPasteboard generalPasteboard];
  g384[@"copied"] = @((BOOL)[(Class)objc_getClass("HorosRegisteredGIF") copyData: data384 toPasteboard: pb384]);
  NSData *back384 = (NSData*)[(Class)objc_getClass("HorosRegisteredGIF") dataOnPasteboard: pb384];
  g384[@"clipboardBytes"] = @((long)[back384 length]);
  g384[@"identical"] = @((BOOL)[back384 isEqualToData: data384]);
  g384[@"clipboardFrames"] = @((long)[(Class)objc_getClass("HorosRegisteredGIF") frameCountInData: back384]);
  g384[@"types"] = (NSArray*)[pb384 types];
  NSString *tmp384 = NSTemporaryDirectory();
  NSArray *entries384 = (NSArray*)[[NSFileManager defaultManager] contentsOfDirectoryAtPath: tmp384 error: nil];
  NSMutableArray *left384 = [NSMutableArray array];
  for (NSString *name384 in entries384)
    if ([name384 hasPrefix: @"horos-print-"] || [name384 hasPrefix: @"horos-gif"]) (void)[left384 addObject: name384];
  g384[@"temporariesLeft"] = left384;
}
''',
}

expression = preamble + steps[args.step].replace('OUTDIR', json.dumps(str(out_dir))).replace('DELAY', repr(args.delay))
expression += '(void)[[NSJSONSerialization dataWithJSONObject:g384 options:3 error:nil] writeToFile:@' + json.dumps(str(staged)) + ' atomically:YES];\n'
commands = out_dir / (args.label + '.lldb')
commands.write_text('expression -l objc++ -- @import AppKit\n'
                    'expression -l objc++ -- { ' + ' '.join(expression.splitlines()) + ' }\nprocess detach\n')
result = subprocess.run(['xcrun', 'lldb', '--batch', '-p', str(args.pid), '-s', str(commands)], capture_output=True, text=True)
(out_dir / (args.label + '.log')).write_text(result.stdout + result.stderr)
if result.returncode or not staged.exists():
    raise SystemExit('lldb step failed; inspect ' + str(out_dir / (args.label + '.log')))
staged.replace(report)
print(json.dumps(json.loads(report.read_text()), indent=1)[:2000])
