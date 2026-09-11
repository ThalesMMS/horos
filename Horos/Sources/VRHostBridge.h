#import "VRController.h"
#import "VRView.h"

/// Metal volume rendering in the host's 3D viewer and comparison window. The viewer
/// keeps the volume, the VTK camera, the transfer function, presets, tools,
/// export and every notification; the bridge reads that state as numbers and
/// renders with `HorosVolumeRenderer`. The native mapper uses Metal for
/// unclipped scalar VR; unsupported modes use CPU with a visible reason.
/// The comparison window also supports scalar projections. Main thread only.
@interface VRController (HorosVolumeHost)
/// Opens or fronts the comparison window for this viewer.
- (void)openVolumeMetalComparison:(id)sender;
/// The state the renderer consumes, or a dictionary with an `error` entry.
- (NSDictionary *)horosVolumeSnapshot;
/// Renders the current state at the given size (BGRA, row 0 at the top).
/// `scalarOut`, when given, receives the projected scalar for MIP/MinIP/mean.
- (NSData *)horosVolumeMetalRenderWithWidth:(NSInteger)width height:(NSInteger)height
                                   scalarOut:(NSMutableData *)scalarOut error:(NSError **)error;
/// Same state, explicit camera: position(3), focal(3), viewUp(3), parallel,
/// parallelScale, viewAngle in the volume's millimetre frame, and a clipping
/// range (far < 0 for none). Used to reproduce the exact sub-rectangle VTK's
/// ray-cast image covers, for the numeric comparison.
- (NSData *)horosVolumeMetalRenderWithCamera:(NSArray<NSNumber *> *)camera near:(double)near far:(double)far
                                        width:(NSInteger)width height:(NSInteger)height
                                    scalarOut:(NSMutableData *)scalarOut error:(NSError **)error;
/// The reason the last render declined, or nil.
- (NSString *)horosVolumeMetalFallbackReason;
/// Milliseconds of the last GPU render, or -1.
- (double)horosVolumeMetalLastMilliseconds;
/// Bytes of the volume on the GPU, or 0.
- (NSInteger)horosVolumeMetalBytes;
/// Drops the GPU volume; the next render re-uploads.
- (void)horosVolumeMetalRelease;
@end

@interface VRView (HorosVolumeHost)
/// Reads camera, window, CLUT, opacity, mode, clipping, shading and crop from
/// the VTK state, in the volume's own millimetre frame (the VTK world divided
/// by the view's factor).
- (NSDictionary *)horosVolumeSnapshot;
/// Fills the mapper's image with Metal RGBA pixels. Returns NO for CPU fallback.
- (BOOL)horosRenderMetalImageForMapper:(vtkHorosFixedPointVolumeRayCastMapper *)mapper
                            renderer:(vtkRenderer *)renderer volume:(vtkVolume *)renderVolume;
@end
