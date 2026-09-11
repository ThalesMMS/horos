#!/usr/bin/env python3
"""Test the production ROI visibility rule for multiple unselected measures."""
from pathlib import Path
import subprocess, tempfile
root = Path(__file__).resolve().parents[1]
s = (root/'Horos/Sources/ROI.m').read_bytes().decode('latin1')
a = s.index('- (BOOL) isTextualDataDisplayed')
b = s.index('- (NSArray*) fitTextualDataToAvailableSpace', a)
code = r'''
#import <Foundation/Foundation.h>
static BOOL ROITEXTIFSELECTED;
enum { ROI_sleep, ROI_selected, ROI_selectedModify, ROI_drawing };
enum { tMesure, tOPolygon, tCPolygon, tPencil, tPlain };
@interface ROI:NSObject {
@public BOOL displayTextualData,hidden,_displayCalciumScoring,mouseOverROI;int mode,type;
}
@end
@implementation ROI
METHOD
@end
#define check(...) do{if(!(__VA_ARGS__)){NSLog(@"FAIL: %s",#__VA_ARGS__);return 1;}}while(0)
int main(){@autoreleasepool{
 ROI *a=[ROI new],*b=[ROI new];
 a->displayTextualData=b->displayTextualData=YES;a->type=b->type=tMesure;
 a->mode=b->mode=ROI_sleep;
 check([a isTextualDataDisplayed] && [b isTextualDataDisplayed]);
 a->mode=ROI_selected;
 check([a isTextualDataDisplayed] && [b isTextualDataDisplayed]);
 // Selection-only is opt-in and applies independently to each measure.
 ROITEXTIFSELECTED=YES;
 check([a isTextualDataDisplayed] && ![b isTextualDataDisplayed]);
 a->mode=ROI_sleep;
 check(![a isTextualDataDisplayed] && ![b isTextualDataDisplayed]);
 b->mouseOverROI=YES;
 check(![a isTextualDataDisplayed] && [b isTextualDataDisplayed]);
 b->mouseOverROI=NO;ROITEXTIFSELECTED=NO;
 check([a isTextualDataDisplayed] && [b isTextualDataDisplayed]);
 // Explicit suppression still takes precedence, independent of the peer ROI.
 for(int state=0;state<4;state++) {
  a->mode=state;a->hidden=YES;
  check(![a isTextualDataDisplayed] && [b isTextualDataDisplayed]);a->hidden=NO;
  a->_displayCalciumScoring=YES;check(![a isTextualDataDisplayed]);a->_displayCalciumScoring=NO;
  a->displayTextualData=NO;check(![a isTextualDataDisplayed]);a->displayTextualData=YES;
 }
 NSLog(@"PASS: two unselected measures, independent selection, opt-in selection-only, hover, restore and explicit suppression");
}}
'''.replace('METHOD',s[a:b])
with tempfile.TemporaryDirectory(prefix='horos-measure-visibility-') as d:
 p=Path(d);(p/'test.m').write_text(code)
 subprocess.run(['xcrun','clang','-fno-objc-arc','-fsanitize=undefined','-framework','Foundation',str(p/'test.m'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
