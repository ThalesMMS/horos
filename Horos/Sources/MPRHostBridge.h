#import "MPRController.h"
#import "MPRDCMView.h"

/// Metal reslice inside the host's 3D MPR (#374). The controller keeps the
/// volume, the camera, the VTK geometry, ROIs, tools and export; when the
/// option is on, the pixels of each plane are recomputed by
/// `HorosMPRReslicer` from the same volume and the same plane geometry the
/// host just derived, and copied into the existing `DCMPix`. Any mode the
/// engine does not represent (volume rendering, fusion, RGB, a reversed
/// stack) keeps the original pixels and says so on the view. Main thread only.
@interface MPRController (HorosMPRHost)
- (BOOL)horosMPRMetalEnabled;
- (void)toggleMPRMetal:(id)sender;
/// The reason the last reconstruction kept the original pixels, or nil.
- (NSString *)horosMPRFallbackReason;
/// Milliseconds of the last GPU reslice, or -1 if none ran.
- (double)horosMPRLastMilliseconds;
/// Bytes of the volume currently on the GPU, or 0.
- (NSInteger)horosMPRVolumeBytes;
/// Drops the GPU volume; the next reconstruction re-uploads if enabled.
- (void)horosMPRReleaseVolume;
@end

@interface MPRDCMView (HorosMPRHost)
/// Called by the host after it has set the plane geometry on `pix` and before
/// the window level is reapplied. Returns YES when the pixels were replaced.
- (BOOL)horosMPRReplacePixels;
@end
