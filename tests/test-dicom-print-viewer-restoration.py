#!/usr/bin/env python3
"""Exercise production print preparation and restoration with a controlled viewer."""
from pathlib import Path
import subprocess
import tempfile
root=Path(__file__).resolve().parent.parent
source=(root/'DICOMPrint/AYNSImageToDicom.m').read_bytes().decode('latin1')
start=source.index('- (NSArray *) dicomFileListForViewer:',source.index('- (NSArray *) dicomFileListForViewer:')+1)
method=source[start:source.index('\n//********',start)]
program=r'''
#import <Foundation/Foundation.h>
static BOOL FULL32BITPIPELINE, constrainFlag, magneticFlag, screenFlag;
static NSString *OsirixGLFontChangeNotification=@"QA font";
@interface OSIWindow : NSObject
+ (BOOL)dontConstrainWindow;
+ (void)setDontConstrainWindow:(BOOL)v;
@end
@implementation OSIWindow
+ (BOOL)dontConstrainWindow { return constrainFlag; }
+ (void)setDontConstrainWindow:(BOOL)v { constrainFlag=v; }
@end
@interface OSIWindowController : NSObject
+ (BOOL)dontEnterMagneticFunctions;
+ (BOOL)dontWindowDidChangeScreen;
+ (void)setDontEnterMagneticFunctions:(BOOL)v;
+ (void)setDontEnterWindowDidChangeScreen:(BOOL)v;
@end
@implementation OSIWindowController
+ (BOOL)dontEnterMagneticFunctions { return magneticFlag; }
+ (BOOL)dontWindowDidChangeScreen { return screenFlag; }
+ (void)setDontEnterMagneticFunctions:(BOOL)v { magneticFlag=v; }
+ (void)setDontEnterWindowDidChangeScreen:(BOOL)v { screenFlag=v; }
@end
@interface NSFont : NSObject
+ (void)resetFont:(int)n;
@end
@implementation NSFont
+ (void)resetFont:(int)n {}
@end
static NSUserDefaults *qaDefaults;
@interface TestDefaults : NSObject
+ (NSUserDefaults*)standardUserDefaults;
@end
@implementation TestDefaults
+ (NSUserDefaults*)standardUserDefaults { return qaDefaults; }
@end
#define NSUserDefaults TestDefaults
@interface ViewerController : NSObject
@property int curImage, imageRows, imageColumns;
@property BOOL magnetic, matrixVisible, displayed;
@property NSRect frame;
- (ViewerController*)imageView;
- (ViewerController*)seriesView;
- (ViewerController*)window;
- (ViewerController*)screen;
- (BOOL)checkFrameSize;
- (float)scaleValue;
- (NSRect)visibleFrame;
- (void)setFrame:(NSRect)frame display:(BOOL)display;
- (void)setImageRows:(int)rows columns:(int)columns;
- (void)setImageIndex:(int)index;
- (void)setIndex:(int)index;
- (void)sendSyncMessage:(int)message;
- (void)adjustSlider;
- (void)display;
@end
@implementation ViewerController
- (ViewerController*)imageView { return self; }
- (ViewerController*)seriesView { return self; }
- (ViewerController*)window { return self; }
- (ViewerController*)screen { return self; }
- (BOOL)checkFrameSize { return self.matrixVisible; }
- (float)scaleValue { return 0.5; }
- (NSRect)visibleFrame { return NSMakeRect(0,0,1200,900); }
- (void)setFrame:(NSRect)frame display:(BOOL)display { self.frame=frame; }
- (void)setImageRows:(int)rows columns:(int)columns { self.imageRows=rows;self.imageColumns=columns; }
- (void)setImageIndex:(int)index { self.curImage=index; }
- (void)setIndex:(int)index { self.curImage=index; }
- (void)sendSyncMessage:(int)message {}
- (void)adjustSlider {}
- (void)display { self.displayed=YES; }
@end
@interface Converter : NSObject
@property int failureMode;
@property(retain) NSMutableArray *previewImages, *annotatedPreviewImages;
- (NSString*)_createDicomImageWithViewer:(ViewerController*)viewer toDestinationPath:(NSString*)path asColorPrint:(BOOL)color withAnnotations:(BOOL)annotations;
@end
@implementation Converter
- (NSString*)_createDicomImageWithViewer:(ViewerController*)viewer toDestinationPath:(NSString*)path asColorPrint:(BOOL)color withAnnotations:(BOOL)annotations {
 if(viewer.curImage==1) {
  if(self.failureMode==1)return nil;
  if(self.failureMode==2)return @"";
  if(self.failureMode==3)[NSException raise:@"QA" format:@"synthetic render failure"];
 }
 NSString *file=[path stringByAppendingPathComponent:[NSString stringWithFormat:@"%d.dcm",viewer.curImage]];
 [@"synthetic bytes" writeToFile:file atomically:YES encoding:NSUTF8StringEncoding error:NULL];return file;
}
METHOD
@end
#define check(v) NSCAssert((v),@"failed: %s",#v)
int main(int argc,char **argv) { @autoreleasepool {
 NSString *root=[NSString stringWithUTF8String:argv[1]];
 NSString *suite=[@"horos.qa.print." stringByAppendingString:NSUUID.UUID.UUIDString];
 qaDefaults=[[NSUserDefaultsClass alloc] initWithSuiteName:suite];
 for(int initial=0;initial<2;initial++) for(int failure=0;failure<4;failure++) {
  constrainFlag=magneticFlag=screenFlag=FULL32BITPIPELINE=initial;
  [qaDefaults setBool:initial forKey:@"allowSmartCropping"];[qaDefaults setFloat:12 forKey:@"FONTSIZE"];
  [qaDefaults setBool:YES forKey:@"printAt100%Minimum"];[qaDefaults setInteger:4096 forKey:@"MAXWindowSize"];
  ViewerController *viewer=[ViewerController new];viewer.curImage=7;viewer.imageRows=2;viewer.imageColumns=3;viewer.magnetic=YES;viewer.matrixVisible=YES;viewer.frame=NSMakeRect(30,40,400,300);
  Converter *converter=[Converter new];converter.failureMode=failure;
  NSString *dir=[root stringByAppendingPathComponent:[NSString stringWithFormat:@"%d-%d",initial,failure]];check([NSFileManager.defaultManager createDirectoryAtPath:dir withIntermediateDirectories:YES attributes:nil error:NULL]);
  NSArray *files=[converter dicomFileListForViewer:viewer destinationPath:dir options:@{@"rows":@2,@"columns":@3} fileList:@[@0,@1,@2] asColorPrint:NO withAnnotations:NO];
  check(files.count==(failure?0:3));check([[NSFileManager.defaultManager contentsOfDirectoryAtPath:dir error:NULL] count]==files.count);
  check(viewer.curImage==7 && viewer.imageRows==2 && viewer.imageColumns==3 && viewer.magnetic && viewer.matrixVisible && viewer.displayed);
  check(NSEqualRects(viewer.frame,NSMakeRect(30,40,400,300)));
  check(FULL32BITPIPELINE==initial && constrainFlag==initial && magneticFlag==initial && screenFlag==initial);
  check([qaDefaults boolForKey:@"allowSmartCropping"]==initial && [qaDefaults floatForKey:@"FONTSIZE"]==12);
 }
 [qaDefaults removePersistentDomainForName:suite];
 NSLog(@"PASS: success/nil/empty/exception restore index, layout, window, flags and preferences; failures discard all partial files");
} }
'''.replace('METHOD',method).replace('NSUserDefaultsClass','NSClassFromString(@"NSUserDefaults")')
with tempfile.TemporaryDirectory(prefix='horos-print-restore-') as directory:
 p=Path(directory);(p/'test.m').write_text(program)
 subprocess.run(['xcrun','clang','-fsanitize=address','-framework','Foundation',str(p/'test.m'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test'),str(p)],check=True)
