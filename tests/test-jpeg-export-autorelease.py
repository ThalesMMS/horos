#!/usr/bin/env python3
"""Execute the database export method with tracked image lifetimes and real JPEG/TIFF encoding."""
from pathlib import Path
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
source = (subprocess.check_output(['git', 'show', sys.argv[1] + ':Horos/Sources/BrowserController.m'])
          if len(sys.argv) > 1 else (root / 'Horos/Sources/BrowserController.m').read_bytes()).decode('latin1')
a = source.index('- (void) exportImageAs:(NSString*) format sender:(id) sender')
b = source.index('- (void)exportJPEG:', a)
method = source[a:b].replace('[NSOpenPanel openPanel]', '[TestPanel openPanel]')
program = r'''
#import <Cocoa/Cocoa.h>
// The exporter now names each series through this helper, which is a static
// function in a header of its own; compiling the real one keeps the harness
// exercising the real naming rather than a stand-in.
#import "HorosRasterSeriesFolder.h"
static NSString *output;
static NSUInteger liveImages, peakImages, encodedImages, cancelAfter;
@interface TrackedImage : NSImage @end
@implementation TrackedImage
- (id)init { if((self=[super initWithSize:NSMakeSize(64,64)])) {
 liveImages++;peakImages=MAX(peakImages,liveImages);
 NSBitmapImageRep *rep=[[[NSBitmapImageRep alloc] initWithBitmapDataPlanes:NULL pixelsWide:64 pixelsHigh:64 bitsPerSample:8 samplesPerPixel:3 hasAlpha:NO isPlanar:NO colorSpaceName:NSDeviceRGBColorSpace bytesPerRow:192 bitsPerPixel:24] autorelease];
 memset(rep.bitmapData,100,64*192);[self addRepresentation:rep];
 } return self; }
- (void)dealloc {liveImages--;[super dealloc];}
@end
@interface TestPanel : NSObject @end
@implementation TestPanel
+ (id)openPanel {return [[[self alloc] init] autorelease];}
- (void)setCanChooseDirectories:(BOOL)x {} - (void)setCanChooseFiles:(BOOL)x {}
- (void)setAllowsMultipleSelection:(BOOL)x {} - (void)setCanCreateDirectories:(BOOL)x {}
- (void)setMessage:(id)x {} - (void)setPrompt:(id)x {} - (void)setTitle:(id)x {}
- (NSInteger)runModalForDirectory:(id)a file:(id)b types:(id)c {return NSFileHandlingPanelOKButton;}
- (NSArray*)filenames {return @[output];}
@end
@interface Wait : NSObject @end
@implementation Wait
- (id)initWithString:(id)s :(BOOL)b {return [super init];}
- (void)setCancel:(BOOL)b {} - (void)showWindow:(id)x {} - (id)progress {return self;}
- (void)setMaxValue:(double)x {} - (void)incrementBy:(double)x {} - (BOOL)aborted {return cancelAfter && encodedImages>=cancelAfter;}
- (void)close {}
@end
@interface DCMPix : NSObject @end
@implementation DCMPix
- (id)initWithPath:(id)p :(int)a :(int)b :(id)c :(int)d :(int)e isBonjour:(BOOL)f imageObj:(id)g {return [super init];}
- (void)checkImageAvailble:(float)a :(float)b {} - (float)savedWW {return 256;} - (float)savedWL {return 128;}
- (NSImage*)image {encodedImages++;return [[[TrackedImage alloc] init] autorelease];}
@end
@interface BrowserController : NSObject {id oMatrix;id _database;}
- (void)exportImageAs:(NSString*)format sender:(id)sender;
@end
@implementation BrowserController
- (id)window {return nil;}
+ (id)replaceNotAdmitted:(id)x {return x;}
- (NSMutableArray*)filesForDatabaseOutlineSelection:(NSMutableArray*)images {
 NSMutableArray *paths=[NSMutableArray array];
 for(int i=0;i<64;i++) {
 [images addObject:@{@"instanceNumber":@(i/2+1),@"frameID":@0,@"completePathResolved":@"synthetic",
 @"series":@{@"name":@"Series",@"id":@1,@"study":@{@"name":@"Patient",@"studyName":@"Study",@"id":@1}}}];
 [paths addObject:@"synthetic"];
 } return paths;
}
- (NSMutableArray*)filesForDatabaseMatrixSelection:(NSMutableArray*)images {return [self filesForDatabaseOutlineSelection:images];}
METHOD
@end
int main(int argc,char **argv) {
 int status=0;
 @autoreleasepool {
 output=[[NSString stringWithUTF8String:argv[1]] retain];
 cancelAfter=argc>2?atoi(argv[2]):0;
 BrowserController *browser=[[[BrowserController alloc] init] autorelease];
 NSString *format=argc>3?[NSString stringWithUTF8String:argv[3]]:@"jpg";
 [browser exportImageAs:format sender:nil];
 NSUInteger count=0;
 for(NSString *relative in [[NSFileManager defaultManager] enumeratorAtPath:output]) {
 if(![relative.pathExtension isEqualToString:format])continue;
 NSData *data=[NSData dataWithContentsOfFile:[output stringByAppendingPathComponent:relative]];
 NSBitmapImageRep *rep=[NSBitmapImageRep imageRepWithData:data];
 if(rep.pixelsWide!=64 || rep.pixelsHigh!=64)return 2;
 count++;
 }
 printf("encoded=%lu readable=%lu peak-live=%lu live-before-idle=%lu\n",encodedImages,count,peakImages,liveImages);
 NSUInteger expected=cancelAfter?:64;
 if(count!=expected || encodedImages!=expected || peakImages>1 || liveImages!=0)status=1;
 [output release];
 }
 printf("live-after-outer-pool=%lu\n",liveImages);
 if(status || liveImages)return 1;
 puts("PASS: per-image temporaries drain before the next image; JPEG/TIFF outputs and deferred collision renames remain valid");
}
'''.replace('METHOD', method)
with tempfile.TemporaryDirectory(prefix='horos-jpeg-pool-') as folder:
    p = Path(folder)
    (p/'test.m').write_text(program)
    subprocess.run(['xcrun','clang','-Wno-incompatible-pointer-types','-Wno-objc-method-access',
                    '-Wno-deprecated-declarations','-Wno-unused-function','-fsanitize=address',
                    '-I', str(root/'Horos/Sources'), str(p/'test.m'),
                    '-framework','Cocoa','-o',str(p/'test')], check=True)
    subprocess.run([str(p/'test'),str(p/'output')], check=True)
    subprocess.run([str(p/'test'),str(p/'cancelled'), '5'], check=True)

    subprocess.run([str(p/'test'),str(p/'tiff'), '0', 'tif'], check=True)
