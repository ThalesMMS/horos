#import "MPRController.h"
#import "MPRDCMView.h"
#import "DCMPix.h"

/// Metal reconstructs scalar 3D MPR planes by default. The host retains its
/// camera, geometry, ROIs, tools and export. Unsupported modes and failures
/// use the CPU renderer. The per-window option permits CPU comparisons.
@interface MPRController (HorosMPRHost)
- (BOOL)horosMPRMetalEnabled;
- (void)toggleMPRMetal:(id)sender;
/// The reason the last reconstruction kept the original pixels, or nil.
- (NSString *)horosMPRFallbackReason;
/// Wall milliseconds of the last synchronous Metal reslice, or -1 if none ran.
- (double)horosMPRLastMilliseconds;
/// Bytes of the volumes currently on the GPU, the fused one included (#658), or 0.
- (NSInteger)horosMPRVolumeBytes;
/// Drops the GPU volume; the next reconstruction re-uploads if enabled.
- (void)horosMPRReleaseVolume;
/// Whether single planes are drawn with cubic interpolation (#702): the
/// `HorosMPRCubicDisplay` preference, off by default.
- (BOOL)horosMPRCubicDisplay;
- (void)toggleMPRCubicDisplay:(id)sender;
@end

@interface MPRDCMView (HorosMPRHost)
/// Returns a malloc-owned float image after preparing the camera geometry.
/// A NULL result requests the normal CPU render. Main thread only.
- (float *)horosMPRCopyImageWidth:(long *)width height:(long *)height;
/// The fused series' plane the last call resliced with it (#658), malloc-owned,
/// or NULL: then the host reslices it with VTK, as it does the plane.
- (float *)horosMPRTakeFusedImageWidth:(long *)width height:(long *)height;
/// Hands `pix` the cubic display plane of the last reconstruction, or takes
/// its old one away when the last reconstruction made none (#702).
- (void)horosMPRAttachDisplayPlaneTo:(DCMPix *)pix;
@end

