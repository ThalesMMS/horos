#import "DCMView.h"
#import "ViewerController.h"
@class HorosLegacyScalarCLUTState;
@class HorosScalarCLUTDraw;
@class HorosPlanarPerformanceTrace;

/// Rendering changes only; controllers, DICOM pixels and plugin APIs remain
/// the host's. These entry points are main-thread-only.
@interface ViewerController (HorosPlanarHost)
- (BOOL)horosPlanarMetalEnabled;
- (void)togglePlanarMetal:(id)sender;
@end

@interface DCMView (HorosPlanarHost)
- (NSDictionary *)horosPlanarSnapshot;
- (BOOL)horosDrawPlanarInContext:(NSOpenGLContext *)context size:(NSSize)size;
- (NSString *)horosPlanarFallbackReason;
/// Which submission path drew the last planar frame, or an empty string when
/// none has (#609). Diagnostics: the picture is the same either way.
- (NSString *)horosPlanarBackendName;
/// The GPU time the last planar submission reported, in milliseconds.
- (double)horosPlanarGPUMilliseconds;
/// Lets another host bridge (the MPR one) show the same paused-renderer notice.
- (void)horosSetPlanarFallbackReason:(NSString *)reason;
- (void)horosInvalidatePlanar;
- (HorosLegacyScalarCLUTState *)horosScalarCLUTState;
- (HorosScalarCLUTDraw *)horosScalarCLUTWithTable:(NSData *)table windowed:(BOOL)windowed;
- (HorosScalarCLUTDraw *)horosScalarCLUTForLens;
- (HorosPlanarPerformanceTrace *)horosPlanarPerformanceTrace;
- (double)horosPlanarLastCommandMilliseconds;
@end
