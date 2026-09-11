// Synthetic, local-only plugin fixture for #373. Build with the companion tool.
// It observes real host requests; it never sleeps a decoder or drives the UI.
// All records are restricted to S373-LIFETIME CT/MR in the isolated bundle.
#import <Horos/PluginFilter.h>
#import <Horos/Notifications.h>
#import <objc/runtime.h>
#import <mach/mach.h>

@interface NSObject (LifetimeSessionAPI)
+ (id)shared;
- (id)horosVolumeSession;
- (id)makeLoadTokenFor:(id)session;
@end

static NSLock *recordLock;
static NSString *outputPath;
static NSMutableArray *heldSessions;
static char allowedPixels;
static IMP originalStart, originalLoad, originalFinish;

static NSString *pointerID(id object) { return object ? [NSString stringWithFormat:@"%p", object] : @""; }
static BOOL synthetic(ViewerController *viewer) {
    if (!viewer || !NSThread.isMainThread) return NO;
    NSString *patient = [viewer valueForKeyPath:@"currentStudy.patientID"];
    NSString *series = [viewer valueForKeyPath:@"currentSeries.name"];
    return ([@[@"LOCAL-SCROLL-CT",@"LOCAL-SCROLL-MR"] containsObject:patient]
        && [series hasPrefix:@"S373-LIFETIME-"]);
}
static void record(NSString *event, NSDictionary *fields) {
    if (!outputPath) return;
    NSMutableDictionary *row = [fields mutableCopy];
    row[@"event"] = event;
    row[@"uptime"] = @(NSProcessInfo.processInfo.systemUptime);
    row[@"mainThread"] = @(NSThread.isMainThread);
    NSData *data = [NSJSONSerialization dataWithJSONObject:row options:NSJSONWritingSortedKeys error:NULL];
    [recordLock lock];
    NSFileHandle *file = [NSFileHandle fileHandleForWritingAtPath:outputPath];
    [file seekToEndOfFile]; [file writeData:data]; [file writeData:[@"\n" dataUsingEncoding:NSUTF8StringEncoding]];
    [file closeFile]; [recordLock unlock]; [row release];
}
static NSDictionary *threadState(NSThread *thread) {
    return @{@"id":pointerID(thread), @"cancelled":@(thread.isCancelled),
        @"executing":@(thread.isExecuting), @"finished":@(thread.isFinished)};
}
static NSArray *sessionState(void) {
    NSMutableArray *states = [NSMutableArray array];
    for (NSDictionary *held in heldSessions) {
        id session = held[@"session"], token = held[@"token"];
        [states addObject:@{@"id":[session valueForKey:@"sessionID"],
            @"open":[session valueForKey:@"isOpen"], @"stale":[session valueForKey:@"isStale"],
            @"generation":[session valueForKeyPath:@"identity.generation"],
            @"cancelled":[token valueForKey:@"isCancelled"],
            @"delivered":[token valueForKey:@"hasDelivered"]}];
    }
    return states;
}
static void startHook(ViewerController *viewer, SEL command) {
    BOOL allowed = synthetic(viewer);
    if (allowed) {
        for (int movie = 0; movie < [viewer maxMovieIndex]; ++movie)
            for (DCMPix *pix in [viewer pixList:movie])
                objc_setAssociatedObject(pix, &allowedPixels, @YES, OBJC_ASSOCIATION_RETAIN_NONATOMIC);
        record(@"request-before", @{@"viewer":pointerID(viewer),
            @"previous":threadState([viewer valueForKey:@"loadingThread"])});
    }
    ((void(*)(id,SEL))originalStart)(viewer,command);
    if (allowed) record(@"request-started", @{@"viewer":pointerID(viewer),
        @"thread":threadState([viewer valueForKey:@"loadingThread"]),
        @"series":[viewer valueForKeyPath:@"currentSeries.name"] ?: @"",
        @"slices":@([viewer pixList].count), @"movies":@([viewer maxMovieIndex])});
}
static void loadHook(id klass, SEL command, NSDictionary *request) {
    DCMPix *first = [request[@"pixListArray"] firstObject][0];
    BOOL allowed = [objc_getAssociatedObject(first, &allowedPixels) boolValue];
    NSThread *thread = NSThread.currentThread;
    if (allowed) record(@"worker-started", @{@"thread":threadState(thread)});
    ((void(*)(id,SEL,id))originalLoad)(klass,command,request);
    if (allowed) {
        NSUInteger loaded = 0, total = 0;
        for (NSArray *array in request[@"pixListArray"])
            for (DCMPix *pix in array) { ++total; loaded += pix.isLoaded ? 1 : 0; }
        record(@"worker-ended", @{@"thread":threadState(thread), @"loaded":@(loaded), @"total":@(total)});
    }
}
static void finishHook(ViewerController *viewer, SEL command, NSDictionary *request) {
    DCMPix *first = [request[@"pixListArray"] firstObject][0];
    BOOL allowed = [objc_getAssociatedObject(first, &allowedPixels) boolValue];
    if (allowed) record(@"delivery-before", @{@"viewer":pointerID(viewer),
        @"origin":threadState(request[@"loadThread"]),
        @"current":threadState([viewer valueForKey:@"loadingThread"]),
        @"closing":@([viewer windowWillClose])});
    ((void(*)(id,SEL,id))originalFinish)(viewer,command,request);
    if (allowed) record(@"delivery-after", @{@"viewer":pointerID(viewer),
        @"origin":threadState(request[@"loadThread"]),
        @"current":threadState([viewer valueForKey:@"loadingThread"]),
        @"closing":@([viewer windowWillClose])});
}

@interface QAHorosLifetime : PluginFilter
@end
@implementation QAHorosLifetime
- (void)initPlugin {
    if (![NSBundle.mainBundle.bundleIdentifier isEqual:@"org.horosproject.horos.planar-performance"]) return;
    NSString *directory = [NSBundle bundleForClass:self.class].infoDictionary[@"ProofDirectory"];
    if (![directory containsString:@"/local-validation/"]) return;
    NSString *path = [directory stringByAppendingPathComponent:@"native-events.jsonl"];
    if ([NSFileManager.defaultManager fileExistsAtPath:path]) return;
    if (![NSFileManager.defaultManager createFileAtPath:path contents:nil attributes:nil]) return;
    outputPath = [path copy]; recordLock = [NSLock new]; heldSessions = [NSMutableArray new];
    Class viewer = NSClassFromString(@"ViewerController");
    originalStart = method_setImplementation(class_getInstanceMethod(viewer,@selector(startLoadImageThread)),(IMP)startHook);
    originalLoad = method_setImplementation(class_getClassMethod(viewer,@selector(loadImageData:)),(IMP)loadHook);
    originalFinish = method_setImplementation(class_getInstanceMethod(viewer,@selector(finishLoadImageData:)),(IMP)finishHook);
    for (NSString *name in @[OsirixViewerControllerDidLoadImagesNotification, OsirixViewerWillChangeNotification,
                             OsirixViewerDidChangeNotification, OsirixCloseViewerNotification, OsirixUpdateVolumeDataNotification])
        [NSNotificationCenter.defaultCenter addObserver:self selector:@selector(observed:) name:name object:nil];
    record(@"plugin-loaded", @{@"plugin":@"QAHorosLifetime",@"api":NSStringFromClass(self.superclass)});
}
- (void)observed:(NSNotification *)note {
    if (![note.object isKindOfClass:NSClassFromString(@"ViewerController")] || !synthetic(note.object)) return;
    ViewerController *viewer = note.object;
    record(@"notification", @{@"name":note.name,@"viewer":pointerID(viewer),
        @"thread":threadState([viewer valueForKey:@"loadingThread"]), @"closing":@([viewer windowWillClose])});
    if ([note.name isEqual:@"CloseViewerNotification"] || [note.name isEqual:@"ViewerWillChangeNotification"])
        dispatch_async(dispatch_get_main_queue(), ^{
            record(@"retired-consumers", @{@"sessions":sessionState(),
                @"registryCount":[[NSClassFromString(@"HorosVolumeSessionRegistry") shared] valueForKey:@"openSessionCount"]});
        });
}
- (BOOL)handleEvent:(NSEvent *)event forViewer:(id)viewer {
    if (synthetic(viewer)) record(@"input", @{@"viewer":pointerID(viewer), @"type":@(event.type),
        @"index":@([[(ViewerController *)viewer imageView] curImage])});
    return NO;
}
- (long)filterImage:(NSString *)menuName {
    if (!outputPath || !NSThread.isMainThread) return -1;
    if ([menuName isEqual:@"Capture Lifetime Registry"]) {
        record(@"registry-capture", @{@"sessions":sessionState(),
            @"viewers":@([self viewerControllersList].count),
            @"registryCount":[[NSClassFromString(@"HorosVolumeSessionRegistry") shared] valueForKey:@"openSessionCount"]});
        return 0;
    }
    if (!synthetic(viewerController)) return -2;
    id session = [viewerController horosVolumeSession];
    if (!session) return -3;
    BOOL held = NO;
    for (NSDictionary *item in heldSessions) if (item[@"session"] == session) held = YES;
    if (!held) {
        id token = [[NSClassFromString(@"HorosVolumeSessionRegistry") shared] makeLoadTokenFor:session];
        if (!token) return -4;
        [heldSessions addObject:@{@"session":session,@"token":token}];
    }
    NSUInteger voxels = 0, mismatches = 0, rois = 0;
    double maximum = 0;
    BOOL ct = [[viewerController valueForKeyPath:@"currentStudy.patientID"] isEqual:@"LOCAL-SCROLL-CT"];
    for (DCMPix *pix in [viewerController pixList]) {
        if (!pix.isLoaded || pix.pwidth != 512 || pix.pheight != 512 || pix.isRGB) return -5;
        NSInteger z = llround(pix.originZ / .5);
        const float *values = pix.fImage;
        for (NSInteger y=0;y<512;++y) for (NSInteger x=0;x<512;++x) {
            float expected = (x+y+3*z)%4096 - (ct ? 1024 : 0);
            double error = fabs(values[y*512+x]-expected);
            ++voxels; if (error != 0) ++mismatches; if (error > maximum) maximum = error;
        }
    }
    for (NSArray *array in [viewerController roiList]) rois += array.count;
    record(@"pixel-capture", @{@"viewer":pointerID(viewerController),
        @"series":[viewerController valueForKeyPath:@"currentSeries.name"],
        @"voxels":@(voxels),@"mismatches":@(mismatches),@"maximumError":@(maximum),@"rois":@(rois),
        @"sessionID":[session valueForKey:@"sessionID"], @"identity":[session valueForKey:@"identity"] ? [[session valueForKey:@"identity"] description] : @"",
        @"seriesUID":[viewerController valueForKeyPath:@"currentSeries.seriesDICOMUID"],
        @"sessionSeriesUID":[session valueForKeyPath:@"identity.seriesInstanceUID"],
        @"sameSession":@([viewerController horosVolumeSession] == session),
        @"metalEnabled":[viewerController valueForKey:@"horosPlanarMetalEnabled"],
        @"fallback":[viewerController.imageView valueForKey:@"horosPlanarFallbackReason"] ?: @"",
        @"sessions":sessionState()});
    return mismatches ? -6 : 0;
}
@end
