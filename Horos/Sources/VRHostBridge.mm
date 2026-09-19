#import "VRHostBridge.h"
#import "DCMPix.h"
#import "Horos-Swift.h"
#import <objc/runtime.h>
#include <vtkCamera.h>
#include <vtkVolumeProperty.h>
#include <vtkBoxWidget.h>
#include <vtkVolume.h>
#include <vtkMatrix4x4.h>
#include <vtkImageData.h>
#include <vtkFixedPointRayCastImage.h>
#include <vtkTextActor.h>

// The fused series has its own renderer, volume and reason (#671).
static char rendererKey, uploadedKey, reasonKey, millisecondsKey;
static char fusedRendererKey, fusedUploadedKey, fusedReasonKey, fusedMillisecondsKey;

/// VTK's ray-cast image grid for one mapper: viewport width and height, the
/// in-use rectangle's top-left origin, and its size, in ray pixels (#659).
static NSArray *HorosRayCastImageRegion(vtkHorosFixedPointVolumeRayCastMapper *mapper) {
    if (!mapper) return nil;
    vtkFixedPointRayCastImage *image = mapper->GetRayCastImage();
    int *viewport = image->GetImageViewportSize(), *origin = image->GetImageOrigin(), *size = image->GetImageInUseSize();
    return @[@(viewport[0]), @(viewport[1]), @(origin[0]), @(viewport[1] - origin[1] - size[1]), @(size[0]), @(size[1])];
}

/// One mapper's ray-cast image as the view shows it: the in-use rectangle,
/// premultiplied RGBA in 15 bits, bottom row first, whichever engine filled it.
static NSData *HorosRayCastImagePixels(vtkHorosFixedPointVolumeRayCastMapper *mapper) {
    if (!mapper) return nil;
    vtkFixedPointRayCastImage *image = mapper->GetRayCastImage();
    int *size = image->GetImageInUseSize(), *memory = image->GetImageMemorySize();
    unsigned short *pixels = image->GetImage();
    if (!pixels || size[0] <= 0 || size[1] <= 0) return nil;
    NSUInteger row = (NSUInteger)size[0] * 4;
    NSMutableData *data = [NSMutableData dataWithLength:row * size[1] * sizeof(unsigned short)];
    unsigned short *out = (unsigned short *)data.mutableBytes;
    for (int y = 0; y < size[1]; ++y)
        memcpy(out + y * row, pixels + (NSUInteger)y * memory[0] * 4, row * sizeof(unsigned short));
    return data;
}

/// How many of VTK's ray samples make a millimetre: the exponent that turns
/// the opacity VTK applies per sample into the renderer's opacity per
/// millimetre. Nominally superSampling / spacing (one sample per unit of VTK's
/// scaled frame); in practice the mapper's sample distance (BESTRENDERING, 1.6
/// units) gives superSampling / (spacing × 1.6), measured against VTK in
/// docs/volume-metal-validation.md. HorosVolumeMetalOpacityExponent overrides
/// it without a rebuild. Both volumes of a fused view share the frame, so the
/// fused series uses the image's spacing too (#671).
static double HorosSamplesPerMillimetre(double superSampling, double spacingX) {
    double rayStep = [[NSUserDefaults standardUserDefaults] floatForKey:@"BESTRENDERING"];
    if (rayStep <= 0) rayStep = 1.6;
    double samplesPerMillimetre = superSampling > 0 ? superSampling / (spacingX * rayStep) : 1;
    double override = [[NSUserDefaults standardUserDefaults] doubleForKey:@"HorosVolumeMetalOpacityExponent"];
    return override > 0 ? override : samplesPerMillimetre;
}

/// The fused series' opacity as VTK holds it: setBlendingFactor: fills a table,
/// and BuildFunctionFromTable spreads its first 255 entries evenly over the
/// fused window, clamped outside it. As the renderer's points (x in 0…256 over
/// the window): `opacity` per millimetre of ray for composite rendering, and
/// `projectionOpacity`, the curve itself, which a projection paints with (#671).
static void HorosFusedOpacityPoints(const double *table, double samplesPerMillimetre,
                                    NSMutableArray *opacity, NSMutableArray *projectionOpacity) {
    for (int i = 0; i < 255; ++i) {
        double x = i * 256.0 / 254.0, y = MIN(1, MAX(0, table[i]));
        [opacity addObject:@(x)];
        [opacity addObject:@(1 - pow(1 - y, samplesPerMillimetre))];
        [projectionOpacity addObject:@(x)];
        [projectionOpacity addObject:@(y)];
    }
}

/// A volume's ray-cast image as VTK displays it: premultiplied RGBA in its
/// 15-bit fixed-point range, row 0 at the top. Composite rendering converts
/// Metal's premultiplied colour and accumulated opacity. A projection's scalar
/// is a value, not an opacity: VTK paints it with the colour and the unscaled
/// opacity curve at that value (#659), so `projection` is the snapshot to
/// paint it with, or nil for composite rendering.
static NSData *HorosVolumePicture(NSData *bgra, NSData *scalar, NSDictionary *projection) {
    NSUInteger count = scalar.length / sizeof(float);
    if (projection)
        return [HorosVolumeRenderer projectionPictureWithScalar:scalar level:[projection[@"level"] doubleValue]
            width:[projection[@"width"] doubleValue] clut:projection[@"clut"] opacityPoints:projection[@"projectionOpacity"]
            background:[projection[@"scalarBackground"] doubleValue]];
    if (count == 0 || bgra.length != count * 4) return nil;
    NSMutableData *picture = [NSMutableData dataWithLength:count * 4 * sizeof(unsigned short)];
    const unsigned char *colour = (const unsigned char *)bgra.bytes;
    const float *alpha = (const float *)scalar.bytes;
    unsigned short *rgba = (unsigned short *)picture.mutableBytes;
    for (NSUInteger i = 0; i < count; ++i) {
        rgba[4 * i] = (colour[4 * i + 2] * 32767u + 127u) / 255u;
        rgba[4 * i + 1] = (colour[4 * i + 1] * 32767u + 127u) / 255u;
        rgba[4 * i + 2] = (colour[4 * i] * 32767u + 127u) / 255u;
        rgba[4 * i + 3] = (unsigned short)(fminf(1, fmaxf(0, alpha[i])) * 32767 + 0.5f);
    }
    return picture;
}

/// `over` drawn on `under` as VTK draws the fused ray-cast image over the
/// image's: GL_ONE, GL_ONE_MINUS_SRC_ALPHA on premultiplied colour. BGRA bytes
/// on black, row 0 at the top (#671).
static NSData *HorosComposedBGRA(NSData *under, NSData *over) {
    NSUInteger count = under.length / (4 * sizeof(unsigned short));
    if (count == 0 || over.length != under.length) return nil;
    NSMutableData *bgra = [NSMutableData dataWithLength:count * 4];
    const unsigned short *lower = (const unsigned short *)under.bytes, *upper = (const unsigned short *)over.bytes;
    unsigned char *out = (unsigned char *)bgra.mutableBytes;
    for (NSUInteger i = 0; i < count; ++i) {
        double keep = 1 - upper[4 * i + 3] / 32767.0;
        for (int channel = 0; channel < 3; ++channel) {
            double value = (upper[4 * i + channel] + keep * lower[4 * i + channel]) / 32767.0;
            out[4 * i + 2 - channel] = (unsigned char)lround(fmin(1, fmax(0, value)) * 255);
        }
        out[4 * i + 3] = 255;
    }
    return bgra;
}

// Why the mapper refused the ray-cast geometry, one text per cause so that a
// trace can count them (#664).
static NSString *HorosGeometryRefusalReason(vtkHorosFixedPointVolumeRayCastMapper *mapper) {
    switch (mapper->GetGeometryRefusal()) {
        case vtkHorosFixedPointVolumeRayCastMapper::GeometryClippingPlane: return @"The crop uses the original renderer.";
        case vtkHorosFixedPointVolumeRayCastMapper::GeometryNoRows: return @"The ray caster has no rows to cast.";
        case vtkHorosFixedPointVolumeRayCastMapper::GeometryNoViewport: return @"The view has no size yet.";
        default: return @"The 3D view has no volume yet.";
    }
}

@interface VRView (HorosRenderWindow)
- (BOOL)prepareRenderWindow;
@end

@interface VRController (HorosVolumeHostPrivate) <HorosVolumeSource>
- (NSData *)horosVolumeData;
- (NSArray *)horosVolumePixList;
- (NSData *)horosVolumeMetalRenderWithCamera:(NSArray *)camera near:(double)near far:(double)far
                                     width:(NSInteger)width height:(NSInteger)height imageRegion:(NSArray *)imageRegion
                             geometryDepth:(NSData *)geometryDepth
                                 scalarOut:(NSMutableData *)scalarOut error:(NSError **)error;
- (NSData *)horosFusedVolumeMetalRenderSnapshot:(NSDictionary *)snapshot width:(NSInteger)width height:(NSInteger)height
                                    imageRegion:(NSArray *)imageRegion geometryDepth:(NSData *)geometryDepth
                                      scalarOut:(NSMutableData *)scalarOut error:(NSError **)error;
- (void)horosFusedVolumeMetalRelease;
@end

@implementation VRView (HorosVolumeHost)

- (BOOL)horosRenderMetalImageForMapper:(vtkHorosFixedPointVolumeRayCastMapper *)mapper
                            renderer:(vtkRenderer *)renderer volume:(vtkVolume *)renderVolume {
    // A fused series has its own mapper and volume, drawn after the image's:
    // each fills its own ray-cast image, and VTK composes the two, the fused
    // one over the image, premultiplied (#671).
    BOOL fused = blendingVolume && renderVolume == blendingVolume && mapper == blendingVolumeMapper;
    if (engine != 2 || renderer != aRenderer || (renderVolume != self.volume && !fused) ||
        [[controller style] isEqualToString:@"noNib"]) return NO;
    @autoreleasepool {
        // A series fused and then closed leaves its volume on the GPU until
        // the image's next frame.
        if (!fused && !blendingVolume) [controller horosFusedVolumeMetalRelease];
        NSString *reason = nil;
        NSDictionary *snapshot = nil;
        // MIP, MinIP and mean draw in Metal, sampled and painted as VTK's ray
        // caster does (#659); the snapshot carries its step and planes. A crop
        // is clipped in Metal against the mapper's own planes, and the clipping
        // range is the camera's own (#664); VTK's cropping regions, which the
        // host never turns on, stay with VTK.
        if (mapper->GetCropping()) reason = @"VTK cropping regions use the original renderer.";
        else if (!fused && (isRGB || advancedCLUT)) reason = [self horosVolumeSnapshot][@"error"];
        if (!reason && !mapper->PrepareMPRGeometry(renderer, renderVolume, true))
            reason = HorosGeometryRefusalReason(mapper);
        // The fused snapshot reads the planes PrepareMPRGeometry just set up.
        if (!reason && fused) reason = (snapshot = [self horosFusedVolumeSnapshot])[@"error"];

        NSData *pixels = nil, *picture = nil;
        NSMutableData *opacity = [NSMutableData data];
        vtkFixedPointRayCastImage *image = mapper->GetRayCastImage();
        int *size = image->GetImageInUseSize();
        if (!reason) {
            NSArray *region = [HorosRayCastImageRegion(mapper) subarrayWithRange:NSMakeRange(0, 4)];
            // As in VTK's CPU pass, stop each ray at already drawn geometry.
            // Without this, ribs behind an ROI are painted over it too.
            std::vector<float> depth = mapper->CaptureGeometryDepth(renderer, factor);
            NSData *geometryDepth = depth.empty() ? nil : [NSData dataWithBytes:depth.data() length:depth.size() * sizeof(float)];
            NSError *error = nil;
            pixels = fused ? [controller horosFusedVolumeMetalRenderSnapshot:snapshot width:size[0] height:size[1]
                                                                 imageRegion:region geometryDepth:geometryDepth scalarOut:opacity error:&error]
                           : [controller horosVolumeMetalRenderWithCamera:nil near:0 far:-1 width:size[0] height:size[1]
                                                             imageRegion:region geometryDepth:geometryDepth scalarOut:opacity error:&error];
            if (!pixels) reason = error.localizedDescription ?: @"Metal could not render this volume.";
        }
        NSUInteger count = (NSUInteger)size[0] * size[1];
        BOOL ready = pixels.length == count * 4 && opacity.length == count * sizeof(float) && count > 0;
        if (!reason && !ready) reason = @"Metal returned an incomplete image.";
        double convertedFrom = [HorosMetalPerformanceTrace now];
        if (!reason) {
            picture = HorosVolumePicture(pixels, opacity, renderingMode == 0 ? nil : fused ? snapshot : [self horosVolumeSnapshot]);
            if (picture.length != count * 4 * sizeof(unsigned short)) reason = @"Metal returned an incomplete image.";
        }
        if (reason) [HorosMetalPerformanceTrace recordRefusal:fused ? @"vr.fusion.refusal" : @"vr.refusal" reason:reason];
        objc_setAssociatedObject(controller, fused ? &fusedReasonKey : &reasonKey, reason, OBJC_ASSOCIATION_COPY_NONATOMIC);
        if (textWLWW) {
            NSString *imageReason = objc_getAssociatedObject(controller, &reasonKey);
            NSString *fusedReason = blendingVolume ? objc_getAssociatedObject(controller, &fusedReasonKey) : nil;
            NSString *status = imageReason ? [@"CPU fallback: " stringByAppendingString:imageReason] : @"Metal";
            if (fusedReason) status = [status stringByAppendingFormat:@"\nFused series, CPU fallback: %@", fusedReason];
            NSString *label = [NSString stringWithFormat:@"WL: %.4g WW: %.4g\n%@", wl, ww, status];
            textWLWW->SetInput(label.UTF8String);
        }
        if (reason) return NO;

        image->ClearImage();
        unsigned short *rgba = image->GetImage();
        const unsigned short *painted = (const unsigned short *)picture.bytes;
        NSUInteger row = (NSUInteger)size[0] * 4, stride = (NSUInteger)image->GetImageMemorySize()[0] * 4;
        // VTK keeps the bottom row first.
        for (int y = 0; y < size[1]; ++y)
            memcpy(rgba + (NSUInteger)(size[1] - 1 - y) * stride, painted + (NSUInteger)y * row, row * sizeof(unsigned short));
        [HorosMetalPerformanceTrace recordHostOperation:fused ? @"vr.fusion.host_convert" : @"vr.host_convert" startedAt:convertedFrom];
        return YES;
    }
}

/// VTK's ray-cast image as the hook renders into it: the viewport in ray
/// pixels, the in-use rectangle's top-left origin, and its size. The native
/// comparison renders Metal on this same grid (#659).
- (NSArray *)horosRayCastImageRegion { return HorosRayCastImageRegion(volumeMapper); }

/// What the view shows: the in-use rectangle of VTK's ray-cast image,
/// premultiplied RGBA in 15 bits, rows as VTK keeps them (bottom row first),
/// whichever engine filled it. The native comparison reads it (#659).
- (NSData *)horosRayCastImagePixels { return HorosRayCastImagePixels(volumeMapper); }

- (BOOL)horosHasFusedVolume { return blendingVolume != nil; }

- (NSArray *)horosFusedRayCastImageRegion { return blendingVolume ? HorosRayCastImageRegion(blendingVolumeMapper) : nil; }

- (NSData *)horosFusedRayCastImagePixels { return blendingVolume ? HorosRayCastImagePixels(blendingVolumeMapper) : nil; }

- (NSString *)horosMPRGeometryRefusalWidth:(long *)width height:(long *)height {
    if (!volumeMapper || !aCamera) return @"The 3D view has no volume yet.";
    if (!aCamera->GetParallelProjection()) return @"A perspective plane keeps the original renderer.";
    if (!clipRangeActivated) return @"A plane without a clipping range keeps the original renderer.";
    if (firstObject.isRGB) return @"RGB planes keep the original renderer.";
    if (volumeMapper->GetCropping()) return @"VTK cropping regions keep the original renderer.";
    if (![self prepareRenderWindow]) return @"The plane has no window yet.";
    if (!volumeMapper->PrepareMPRGeometry(aRenderer, volume)) return HorosGeometryRefusalReason(volumeMapper);
    int size[2];
    volumeMapper->GetRayCastImage()->GetImageInUseSize(size);
    *width = size[0];
    *height = size[1];
    return size[0] > 0 && size[1] > 0 ? nil : @"The view has no size yet.";
}

- (NSString *)horosMPRFusedGeometryRefusalWidth:(long *)width height:(long *)height {
    if (!blendingVolumeMapper || !blendingVolume) return @"The fused series has no volume yet.";
    if (blendingVolumeMapper->GetCropping()) return @"VTK cropping regions keep the original renderer.";
    if (!blendingVolumeMapper->PrepareMPRGeometry(aRenderer, blendingVolume)) return HorosGeometryRefusalReason(blendingVolumeMapper);
    int size[2];
    blendingVolumeMapper->GetRayCastImage()->GetImageInUseSize(size);
    *width = size[0];
    *height = size[1];
    return size[0] > 0 && size[1] > 0 ? nil : @"The view has no size yet.";
}

- (NSDictionary *)horosMPRFusedVolume {
    if (!blendingController || !blendingVolume || !blendingReader || !blendingFirstObject || !blendingData || !blendingPixList.count)
        return @{@"error": @"The fused series has no volume yet."};
    if (isBlendingRGB) return @{@"error": @"An RGB fused series keeps the original renderer."};
    DCMPix *first = blendingFirstObject;
    double dz = first.sliceInterval;
    if (dz == 0) dz = first.sliceThickness;
    if (dz < 0) return @{@"error": @"A reversed fused stack keeps the original renderer."};
    double sx = first.pixelSpacingX, sy = first.pixelSpacingY;
    if (sx <= 0 || sy <= 0) { sx = 1; sy = 1; }
    if (dz <= 0 || !isfinite(dz) || !isfinite(sx) || !isfinite(sy)) return @{@"error": @"The fused volume spacing is not usable."};
    // The float buffer VTK converts to 16 bits from, found among the fused
    // viewer's volumes: the phase setBlendingPixSource: or
    // movieBlendingChangeSource: gave the reader.
    NSUInteger expected = [HorosVolumeAllocation byteCountForWidth:first.pwidth height:first.pheight
                                                             slices:blendingPixList.count bytesPerVoxel:4];
    NSData *voxels = nil;
    for (long i = 0; i < MAX(1, (long)[blendingController maxMovieIndex]) && !voxels; ++i)
        if ([blendingController volumeData:i].bytes == blendingData) voxels = [blendingController volumeData:i];
    if (!voxels || expected == 0 || voxels.length < expected) return @{@"error": @"The fused volume bytes do not match its slices."};
    // As -mprVoxelToWorldTransform places the volume, for the blending reader
    // and volume: the reader's origin and spacing through the volume's matrix,
    // out of VTK's frame scaled by `factor`, column by column.
    vtkImageData *input = blendingReader->GetOutput();
    if (!input || !isfinite(factor) || factor <= 0) return @{@"error": @"The fused volume transform is unavailable."};
    double origin[3], spacing[3];
    input->GetOrigin(origin);
    input->GetSpacing(spacing);
    vtkMatrix4x4 *matrix = blendingVolume->GetMatrix();
    NSMutableArray *transform = [NSMutableArray arrayWithCapacity:16];
    for (int column = 0; column < 4; ++column)
        for (int row = 0; row < 4; ++row)
        {
            double value = row == 3 ? (column == 3 ? 1 : 0) :
                (column < 3 ? matrix->GetElement(row, column) * spacing[column] :
                 matrix->GetElement(row, 3) + matrix->GetElement(row, 0) * origin[0] +
                 matrix->GetElement(row, 1) * origin[1] + matrix->GetElement(row, 2) * origin[2]) / factor;
            [transform addObject:@(value)];
        }
    // A ray that misses the volume leaves 0 in VTK's 16-bit image, which
    // -imageInFullDepthWidth:... reads back as -blendingOFFSET16.
    return @{@"volume": voxels, @"width": @(first.pwidth), @"height": @(first.pheight), @"depth": @(blendingPixList.count),
             @"transform": transform, @"background": @(-blendingOFFSET16), @"sampleStep": @(MIN(sx, MIN(sy, dz)))};
}

/// The view's camera in the volume's own millimetre frame (the VTK world
/// divided by the view's factor) and the rays' near and far distances: the
/// same for every volume the view draws (#671).
- (NSDictionary *)horosVolumeCameraSnapshot {
    double position[3], focal[3], viewUp[3];
    aCamera->GetPosition(position); aCamera->GetFocalPoint(focal); aCamera->GetViewUp(viewUp);
    // VTK works in the local frame scaled by `factor`; the renderer wants millimetres.
    NSMutableArray *camera = [NSMutableArray array];
    for (int i = 0; i < 3; ++i) [camera addObject:@(position[i] / factor)];
    for (int i = 0; i < 3; ++i) [camera addObject:@(focal[i] / factor)];
    for (int i = 0; i < 3; ++i) [camera addObject:@(viewUp[i])];
    [camera addObject:@(aCamera->GetParallelProjection() ? 1 : 0)];
    [camera addObject:@(aCamera->GetParallelScale() / factor)];
    [camera addObject:@(aCamera->GetViewAngle())];
    double near = 0, far = -1;
    if (clipRangeActivated) { near = 0; far = clippingRangeThickness / factor; }
    // VTK starts every ray on the near plane and samples it every
    // SampleDistance; a projection takes both from the mapper, in millimetres,
    // so its samples fall where VTK's do (#659). With a clipping range the near
    // plane is the camera's own, [0, thickness] (#664).
    if (renderingMode != 0) {
        double range[2];
        aCamera->GetClippingRange(range);
        near = range[0] / factor; far = range[1] / factor;
    }
    return @{@"camera": camera, @"near": @(near), @"far": @(far)};
}

/// VTK samples every unit of its scaled frame (pixelSpacingX / superSampling
/// millimetres) in composite rendering; compositing with a coarser step locks
/// a boundary sample's colour into the pixel, so the renderer walks the same
/// distance. A fused series is sampled in the same frame (#671).
static double HorosCompositeSampleStep(double sx, double sy, double dz, double superSampling) {
    return superSampling > 0 ? MIN(sx, MIN(sy, dz)) / superSampling : MIN(sx, MIN(sy, dz));
}

/// The crop reaches VTK as clipping planes on the mapper - the box widget's
/// or a saved camera's, possibly rotated - and the renderer clips each ray
/// against the same planes, in voxel index space, as VTK's ray caster clips
/// it (#664). Planes that do not cut into the voxel centres, such as the six
/// restoreCamera installs around an uncropped volume, change nothing. The
/// crop callback gives a fused series' mapper the same planes (#671).
static NSArray *HorosCuttingPlanes(vtkHorosFixedPointVolumeRayCastMapper *mapper, long width, long height, NSUInteger depth) {
    NSMutableArray *clippingPlanes = [NSMutableArray array];
    const float *voxelPlanes = NULL;
    int planeCount = mapper ? mapper->GetVoxelClippingPlanes(&voxelPlanes) : 0;
    double lastVoxel[3] = {width - 1.0, height - 1.0, depth - 1.0};
    for (int i = 0; i < planeCount; ++i) {
        const float *plane = voxelPlanes + 4 * i;
        BOOL cuts = NO;
        for (int corner = 0; corner < 8 && !cuts; ++corner) {
            double distance = plane[3];
            for (int axis = 0; axis < 3; ++axis) distance += plane[axis] * (((corner >> axis) & 1) ? lastVoxel[axis] : 0);
            cuts = distance < -1e-4;
        }
        if (cuts) for (int k = 0; k < 4; ++k) [clippingPlanes addObject:@(plane[k])];
    }
    return clippingPlanes;
}

- (NSDictionary *)horosVolumeSnapshot {
    NSAssert([NSThread isMainThread], @"Volume snapshots require the main thread");
    if (isRGB) return @{@"error": @"RGB volumes keep the original renderer."};
    if (advancedCLUT) return @{@"error": @"The 16-bit CLUT keeps the original renderer."};
    if (aCamera == nil || volumeProperty == nil || firstObject == nil || factor <= 0) return @{@"error": @"The 3D view has no volume yet."};
    NSArray *pix = [controller horosVolumePixList];
    NSData *volume = [controller horosVolumeData];
    if (pix.count == 0 || volume == nil) return @{@"error": @"The 3D view has no volume yet."};
    DCMPix *first = pix.firstObject;
    double dz = first.sliceInterval != 0 ? fabs(first.sliceInterval) : fabs(first.sliceThickness);
    double sx = first.pixelSpacingX > 0 ? first.pixelSpacingX : 1, sy = first.pixelSpacingY > 0 ? first.pixelSpacingY : 1;
    if (dz <= 0 || !isfinite(dz)) return @{@"error": @"The volume spacing is not usable."};

    NSDictionary *view = [self horosVolumeCameraSnapshot];
    BOOL projection = renderingMode != 0;

    unsigned char rgba[1024];
    for (int i = 0; i < 256; ++i) {
        rgba[4 * i] = (unsigned char)fmin(255, fmax(0, table[i][0] * 255 + 0.5));
        rgba[4 * i + 1] = (unsigned char)fmin(255, fmax(0, table[i][1] * 255 + 0.5));
        rgba[4 * i + 2] = (unsigned char)fmin(255, fmax(0, table[i][2] * 255 + 0.5));
        rgba[4 * i + 3] = 255;
    }
    // The host divides its opacity curve by superSampling and VTK applies it
    // per unit of the scaled frame (pixelSpacingX / superSampling millimetres);
    // the renderer wants opacity per millimetre, so each point is converted:
    // α_mm = 1 − (1 − y / ss)^(ss / sx).
    // Two readings of that curve are possible: `unit` takes VTK at its word
    // (opacity per scaled unit, corrected to millimetres by the exponent
    // superSampling / spacing), `sample` takes the value as VTK's fixed-point
    // mapper uses it in practice, once per millimetre of ray. The measured
    // choice is recorded in docs/volume-metal-validation.md; the preference
    // HorosVolumeMetalOpacityModel switches it without a rebuild.
    NSMutableArray *opacity = [NSMutableArray array];
    double samplesPerMillimetre = HorosSamplesPerMillimetre(superSampling, sx);
    // A projection paints with the curve itself: outside composite blending
    // VTK neither divides it by superSampling nor corrects it for the step.
    NSMutableArray *projectionOpacity = [NSMutableArray array];
    for (NSString *point in currentOpacityArray) {
        NSPoint pt = NSPointFromString(point);
        double y = renderingMode == 0 && superSampling > 0 ? pt.y / superSampling : pt.y;
        double perMillimetre = 1 - pow(1 - MIN(1, MAX(0, y)), samplesPerMillimetre);
        [opacity addObject:@(pt.x - 1000)];
        [opacity addObject:@(perMillimetre)];
        [projectionOpacity addObject:@(pt.x - 1000)];
        [projectionOpacity addObject:@(pt.y)];
    }
    // VTK places the volume in the patient frame: user matrix of the DICOM
    // cosines and a position that resolves to the first slice's origin.
    NSArray *columns = [self mprVoxelToWorldTransform];
    if (columns.count != 16) return @{@"error": @"The volume transform is unavailable."};
    NSMutableArray *transform = [NSMutableArray arrayWithCapacity:16];
    for (int row = 0; row < 4; ++row)
        for (int column = 0; column < 4; ++column)
            [transform addObject:columns[column * 4 + row]];
    NSArray *clippingPlanes = HorosCuttingPlanes(volumeMapper, first.pwidth, first.pheight, pix.count);
    if (clippingPlanes.count > 4 * (NSUInteger)[HorosVolumeRenderer maximumClippingPlanes])
        return @{@"error": @"More than six crop planes use the original renderer."};
    float ambient = 0, diffuse = 0, specular = 0, power = 0;
    [self getShadingValues:&ambient :&diffuse :&specular :&power];
    NSArray *shading = @[@(volumeProperty->GetShade() ? 1 : 0), @(ambient), @(diffuse), @(specular), @(power)];
    return @{@"camera": view[@"camera"], @"near": view[@"near"], @"far": view[@"far"], @"level": @(wl), @"width": @(ww > 0 ? ww : 1),
             @"clut": [NSData dataWithBytes:rgba length:sizeof(rgba)], @"opacity": opacity, @"mode": @(renderingMode),
             @"shading": shading, @"clippingPlanes": clippingPlanes, @"movieIndex": @([controller curMovieIndex]),
             @"volume": volume, @"volumeWidth": @(first.pwidth), @"volumeHeight": @(first.pheight), @"volumeDepth": @(pix.count),
             @"spacing": @[@(sx), @(sy), @(dz)], @"transform": transform, @"superSampling": @(superSampling),
             @"sampleStep": @(projection && volumeMapper ? volumeMapper->GetSampleDistance() / factor :
                 HorosCompositeSampleStep(sx, sy, dz, superSampling)),
             @"anchoredProjection": @(projection), @"projectionOpacity": projectionOpacity,
             @"scalarBackground": @([controller minimumValue])};
}

- (NSDictionary *)horosFusedVolumeSnapshot {
    NSAssert([NSThread isMainThread], @"Volume snapshots require the main thread");
    if (!blendingVolume || !blendingVolumeMapper || !blendingVolumeProperty) return @{@"error": @"The fused series has no volume yet."};
    if (aCamera == nil || firstObject == nil || factor <= 0) return @{@"error": @"The 3D view has no volume yet."};
    // The fused voxels, their size and their placement are the MPR's (#658).
    NSDictionary *fused = [self horosMPRFusedVolume];
    if (fused[@"error"]) return fused;
    NSArray *pix = [controller horosVolumePixList];
    DCMPix *first = pix.firstObject ?: firstObject;
    double dz = first.sliceInterval != 0 ? fabs(first.sliceInterval) : fabs(first.sliceThickness);
    double sx = first.pixelSpacingX > 0 ? first.pixelSpacingX : 1, sy = first.pixelSpacingY > 0 ? first.pixelSpacingY : 1;
    if (dz <= 0 || !isfinite(dz)) return @{@"error": @"The volume spacing is not usable."};
    NSDictionary *view = [self horosVolumeCameraSnapshot];
    BOOL projection = renderingMode != 0;

    // setBlendingCLUT: and setBlendingWLWW:: build the fused colour function
    // from blendingtable over the fused window, as the image's is built.
    unsigned char rgba[1024];
    for (int i = 0; i < 256; ++i) {
        rgba[4 * i] = (unsigned char)fmin(255, fmax(0, blendingtable[i][0] * 255 + 0.5));
        rgba[4 * i + 1] = (unsigned char)fmin(255, fmax(0, blendingtable[i][1] * 255 + 0.5));
        rgba[4 * i + 2] = (unsigned char)fmin(255, fmax(0, blendingtable[i][2] * 255 + 0.5));
        rgba[4 * i + 3] = 255;
    }
    // The fused table is not divided by superSampling: VTK applies it per
    // sample as it is.
    NSMutableArray *opacity = [NSMutableArray array], *projectionOpacity = [NSMutableArray array];
    HorosFusedOpacityPoints(alpha, HorosSamplesPerMillimetre(superSampling, sx), opacity, projectionOpacity);
    // The renderer takes the transform row by row; the MPR's is column by column.
    NSArray *columns = fused[@"transform"];
    NSMutableArray *transform = [NSMutableArray arrayWithCapacity:16];
    for (int row = 0; row < 4; ++row)
        for (int column = 0; column < 4; ++column)
            [transform addObject:columns[column * 4 + row]];
    long width = [fused[@"width"] longValue], height = [fused[@"height"] longValue];
    NSUInteger depth = [fused[@"depth"] unsignedIntegerValue];
    NSArray *clippingPlanes = HorosCuttingPlanes(blendingVolumeMapper, width, height, depth);
    if (clippingPlanes.count > 4 * (NSUInteger)[HorosVolumeRenderer maximumClippingPlanes])
        return @{@"error": @"More than six crop planes use the original renderer."};
    // The fused property is shaded only if something turns it on; nothing in
    // the host does.
    NSArray *shading = @[@(blendingVolumeProperty->GetShade() ? 1 : 0), @(blendingVolumeProperty->GetAmbient()),
                         @(blendingVolumeProperty->GetDiffuse()), @(blendingVolumeProperty->GetSpecular()),
                         @(blendingVolumeProperty->GetSpecularPower())];
    return @{@"camera": view[@"camera"], @"near": view[@"near"], @"far": view[@"far"],
             @"level": @(blendingWl), @"width": @(blendingWw > 0 ? blendingWw : 1),
             @"clut": [NSData dataWithBytes:rgba length:sizeof(rgba)], @"opacity": opacity, @"mode": @(renderingMode),
             @"shading": shading, @"clippingPlanes": clippingPlanes,
             @"volume": fused[@"volume"], @"volumeWidth": @(width), @"volumeHeight": @(height), @"volumeDepth": @(depth),
             @"transform": transform, @"superSampling": @(superSampling),
             // The fused mapper samples in the same world frame and at the same
             // SampleDistance as the image's.
             @"sampleStep": @(projection ? blendingVolumeMapper->GetSampleDistance() / factor :
                 HorosCompositeSampleStep(sx, sy, dz, superSampling)),
             @"anchoredProjection": @(projection), @"projectionOpacity": projectionOpacity,
             // A ray that misses the fused volume leaves 0 in VTK's 16-bit image.
             @"scalarBackground": fused[@"background"]};
}

- (NSMenu *)menuForEvent:(NSEvent *)event {
    NSMenu *menu = [[[NSMenu alloc] init] autorelease];
    NSMenuItem *item = [menu addItemWithTitle:NSLocalizedString(@"Compare in Metal (3D)", nil)
                                       action:@selector(openVolumeMetalComparison:) keyEquivalent:@""];
    item.target = controller;
    return menu;
}

@end

@implementation VRController (HorosVolumeHost)

- (NSData *)horosVolumeData { return volumeData[curMovieIndex]; }
- (NSArray *)horosVolumePixList { return pixList[curMovieIndex]; }

- (void)openVolumeMetalComparison:(id)sender {
    [HorosVolumeComparison openWithSource:(id<HorosVolumeSource>)self];
}

- (NSDictionary *)horosVolumeSnapshot { return [[self view] horosVolumeSnapshot]; }

- (NSWindow *)volumeHostWindow { return self.window; }
- (NSView *)volumeHostView { return [self view]; }

- (NSString *)volumeStateSignature {
    NSDictionary *snapshot = [self horosVolumeSnapshot];
    if (snapshot[@"error"]) return snapshot[@"error"];
    NSMutableString *signature = [NSMutableString string];
    for (NSNumber *value in snapshot[@"camera"]) [signature appendFormat:@"%.4f,", value.doubleValue];
    [signature appendFormat:@"%@,%@,%@,%@,%@,%@,%@,%lu,", snapshot[@"near"], snapshot[@"far"], snapshot[@"level"], snapshot[@"width"],
        snapshot[@"mode"], snapshot[@"movieIndex"], snapshot[@"shading"], (unsigned long)[snapshot[@"clut"] hash]];
    [signature appendString:[snapshot[@"opacity"] componentsJoinedByString:@","]];
    [signature appendString:[snapshot[@"clippingPlanes"] componentsJoinedByString:@","]];
    // The fused series' window, CLUT and opacity change the picture too (#671).
    if ([self horosViewHasFusedVolume]) {
        NSDictionary *fused = [[self view] horosFusedVolumeSnapshot];
        [signature appendFormat:@"|%@,%@,%@,%lu,", fused[@"error"] ?: @"", fused[@"level"], fused[@"width"], (unsigned long)[fused[@"clut"] hash]];
        [signature appendString:[fused[@"opacity"] componentsJoinedByString:@","]];
    }
    return signature;
}

- (BOOL)horosViewHasFusedVolume { return [[self view] horosHasFusedVolume]; }

/// The comparison window's picture: the image's render, and with a fused
/// series, the fused render drawn over it as VTK draws it (#671).
- (NSData *)volumeMetalRenderWithWidth:(NSInteger)width height:(NSInteger)height reason:(NSString *__autoreleasing *)reason {
    NSError *error = nil;
    BOOL fusion = [self horosViewHasFusedVolume];
    NSMutableData *scalar = fusion ? [NSMutableData data] : nil;
    NSData *bytes = [self horosVolumeMetalRenderWithWidth:width height:height scalarOut:scalar error:&error];
    if (bytes && fusion) {
        NSDictionary *image = [self horosVolumeSnapshot], *snapshot = [[self view] horosFusedVolumeSnapshot];
        NSMutableData *fusedScalar = [NSMutableData data];
        NSData *fused = snapshot[@"error"] ? nil : [self horosFusedVolumeMetalRenderSnapshot:snapshot width:width height:height
                                                                                 imageRegion:@[] geometryDepth:nil scalarOut:fusedScalar error:&error];
        NSInteger mode = [image[@"mode"] integerValue];
        bytes = fused ? HorosComposedBGRA(HorosVolumePicture(bytes, scalar, mode ? image : nil),
                                          HorosVolumePicture(fused, fusedScalar, mode ? snapshot : nil)) : nil;
        if (!bytes && !error)
            error = [NSError errorWithDomain:@"HorosVolumeMetal" code:1
                                    userInfo:@{NSLocalizedDescriptionKey: snapshot[@"error"] ?: @"The fused series could not be drawn."}];
    }
    if (!bytes && reason) *reason = error.localizedDescription ?: [self horosVolumeMetalFallbackReason];
    return bytes;
}

- (NSData *)horosVolumeMetalRenderWithWidth:(NSInteger)width height:(NSInteger)height
                                   scalarOut:(NSMutableData *)scalarOut error:(NSError **)error {
    return [self horosVolumeMetalRenderWithCamera:nil near:0 far:-1 width:width height:height scalarOut:scalarOut error:error];
}

- (NSData *)horosVolumeMetalRenderWithCamera:(NSArray<NSNumber *> *)camera near:(double)near far:(double)far
                                        width:(NSInteger)width height:(NSInteger)height
                                    scalarOut:(NSMutableData *)scalarOut error:(NSError **)error {
    return [self horosVolumeMetalRenderWithCamera:camera near:near far:far width:width height:height
                                     imageRegion:@[] scalarOut:scalarOut error:error];
}

- (NSData *)horosVolumeMetalRenderWithCamera:(NSArray *)camera near:(double)near far:(double)far
                                     width:(NSInteger)width height:(NSInteger)height imageRegion:(NSArray *)imageRegion
                                 scalarOut:(NSMutableData *)scalarOut error:(NSError **)error {
    return [self horosVolumeMetalRenderWithCamera:camera near:near far:far width:width height:height
                                     imageRegion:imageRegion geometryDepth:nil scalarOut:scalarOut error:error];
}

- (NSData *)horosVolumeMetalRenderWithCamera:(NSArray *)camera near:(double)near far:(double)far
                                     width:(NSInteger)width height:(NSInteger)height imageRegion:(NSArray *)imageRegion
                             geometryDepth:(NSData *)geometryDepth
                                 scalarOut:(NSMutableData *)scalarOut error:(NSError **)error {
    NSAssert([NSThread isMainThread], @"Volume rendering requires the main thread");
    double snapshotFrom = [HorosMetalPerformanceTrace now];
    NSDictionary *snapshot = [self horosVolumeSnapshot];
    [HorosMetalPerformanceTrace recordHostOperation:@"vr.host_snapshot" startedAt:snapshotFrom];
    if (camera.count == 12 && !snapshot[@"error"]) {
        NSMutableDictionary *overridden = [NSMutableDictionary dictionaryWithDictionary:snapshot];
        overridden[@"camera"] = camera; overridden[@"near"] = @(near); overridden[@"far"] = @(far);
        snapshot = overridden;
    }
    return [self horosVolumeMetalRender:snapshot fused:NO width:width height:height imageRegion:imageRegion
                        geometryDepth:geometryDepth scalarOut:scalarOut error:error];
}

- (NSData *)horosFusedVolumeMetalRenderSnapshot:(NSDictionary *)snapshot width:(NSInteger)width height:(NSInteger)height
                                    imageRegion:(NSArray *)imageRegion geometryDepth:(NSData *)geometryDepth
                                      scalarOut:(NSMutableData *)scalarOut error:(NSError **)error {
    NSAssert([NSThread isMainThread], @"Volume rendering requires the main thread");
    return [self horosVolumeMetalRender:snapshot fused:YES width:width height:height imageRegion:imageRegion
                        geometryDepth:geometryDepth scalarOut:scalarOut error:error];
}

/// Renders one volume's snapshot with its own renderer: the image's, or the
/// fused series', each holding its own volume on the GPU (#671).
- (NSData *)horosVolumeMetalRender:(NSDictionary *)snapshot fused:(BOOL)fused width:(NSInteger)width height:(NSInteger)height
                       imageRegion:(NSArray *)imageRegion geometryDepth:(NSData *)geometryDepth
                         scalarOut:(NSMutableData *)scalarOut error:(NSError **)error {
    const void *rendererSlot = fused ? &fusedRendererKey : &rendererKey, *uploadedSlot = fused ? &fusedUploadedKey : &uploadedKey;
    NSString *reason = snapshot[@"error"];
    HorosVolumeRenderer *renderer = objc_getAssociatedObject(self, rendererSlot);
    if (!reason && !renderer) {
        NSError *failure = nil;
        renderer = [HorosVolumeRenderer makeAndReturnError:&failure];
        if (renderer) {
            objc_setAssociatedObject(self, rendererSlot, renderer, OBJC_ASSOCIATION_RETAIN_NONATOMIC);
            [[NSNotificationCenter defaultCenter] removeObserver:self name:NSWindowWillCloseNotification object:self.window];
            [[NSNotificationCenter defaultCenter] addObserver:self selector:@selector(horosVolumeMetalWindowWillClose:)
                                                         name:NSWindowWillCloseNotification object:self.window];
        } else reason = failure.localizedDescription ?: @"Metal is unavailable.";
    }
    if (!reason) {
        NSData *volume = snapshot[@"volume"];
        NSInteger w = [snapshot[@"volumeWidth"] integerValue], h = [snapshot[@"volumeHeight"] integerValue], d = [snapshot[@"volumeDepth"] integerValue];
        NSUInteger expected = [HorosVolumeAllocation byteCountForWidth:w height:h slices:d bytesPerVoxel:4];
        if (expected == 0 || volume.length < expected) reason = @"The volume bytes do not match the slice list.";
        else if (objc_getAssociatedObject(self, uploadedSlot) != volume || !renderer.isReady) {
            NSData *slices = volume.length == expected ? volume : [NSData dataWithBytesNoCopy:(void *)volume.bytes length:expected freeWhenDone:NO];
            NSError *failure = nil;
            if ([renderer uploadVolume:slices width:w height:h depth:d transform:snapshot[@"transform"] error:&failure]) {
                objc_setAssociatedObject(self, uploadedSlot, volume, OBJC_ASSOCIATION_RETAIN_NONATOMIC);
            } else {
                objc_setAssociatedObject(self, uploadedSlot, nil, OBJC_ASSOCIATION_RETAIN_NONATOMIC);
                reason = failure.localizedDescription ?: @"The volume could not be uploaded.";
            }
        }
    }
    NSData *bytes = nil;
    if (!reason) {
        NSError *failure = nil;
        bytes = [renderer renderWithCamera:snapshot[@"camera"] near:[snapshot[@"near"] doubleValue] far:[snapshot[@"far"] doubleValue]
                                     level:[snapshot[@"level"] doubleValue] width:[snapshot[@"width"] doubleValue] clut:snapshot[@"clut"]
                             opacityPoints:snapshot[@"opacity"] mode:[snapshot[@"mode"] integerValue] shading:snapshot[@"shading"]
                                      crop:@[] clippingPlanes:snapshot[@"clippingPlanes"] width:width height:height
                                sampleStep:[snapshot[@"sampleStep"] doubleValue]
                          scalarBackground:[snapshot[@"scalarBackground"] doubleValue]
                        anchoredProjection:[snapshot[@"anchoredProjection"] boolValue] imageRegion:imageRegion
                             geometryDepth:geometryDepth scalarOut:scalarOut error:&failure];
        if (bytes) objc_setAssociatedObject(self, fused ? &fusedMillisecondsKey : &millisecondsKey, @(renderer.lastMilliseconds), OBJC_ASSOCIATION_RETAIN_NONATOMIC);
        else reason = failure.localizedDescription ?: @"The render produced no image.";
    }
    objc_setAssociatedObject(self, fused ? &fusedReasonKey : &reasonKey, reason, OBJC_ASSOCIATION_COPY_NONATOMIC);
    if (!bytes && error) *error = [NSError errorWithDomain:@"HorosVolumeMetal" code:1 userInfo:@{NSLocalizedDescriptionKey: reason ?: @""}];
    return bytes;
}

- (NSString *)horosVolumeMetalFallbackReason { return objc_getAssociatedObject(self, &reasonKey); }

- (NSString *)horosFusedVolumeMetalFallbackReason { return objc_getAssociatedObject(self, &fusedReasonKey); }

- (double)horosVolumeMetalLastMilliseconds {
    NSNumber *value = objc_getAssociatedObject(self, &millisecondsKey);
    return value ? value.doubleValue : -1;
}

- (double)horosFusedVolumeMetalLastMilliseconds {
    NSNumber *value = objc_getAssociatedObject(self, &fusedMillisecondsKey);
    return value ? value.doubleValue : -1;
}

- (NSInteger)horosVolumeMetalBytes {
    HorosVolumeRenderer *renderer = objc_getAssociatedObject(self, &rendererKey);
    HorosVolumeRenderer *fused = objc_getAssociatedObject(self, &fusedRendererKey);
    return renderer.volumeBytes + fused.volumeBytes;
}

- (void)horosVolumeMetalRelease {
    HorosVolumeRenderer *renderer = objc_getAssociatedObject(self, &rendererKey);
    [renderer releaseVolume];
    objc_setAssociatedObject(self, &uploadedKey, nil, OBJC_ASSOCIATION_RETAIN_NONATOMIC);
    objc_setAssociatedObject(self, &millisecondsKey, nil, OBJC_ASSOCIATION_RETAIN_NONATOMIC);
    [self horosFusedVolumeMetalRelease];
}

/// Drops the fused series' renderer and its volume; a later fusion makes a
/// new one (#671).
- (void)horosFusedVolumeMetalRelease {
    HorosVolumeRenderer *renderer = objc_getAssociatedObject(self, &fusedRendererKey);
    if (!renderer) return;
    [renderer releaseVolume];
    objc_setAssociatedObject(self, &fusedRendererKey, nil, OBJC_ASSOCIATION_RETAIN_NONATOMIC);
    objc_setAssociatedObject(self, &fusedUploadedKey, nil, OBJC_ASSOCIATION_RETAIN_NONATOMIC);
    objc_setAssociatedObject(self, &fusedMillisecondsKey, nil, OBJC_ASSOCIATION_RETAIN_NONATOMIC);
    objc_setAssociatedObject(self, &fusedReasonKey, nil, OBJC_ASSOCIATION_COPY_NONATOMIC);
}

- (void)horosVolumeMetalWindowWillClose:(NSNotification *)note {
    [[NSNotificationCenter defaultCenter] removeObserver:self name:NSWindowWillCloseNotification object:note.object];
    [self horosVolumeMetalRelease];
    objc_setAssociatedObject(self, &rendererKey, nil, OBJC_ASSOCIATION_RETAIN_NONATOMIC);
    objc_setAssociatedObject(self, &fusedRendererKey, nil, OBJC_ASSOCIATION_RETAIN_NONATOMIC);
}

@end
