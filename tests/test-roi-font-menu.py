#!/usr/bin/env python3
"""ROI font-size menu stays enabled from the 2D viewer after a redraw.

Increase/Decrease Font Size target the first responder. After a font action
the OpenGL view can lose first-responder while it rebuilds, so the next menu
validation must still find the actions on ViewerController and enable them from
LabelFONTSIZE rather than from a selected ROI.
"""
from pathlib import Path
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]


def source(name):
    path = 'Horos/Sources/' + name
    return (subprocess.check_output(['git', 'show', sys.argv[1] + ':' + path])
            if len(sys.argv) > 1 else (root / path).read_bytes()).decode('latin1')


view = source('DCMView.m')
controller = source('ViewerController.m')
header = source('ViewerController.h')


def isolate(text, start, *stops):
    if start not in text:
        print('FAIL: missing', start, file=sys.stderr)
        sys.exit(1)
    a = text.index(start)
    end = len(text)
    for stop in stops:
        i = text.find(stop, a + len(start))
        if i != -1:
            end = min(end, i)
    return text[a:end]


helper = isolate(view, '+ (BOOL) labelFontSizeMenuItemIsEnabled:',
                 '\n- (BOOL)validateMenuItem:', '\n- (void) increaseFontSize:')
increase = isolate(controller, '- (void) increaseFontSize:',
                   '\n- (void) decreaseFontSize:')
decrease = isolate(controller, '- (void) decreaseFontSize:',
                   '\n- (void) rotate0:', '\n- (void) flipVertical:')
view_validate = isolate(view, '- (BOOL)validateMenuItem:',
                         '\n- (IBAction) roiSaveSelected:')
controller_validate = isolate(controller, '- (BOOL)validateMenuItem:',
                               '\n- (IBAction) resetWindowsState:')

if 'increaseThickness:' in helper or 'ROI_selected' in helper:
    print('FAIL: font-size enablement must not require a selected ROI', file=sys.stderr)
    sys.exit(1)
if 'LabelFONTSIZE' not in helper:
    print('FAIL: font-size menu enablement must read LabelFONTSIZE', file=sys.stderr)
    sys.exit(1)
if '[DCMView labelFontSizeMenuItemIsEnabled:' not in view_validate:
    print('FAIL: DCMView validateMenuItem must use the shared LabelFONTSIZE helper',
          file=sys.stderr)
    sys.exit(1)
if 'increaseFontSize:' not in view_validate or 'decreaseFontSize:' not in view_validate:
    print('FAIL: DCMView validateMenuItem does not mention the font-size actions',
          file=sys.stderr)
    sys.exit(1)
if '[DCMView labelFontSizeMenuItemIsEnabled:' not in controller_validate:
    print('FAIL: ViewerController validateMenuItem must use the shared LabelFONTSIZE helper',
          file=sys.stderr)
    sys.exit(1)
if 'windowWillClose' in increase or 'closeWindow' in increase + decrease:
    print('FAIL: font-size actions must not recreate the viewer', file=sys.stderr)
    sys.exit(1)
if '[imageView increaseFontSize: sender]' not in increase:
    print('FAIL: ViewerController increaseFontSize: must forward to imageView',
          file=sys.stderr)
    sys.exit(1)
if '[imageView decreaseFontSize: sender]' not in decrease:
    print('FAIL: ViewerController decreaseFontSize: must forward to imageView',
          file=sys.stderr)
    sys.exit(1)
if 'increaseFontSize:' not in header or 'decreaseFontSize:' not in header:
    print('FAIL: ViewerController must declare the font-size actions', file=sys.stderr)
    sys.exit(1)
for forbidden in ('HorosROILineGeometry', 'HorosROILabelPresentation',
                  'generateGeometryFromSelectedLine', 'tMesure'):
    if forbidden in increase + decrease + helper:
        print('FAIL: font-size menu must not touch ROI geometry', file=sys.stderr)
        sys.exit(1)

code = r'''
#import <Cocoa/Cocoa.h>
@interface DCMView:NSObject
+ (BOOL) labelFontSizeMenuItemIsEnabled:(NSMenuItem *)item;
@end
@implementation DCMView
HELPER
@end
@interface ImageView:NSObject
@property int increases;
@property int decreases;
-(void)increaseFontSize:(id)sender;
-(void)decreaseFontSize:(id)sender;
@end
@implementation ImageView
-(void)increaseFontSize:(id)sender{self.increases++;}
-(void)decreaseFontSize:(id)sender{self.decreases++;}
@end
@interface ViewerController:NSObject {ImageView *imageView;}
-(void)increaseFontSize:(id)sender;
-(void)decreaseFontSize:(id)sender;
@end
@implementation ViewerController
INCREASE
DECREASE
@end
#define check(...) do {if(!(__VA_ARGS__)){NSLog(@"FAIL: %s",#__VA_ARGS__);return 1;}}while(0)
int main(){@autoreleasepool{
 NSUserDefaults *d=[NSUserDefaults standardUserDefaults];
 NSMenuItem *up=[[NSMenuItem alloc] initWithTitle:@"Increase Font Size" action:@selector(increaseFontSize:) keyEquivalent:@""];
 NSMenuItem *down=[[NSMenuItem alloc] initWithTitle:@"Decrease Font Size" action:@selector(decreaseFontSize:) keyEquivalent:@""];
 for(NSNumber *size in @[@6,@13,@60]){
  [d setVolatileDomain:@{@"LabelFONTSIZE":size} forName:NSArgumentDomain];
  BOOL canUp=[DCMView labelFontSizeMenuItemIsEnabled:up];
  BOOL canDown=[DCMView labelFontSizeMenuItemIsEnabled:down];
  if(size.intValue==6){check(!canDown);check(canUp);}
  else if(size.intValue==13){check(canUp);check(canDown);}
  else {check(!canUp);check(canDown);}
 }
 ViewerController *vc=[ViewerController new];
 ImageView *view=[ImageView new];
 [vc setValue:view forKey:@"imageView"];
 [vc increaseFontSize:up];
 [vc decreaseFontSize:down];
 check(view.increases==1 && view.decreases==1);
 NSLog(@"PASS: LabelFONTSIZE 6/13/60 menu enablement and viewer forwarding");
}}
'''.replace('HELPER', helper).replace('INCREASE', increase).replace('DECREASE', decrease)

with tempfile.TemporaryDirectory(prefix='horos-roi-font-menu-') as d:
    p = Path(d)
    (p / 'test.m').write_text(code)
    subprocess.run(['xcrun', 'clang', '-fno-objc-arc', '-fsanitize=undefined',
                    '-framework', 'Cocoa', str(p / 'test.m'), '-o', str(p / 'test')],
                   check=True)
    subprocess.run([str(p / 'test')], check=True)
