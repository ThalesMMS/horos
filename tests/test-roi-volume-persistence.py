#!/usr/bin/env python3
"""Execute #680 controller methods with in-memory viewer/database dependencies.

The registration, aliasing, undo/redo, reslice snapshot, load, and save/merge
implementations are extracted verbatim from ViewerController.m and compiled.
ROI, database, and SR doubles provide storage without loading AppKit, DCMTK, a
private database, or patient data. The SR double writes real NSArchiver bytes
and only indexes their paths when addFilesAtPaths is called, as the host does.
Pixel resampling, DICOM SR encoding, and native event delivery remain app checks.
"""
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
source = (root / 'Horos/Sources/ViewerController.m').read_text(encoding='latin1')
if shutil.which('xcrun') is None:
    print('needs xcrun and the macOS Foundation framework', file=sys.stderr)
    raise SystemExit(2)


def body(signature):
    """Read a definition, not its declaration, preserving its complete body."""
    match = re.search(re.escape(signature) + r'\s*\n\{', source)
    assert match, f'missing implementation: {signature}'
    start = match.start()
    brace = source.index('{', match.start())
    depth = 0
    # These methods have no braces inside string literals; comments and literal
    # dictionaries are balanced. Keep extraction strict if the source changes.
    for end in range(brace, len(source)):
        depth += (source[end] == '{') - (source[end] == '}')
        if depth == 0:
            return source[start:end + 1]
    raise AssertionError(f'unterminated implementation: {signature}')


signatures = [
    '- (NSMutableDictionary *)volumeLengthStateForMovieIndex:(long)movieIndex create:(BOOL)create',
    '- (NSArray<HorosVolumeLengthROI *> *)volumeLengthROIsForMovieIndex:(long)movieIndex',
    '- (void)registerVolumeLengthROI:(HorosVolumeLengthROI *)roi movieIndex:(long)movieIndex anchor:(DicomImage *)anchor',
    '- (void)attachVolumeLengthROI:(HorosVolumeLengthROI *)roi movieIndex:(long)movieIndex',
    '- (void)addVolumeLengthROI:(HorosVolumeLengthROI *)roi',
    '- (void)addVolumeLengthROI:(HorosVolumeLengthROI *)roi movieIndex:(long)movieIndex',
    '- (void)restoreVolumeLengthSnapshot:(NSDictionary *)snapshot movieIndex:(long)movieIndex',
    '- (void)saveVolumeLengthROIs:(long)movieIndex writtenPaths:(NSMutableArray *)paths anchorPaths:(NSDictionary *)anchorPaths',
    '- (id) prepareObjectForUndo:(NSString*) string',
    '- (void) executeUndo:(NSMutableArray*) u',
    '- (IBAction) undo:(id) sender',
    '- (IBAction) redo:(id) sender',
    '- (void) deleteROI: (ROI*) roi',
    '- (void) loadROI:(long) mIndex',
    '- (void) saveROI:(long) mIndex',
    '+ (BOOL) areROIsArraysIdentical: (NSArray*) copy with: (NSArray*) roisArray',
]
methods = '\n\n'.join(body(signature) for signature in signatures)
snapshot_start = source.index('        NSMutableArray *volumeSnapshots = [NSMutableArray arrayWithCapacity:mx];')
snapshot_end = source.index('        ViewerController *reslicedViewer = self;', snapshot_start)
snapshot = source[snapshot_start:snapshot_end]
archive_reader = body('static NSArray *HorosVolumeLengthReadArchive(NSString *path)')

DECLARATIONS = r'''
#import <Foundation/Foundation.h>
#import <objc/runtime.h>
#include <stdio.h>
#include <stdlib.h>

#define MAX4D 500
#define CHECK(condition, message) do { if (!(condition)) { fprintf(stderr, "FAIL: %s (line %d)\n", message, __LINE__); exit(1); } } while(0)
static void N2LogException(NSException *e) { NSLog(@"Probe caught: %@", e.name); }
static void N2LogExceptionWithStackTrace(NSException *e) { N2LogException(e); }
static void NSBeep(void) {}
static NSString * const OsirixAddROINotification = @"add";
static NSString * const OsirixRemoveROINotification = @"remove";
static NSString * const OsirixROIChangeNotification = @"change";
static char HorosVolumeLengthStateKey;
static NSUInteger volumeCopyCount;

@interface ProbeContext : NSObject
- (void)lock;
- (void)unlock;
@end
@implementation ProbeContext
- (void)lock {}
- (void)unlock {}
@end

// Dependency doubles, deliberately separate from the extracted controller.
@interface ROI : NSObject <NSCopying, NSCoding>
@property(copy) NSString *name;
@property BOOL isAliased;
@property NSInteger originalIndexForAlias;
@property(assign) id curView;
@property(retain) id pix;
@property(readonly) NSData *data;
@end
@implementation ROI
- (id)copyWithZone:(NSZone *)zone {
    ROI *copy = [[[self class] allocWithZone:zone] init];
    copy.name = self.name; copy.isAliased = self.isAliased;
    return copy;
}
- (void)encodeWithCoder:(NSCoder *)coder {
    [coder encodeObject:self.name]; [coder encodeObject:@(self.isAliased)];
}
- (id)initWithCoder:(NSCoder *)coder {
    if ((self = [super init])) { self.name = [coder decodeObject]; self.isAliased = [[coder decodeObject] boolValue]; }
    return self;
}
- (NSData *)data { return [NSArchiver archivedDataWithRootObject:self]; }
- (void)dealloc { [_name release]; [_pix release]; [super dealloc]; }
@end

@interface HorosVolumeLengthROI : ROI
@property(copy) NSDictionary *volumeLength;
@property(readonly) NSString *volumeIdentifier;
@end
@implementation HorosVolumeLengthROI
- (NSString *)volumeIdentifier { return self.volumeLength[@"id"]; }
- (id)copyWithZone:(NSZone *)zone {
    volumeCopyCount++;
    HorosVolumeLengthROI *copy = [super copyWithZone:zone]; copy.volumeLength = self.volumeLength;
    return copy;
}
- (void)encodeWithCoder:(NSCoder *)coder { [super encodeWithCoder:coder]; [coder encodeObject:self.volumeLength]; }
- (id)initWithCoder:(NSCoder *)coder { if ((self = [super initWithCoder:coder])) self.volumeLength = [coder decodeObject]; return self; }
- (void)dealloc { [_volumeLength release]; [super dealloc]; }
@end

@class DicomStudy, DicomSeries, DicomImage;
@interface ProbeManagedObject : NSObject @end
@implementation ProbeManagedObject @end
// Foundation can load CoreData transitively; avoid defining its runtime class.
// The production controller still uses its exact NSManagedObject type checks.
#define NSManagedObject ProbeManagedObject
@interface DicomImage : ProbeManagedObject
@property(copy) NSString *objectID, *sopInstanceUID;
@property(retain) NSNumber *frameID;
@property(retain) DicomSeries *series;
@property(retain) ProbeContext *managedObjectContext;
- (NSString *)SRPath;
@end
@interface DicomSeries : NSObject
@property(retain) DicomStudy *study;
@end
@interface DicomStudy : NSObject
@property(retain) NSMutableDictionary *paths;
- (NSString *)roiPathForImage:(DicomImage *)image;
- (NSString *)roiPathForImage:(DicomImage *)image inArray:(NSArray *)images;
- (id)roiSRSeries;
@end
@implementation DicomImage
- (NSString *)SRPath { return nil; }
@end
@implementation DicomSeries @end
@implementation DicomStudy
- (id)init { if ((self = [super init])) self.paths = [NSMutableDictionary dictionary]; return self; }
- (NSString *)roiPathForImage:(DicomImage *)image { return self.paths[image.objectID]; }
- (NSString *)roiPathForImage:(DicomImage *)image inArray:(NSArray *)images { return [self roiPathForImage:image]; }
- (id)roiSRSeries { return @{@"seriesDICOMUID":@"synthetic-sr-series", @"images":[NSSet set]}; }
@end

@interface DCMPix : NSObject
@property BOOL generated;
@end
@implementation DCMPix @end

static NSMutableDictionary *writtenImages;
@interface DicomDatabase : NSObject
@property(copy) NSString *directory;
@property(retain) ProbeContext *managedObjectContext;
@property NSUInteger nextPath, writes, indexed;
+ (id)databaseForContext:(id)context;
- (NSString *)uniquePathForNewDataFileWithExtension:(NSString *)extension;
- (void)addFilesAtPaths:(NSArray *)paths postNotifications:(BOOL)a dicomOnly:(BOOL)b rereadExistingItems:(BOOL)c generatedByOsiriX:(BOOL)d;
- (void)lock;
- (void)unlock;
@end
static DicomDatabase *database;
@implementation DicomDatabase
+ (id)databaseForContext:(id)context { return database; }
- (NSString *)uniquePathForNewDataFileWithExtension:(NSString *)extension {
    return [self.directory stringByAppendingPathComponent:[NSString stringWithFormat:@"%lu.%@", (unsigned long)++_nextPath, extension]];
}
- (void)addFilesAtPaths:(NSArray *)paths postNotifications:(BOOL)a dicomOnly:(BOOL)b rereadExistingItems:(BOOL)c generatedByOsiriX:(BOOL)d {
    for (NSString *path in paths) {
        DicomImage *image = writtenImages[path];
        CHECK(image != nil, "index only a successfully written archive");
        image.series.study.paths[image.objectID] = path; self.indexed++;
    }
}
- (void)lock {}
- (void)unlock {}
@end
@interface BrowserController : NSObject
+ (id)currentBrowser;
- (DicomDatabase *)database;
@end
@implementation BrowserController
+ (id)currentBrowser { static BrowserController *browser; if (!browser) browser = [self new]; return browser; }
- (DicomDatabase *)database { return database; }
@end

@interface SRAnnotation : NSObject
@property(retain) NSArray *rois;
@property(retain) DicomImage *image;
+ (NSData *)roiFromDICOM:(NSString *)path;
+ (NSString *)archiveROIsAsDICOM:(NSArray *)rois toPath:(NSString *)path forImage:(DicomImage *)image;
- (id)initWithROIs:(NSArray *)rois path:(NSString *)path forImage:(DicomImage *)image;
- (void)setSeriesInstanceUID:(NSString *)uid;
- (BOOL)writeToFileAtPath:(NSString *)path;
@end
@implementation SRAnnotation
+ (NSData *)roiFromDICOM:(NSString *)path { return path ? [NSData dataWithContentsOfFile:path] : nil; }
+ (NSString *)archiveROIsAsDICOM:(NSArray *)rois toPath:(NSString *)path forImage:(DicomImage *)image {
    SRAnnotation *sr = [[[self alloc] initWithROIs:rois path:path forImage:image] autorelease];
    [sr writeToFileAtPath:path]; return nil;
}
- (id)initWithROIs:(NSArray *)rois path:(NSString *)path forImage:(DicomImage *)image {
    if ((self = [super init])) { self.rois = rois; self.image = image; } return self;
}
- (void)setSeriesInstanceUID:(NSString *)uid {}
- (BOOL)writeToFileAtPath:(NSString *)path {
    BOOL ok = [[NSArchiver archivedDataWithRootObject:self.rois] writeToFile:path atomically:YES];
    if (ok) { writtenImages[path] = self.image; database.writes++; } return ok;
}
@end

@interface ProbeView : NSObject
@property NSInteger index, cancellations;
- (NSInteger)curImage;
- (void)cancelLengthPlacement;
- (void)stopROIEditing;
- (void)stopROIEditingForce:(BOOL)force;
- (void)roiSet:(ROI *)roi;
- (void)setNeedsDisplay:(BOOL)needed;
@end
@implementation ProbeView
- (NSInteger)curImage { return self.index; }
- (void)cancelLengthPlacement { self.cancellations++; }
- (void)stopROIEditing {}
- (void)stopROIEditingForce:(BOOL)force {}
- (void)roiSet:(ROI *)roi { roi.curView = self; }
- (void)setNeedsDisplay:(BOOL)needed {}
@end

@interface ViewerController : NSObject {
@public
    NSMutableArray *roiList[MAX4D], *fileList[MAX4D], *pixList[MAX4D], *copyRoiList[MAX4D];
    NSInteger maxMovieIndex, curMovieIndex;
    ProbeView *imageView;
    NSMutableArray *undoQueue, *redoQueue;
}
__METHOD_DECLARATIONS__
- (NSArray *)probeSnapshotsForNewViewer:(BOOL)newViewer;
@end
__ARCHIVE_READER__
@implementation ViewerController
__METHODS__
- (NSArray *)probeSnapshotsForNewViewer:(BOOL)newViewer {
    int mx = (int)maxMovieIndex;
__SNAPSHOT__
    return volumeSnapshots;
}
@end
'''

DRIVER = r'''
static ROI *planar(NSString *name) { ROI *roi = [ROI new]; roi.name = name; return [roi autorelease]; }
static HorosVolumeLengthROI *length(NSString *identifier, NSInteger phase, double end) {
    HorosVolumeLengthROI *roi = [HorosVolumeLengthROI new]; roi.name = identifier; roi.isAliased = YES;
    roi.volumeLength = @{@"id":identifier, @"temporalIndex":@(phase), @"a":@[@0, @0, @0], @"b":@[@3, @4, @(end)]};
    return [roi autorelease];
}
static void moveEnd(HorosVolumeLengthROI *roi, double end) {
    NSMutableDictionary *payload = [[roi.volumeLength mutableCopy] autorelease];
    payload[@"b"] = @[@3, @4, @(end)]; roi.volumeLength = payload;
}
static DicomImage *makeImage(DicomSeries *series, NSInteger phase, NSInteger slice) {
    DicomImage *image = [DicomImage new];
    image.objectID = [NSString stringWithFormat:@"image-%ld-%ld", (long)phase, (long)slice];
    image.sopInstanceUID = [NSString stringWithFormat:@"synthetic-sop-%ld", (long)phase];
    image.frameID = @(slice); image.series = series; image.managedObjectContext = database.managedObjectContext;
    return [image autorelease];
}
static void phase(ViewerController *viewer, NSInteger movie, NSInteger slices, DicomSeries *series, DicomImage *source) {
    viewer->roiList[movie] = [NSMutableArray new]; viewer->pixList[movie] = [NSMutableArray new];
    viewer->fileList[movie] = [NSMutableArray new]; viewer->copyRoiList[movie] = [NSMutableArray new];
    for (NSInteger slice = 0; slice < slices; slice++) {
        [viewer->roiList[movie] addObject:[NSMutableArray array]];
        [viewer->copyRoiList[movie] addObject:[NSData data]];
        DCMPix *pix = [[[DCMPix alloc] init] autorelease]; pix.generated = source != nil;
        [viewer->pixList[movie] addObject:pix];
        [viewer->fileList[movie] addObject:source ?: makeImage(series, movie, slice)];
    }
}
static ViewerController *viewer(void) {
    ViewerController *v = [ViewerController new]; v->maxMovieIndex = 2;
    v->imageView = [ProbeView new]; v->undoQueue = [NSMutableArray new]; v->redoQueue = [NSMutableArray new];
    return [v autorelease];
}
static void uniqueAliases(ViewerController *v, NSInteger phase, NSString *identifier, NSUInteger expected) {
    HorosVolumeLengthROI *first = nil; NSUInteger count = 0;
    for (NSArray *slice in v->roiList[phase]) {
        NSUInteger perSlice = 0;
        for (ROI *roi in slice) if ([roi isKindOfClass:[HorosVolumeLengthROI class]] &&
                                   [[(HorosVolumeLengthROI *)roi volumeIdentifier] isEqual:identifier]) {
            if (!first) first = (id)roi;
            CHECK(first == roi, "all aliases of a UUID point to the same object");
            perSlice++; count++;
        }
        CHECK(perSlice <= 1, "each slice contains at most one alias for a UUID");
    }
    CHECK(count == expected, "alias coverage matches the phase's slice count");
}
static HorosVolumeLengthROI *onlyVolume(ViewerController *v, NSInteger phase) {
    NSArray *rois = [v volumeLengthROIsForMovieIndex:phase];
    CHECK(rois.count == 1, "one canonical volume in phase"); return rois[0];
}
static NSUInteger countNamed(NSArray *rois, NSString *name) {
    NSUInteger count = 0; for (ROI *roi in rois) if ([roi.name isEqual:name]) count++; return count;
}
static NSArray *stored(DicomImage *image) { return HorosVolumeLengthReadArchive([image.series.study roiPathForImage:image]); }

int main(int argc, char **argv) { @autoreleasepool {
    CHECK(argc == 2, "temporary directory supplied");
    database = [DicomDatabase new]; database.directory = [NSString stringWithUTF8String:argv[1]];
    database.managedObjectContext = [ProbeContext new]; writtenImages = [NSMutableDictionary new];
    [[NSUserDefaults standardUserDefaults] setBool:YES forKey:@"SAVEROIS"];
    DicomSeries *series = [DicomSeries new]; series.study = [DicomStudy new];
    ViewerController *v = viewer(); phase(v, 0, 3, series, nil); phase(v, 1, 2, series, nil);
    DicomImage *anchor0 = v->fileList[0][0], *anchor1 = v->fileList[1][0];
    [v->roiList[0][0] addObject:planar(@"source 2D")];
    [v->roiList[0][1] addObject:planar(@"another slice 2D")];
    HorosVolumeLengthROI *a = length(@"length-A", 0, 12), *b = length(@"length-B", 1, 20);
    [v addVolumeLengthROI:a]; [v addVolumeLengthROI:b movieIndex:1];
    [v addVolumeLengthROI:a];
    uniqueAliases(v, 0, @"length-A", 3); uniqueAliases(v, 1, @"length-B", 2);
    uniqueAliases(v, 0, @"length-B", 0); uniqueAliases(v, 1, @"length-A", 0);
    CHECK(v->undoQueue.count == 0, "registration does not create an undo operation");
    CHECK([a.volumeLength[@"storageSOPInstanceUID"] isEqual:anchor0.sopInstanceUID], "original storage SOP recorded");
    CHECK([a.volumeLength[@"storageFrame"] isEqual:anchor0.frameID], "original frame recorded");
    [v addVolumeLengthROI:length(@"invalid", 9, 8) movieIndex:9];
    CHECK([v volumeLengthROIsForMovieIndex:9].count == 0, "unavailable phase is not populated");

    // The real undo serializer must copy each volume once, not once per slice.
    volumeCopyCount = 0;
    NSDictionary *beforeEdit = [v prepareObjectForUndo:@"roi"];
    CHECK(volumeCopyCount == 2, "undo copies two volume UUIDs exactly twice");
    NSArray *snapshotPhases = beforeEdit[@"rois"];
    CHECK(snapshotPhases[0][0][1] == snapshotPhases[0][1][1], "undo preserves shared alias references");
    CHECK(snapshotPhases[0][0][1] != a, "undo data is independent from current objects");
    [v->undoQueue addObject:beforeEdit]; moveEnd(a, 30);
    v->curMovieIndex = 1; [v deleteROI:b]; v->curMovieIndex = 0;
    [v undo:nil];
    uniqueAliases(v, 0, @"length-A", 3); uniqueAliases(v, 1, @"length-B", 2);
    CHECK([onlyVolume(v, 0).volumeLength[@"b"][2] doubleValue] == 12, "undo restores physical endpoints");
    CHECK(v->imageView.cancellations == 1, "undo cancels an incomplete placement");
    [v redo:nil];
    CHECK([onlyVolume(v, 0).volumeLength[@"b"][2] doubleValue] == 30, "redo restores edited endpoint");
    CHECK([v volumeLengthROIsForMovieIndex:1].count == 0, "redo restores deletion in the other phase");
    [v undo:nil];

    // A fresh 2D archive and its new volume are saved in the same operation.
    // The database cannot find the fresh path until saveROI finally indexes it.
    [v saveROI:0]; [v saveROI:1];
    CHECK(series.study.paths.count == 3, "one indexed SR per source image, with no parallel volume archive");
    CHECK(countNamed(stored(anchor0), @"source 2D") == 1, "save preserves the planar ROI at the anchor");
    CHECK(countNamed(stored(anchor0), @"length-A") == 1, "save persists the volume exactly once");
    CHECK(countNamed(stored(anchor1), @"length-B") == 1, "second phase uses its own source anchor");

    ViewerController *reopened = viewer();
    phase(reopened, 0, 3, series, nil); phase(reopened, 1, 2, series, nil);
    [reopened loadROI:0]; [reopened loadROI:1];
    uniqueAliases(reopened, 0, @"length-A", 3); uniqueAliases(reopened, 1, @"length-B", 2);
    CHECK(countNamed(reopened->roiList[0][0], @"source 2D") == 1, "reopening retains original planar ROI");

    // Run the actual inlined reslice snapshot block, then restore into generated
    // slice arrays. Pixel resampling itself is deliberately outside this test.
    NSArray *snapshots = [reopened probeSnapshotsForNewViewer:YES];
    ViewerController *resliced = viewer();
    phase(resliced, 0, 5, series, anchor0); phase(resliced, 1, 4, series, anchor1);
    [resliced loadROI:0]; [resliced loadROI:1];
    CHECK(countNamed(resliced->roiList[0][0], @"source 2D") == 0, "generated planes do not load source planar ROIs");
    [resliced restoreVolumeLengthSnapshot:snapshots[0] movieIndex:0];
    [resliced restoreVolumeLengthSnapshot:snapshots[1] movieIndex:1];
    uniqueAliases(resliced, 0, @"length-A", 5); uniqueAliases(resliced, 1, @"length-B", 4);
    CHECK(onlyVolume(resliced, 0) != onlyVolume(reopened, 0), "new reslice window owns a separate mutable object");
    moveEnd(onlyVolume(resliced, 0), 42);
    CHECK([onlyVolume(reopened, 0).volumeLength[@"b"][2] doubleValue] == 12, "reslice window does not mutate source window endpoints");

    // Simulate another window saving a new UUID after this viewer loaded: the
    // merge must preserve that unknown UUID, as well as the source 2D record.
    NSString *path0 = [series.study roiPathForImage:anchor0];
    NSMutableArray *withForeign = [NSMutableArray arrayWithArray:stored(anchor0)];
    [withForeign addObject:length(@"foreign-length", 0, 7)];
    [SRAnnotation archiveROIsAsDICOM:withForeign toPath:path0 forImage:anchor0];
    [resliced saveROI:0];
    NSArray *afterEdit = stored(anchor0);
    CHECK(countNamed(afterEdit, @"source 2D") == 1, "generated save preserves source planar geometry");
    CHECK(countNamed(afterEdit, @"foreign-length") == 1, "merge preserves UUIDs owned by another writer");
    CHECK(countNamed(afterEdit, @"length-A") == 1, "generated save replaces, rather than duplicates, canonical UUID");
    for (ROI *roi in afterEdit) if ([roi.name isEqual:@"length-A"])
        CHECK([[(HorosVolumeLengthROI *)roi volumeLength][@"b"][2] doubleValue] == 42, "generated edit reaches original archive");
    [resliced deleteROI:onlyVolume(resliced, 0)]; [resliced saveROI:0];
    CHECK(countNamed(stored(anchor0), @"length-A") == 0, "known deleted UUID is removed from persistent archive");
    CHECK(countNamed(stored(anchor0), @"source 2D") == 1, "deleting volume retains source planar ROI");
    CHECK(countNamed(stored(anchor0), @"foreign-length") == 1, "deletion leaves unrelated persistent UUID intact");
    CHECK(countNamed(stored(anchor1), @"length-B") == 1, "saving/deleting phase zero leaves phase one intact");

    // Restoring an empty snapshot (after undoing creation) must remove aliases
    // that loadROI may have just recovered from disk before a reslice.
    NSMutableDictionary *empty = [[snapshots[1] mutableCopy] autorelease]; empty[@"rois"] = @[];
    [resliced restoreVolumeLengthSnapshot:empty movieIndex:1];
    CHECK([resliced volumeLengthROIsForMovieIndex:1].count == 0, "empty snapshot does not resurrect disk aliases");

    // An unreadable source archive is not an empty collection to overwrite.
    NSData *corrupt = [@"not an ROI archive" dataUsingEncoding:NSUTF8StringEncoding];
    [corrupt writeToFile:path0 atomically:YES]; NSUInteger writesBefore = database.writes;
    [resliced saveROI:0];
    CHECK([[NSData dataWithContentsOfFile:path0] isEqual:corrupt], "unreadable original is preserved byte for byte");
    CHECK(database.writes == writesBefore, "failed read never triggers archive replacement");
    puts("PASS: real controller registration, alias identity, undo/redo, phases, reslice snapshots, original/generated persistence and merge deletion");
    return 0;
}}
'''

translation_unit = DECLARATIONS.replace(
    '__METHOD_DECLARATIONS__', '\n'.join(signature + ';' for signature in signatures)
).replace('__ARCHIVE_READER__', archive_reader).replace('__METHODS__', methods).replace(
    '__SNAPSHOT__', snapshot
) + DRIVER

with tempfile.TemporaryDirectory(prefix='horos-volume-persistence-') as directory:
    folder = Path(directory)
    program = folder / 'test.m'
    program.write_text(translation_unit)
    subprocess.run([
        'xcrun', 'clang', '-fno-objc-arc', '-fsanitize=undefined',
        '-Wno-deprecated-declarations', '-framework', 'Foundation',
        str(program), '-o', str(folder / 'test'),
    ], check=True)
    subprocess.run([str(folder / 'test'), str(folder)], check=True)
