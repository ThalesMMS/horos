#!/usr/bin/env python3
"""Check VR measurement labels keep complete digits and units; no VTK rebuild."""
from pathlib import Path
import subprocess, sys, tempfile

root = Path(__file__).resolve().parents[1]
src = (subprocess.check_output(['git', 'show', sys.argv[1] + ':Horos/Sources/VRView.mm'])
       if len(sys.argv) > 1 else (root / 'Horos/Sources/VRView.mm').read_bytes()).decode('latin1')
roi = (subprocess.check_output(['git', 'show', sys.argv[1] + ':Horos/Sources/ROI.m'])
       if len(sys.argv) > 1 else (root / 'Horos/Sources/ROI.m').read_bytes()).decode('latin1')
start = src.index('Line2DText = vtkTextActor::New();')
end = src.index('aRenderer->AddActor2D( Line2DActor);', start)
setup = src[start:end]
if 'SetTextScaleModeToNone()' not in setup:
    raise SystemExit('FAIL: Line2DText must keep SetTextScaleModeToNone so zoom does not scale/clip glyphs')
format_a = src.index('        NSString *localizedText = nil;', src.index('- (void) computeLength'))
format_b = src.index('        Line2DText->SetInput', format_a)
vr_format = src[format_a:format_b]
length_a = roi.index('+ (NSString*) formattedLength: (float) lCm')
length_b = roi.index('\n}', length_a) + 2
roi_format = roi[length_a:length_b]
owner_a = src.index('        text = vtkTextActor::New();', src.index('@implementation HorosVRStoredMeasurement'))
owner_b = src.index('        text->GetPositionCoordinate()->SetCoordinateSystemToViewport();', owner_a)
if 'SetTextScaleModeToNone()' not in src[owner_a:owner_b]:
    raise SystemExit('FAIL: stored VR overlays must copy SetTextScaleModeToNone')
if 'SetInput(sourceText->GetInput())' not in src[owner_a:owner_b]:
    raise SystemExit('FAIL: stored VR overlays must copy the complete input string')
code = r'''
#import <Foundation/Foundation.h>
#undef NSLocalizedString
#define NSLocalizedString(key, comment) (key)
@interface ROI:NSObject
+(NSString*) formattedLength:(float)lCm;
@end
@implementation ROI
ROI_FORMAT
@end
static NSString *vrLabel(double length, double factor) {
 VR_FORMAT
 return localizedText;
}
#define check(...) do{if(!(__VA_ARGS__)){NSLog(@"FAIL: %s",#__VA_ARGS__);return 1;}}while(0)
static BOOL completeUnit(NSString *text, NSString *unit) {
 return [text containsString:@"Length:"] && [text containsString:unit]
     && [text rangeOfCharacterFromSet:[NSCharacterSet decimalDigitCharacterSet]].location!=NSNotFound;
}
int main(){@autoreleasepool{
 NSString *cm=vrLabel(31,1);
 check([cm isEqualToString:@"Length: 3.10 cm "]);
 check(completeUnit(cm,@"cm"));
 NSString *small=vrLabel(0.5,1);
 check([small isEqualToString:@"Length: 0.50 mm "]);
 check(completeUnit(small,@"mm"));
 NSString *native=vrLabel(21.5,1);
 check([native isEqualToString:@"Length: 2.15 cm "]);
 NSString *zoom=vrLabel(19.4,1);
 check([zoom isEqualToString:@"Length: 1.94 cm "]);
 check([[ROI formattedLength:5.501] isEqualToString:@"5.50 cm"]);
 check([[ROI formattedLength:5.298] hasSuffix:@"cm"]);
 check([[ROI formattedLength:0.05] hasSuffix:@"mm"]);
 NSString *micron=[ROI formattedLength:0.005];
 check([micron hasSuffix:@"m"]);
 check([micron containsString:[NSString stringWithFormat:@"%c",0xb5]]);
 NSLog(@"PASS: VR computeLength labels keep digits and cm/mm units for phantom 3.10/2.15/1.94 cm and 0.50 mm; 2D formattedLength units remain complete; VR text is unscaled");
}}
'''.replace('ROI_FORMAT', roi_format).replace('VR_FORMAT', vr_format)
with tempfile.TemporaryDirectory(prefix='horos-vr-label-') as d:
    p = Path(d)
    (p / 'test.m').write_text(code)
    subprocess.run(['xcrun', 'clang', '-fno-objc-arc', '-fsanitize=undefined',
                    '-framework', 'Foundation', str(p / 'test.m'), '-o', str(p / 'test')],
                   check=True)
    subprocess.run([str(p / 'test')], check=True)
