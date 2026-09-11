#!/usr/bin/env python3
"""Check production ROI/OSIROI color bridging against real AppKit channels."""
from pathlib import Path
import subprocess
import sys
import tempfile
root = Path(__file__).resolve().parents[1]
def source(name):
    path = 'Horos/Sources/' + name
    return (subprocess.check_output(['git', 'show', sys.argv[1] + ':' + path])
            if len(sys.argv) > 1 else (root / path).read_bytes()).decode('latin1')
s = source('ROI.m')
bridge = s[s.index('-(void)setNSColor:(NSColor*)nsColor {'):s.rindex('@end')]
s = source('OSIROI.m')
consumers = s[s.index('- (NSColor *)fillColor'):s.index('- (CGFloat)strokeThickness')]
code = r'''
#import <Cocoa/Cocoa.h>
enum {tPlain=1,tMesure=2};
@interface ROI:NSObject {RGBColor color;float opacity;}
@property int type;
-(void)setColor:(RGBColor)c globally:(BOOL)g;
-(void)setOpacity:(float)a globally:(BOOL)g;
-(void)setOpacity:(float)a;
-(float)opacity;
-(NSColor*)NSColor;
-(void)setNSColor:(NSColor*)c;
-(void)setNSColor:(NSColor*)c globally:(BOOL)g;
@end
@implementation ROI
-(void)setColor:(RGBColor)c globally:(BOOL)g {color=c;}
-(void)setOpacity:(float)a globally:(BOOL)g {opacity=a;}
-(void)setOpacity:(float)a {opacity=a;}
-(float)opacity {return opacity;}
BRIDGE
@end
@interface OSIROI:NSObject
@property(retain) NSSet *osiriXROIs;
@end
@implementation OSIROI
CONSUMERS
@end
#define check(...) do {if(!(__VA_ARGS__)){NSLog(@"FAIL: %s",#__VA_ARGS__);return 1;}}while(0)
static BOOL matches(NSColor*c,RGBColor rgb,float alpha){
 if(!c)return NO;
 CGFloat r,g,b,a;[c getRed:&r green:&g blue:&b alpha:&a];
 return fabs(r-rgb.red/65535.0)<1.1/65535 && fabs(g-rgb.green/65535.0)<1.1/65535 && fabs(b-rgb.blue/65535.0)<1.1/65535 && fabs(a-alpha)<1e-6;
}
int main(){@autoreleasepool{
 RGBColor cases[]={{32768,32768,32768},{12345,45678,23456},{1,65534,30000},{65535,0,0},{0,65535,0},{0,0,65535},{65535,65535,0},{0,0,0},{65535,65535,65535}};
 for(unsigned i=0;i<sizeof(cases)/sizeof(cases[0]);i++)for(NSNumber *alpha in @[@0,@0.5,@1]){
  ROI*r=[ROI new];[r setColor:cases[i] globally:NO];[r setOpacity:alpha.floatValue globally:NO];
  if(!matches([r NSColor],cases[i],alpha.floatValue)) {NSLog(@"FAIL RGB %u,%u,%u alpha %.2f became %@",cases[i].red,cases[i].green,cases[i].blue,alpha.floatValue,[r NSColor]);return 1;}
  OSIROI*wrapper=[OSIROI new];wrapper.osiriXROIs=[NSSet setWithObject:r];
  r.type=tMesure;check(matches([wrapper strokeColor],cases[i],alpha.floatValue));check([wrapper fillColor]==nil);
  r.type=tPlain;check(matches([wrapper fillColor],cases[i],alpha.floatValue));check([wrapper strokeColor]==nil);
  // The public bridge must preserve intermediate channels when its own output is reapplied.
  for(int j=0;j<20;j++){[r setNSColor:[r NSColor] globally:NO];check(matches([r NSColor],cases[i],alpha.floatValue));}
  [wrapper release];[r release];
 }


 // Control both enumeration orders: the getters must not depend on NSSet order.
 ROI *brush=[ROI new], *line=[ROI new], *brush2=[ROI new], *line2=[ROI new];
 brush.type=brush2.type=tPlain;line.type=line2.type=tMesure;
 RGBColor fill={12345,23456,34567},stroke={45678,56789,12345};
 for(ROI*r in @[brush,brush2]){[r setColor:fill globally:NO];[r setOpacity:0.5];}
 for(ROI*r in @[line,line2]){[r setColor:stroke globally:NO];[r setOpacity:1];}
 OSIROI *group=[OSIROI new];
 for(NSArray *order in @[@[brush,line],@[line,brush],@[brush,line2,line,brush2],@[line,brush2,brush,line2]]){
  // The peer supplies a deterministic fast-enumerable collection; production uses NSSet.
  group.osiriXROIs=(NSSet*)order;
  check(matches([group fillColor],fill,0.5));check(matches([group strokeColor],stroke,1));
 }
 group.osiriXROIs=[NSSet setWithObjects:brush,line,brush2,line2,nil];
 check(matches([group fillColor],fill,0.5));check(matches([group strokeColor],stroke,1));
 [brush2 setOpacity:0.75];check([group fillColor]==nil);check(matches([group strokeColor],stroke,1));
 [brush2 setOpacity:0.5];[line2 setColor:fill globally:NO];
 check([group strokeColor]==nil);check(matches([group fillColor],fill,0.5));
 group.osiriXROIs=[NSSet set];check([group fillColor]==nil && [group strokeColor]==nil);
 [group release];[brush release];[brush2 release];[line release];[line2 release];
 // Public NSColor inputs can have non-RGB components or a different RGB profile.
 for(NSColor *input in @[[NSColor colorWithCalibratedWhite:0.4 alpha:0.5],
                         [NSColor colorWithDeviceRed:0.4 green:0.6 blue:0.2 alpha:0.75],
                         [NSColor colorWithDisplayP3Red:0.4 green:0.6 blue:0.2 alpha:0.25],
                         [NSColor colorWithDeviceCyan:0.2 magenta:0.4 yellow:0.6 black:0.1 alpha:1]]) {
  NSColor *expected=[input colorUsingColorSpace:[NSColorSpace genericRGBColorSpace]];
  CGFloat r,g,b,a;[expected getRed:&r green:&g blue:&b alpha:&a];
  RGBColor channels={r*65535,g*65535,b*65535};
  ROI *roi=[ROI new];
  @try {[roi setNSColor:input globally:NO];}
  @catch(NSException *e){NSLog(@"FAIL accepting %@: %@",input,e.reason);return 1;}
  check(matches([roi NSColor],channels,a));
  OSIROI *wrapper=[OSIROI new];wrapper.osiriXROIs=[NSSet setWithObject:roi];
  roi.type=tPlain;[wrapper setFillColor:input];check(matches([wrapper fillColor],channels,a));
  roi.type=tMesure;[wrapper setStrokeColor:input];check(matches([wrapper strokeColor],channels,a));
  [wrapper release];[roi release];
 }
 ROI *unchanged=[ROI new];RGBColor original={12345,23456,34567};
 [unchanged setColor:original globally:NO];[unchanged setOpacity:0.5 globally:NO];
 NSImage *pattern=[[NSImage alloc] initWithSize:NSMakeSize(2,2)];
 @try {
  [unchanged setNSColor:[NSColor colorWithPatternImage:pattern] globally:NO];
  check(matches([unchanged NSColor],original,0.5));
  [unchanged setNSColor:nil globally:NO];
  check(matches([unchanged NSColor],original,0.5));
 } @catch(NSException *e){NSLog(@"FAIL unsupported input: %@",e.reason);return 1;}
 [pattern release];[unchanged release];
 NSLog(@"PASS: ROI NSColor and OSIROI fill/stroke retain nine RGB colors, three alpha levels, repeated roundtrips, gray/device/P3/CMYK inputs unsupported-input preservation and mixed-type collection ordering");
}}
'''.replace('BRIDGE',bridge).replace('CONSUMERS',consumers)
with tempfile.TemporaryDirectory(prefix='horos-roi-nscolor-') as d:
    p=Path(d);(p/'test.m').write_text(code)
    subprocess.run(['xcrun','clang','-fno-objc-arc','-fsanitize=undefined','-framework','Cocoa',str(p/'test.m'),'-o',str(p/'test')],check=True)
    subprocess.run([str(p/'test')],check=True)
