#!/usr/bin/env python3
"""Run the adapted external plugin conversion method with controlled host failures.

Pass the locally adapted DCMJpegImportFilter.m; no external source is vendored.
"""
from pathlib import Path
import subprocess,sys,tempfile
if len(sys.argv) < 2:
    print('skipped: needs the locally adapted DCMJpegImportFilter.m: SOURCE', file=sys.stderr)
    raise SystemExit(2)
s=Path(sys.argv[1]).read_text();a=s.index('- (NSString*) convertImageToDICOM:');b=s.index('@end',a);method=s[a:b]
program=r'''
#import <Cocoa/Cocoa.h>
static int mode,writes,imports;
@interface Exporter:NSObject @end
@implementation Exporter
- (void)setSourceFile:(id)x {}
- (long)setPixelNSImage:(NSImage*)im {return mode==1?-1:0;}
- (NSString*)writeDCMFile:(id)x {writes++;return mode==2?nil:@"created.dcm";}
@end
@interface BrowserController:NSObject @end
@implementation BrowserController
+ (id)currentBrowser {return nil;}
+ (void)addFiles:(id)a toContext:(id)b toDatabase:(id)c onlyDICOM:(BOOL)d notifyAddedFiles:(BOOL)e parseExistingObject:(BOOL)f dbFolder:(id)g generatedByOsiriX:(BOOL)h {imports++;}
@end
@interface TestPlugin:NSObject {id e;NSMutableArray *conversionFailures;}
- (NSString*)convertImageToDICOM:(NSString*)path source:(NSString*)src;
- (NSUInteger)failureCount;
@end
@implementation TestPlugin
- (id)init {if((self=[super init])){e=[Exporter new];conversionFailures=[NSMutableArray new];}return self;}
- (void)dealloc {[e release];[conversionFailures release];[super dealloc];}
- (NSUInteger)failureCount {return conversionFailures.count;}
METHOD
@end
int main(int argc,char **argv){@autoreleasepool{
NSString *dir=[NSString stringWithUTF8String:argv[1]],*good=[dir stringByAppendingPathComponent:@"good.tiff"],*bad=[dir stringByAppendingPathComponent:@"bad.jpg"];
NSBitmapImageRep *r=[[[NSBitmapImageRep alloc] initWithBitmapDataPlanes:NULL pixelsWide:2 pixelsHigh:2 bitsPerSample:8 samplesPerPixel:3 hasAlpha:NO isPlanar:NO colorSpaceName:NSDeviceRGBColorSpace bytesPerRow:6 bitsPerPixel:24] autorelease];memset(r.bitmapData,100,12);[[r TIFFRepresentation] writeToFile:good atomically:YES];[@"invalid jpeg" writeToFile:bad atomically:YES encoding:NSUTF8StringEncoding error:NULL];
TestPlugin *p=[[[TestPlugin alloc] init] autorelease];
if(![p convertImageToDICOM:good source:nil] || writes!=1 || imports!=1 || p.failureCount)return 1;
mode=1;if([p convertImageToDICOM:good source:nil] || writes!=1 || imports!=1 || p.failureCount!=1)return 2;
mode=2;if([p convertImageToDICOM:good source:nil] || writes!=2 || imports!=1 || p.failureCount!=2)return 3;
mode=0;if([p convertImageToDICOM:bad source:nil] || writes!=2 || imports!=1 || p.failureCount!=3)return 4;
puts("PASS: success imports once; rejected pixels, failed write and unreadable image are collected without false import");
}}
'''.replace('METHOD',method)
with tempfile.TemporaryDirectory(prefix='horos-plugin-failure-') as folder:
 p=Path(folder);(p/'test.m').write_text(program)
 subprocess.run(['xcrun','clang','-Wno-objc-method-access','-fsanitize=address',str(p/'test.m'),'-framework','Cocoa','-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test'),folder],check=True)
