#!/usr/bin/env python3
"""Exercise ROI Info's production color load/action with real AppKit conversion."""
from pathlib import Path
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
path = 'Horos/Sources/ROIWindow.m'
source = (subprocess.check_output(['git', 'show', sys.argv[1] + ':' + path])
          if len(sys.argv) > 1 else (root / path).read_bytes()).decode('latin1')
a = source.index('\tRGBColor\trgb = [curROI rgbcolor];')
b = source.index('[thicknessSlider setFloatValue:', a)
load = source[a:b]
a = source.index('- (IBAction) setColor:(NSColorWell*) sender')
b = source.index('+ (void) addROIValues:', a)
action = source[a:b]
code = r'''
#import <Cocoa/Cocoa.h>
NSString *OsirixROIChangeNotification = @"QA ROI changed";
@interface ROI:NSObject
@property RGBColor rgbcolor;
@property(copy) NSString *name;
-(void)setColor:(RGBColor)c;
@end
@implementation ROI
-(void)setColor:(RGBColor)c {self.rgbcolor=c;}
@end
@interface Peer:NSObject {
@public ROI *curROI; NSColorWell *colorButton; NSTextView *comments;
}
-(void)loadColor;
-(BOOL)allWithSameName;
-(void)setAllMatchingROIsToSameParamsAs:(ROI*)r withNewName:(NSString*)n;
-(IBAction)setColor:(NSColorWell*)sender;
@end
@implementation Peer
-(void)loadColor { LOAD }
-(BOOL)allWithSameName {return NO;}
-(void)setAllMatchingROIsToSameParamsAs:(ROI*)r withNewName:(NSString*)n {abort();}
ACTION
@end
#define check(...) do {if(!(__VA_ARGS__)){NSLog(@"FAIL: %s",#__VA_ARGS__);return 1;}}while(0)
int main(){@autoreleasepool{
 [NSApplication sharedApplication];
 Peer *p=[Peer new];p->curROI=[ROI new];p->colorButton=[NSColorWell new];
 __block int notifications=0;
 id token=[[NSNotificationCenter defaultCenter] addObserverForName:OsirixROIChangeNotification object:p->curROI queue:nil usingBlock:^(NSNotification*n){notifications++;}];
 RGBColor cases[]={{32768,32768,32768},{12345,45678,23456},{65535,0,0},{0,65535,0},{0,0,65535},{65535,65535,0},{0,0,0},{65535,65535,65535}};
 for(unsigned i=0;i<sizeof(cases)/sizeof(cases[0]);i++) {
  RGBColor expected=cases[i];p->curROI.rgbcolor=expected;
  for(int j=0;j<20;j++) {
   [p loadColor];[p setColor:p->colorButton];
   RGBColor got=p->curROI.rgbcolor;
   if(abs(got.red-expected.red)>1 || abs(got.green-expected.green)>1 || abs(got.blue-expected.blue)>1){
    NSLog(@"FAIL roundtrip %d: RGB %u,%u,%u became %u,%u,%u",j,expected.red,expected.green,expected.blue,got.red,got.green,got.blue);return 1;
   }
  }
 }
 check(notifications==160);
 [[NSNotificationCenter defaultCenter] removeObserver:token];
 NSLog(@"PASS: 8 colors retain 16-bit channels through 20 ROI Info load/apply cycles; change notifications delivered");
}}
'''.replace('LOAD', load).replace('ACTION', action)
with tempfile.TemporaryDirectory(prefix='horos-roi-color-') as d:
    p = Path(d)
    (p / 'test.m').write_text(code)
    subprocess.run(['xcrun', 'clang', '-fno-objc-arc', '-Wno-deprecated-declarations',
                    '-fsanitize=undefined', '-framework', 'Cocoa', str(p / 'test.m'),
                    '-o', str(p / 'test')], check=True)
    subprocess.run([str(p / 'test')], check=True)
