#!/usr/bin/env python3
"""Test Swift compact formatting and production ROI presentation selection."""
from pathlib import Path
import subprocess,tempfile
root=Path(__file__).resolve().parents[1]
s=(root/'Horos/Sources/ROI.m').read_bytes().decode('latin1')
a=s.index('- (NSArray*) displayedTextualLines');b=s.index('- (void) prepareTextualData:',a)
code=r'''
#import <Cocoa/Cocoa.h>
#import "Presentation-Swift.h"
static BOOL ROITEXTNAMEONLY;
enum{tOPolygon,tMesure,tAngle,tOval,tROI,tCPolygon,tPencil,tPlain,tText};
@interface ROI:NSObject {
@public NSString *textualBoxLine1,*textualBoxLine2,*textualBoxLine3,*textualBoxLine4,*textualBoxLine5,*textualBoxLine6;int type;
}
@end
@implementation ROI
METHOD
@end
#define check(...) do{if(!(__VA_ARGS__)){NSLog(@"FAIL: %s",#__VA_ARGS__);return 1;}}while(0)
int main(){@autoreleasepool{
 ROI*r=[ROI new];r->type=tCPolygon;
 r->textualBoxLine1=@"QA Area";r->textualBoxLine2=@"Area: 25.000 mm²";
 r->textualBoxLine3=@"Mean: 22.500";r->textualBoxLine5=@"Length: 2.000 cm";
 NSUserDefaults*d=[NSUserDefaults standardUserDefaults];
 [d setVolatileDomain:@{@"ROIPRIMARYMEASUREMENTONLY":@NO} forName:NSArgumentDomain];
 NSArray*full=[r displayedTextualLines];check(full.count==6 && [full[2] isEqual:@"Mean: 22.500"]);
 [d setVolatileDomain:@{@"ROIPRIMARYMEASUREMENTONLY":@YES} forName:NSArgumentDomain];
 for(NSNumber*t in @[@(tCPolygon),@(tOval),@(tROI),@(tPencil),@(tPlain)]){
  r->type=t.intValue;check([[r displayedTextualLines] isEqual:@[@"25.000 mm²"]]);
 }
 r->type=tOPolygon;check([[r displayedTextualLines] isEqual:@[@"2.000 cm"]]);
 r->type=tMesure;r->textualBoxLine2=@"Comprimento: 5,501 cm";
 check([[r displayedTextualLines] isEqual:@[@"5,501 cm"]]);
 r->type=tAngle;r->textualBoxLine2=@"Angle: 60.000° / 300.000°";
 check([[r displayedTextualLines] isEqual:@[@"60.000°"]]);
 r->type=tMesure;r->textualBoxLine2=@"Length: X=3 cm, Y=2 cm/sec";
 check([r displayedTextualLines].count==6);
 r->type=tText;check([r displayedTextualLines].count==6);
 r->type=tCPolygon;r->textualBoxLine2=@"Area: 25.000 mm²";
 ROITEXTNAMEONLY=YES;check([[r displayedTextualLines] isEqual:full]);ROITEXTNAMEONLY=NO;
 [d setVolatileDomain:@{@"ROIPRIMARYMEASUREMENTONLY":@NO} forName:NSArgumentDomain];
 check([[r displayedTextualLines] isEqual:full]);
 check([r->textualBoxLine3 isEqual:@"Mean: 22.500"]);
 check(![HorosROILabelPresentation compactMeasurement:@"Area:" primaryAngle:NO]);
 check(![HorosROILabelPresentation compactMeasurement:nil primaryAngle:NO]);
 check([[HorosROILabelPresentation compactMeasurement:@"Length: 40.0 µm" primaryAngle:NO] isEqual:@"40.0 µm"]);
 NSLog(@"PASS: opt-in/default/restore, area/length/angle, units/locale, full-source preservation, name-only precedence, compound and unknown fallbacks");
}}
'''.replace('METHOD',s[a:b])
with tempfile.TemporaryDirectory(prefix='horos-primary-label-') as d:
    p=Path(d);(p/'test.m').write_text(code)
    subprocess.run(['xcrun','swiftc',str(root/'Horos/Sources/ROILabelPresentation.swift'),'-emit-library','-module-name','Presentation','-emit-objc-header-path',str(p/'Presentation-Swift.h'),'-o',str(p/'libPresentation.dylib')],check=True)
    subprocess.run(['xcrun','clang','-fno-objc-arc','-fsanitize=undefined','-framework','Cocoa','-I',d,str(p/'test.m'),'-L',d,'-lPresentation','-o',str(p/'test')],check=True)
    subprocess.run([str(p/'test')],check=True)
