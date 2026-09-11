#!/usr/bin/env python3
"""#384 A executes the actual BrowserController print methods with synthetic model/pixel adapters.

The database and DCMPix adapters are deliberate doubles; this covers caller
selection/wiring/error paths, not native DICOM decoding or visible UI.
"""
from pathlib import Path
import subprocess
import tempfile
root = Path(__file__).resolve().parents[1]
browser = (root / 'Horos/Sources/BrowserController.m').read_bytes().decode('latin1')
start = browser.index('- (void)printDatabaseSelection:(id)sender\n{')
end = browser.index('- (IBAction)databaseDoublePressed:', start)
methods = browser[start:end]
stubs = r'''
#import <AppKit/AppKit.h>
#import <Quartz/Quartz.h>
#import "HorosPrinting-Swift.h"
#import "HorosBoundedTask.h"
static int alerts = 0, calls = 0, cancelAfter = -1;
static NSMutableArray *loaded;
static NSInteger TestAlert(NSString *title, NSString *message, NSString *button, NSString *a, NSString *b, ...) { alerts++; return NSAlertFirstButtonReturn; }
#define NSRunInformationalAlertPanel TestAlert
@interface NSWindowController (PrintDeclaration)
- (void)print:(id)sender;
@end
@class DicomSeries;
@interface DicomStudy : NSObject
@property(retain) NSSet *series;
@end
@implementation DicomStudy @end
@interface DicomSeries : NSObject
@property(retain) NSNumber *id, *windowWidth, *windowLevel;
@property(copy) NSString *seriesSOPClassUID, *modality, *name;
@property(retain) NSArray *sortedImages;
@end
@implementation DicomSeries @end
@interface DicomImage : NSObject
@property(retain) DicomSeries *series;
@property(copy) NSString *completePathResolved;
@property(retain) NSNumber *numberOfFrames, *frameID;
@end
@implementation DicomImage @end
@interface DCMObject : NSObject
@property(retain) NSData *payload;
+ (id)objectWithContentsOfFile:(NSString *)path decodingPixelData:(BOOL)decode;
- (id)attributeValueWithName:(NSString *)name;
@end
@implementation DCMObject
+ (id)objectWithContentsOfFile:(NSString *)path decodingPixelData:(BOOL)decode {
    DCMObject *object = [[[self alloc] init] autorelease];
    NSData *bytes = [NSData dataWithContentsOfFile:path];
    if (bytes.length > 5) object.payload = [bytes subdataWithRange:NSMakeRange(5, bytes.length-5)];
    return object;
}
- (id)attributeValueWithName:(NSString *)name { return [name isEqual:@"EncapsulatedDocument"] ? self.payload : nil; }
@end
@interface DCMPix : NSObject
@property BOOL notAbleToLoadImage;
@property long pwidth, pheight;
@property float savedWW, savedWL;
@property double pixelRatio;
@property(retain) NSImage *image;
- (id)initWithPath:(NSString *)path :(long)a :(long)b :(id)c :(long)frame :(long)e isBonjour:(BOOL)bonjour imageObj:(id)object;
- (void)CheckLoad;
- (float)calibratedWindowLevelForStoredLevel:(float)level;
- (void)checkImageAvailble:(float)width :(float)level;
@end
@implementation DCMPix
- (id)initWithPath:(NSString *)path :(long)a :(long)b :(id)c :(long)frame :(long)e isBonjour:(BOOL)bonjour imageObj:(id)object {
    if ((self=[super init])) {
        [loaded addObject:@[path.lastPathComponent, @(frame)]];
        self.notAbleToLoadImage = [path.lastPathComponent isEqual:@"missing"];
        self.pwidth=8; self.pheight=12; self.pixelRatio=2; self.savedWW=100; self.savedWL=50;
        unsigned char rgba[8*12*4];
        for (int i=0; i<8*12; i++) { rgba[4*i]=240; rgba[4*i+1]=frame*30; rgba[4*i+2]=17; rgba[4*i+3]=255; }
        NSData *data = [NSData dataWithBytes:rgba length:sizeof(rgba)];
        CGDataProviderRef provider = CGDataProviderCreateWithCFData((CFDataRef)data);
        CGColorSpaceRef space = CGColorSpaceCreateDeviceRGB();
        CGImageRef image = CGImageCreate(8,12,8,32,8*4,space,(CGBitmapInfo)kCGImageAlphaPremultipliedLast,provider,NULL,NO,kCGRenderingIntentDefault);
        self.image = [[[NSImage alloc] initWithCGImage:image size:NSMakeSize(8,12)] autorelease];
        CGImageRelease(image); CGColorSpaceRelease(space); CGDataProviderRelease(provider);
    } return self;
}
- (void)CheckLoad {}
// This selection test uses MONOCHROME2; native polarity is covered separately.
- (float)calibratedWindowLevelForStoredLevel:(float)level { return level; }
- (void)checkImageAvailble:(float)width :(float)level { NSCAssert(width == 400 && level == 40, @"stored WL/WW was lost"); }
@end
@interface Wait : NSObject
@property(retain) NSProgressIndicator *indicator;
- (id)initWithString:(NSString *)message :(BOOL)session;
- (void)setCancel:(BOOL)value;
- (NSProgressIndicator *)progress;
- (void)showWindow:(id)sender;
- (void)incrementBy:(double)value;
- (BOOL)pollCancellation;
- (void)close;
@end
@implementation Wait
- (id)initWithString:(NSString *)message :(BOOL)session { if ((self=[super init])) self.indicator=[[[NSProgressIndicator alloc] init] autorelease]; return self; }
- (void)setCancel:(BOOL)value {}
- (NSProgressIndicator *)progress { return self.indicator; }
- (void)showWindow:(id)sender {}
- (void)incrementBy:(double)value {}
- (BOOL)pollCancellation { return cancelAfter >= 0 && self.indicator.doubleValue >= cancelAfter; }
- (void)close {}
@end
@interface BrowserController : NSWindowController {
@public NSMatrix *oMatrix; NSArray *matrixViewArray;
}
@property(retain) NSArray *selection;
- (NSArray *)databaseSelection;
- (void)printDatabaseSelection:(id)sender;
- (void)printDatabaseSpool:(id)object;
@end
@implementation BrowserController
- (NSArray *)databaseSelection { return self.selection; }
'''
tail = r'''
@end
@interface ProbeBrowser : BrowserController
@property(retain) NSArray *printed;
@end
@implementation ProbeBrowser
- (void)printDatabaseSpool:(id)object {
    HorosPrintSpool *spool=object;
    NSCAssert(spool.success && !spool.cancelled, @"partial job reached printing");
    NSMutableArray *pages=[NSMutableArray array];
    for (HorosPrintPage *page in spool.pages) [pages addObject:[NSData dataWithContentsOfURL:page.url]];
    self.printed=pages; calls++;
}
@end
#define check(x) do { if (!(x)) { fprintf(stderr,"FAIL line %d: %s\n",__LINE__,#x); return 1; } } while (0)
static DicomImage *image(DicomSeries *series, NSString *path, int frame, int frames) {
    DicomImage *item=[[[DicomImage alloc] init] autorelease]; item.series=series; item.completePathResolved=path;
    item.frameID=@(frame); item.numberOfFrames=@(frames); return item;
}
static DicomSeries *series(int identifier) {
    DicomSeries *item=[[[DicomSeries alloc] init] autorelease]; item.id=@(identifier);
    item.seriesSOPClassUID=HorosPrintSelection.ctImageStorage; item.modality=@"CT"; item.name=@"fixture";
    item.windowWidth=@400; item.windowLevel=@40; return item;
}
static NSSet *spools(void) {
    NSMutableSet *paths=[NSMutableSet set];
    for (NSString *name in [NSFileManager.defaultManager contentsOfDirectoryAtPath:NSTemporaryDirectory() error:NULL])
        if ([name hasPrefix:HorosPrintSelection.spoolDirectoryPrefix]) [paths addObject:name];
    return paths;
}
int main(int argc, char **argv) { @autoreleasepool {
    [NSApplication sharedApplication];
    loaded=[NSMutableArray array];
    NSSet *before=[[spools() copy] autorelease];
    NSWindow *window=[[[NSWindow alloc] initWithContentRect:NSMakeRect(0,0,300,300) styleMask:NSWindowStyleMaskBorderless backing:NSBackingStoreBuffered defer:NO] autorelease];
    window.releasedWhenClosed=NO;
    ProbeBrowser *browser=[[[ProbeBrowser alloc] initWithWindow:window] autorelease];
    DicomSeries *first=series(1), *multi=series(2), *archive=series(3);
    first.sortedImages=@[image(first,@"first-0",0,1),image(first,@"first-1",0,1),image(first,@"first-2",0,1)];
    multi.sortedImages=@[image(multi,@"multi",0,4)];
    archive.name=@"OsiriX ROI"; archive.sortedImages=@[image(archive,@"archive",0,1)];
    DicomStudy *study=[[[DicomStudy alloc] init] autorelease]; study.series=[NSSet setWithArray:@[archive,multi,first]];
    browser.selection=@[study,first.sortedImages[1]];
    [browser printDatabaseSelection:nil];
    check(calls == 1 && alerts == 0 && browser.printed.count == 7 && loaded.count == 7);
    check(([loaded isEqual:@[@[@"first-0",@0],@[@"first-1",@0],@[@"first-2",@0],@[@"multi",@0],@[@"multi",@1],@[@"multi",@2],@[@"multi",@3]]]));
    PDFDocument *page=[[[PDFDocument alloc] initWithData:browser.printed[0]] autorelease];
    check(NSEqualRects([page pageAtIndex:0].boundsForBox:kPDFDisplayBoxMediaBox,NSMakeRect(0,0,8,24)));
    check([spools() isEqual:before]);

    browser->oMatrix=[[[NSMatrix alloc] initWithFrame:NSMakeRect(0,0,100,100) mode:NSListModeMatrix cellClass:NSActionCell.class numberOfRows:3 numberOfColumns:1] autorelease];
    browser->matrixViewArray=first.sortedImages;
    for (NSInteger i=0; i<3; i++) { NSCell *cell=[browser->oMatrix cellAtRow:i column:0]; cell.tag=i; cell.enabled=YES; }
    [browser->oMatrix selectCellAtRow:1 column:0];
    window.contentView=browser->oMatrix;
    [window makeFirstResponder:browser->oMatrix];
    [loaded removeAllObjects];
    [browser printDatabaseSelection:nil]; // File > Print with thumbnail focus.
    check(calls == 2 && browser.printed.count == 1 && ([loaded isEqual:@[@[@"first-1",@0]]]));
    window.contentView=[[[NSView alloc] initWithFrame:NSMakeRect(0,0,100,100)] autorelease];
    [window makeFirstResponder:nil];

    cancelAfter=1; [loaded removeAllObjects];
    [browser printDatabaseSelection:nil];
    check(calls == 2 && alerts == 0 && loaded.count == 1 && [spools() isEqual:before]);
    cancelAfter=-1;
    DicomSeries *bad=series(9); bad.sortedImages=@[image(bad,@"first",0,1),image(bad,@"missing",0,1)];
    browser.selection=@[bad];
    [browser printDatabaseSelection:nil];
    check(calls == 2 && alerts == 1 && [spools() isEqual:before]);

    // Fake DICOM envelope makes passing the whole file as PDF fail: the caller
    // must ask DCMObject for EncapsulatedDocument instead.
    NSString *folder=[NSString stringWithUTF8String:argv[1]];
    NSString *path=[folder stringByAppendingPathComponent:@"encapsulated.dcm"];
    NSMutableData *bytes=[NSMutableData dataWithBytes:"DICOM" length:5];
    PDFDocument *three=[[[PDFDocument alloc] init] autorelease];
    PDFDocument *one=[[[PDFDocument alloc] initWithData:browser.printed[0]] autorelease];
    for (int i=0; i<3; i++) [three insertPage:[[[one pageAtIndex:0] copy] autorelease] atIndex:i];
    [bytes appendData:three.dataRepresentation];
    [bytes writeToFile:path atomically:YES];
    DicomSeries *report=series(10); report.seriesSOPClassUID=HorosPrintSelection.encapsulatedPDF; report.modality=@"DOC";
    report.sortedImages=@[image(report,path,0,3),image(report,path,1,3),image(report,path,2,3)]; browser.selection=@[report];
    [browser printDatabaseSelection:nil];
    check(calls == 3 && alerts == 1 && browser.printed.count == 3);
    browser->matrixViewArray=report.sortedImages;
    [browser->oMatrix selectCellAtRow:1 column:0];
    [browser printDatabaseSelection:browser->oMatrix];
    check(calls == 4 && alerts == 1 && browser.printed.count == 1);
    check([[NSData dataWithContentsOfFile:path] isEqual:bytes]);
    check([spools() isEqual:before]);
    puts("PASS: actual browser methods select full ordered series/frames and focused matrix subset; dedup, WL/WW, pixel aspect, cancellation, failure, encapsulated PDF extraction, temp cleanup");
    return 0;
}}
'''
# Dot syntax cannot call a parameterized method.
tail = tail.replace('[page pageAtIndex:0].boundsForBox:kPDFDisplayBoxMediaBox', '[[page pageAtIndex:0] boundsForBox:kPDFDisplayBoxMediaBox]')
with tempfile.TemporaryDirectory(prefix='horos-print-384-browser-') as temporary:
    folder=Path(temporary)
    (folder/'Check.m').write_text(stubs+methods+tail)
    subprocess.run(['xcrun','swiftc','-parse-as-library','-emit-library','-emit-objc-header','-emit-objc-header-path',str(folder/'HorosPrinting-Swift.h'),'-module-name','HorosPrinting',str(root/'Horos/Sources/PrintSelection.swift'),'-o',str(folder/'libHorosPrinting.dylib')],check=True,timeout=60)
    subprocess.run(['xcrun','clang','-fblocks','-fmodules','-I',str(folder),'-I',str(root/'Horos/Sources'),'-framework','AppKit','-framework','Quartz','-L',str(folder),'-lHorosPrinting','-Wl,-rpath,'+str(folder),str(folder/'Check.m'),'-o',str(folder/'check')],check=True,timeout=60)
    subprocess.run([str(folder/'check'),str(folder)],check=True,timeout=30)
