#!/usr/bin/env python3
"""Execute the host's real loading methods under deterministic replacement/cancel races.

Only pixels, catalog records and UI callbacks are stubs. NSThread, the operation
queue and main-thread delivery are real. --source accepts a previous revision.
The barriers hold an in-flight decode; they never alter the production methods.
"""
import argparse
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--source', type=Path, default=ROOT/'Horos/Sources/ViewerController.m')
parser.add_argument('--case')
args = parser.parse_args()
source = args.source.read_bytes().decode('latin1')


def method(signature):
    at = source.index(signature)
    end = re.search(r'\n[-+]\s*\(', source[at+len(signature):])
    assert end, signature
    return source[at:at+len(signature)+end.start()]


methods = '\n'.join(method(s) for s in (
    '- (void) startLoadImageThread',
    '- (void) finishLoadImageData:',
    '+ (void) loadImageData:',
))
stub = r'''
#import <Foundation/Foundation.h>
#include <assert.h>
#define N2LogException(e) NSLog(@"%@", e)
NSString * const OsirixViewerControllerDidLoadImagesNotification = @"DidLoad";

@interface NSThread (Status)
@property double progress;
@property(copy) NSString *status;
@end
@implementation NSThread (Status)
- (void)setProgress:(double)x {}
- (double)progress { return 0; }
- (void)setStatus:(NSString *)s {}
- (NSString *)status { return @""; }
@end

@interface Probe : NSObject {
@public NSCondition *gate;
    BOOL released, compressed;
    NSUInteger entered, decoded, wrongOrigin;
    NSThread *origin;
}
- (void)decodeFrom:(NSThread *)thread;
- (void)waitForEntry;
- (void)resume;
- (void)park;
@end
@implementation Probe
- (id)init { if ((self = [super init])) gate = [NSCondition new]; return self; }
- (void)decodeFrom:(NSThread *)thread {
    [gate lock];
    if (thread && origin && thread != origin) ++wrongOrigin;
    ++entered; [gate broadcast];
    while (!released) [gate wait];
    ++decoded; [gate unlock];
}
- (void)waitForEntry {
    [gate lock]; NSDate *deadline = [NSDate dateWithTimeIntervalSinceNow:5];
    while (!entered && [gate waitUntilDate:deadline]) {}
    assert(entered); [gate unlock];
}
- (void)resume { [gate lock]; released = YES; [gate broadcast]; [gate unlock]; }
- (void)park { @autoreleasepool { [self decodeFrom:nil]; } }
@end

@interface DCMPix : NSObject
@property(retain) Probe *probe;
@property BOOL shutterEnabled;
- (NSString *)srcFile;
- (NSString *)modalityString;
- (void)CheckLoad;
- (void)CheckLoadFromThread:(NSThread *)thread;
- (void)setMaxValueOfSeries:(float)x;
- (void)setMinValueOfSeries:(float)x;
- (long)pwidth;
- (long)pheight;
@end
@implementation DCMPix
- (NSString *)srcFile { return self.probe->compressed ? @"compressed" : @"plain"; }
- (NSString *)modalityString { return @"CT"; }
- (void)CheckLoad { [self.probe decodeFrom:nil]; }
- (void)CheckLoadFromThread:(NSThread *)thread {
    if (!thread.isExecuting || thread.isCancelled || thread.isFinished) return;
    [self.probe decodeFrom:thread];
}
- (void)setMaxValueOfSeries:(float)x {}
- (void)setMinValueOfSeries:(float)x {}
- (long)pwidth { return 32; }
- (long)pheight { return 32; }
@end

@interface DicomFile : NSObject
+ (void)isDICOMFile:(NSString *)path compressed:(BOOL *)out;
@end
@implementation DicomFile
+ (void)isDICOMFile:(NSString *)path compressed:(BOOL *)out { *out = [path isEqual:@"compressed"]; }
@end
@interface BrowserController : NSObject
+ (BOOL)isItCD:(NSString *)path;
@end
@implementation BrowserController
+ (BOOL)isItCD:(NSString *)path { return NO; }
@end

@interface ViewStub : NSObject
@property(getter=isVisible) BOOL visible;
- (void)updatePresentationStateFromSeries;
- (void)setStartWLWW;
@end
@implementation ViewStub
- (void)updatePresentationStateFromSeries {}
- (void)setStartWLWW {}
@end

@interface ViewerController : NSObject {
@public NSThread *loadingThread;
    BOOL requestLoadingCancel, windowWillClose, enableSubtraction, subCtrlMinMaxComputed;
    int originalOrientation, maxMovieIndex;
    NSMutableArray *pixList[4], *fileList[4];
    NSData *volumeData[4];
    ViewStub *imageView;
    NSUInteger orientations, backgroundOrientations, backgroundWindows;
}
@property(retain) ViewStub *window;
- (void)startLoadImageThread;
- (void)finishLoadImageData:(NSDictionary *)dict;
+ (void)loadImageData:(NSDictionary *)dict;
- (void)setWindowTitle:(id)sender;
- (void)enableSubtraction;
- (void)convertPETtoSUV;
- (void)setShutterOnOffButton:(id)sender;
- (void)computeIntervalAsync;
- (double)computeOriginalOrientation;
@end
@implementation ViewerController
- (id)init {
    if ((self = [super init])) {
        imageView = [ViewStub new]; imageView.visible = YES;
        maxMovieIndex = 1;
    }
    return self;
}
- (ViewStub *)window { if (!NSThread.isMainThread) ++backgroundWindows; return imageView; }
- (void)setWindow:(ViewStub *)view {}
- (void)setWindowTitle:(id)sender { assert(NSThread.isMainThread); }
- (void)enableSubtraction { assert(NSThread.isMainThread); }
- (void)convertPETtoSUV { assert(NSThread.isMainThread); }
- (void)setShutterOnOffButton:(id)sender { assert(NSThread.isMainThread); }
- (void)computeIntervalAsync { assert(NSThread.isMainThread); }
- (double)computeOriginalOrientation {
    ++orientations; if (!NSThread.isMainThread) ++backgroundOrientations; return 0;
}
'''
driver = r'''
@end

static NSMutableArray *pixels(Probe *probe, NSUInteger count) {
    NSMutableArray *array = [NSMutableArray array];
    for (NSUInteger i=0; i<count; ++i) {
        DCMPix *p = [DCMPix new]; p.probe = probe;
        [array addObject:p]; [p release];
    }
    return array;
}
static NSDictionary *job(ViewerController *viewer, NSArray *arrays) {
    return @{ @"viewerController":viewer, @"pixListArray":arrays,
        @"volumeDataArray":@[[NSData data]], @"fileListArray":@[] };
}
static NSDictionary *completion(ViewerController *viewer, NSArray *arrays, NSThread *thread) {
    NSMutableDictionary *dict = [[job(viewer, arrays) mutableCopy] autorelease];
    dict[@"loadThread"] = thread;
    return dict;
}
static void waitFinished(NSThread *thread) {
    NSDate *until = [NSDate dateWithTimeIntervalSinceNow:5];
    while (!thread.isFinished && until.timeIntervalSinceNow > 0) [NSThread sleepForTimeInterval:.005];
    assert(thread.isFinished);
}
static void drainMain(void) {
    [[NSRunLoop currentRunLoop] runUntilDate:[NSDate dateWithTimeIntervalSinceNow:.05]];
}
static void check(BOOL value, const char *message) {
    if (!value) { fprintf(stderr, "FAIL: %s\n", message); exit(1); }
}
static int notices;

static void staleCase(NSString *name) {
    ViewerController *v = [ViewerController new]; Probe *probe = [Probe new];
    NSMutableArray *first = pixels(probe, 2), *second = pixels(probe, 2);
    NSThread *old = [NSThread new], *current = [NSThread new];
    v->loadingThread = [current retain]; v->pixList[0] = [second retain];
    NSArray *oldArrays = @[first];
    if ([name isEqual:@"restart-same-pixels"]) oldArrays = @[second];
    if ([name isEqual:@"changed-timepoint"]) {
        v->maxMovieIndex = 2; v->pixList[1] = [second retain];
        oldArrays = @[second, first]; old = current;
    }
    if ([name isEqual:@"closed"]) {
        oldArrays = @[second]; old = current; v->windowWillClose = YES;
    }
    if ([name isEqual:@"cancelled"]) {
        oldArrays = @[second]; old = current; [old cancel];
    }
    [v finishLoadImageData:completion(v, oldArrays, old)];
    check(v->loadingThread == current, "obsolete completion detached the current load");
    if (![name isEqual:@"cancelled"]) check(!current.isCancelled, "obsolete completion cancelled the replacement load");
    check(notices == 0, "obsolete completion announced a loaded volume");
    check(v->orientations == 0, "obsolete completion recomputed viewer geometry");
}

static void workerCase(BOOL compressed) {
    ViewerController *v = [ViewerController new];
    Probe *a = [Probe new]; a->compressed = compressed;
    NSArray *arrays = @[pixels(a, 64), pixels(a, 64)];
    v->maxMovieIndex = 2;
    v->pixList[0] = [arrays[0] retain]; v->pixList[1] = [arrays[1] retain];
    NSThread *old = [[NSThread alloc] initWithTarget:ViewerController.class selector:@selector(loadImageData:) object:job(v, arrays)];
    a->origin = old; v->loadingThread = [old retain];
    [old start]; [a waitForEntry];
    [old cancel];
    Probe *b = [Probe new];
    NSThread *replacement = [[NSThread alloc] initWithTarget:b selector:@selector(park) object:nil];
    v->loadingThread = [replacement retain];
    v->pixList[0] = [pixels(b,2) retain]; v->pixList[1] = [pixels(b,2) retain];
    [replacement start]; [b waitForEntry];
    [a resume]; waitFinished(old); drainMain();
    check(v->loadingThread == replacement && !replacement.isCancelled,
          "cancelled worker disturbed its replacement");
    check(notices == 0 && v->orientations == 0, "cancelled worker delivered UI/geometry effects");
    check(a->wrongOrigin == 0, "compressed decode borrowed the replacement's cancellation thread");
    check(a->decoded < 128, "cancelled worker decoded the entire old volume");
    if (!compressed) check(a->decoded == 1, "sequential cancellation crossed a slice/timepoint boundary");
    check(v->backgroundWindows == 0, "loader accessed the AppKit window on its worker");
    [replacement cancel]; [b resume]; waitFinished(replacement);
}

static void validCase(BOOL compressed) {
    ViewerController *v = [ViewerController new]; Probe *p = [Probe new];
    p->compressed = compressed; [p resume];
    v->pixList[0] = [pixels(p, 8) retain]; v->fileList[0] = [NSMutableArray new];
    v->volumeData[0] = [NSData new];
    [v startLoadImageThread]; NSThread *thread = [v->loadingThread retain];
    waitFinished(thread); drainMain();
    check(p->decoded == 8, "valid load did not decode all slices");
    check(notices == 1 && v->loadingThread == nil, "valid load did not finish exactly once");
    check(v->orientations == 1 && v->backgroundOrientations == 0, "geometry did not stay on main thread");
    check(v->backgroundWindows == 0, "loader accessed the AppKit window on its worker");
}

static void reentrantCase(void) {
    ViewerController *v = [ViewerController new]; Probe *p = [Probe new];
    v->pixList[0] = [pixels(p,2) retain];
    NSThread *old = [NSThread new], *replacement = [NSThread new];
    v->loadingThread = [old retain];
    id observer = [NSNotificationCenter.defaultCenter addObserverForName:OsirixViewerControllerDidLoadImagesNotification
        object:v queue:nil usingBlock:^(NSNotification *note) { v->loadingThread = [replacement retain]; }];
    [v finishLoadImageData:completion(v, @[v->pixList[0]], old)];
    check(v->loadingThread == replacement && !replacement.isCancelled,
          "completion cancelled the load started by its notification observer");
    check(notices == 1, "accepted completion did not announce exactly once");
    [NSNotificationCenter.defaultCenter removeObserver:observer];
}

int main(int argc, const char **argv) { @autoreleasepool {
    assert(argc == 2 && NSThread.isMainThread);
    NSString *name = @(argv[1]);
    id observer = [NSNotificationCenter.defaultCenter addObserverForName:OsirixViewerControllerDidLoadImagesNotification
        object:nil queue:nil usingBlock:^(NSNotification *note) { assert(NSThread.isMainThread); ++notices; }];
    if ([name isEqual:@"worker-plain"]) workerCase(NO);
    else if ([name isEqual:@"worker-compressed"]) workerCase(YES);
    else if ([name isEqual:@"valid-plain"]) validCase(NO);
    else if ([name isEqual:@"valid-compressed"]) validCase(YES);
    else if ([name isEqual:@"reentrant"]) reentrantCase();
    else staleCase(name);
    [NSNotificationCenter.defaultCenter removeObserver:observer];
    printf("PASS: %s\n", argv[1]);
} return 0; }
'''

cases = ['stale-series', 'restart-same-pixels', 'changed-timepoint', 'closed',
         'cancelled', 'worker-plain', 'worker-compressed', 'valid-plain',
         'valid-compressed', 'reentrant']
if args.case:
    assert args.case in cases
    cases = [args.case]
with tempfile.TemporaryDirectory(prefix='horos-loader-lifetime-') as tmp:
    folder = Path(tmp)
    (folder/'Check.m').write_text(stub+methods+driver)
    subprocess.run(['xcrun','clang','-fno-objc-arc','-fblocks','-O1','-g',
                    '-framework','Foundation',str(folder/'Check.m'),'-o',str(folder/'check')], check=True)
    failed = []
    for case in cases:
        result = subprocess.run([str(folder/'check'), case], timeout=20)
        if result.returncode:
            failed.append(case)
    if failed:
        raise SystemExit('FAIL: '+', '.join(failed))
print(f'PASS: {len(cases)} host loading lifetime scenarios')
