#!/usr/bin/env python3
"""What the viewer hands the printer, on each planar backend (#610).

The upstream fix for blank Planar print output was a responder-chain
correction: a focused view that inherited `NSView.print:` let AppKit try to
print a Metal layer as an ordinary view. This checks the same question here -
which implementation of `print:` the image view actually has - and then
captures the image the print path builds, so the page content can be compared
against the frame on screen instead of merely being non-empty.

    python3 tools/exercise-native-planar-print.py responder --pid P
    python3 tools/exercise-native-planar-print.py capture   --pid P --index 12 --label metal3-12

`capture` moves the viewer to one slice, draws it, asks the view for the image
the print path uses and writes it as PNG under local-validation. Nothing leaves
the machine; the phantom is synthetic.
"""
import argparse
import json
from pathlib import Path
import re
import subprocess
import uuid

parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument('step', choices=['responder', 'capture'])
parser.add_argument('--pid', type=int, required=True)
parser.add_argument('--index', type=int, default=0)
parser.add_argument('--label', default=None)
parser.add_argument('--output', type=Path, default=Path('local-validation/issue-610-native'))
arguments = parser.parse_args()

label = arguments.label or arguments.step
if not re.fullmatch('[a-z0-9-]+', label):
    parser.error('Use a lowercase label')
arguments.output.mkdir(parents=True, exist_ok=True)
output = (arguments.output / ('print-' + label + '.json')).resolve()
image = (arguments.output / ('print-' + label + '.png')).resolve()
staged = output.with_name(output.name + '.' + uuid.uuid4().hex + '.partial')

COMMON = r'''
NSMutableDictionary *m610 = [NSMutableDictionary dictionary];
id vc610 = (id)[(NSArray*)[(Class)objc_getClass("ViewerController") get2DViewers] firstObject];
id view610 = vc610 ? (id)[(id)vc610 imageView] : nil;
m610[@"hasViewer"] = @(vc610 != nil);
'''

if arguments.step == 'responder':
    body = COMMON + r'''
Class dcm610 = (Class)objc_getClass("DCMView");
Class ns610 = (Class)objc_getClass("NSView");
IMP own610 = (IMP)class_getMethodImplementation(dcm610, @selector(print:));
IMP inherited610 = (IMP)class_getMethodImplementation(ns610, @selector(print:));
m610[@"respondsToPrint"] = @((BOOL)[dcm610 instancesRespondToSelector: @selector(print:)]);
m610[@"overridesPrint"] = @(own610 != inherited610);
m610[@"printImplementation"] = [NSString stringWithFormat: @"%p", own610];
m610[@"nsviewPrintImplementation"] = [NSString stringWithFormat: @"%p", inherited610];
Method method610 = (Method)class_getInstanceMethod(dcm610, @selector(print:));
m610[@"printDeclaredOn"] = method610 ? @"DCMView" : @"none";
Class owner610 = dcm610;
while (owner610 && (IMP)class_getMethodImplementation((Class)class_getSuperclass(owner610), @selector(print:)) == own610)
  owner610 = (Class)class_getSuperclass(owner610);
m610[@"printOwner"] = owner610 ? [NSString stringWithUTF8String: class_getName(owner610)] : @"";
if (view610) {
  m610[@"viewClass"] = [NSString stringWithUTF8String: object_getClassName(view610)];
  m610[@"viewOverridesPrint"] = @((IMP)class_getMethodImplementation((Class)object_getClass(view610), @selector(print:)) != inherited610);
  m610[@"backend"] = (NSString*)[(id)view610 horosPlanarBackendName] ?: @"";
}
'''

elif arguments.step == 'capture':
    body = COMMON + r'''
if (view610) {
  (void)[(id)view610 setIndex: (short)INDEX];
  (void)[(id)view610 setNeedsDisplay: YES];
  (void)[(id)view610 display];
  float wl610 = 0; float ww610 = 0;
  (void)[(id)view610 getWLWW:&wl610 :&ww610];
  m610[@"windowLevel"] = @((double)wl610);
  m610[@"windowWidth"] = @((double)ww610);
  m610[@"curImage"] = @((long)[(id)view610 curImage]);
  m610[@"backend"] = (NSString*)[(id)view610 horosPlanarBackendName] ?: @"";
  m610[@"planarEnabled"] = @((BOOL)[(id)vc610 horosPlanarMetalEnabled]);
  m610[@"fallbackReason"] = (NSString*)[(id)view610 horosPlanarFallbackReason] ?: @"";
  NSImage *image610 = (NSImage*)[(id)view610 nsimage: NO];
  if (image610) {
    m610[@"imageWidth"] = @((double)[image610 size].width);
    m610[@"imageHeight"] = @((double)[image610 size].height);
    NSData *tiff610 = (NSData*)[image610 TIFFRepresentation];
    NSBitmapImageRep *rep610 = [NSBitmapImageRep imageRepWithData: tiff610];
    NSData *png610 = [rep610 representationUsingType: NSBitmapImageFileTypePNG properties: @{}];
    m610[@"wrotePNG"] = @((BOOL)[png610 writeToFile: @"IMAGE" atomically: YES]);
    m610[@"pixelsWide"] = @((long)[rep610 pixelsWide]);
    m610[@"pixelsHigh"] = @((long)[rep610 pixelsHigh]);
  } else m610[@"wrotePNG"] = @NO;
}
'''.replace('INDEX', str(arguments.index)).replace('IMAGE', str(image))

expr = body + '(void)[[NSJSONSerialization dataWithJSONObject:m610 options:3 error:nil] writeToFile:@"STAGED" atomically:YES];\n'
expr = expr.replace('STAGED', str(staged))
commands = arguments.output / ('print-' + label + '.lldb')
commands.write_text('expression -l objc++ -- @import AppKit\n'
                    'expression -l objc++ -- @import ObjectiveC\n'
                    'expression -l objc++ -- { ' + ' '.join(expr.splitlines()) + ' }\nprocess detach\n')
run = subprocess.run(['xcrun', 'lldb', '--batch', '-p', str(arguments.pid), '-s', str(commands)],
                     capture_output=True, text=True)
(arguments.output / ('print-' + label + '.log')).write_text(run.stdout + run.stderr)
if not staged.exists():
    print(run.stdout[-3000:])
    print(run.stderr[-2000:])
    raise SystemExit('the step produced no snapshot; see %s' % (arguments.output / ('print-' + label + '.log')))
staged.replace(output)
print(output)
print(json.dumps(json.loads(output.read_text()), indent=1))
