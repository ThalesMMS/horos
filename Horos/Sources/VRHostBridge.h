#import "VRController.h"
#import "VRView.h"

/// Metal volume rendering in the host's 3D viewer and comparison window. The viewer
/// keeps the volume, the VTK camera, the transfer function, presets, tools,
/// export and every notification; the bridge reads that state as numbers and
/// renders with `HorosVolumeRenderer`. Each native mapper - the volume's and a
/// fused series' - fills its own ray-cast image in Metal, and VTK composes
/// them (#671); unsupported cases use CPU with a visible reason. Main thread only.
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
/// The same for the fused series' volume (#671).
- (NSString *)horosFusedVolumeMetalFallbackReason;
/// Milliseconds of the last GPU render, or -1.
- (double)horosVolumeMetalLastMilliseconds;
/// The same for the fused series' volume (#671).
- (double)horosFusedVolumeMetalLastMilliseconds;
/// Bytes of the volumes on the GPU, the image's and a fused series', or 0.
- (NSInteger)horosVolumeMetalBytes;
/// Drops the GPU volumes; the next render re-uploads.
- (void)horosVolumeMetalRelease;
@end

@interface VRView (HorosVolumeHost)
/// VTK's ray-cast image grid: viewport width and height, top-left origin x
/// and y, in-use width and height, in ray pixels (#659).
- (NSArray *)horosRayCastImageRegion;
/// The ray-cast image's in-use rectangle, premultiplied RGBA in 15 bits, bottom
/// row first: what the view shows, from either engine (#659).
- (NSData *)horosRayCastImagePixels;
/// Whether a series is fused over the volume (#671).
- (BOOL)horosHasFusedVolume;
/// The same two for the fused series' mapper, whose image VTK draws over the
/// volume's; nil without a fused series (#671).
- (NSArray *)horosFusedRayCastImageRegion;
- (NSData *)horosFusedRayCastImagePixels;
/// Whether the MPR reslice can stand in for this plane's ray cast: nil when it
/// can, with the plane's size in ray pixels, otherwise the reason, one text per
/// cause so that the trace can count them (#664).
- (NSString *)horosMPRGeometryRefusalWidth:(long *)width height:(long *)height;
/// The same for the series fused over the MPR (#658): the blending mapper's
/// ray-cast geometry, prepared for its own volume without a render.
- (NSString *)horosMPRFusedGeometryRefusalWidth:(long *)width height:(long *)height;
/// The fused series as VTK reslices it (#658): its float voxels (`volume`, the
/// buffer VTK converts to 16 bits from), `width`, `height`, `depth`, the
/// column-major voxel-to-world `transform` in millimetres, the `background` a
/// ray that misses it reads back as, and a `sampleStep`; or an `error`.
- (NSDictionary *)horosMPRFusedVolume;
/// Reads camera, window, CLUT, opacity, mode, clipping, shading and crop from
/// the VTK state, in the volume's own millimetre frame (the VTK world divided
/// by the view's factor).
- (NSDictionary *)horosVolumeSnapshot;
/// The fused series as the renderer takes it, with the same keys (#671): its
/// voxels and placement, its window, CLUT, opacity table, shading, crop planes
/// and step, under the view's camera and mode; or an `error`.
- (NSDictionary *)horosFusedVolumeSnapshot;
/// Fills the mapper's image - the volume's or a fused series' - with Metal
/// RGBA pixels. Returns NO for CPU fallback.
- (BOOL)horosRenderMetalImageForMapper:(vtkHorosFixedPointVolumeRayCastMapper *)mapper
                            renderer:(vtkRenderer *)renderer volume:(vtkVolume *)renderVolume;
@end
