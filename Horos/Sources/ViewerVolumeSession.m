#import "ViewerVolumeSession.h"
#import "Horos-Swift.h"
#import "DicomImage.h"
#import "DCMPix.h"
#import "DicomSeries.h"
#import "DicomStudy.h"
#import "Notifications.h"
#import <objc/runtime.h>

@interface HorosViewerVolumeContext : NSObject {
    ViewerController *_viewer;
    NSString *_owner;
    HorosVolumeSession *_session;
    BOOL _changing;
}
- (id)initWithViewer:(ViewerController *)viewer;
- (HorosVolumeSession *)session;
@end

@implementation HorosViewerVolumeContext
- (id)initWithViewer:(ViewerController *)viewer {
    if ((self = [super init])) {
        _viewer = viewer;
        _owner = [[[NSUUID UUID] UUIDString] copy];
        NSNotificationCenter *nc = [NSNotificationCenter defaultCenter];
        [nc addObserver:self selector:@selector(close:) name:OsirixCloseViewerNotification object:viewer];
        [nc addObserver:self selector:@selector(willChange:) name:OsirixViewerWillChangeNotification object:viewer];
        [nc addObserver:self selector:@selector(didChange:) name:OsirixViewerDidChangeNotification object:viewer];
        [nc addObserver:self selector:@selector(invalidate:) name:OsirixUpdateVolumeDataNotification object:nil];
    }
    return self;
}
- (void)willChange:(NSNotification *)notification {
    _changing = YES;
    [self close:notification];
}
- (void)didChange:(NSNotification *)notification { _changing = NO; }
- (void)close:(NSNotification *)notification {
    if (_session) {
        [[HorosVolumeSessionRegistry shared] close:_session];
        [[HorosPatientCrosshairController shared] invalidateSession:_session];
    }
    [_session release]; _session = nil;
}
- (void)invalidate:(NSNotification *)notification {
    if (![NSThread isMainThread]) {
        [self performSelectorOnMainThread:@selector(invalidate:) withObject:notification waitUntilDone:NO];
        return;
    }
    if (_session && notification.object == [_viewer pixList]) {
        [[HorosVolumeSessionRegistry shared] invalidateVolume:_session.identity];
        [[HorosPatientCrosshairController shared] invalidateSession:_session];
    }
}
- (HorosVolumeSession *)session {
    NSAssert([NSThread isMainThread], @"Viewer volume access requires the main thread");
    if (_changing || [_viewer windowWillClose]) return nil;
    DicomImage *image = [_viewer currentImage];
    HorosVolumeIdentity *identity = [[[HorosVolumeIdentity alloc]
        initWithStudyInstanceUID:image.series.study.studyInstanceUID ?: @""
        // seriesInstanceUID is the catalog's grouping/sort key and can contain
        // a series-number prefix. The public identity uses DICOM (0020,000E).
        seriesInstanceUID:image.series.seriesDICOMUID ?: @""
        frameOfReferenceUID:_viewer.imageView.curDCM.frameofReferenceUID ?: @""
        timeIndex:[_viewer curMovieIndex] generation:0] autorelease];
    if (!identity) { [self close:nil]; return nil; }
    if (_session && _session.isOpen && [_session.identity refersToSameVolumeAs:identity]) {
        if (!_session.isStale) return _session;
        // Invalidation advances the identity and cancels old loads. Retire the
        // stale session so consumers can reopen, keeping that new generation.
        identity = [[_session.identity retain] autorelease];
    }
    [self close:nil];
    _session = [[[HorosVolumeSessionRegistry shared] openWithIdentity:identity owner:_owner] retain];
    return _session;
}
- (void)dealloc {
    [[NSNotificationCenter defaultCenter] removeObserver:self];
    [self close:nil]; [_owner release]; [super dealloc];
}
@end

@implementation ViewerController (HorosVolumeSession)
- (HorosVolumeSession *)horosVolumeSession {
    NSAssert([NSThread isMainThread], @"Viewer volume access requires the main thread");
    if ([self windowWillClose]) return nil;
    static char contextKey;
    HorosViewerVolumeContext *context = objc_getAssociatedObject(self, &contextKey);
    if (!context) {
        context = [[[HorosViewerVolumeContext alloc] initWithViewer:self] autorelease];
        objc_setAssociatedObject(self, &contextKey, context, OBJC_ASSOCIATION_RETAIN_NONATOMIC);
    }
    return [context session];
}
@end
