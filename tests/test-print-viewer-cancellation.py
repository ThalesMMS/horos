#!/usr/bin/env python3
"""#384 A executes the legacy viewer's real post-preparation dispatch block.

Image capture and the print panel are doubles. The production decision that
submits a prepared prefix, discards its spool, and restores windows is compiled
unchanged, for a cancelled preparation and for a failed one: a page that could
not be written must not reach a printer as a blank cell. --source permits
proving the regression against an earlier source.
"""
import argparse
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--source', type=Path, default=root/'Horos/Sources/ViewerController.m')
args = parser.parse_args()
source = args.source.read_bytes().decode('latin1')
method = source[source.index('-(IBAction) endPrint:(id) sender'):source.index('- (IBAction) printSlider:')]
start = method.rindex('        [self adjustSlider];') + len('        [self adjustSlider];')
end = method.rindex('    }\n    else\n        [self restoreWindowsAfterPrint];')
dispatch = method[start:end]

code = r'''
#import <Foundation/Foundation.h>
static int operations, submittedFiles, restored, discarded, reported;
static NSString *spoolToDiscard, *jobTitle;
@interface ProbeWait : NSObject
@property BOOL cancelled;
- (BOOL)aborted;
- (void)close;
@end
@implementation ProbeWait
- (BOOL)aborted { return self.cancelled; }
- (void)close {}
@end
@interface ProbePrintInfo : NSObject
+ (id)sharedPrintInfo;
@end
@implementation ProbePrintInfo
+ (id)sharedPrintInfo { return nil; }
@end
@interface printView : NSObject
- (id)initWithViewer:(id)viewer settings:(id)settings files:(NSArray *)files printInfo:(id)info;
@end
@implementation printView
- (id)initWithViewer:(id)viewer settings:(id)settings files:(NSArray *)files printInfo:(id)info {
    if ((self = [super init])) submittedFiles = (int)files.count;
    return self;
}
@end
@interface ProbePrintOperation : NSObject
+ (id)printOperationWithView:(id)view;
- (void)setCanSpawnSeparateThread:(BOOL)value;
- (void)setJobTitle:(NSString *)title;
- (void)runOperationModalForWindow:(id)window delegate:(id)delegate didRunSelector:(SEL)selector contextInfo:(void *)context;
@end
@implementation ProbePrintOperation
+ (id)printOperationWithView:(id)view { operations++; return [[[self alloc] init] autorelease]; }
- (void)setCanSpawnSeparateThread:(BOOL)value {}
- (void)setJobTitle:(NSString *)title { jobTitle = [title copy]; }
- (void)runOperationModalForWindow:(id)window delegate:(id)delegate didRunSelector:(SEL)selector contextInfo:(void *)context {}
@end
#define NSPrintInfo ProbePrintInfo
#define NSPrintOperation ProbePrintOperation
@interface Viewer : NSObject
- (void)finish:(ProbeWait *)splash files:(NSArray *)files folder:(NSString *)tmpFolder failed:(BOOL)preparationFailed;
- (id)window;
- (void)restoreWindowsAfterPrint;
- (void)discardPrintSpoolDirectory;
- (void)presentPrintPreparationFailure;
- (void)printOperationDidRun:(id)operation success:(BOOL)success contextInfo:(void *)context;
@end
@implementation Viewer
- (id)window { return nil; }
- (void)restoreWindowsAfterPrint { restored++; }
- (void)discardPrintSpoolDirectory { [NSFileManager.defaultManager removeItemAtPath:spoolToDiscard error:NULL]; discarded++; }
- (void)presentPrintPreparationFailure { reported++; }
- (void)printOperationDidRun:(id)operation success:(BOOL)success contextInfo:(void *)context {}
- (void)finish:(ProbeWait *)splash files:(NSArray *)files folder:(NSString *)tmpFolder failed:(BOOL)preparationFailed {
    NSDictionary *settings = @{};
    spoolToDiscard = tmpFolder;
''' + dispatch + r'''
}
@end
int main(void) { @autoreleasepool {
    Viewer *viewer = [[[Viewer alloc] init] autorelease];
    for (int failed = 0; failed <= 1; failed++)
    for (int cancel = 1; cancel >= 0; cancel--) for (int scenario = 0; scenario <= 3; scenario++) {
        int count = (scenario + 1) % 4;
        NSString *folder = [NSTemporaryDirectory() stringByAppendingPathComponent:NSUUID.UUID.UUIDString];
        NSFileManager *fm = NSFileManager.defaultManager;
        NSCAssert([fm createDirectoryAtPath:folder withIntermediateDirectories:NO attributes:nil error:NULL], @"fixture directory");
        NSMutableArray *files = [NSMutableArray array];
        for (int i = 0; i < count; i++) {
            NSString *path = [folder stringByAppendingPathComponent:[NSString stringWithFormat:@"%d", i]];
            NSCAssert([[@"synthetic prepared image" dataUsingEncoding:NSUTF8StringEncoding] writeToFile:path atomically:YES], @"prepared fixture");
            [files addObject:path];
        }
        ProbeWait *wait = [[ProbeWait alloc] init]; // production tail autoreleases it
        wait.cancelled = cancel;
        operations = submittedFiles = restored = discarded = reported = 0;
        jobTitle = nil;
        [viewer finish:wait files:files folder:folder failed:failed];
        BOOL dispatchExpected = !cancel && !failed && count > 0;
        BOOL passed = operations == dispatchExpected && submittedFiles == (dispatchExpected ? count : 0)
            && restored == !dispatchExpected && discarded == !dispatchExpected
            && [fm fileExistsAtPath:folder] == dispatchExpected
            && reported == (!dispatchExpected && failed)
            && (!dispatchExpected || [jobTitle isEqualToString:@"Horos"]);
        [fm removeItemAtPath:folder error:NULL];
        if (!passed) {
            fprintf(stderr, "FAIL: cancel=%d failed=%d prepared=%d operations=%d submitted=%d restored=%d discarded=%d reported=%d title=%s\n",
                    cancel, failed, count, operations, submittedFiles, restored, discarded, reported, jobTitle.UTF8String);
            return 1;
        }
    }
    puts("PASS: real viewer dispatch refuses cancelled and failed prefixes (0..3 images), discards the spool, "
         "reports a failure and restores windows; a complete job submits under a job title that is not the window's");
    return 0;
}}
'''
with tempfile.TemporaryDirectory(prefix='horos-print-viewer-cancel-') as temporary:
    folder = Path(temporary)
    (folder/'Check.m').write_text(code)
    subprocess.run(['xcrun','clang','-framework','Foundation',str(folder/'Check.m'),'-o',str(folder/'check')],check=True,timeout=30)
    subprocess.run([str(folder/'check')],check=True,timeout=10)
