#!/usr/bin/env python3
"""Compile production rate actions and verify independent rates and reverse labels."""
from pathlib import Path
import subprocess, tempfile
root=Path(__file__).resolve().parents[1]
s=(root/'Horos/Sources/ViewerController.m').read_bytes().decode('latin1')
a=s.index('- (float) frameRate\n');b=s.index('-(NSSlider*) moviePosSlider',a)
methods=s[a:b]
code=r'''
#import <AppKit/AppKit.h>
#define check(c) NSCAssert((c),@"failed: %s",#c)
@interface WindowProbe:NSObject
@property BOOL keyWindow;
@end
@implementation WindowProbe
- (BOOL)isKeyWindow{return self.keyWindow;}
@end
@interface ViewerController:NSObject {
@public
 NSSlider *speedSlider,*movieRateSlider;
 NSTextField *speedText,*movieTextSlide;
 short direction;
}
@property WindowProbe *window;
@property(readonly) NSSlider *speedSlider,*movieRateSlider;
@property(readonly) NSTextField *speedText,*movieTextSlide;
@property(readonly) float frameRate;
+ (NSArray*)getDisplayed2DViewers;
@end
static NSArray *viewers;
@implementation ViewerController
@synthesize speedSlider,movieRateSlider,speedText,movieTextSlide;
+ (NSArray*)getDisplayed2DViewers{return viewers;}
- (id)init{if((self=[super init])){
 speedSlider=[NSSlider new];speedSlider.maxValue=60;
 movieRateSlider=[NSSlider new];movieRateSlider.maxValue=60;
 speedText=[NSTextField new];movieTextSlide=[NSTextField new];
 self.window=[WindowProbe new];direction=1;
}return self;}
METHODS
@end
int main(void){@autoreleasepool {
 [NSApplication sharedApplication];
 ViewerController *source=[ViewerController new],*reverse=[ViewerController new],*custom=[ViewerController new];
 viewers=@[source,reverse,custom];source.window.keyWindow=YES;reverse->direction=-1;
 for(ViewerController *v in viewers){v.speedSlider.floatValue=10;v.movieRateSlider.floatValue=3;}
 custom.speedSlider.floatValue=7;custom.movieRateSlider.floatValue=4;
 [NSUserDefaults.standardUserDefaults setFloat:10 forKey:@"defaultFrameRate"];
 [NSUserDefaults.standardUserDefaults setFloat:3 forKey:@"defaultMovieRate"];
 source.speedSlider.floatValue=5;[source speedSliderAction:nil];
 check(reverse.speedSlider.floatValue==5);check(custom.speedSlider.floatValue==7);
 check([source.speedText.stringValue hasPrefix:@"5.0"]);
 check([reverse.speedText.stringValue hasPrefix:@"-5.0"]);
 check(reverse.movieRateSlider.floatValue==3);check(custom.movieRateSlider.floatValue==4);
 source.movieRateSlider.floatValue=2;[source movieRateSliderAction:nil];
 check(reverse.movieRateSlider.floatValue==2);check(custom.movieRateSlider.floatValue==4);
 check(reverse.speedSlider.floatValue==5);check(custom.speedSlider.floatValue==7);
 check([reverse.speedText.stringValue hasPrefix:@"-5.0"]);
 source.window.keyWindow=NO;source.speedSlider.floatValue=9;[source speedSliderAction:nil];
 check(reverse.speedSlider.floatValue==5);
 check([NSUserDefaults.standardUserDefaults floatForKey:@"defaultFrameRate"]==5);
 [NSUserDefaults.standardUserDefaults removeObjectForKey:@"defaultFrameRate"];
 [NSUserDefaults.standardUserDefaults removeObjectForKey:@"defaultMovieRate"];
 NSLog(@"PASS: independent slice/phase controls, reversed label, customized rates preserved, only key viewer propagates");
}}
'''.replace('METHODS',methods)
with tempfile.TemporaryDirectory(prefix='horos-cine-controls-') as tmp:
 p=Path(tmp);(p/'test.m').write_text(code)
 subprocess.run(['xcrun','clang','-fobjc-arc','-framework','AppKit',str(p/'test.m'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
