#import "VRHostBridge.h"
#import "DCMPix.h"
#import "Horos-Swift.h"
#import <objc/runtime.h>
#include <vtkCamera.h>
#include <vtkVolumeProperty.h>
#include <vtkBoxWidget.h>
#include <vtkVolume.h>
#include <vtkFixedPointRayCastImage.h>
#include <vtkTextActor.h>

static char rendererKey, uploadedKey, reasonKey, millisecondsKey;

@interface VRController (HorosVolumeHostPrivate) <HorosVolumeSource>
- (NSData *)horosVolumeData;
- (NSArray *)horosVolumePixList;
- (NSData *)horosVolumeMetalRenderWithCamera:(NSArray *)camera near:(double)near far:(double)far
                                     width:(NSInteger)width height:(NSInteger)height imageRegion:(NSArray *)imageRegion
                                 scalarOut:(NSMutableData *)scalarOut error:(NSError **)error;
@end

@implementation VRView (HorosVolumeHost)

- (BOOL)horosRenderMetalImageForMapper:(vtkHorosFixedPointVolumeRayCastMapper *)mapper
                            renderer:(vtkRenderer *)renderer volume:(vtkVolume *)renderVolume {
    if (engine != 2 || renderer != aRenderer || renderVolume != self.volume ||
        [[controller style] isEqualToString:@"noNib"]) return NO;
    @autoreleasepool {
        NSString *reason = nil;
        if (renderingMode != 0) reason = @"This projection uses the original renderer.";
        else if (clipRangeActivated || mapper->GetCropping()) reason = @"Clipping uses the original renderer.";
        else if (isRGB || blendingVolume || blendingController || advancedCLUT) reason = [self horosVolumeSnapshot][@"error"];
        if (!reason && !mapper->PrepareMPRGeometry(renderer, renderVolume))
            reason = @"This camera or crop uses the original renderer.";

        NSData *pixels = nil;
        NSMutableData *opacity = [NSMutableData data];
        vtkFixedPointRayCastImage *image = mapper->GetRayCastImage();
        int *size = image->GetImageInUseSize();
        if (!reason) {
            int *viewport = image->GetImageViewportSize(), *origin = image->GetImageOrigin();
            NSArray *region = @[@(viewport[0]), @(viewport[1]), @(origin[0]), @(viewport[1] - origin[1] - size[1])];
            NSError *error = nil;
            pixels = [controller horosVolumeMetalRenderWithCamera:nil near:0 far:-1 width:size[0] height:size[1]
                                                     imageRegion:region scalarOut:opacity error:&error];
            if (!pixels) reason = error.localizedDescription ?: @"Metal could not render this volume.";
        }
        NSUInteger count = (NSUInteger)size[0] * size[1];
        BOOL ready = pixels.length == count * 4 && opacity.length == count * sizeof(float) && count > 0;
        if (!reason && !ready) reason = @"Metal returned an incomplete image.";
        objc_setAssociatedObject(controller, &reasonKey, reason, OBJC_ASSOCIATION_COPY_NONATOMIC);
        if (textWLWW) {
            NSString *status = reason ? [@"CPU fallback: " stringByAppendingString:reason] : @"Metal";
            NSString *label = [NSString stringWithFormat:@"WL: %.4g WW: %.4g\n%@", wl, ww, status];
            textWLWW->SetInput(label.UTF8String);
        }
        if (reason) return NO;

        image->ClearImage();
        const unsigned char *bgra = (const unsigned char *)pixels.bytes;
        const float *alpha = (const float *)opacity.bytes;
        unsigned short *rgba = image->GetImage();
        int stride = image->GetImageMemorySize()[0];
        for (int y = 0; y < size[1]; ++y)
            for (int x = 0; x < size[0]; ++x) {
                NSUInteger source = (NSUInteger)y * size[0] + x;
                NSUInteger destination = ((NSUInteger)(size[1] - 1 - y) * stride + x) * 4;
                // VTK displays premultiplied RGBA in its 15-bit fixed-point range.
                rgba[destination] = (bgra[source * 4 + 2] * 32767u + 127u) / 255u;
                rgba[destination + 1] = (bgra[source * 4 + 1] * 32767u + 127u) / 255u;
                rgba[destination + 2] = (bgra[source * 4] * 32767u + 127u) / 255u;
                rgba[destination + 3] = (unsigned short)(fminf(1, fmaxf(0, alpha[source])) * 32767 + 0.5f);
            }
        return YES;
    }
}

- (NSDictionary *)horosVolumeSnapshot {
    NSAssert([NSThread isMainThread], @"Volume snapshots require the main thread");
    if (isRGB) return @{@"error": @"RGB volumes keep the original renderer."};
    if (blendingVolume || blendingController) return @{@"error": @"Fusion keeps the original renderer."};
    if (advancedCLUT) return @{@"error": @"The 16-bit CLUT keeps the original renderer."};
    if (aCamera == nil || volumeProperty == nil || firstObject == nil || factor <= 0) return @{@"error": @"The 3D view has no volume yet."};
    NSArray *pix = [controller horosVolumePixList];
    NSData *volume = [controller horosVolumeData];
    if (pix.count == 0 || volume == nil) return @{@"error": @"The 3D view has no volume yet."};
    DCMPix *first = pix.firstObject;
    double dz = first.sliceInterval != 0 ? fabs(first.sliceInterval) : fabs(first.sliceThickness);
    double sx = first.pixelSpacingX > 0 ? first.pixelSpacingX : 1, sy = first.pixelSpacingY > 0 ? first.pixelSpacingY : 1;
    if (dz <= 0 || !isfinite(dz)) return @{@"error": @"The volume spacing is not usable."};

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
    // The curve value divided by superSampling is VTK's opacity per ray
    // sample; how many such samples make a millimetre decides the picture.
    // Nominally superSampling / spacing (one sample per scaled unit), in
    // practice the mapper's sample distance (BESTRENDERING, 1.6 units) gives
    // superSampling / (spacing × 1.6). The exponent is measured against VTK
    // in docs/volume-metal-validation.md; HorosVolumeMetalOpacityExponent
    // overrides it without a rebuild.
    NSMutableArray *opacity = [NSMutableArray array];
    double rayStep = [[NSUserDefaults standardUserDefaults] floatForKey:@"BESTRENDERING"];
    if (rayStep <= 0) rayStep = 1.6;
    double samplesPerMillimetre = superSampling > 0 ? superSampling / (sx * rayStep) : 1;
    double override = [[NSUserDefaults standardUserDefaults] doubleForKey:@"HorosVolumeMetalOpacityExponent"];
    if (override > 0) samplesPerMillimetre = override;
    for (NSString *point in currentOpacityArray) {
        NSPoint pt = NSPointFromString(point);
        double y = renderingMode == 0 && superSampling > 0 ? pt.y / superSampling : pt.y;
        double perMillimetre = 1 - pow(1 - MIN(1, MAX(0, y)), samplesPerMillimetre);
        [opacity addObject:@(pt.x - 1000)];
        [opacity addObject:@(perMillimetre)];
    }
    // VTK places the volume in the patient frame: user matrix of the DICOM
    // cosines and a position that resolves to the first slice's origin.
    NSArray *columns = [self mprVoxelToWorldTransform];
    if (columns.count != 16) return @{@"error": @"The volume transform is unavailable."};
    NSMutableArray *transform = [NSMutableArray arrayWithCapacity:16];
    for (int row = 0; row < 4; ++row)
        for (int column = 0; column < 4; ++column)
            [transform addObject:columns[column * 4 + row]];
    NSMutableArray *crop = [NSMutableArray array];
    if (croppingBox && croppingBox->GetEnabled() && volume) {
        double bounds[6];
        if ([VRView getCroppingBox:bounds :self.volume :croppingBox]) {
            // bounds: xmin, xmax, ymin, ymax, zmin, zmax in the scaled local frame; to voxel indices.
            double spacing[3] = {sx, sy, dz};
            for (int axis = 0; axis < 3; ++axis) [crop addObject:@(bounds[2 * axis] / factor / spacing[axis])];
            for (int axis = 0; axis < 3; ++axis) [crop addObject:@(bounds[2 * axis + 1] / factor / spacing[axis])];
        }
    }
    float ambient = 0, diffuse = 0, specular = 0, power = 0;
    [self getShadingValues:&ambient :&diffuse :&specular :&power];
    NSArray *shading = @[@(volumeProperty->GetShade() ? 1 : 0), @(ambient), @(diffuse), @(specular), @(power)];
    return @{@"camera": camera, @"near": @(near), @"far": @(far), @"level": @(wl), @"width": @(ww > 0 ? ww : 1),
             @"clut": [NSData dataWithBytes:rgba length:sizeof(rgba)], @"opacity": opacity, @"mode": @(renderingMode),
             @"shading": shading, @"crop": crop, @"movieIndex": @([controller curMovieIndex]),
             @"volume": volume, @"volumeWidth": @(first.pwidth), @"volumeHeight": @(first.pheight), @"volumeDepth": @(pix.count),
             @"spacing": @[@(sx), @(sy), @(dz)], @"transform": transform, @"superSampling": @(superSampling),
             // VTK samples every unit of its scaled frame (pixelSpacingX / superSampling
             // millimetres); compositing with a coarser step locks a boundary sample's
             // colour into the pixel, so the renderer walks the same distance.
             @"sampleStep": @(superSampling > 0 ? MIN(sx, MIN(sy, dz)) / superSampling : MIN(sx, MIN(sy, dz))),
             @"scalarBackground": @([controller minimumValue])};
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
    [signature appendString:[snapshot[@"crop"] componentsJoinedByString:@","]];
    return signature;
}

- (NSData *)volumeMetalRenderWithWidth:(NSInteger)width height:(NSInteger)height reason:(NSString *__autoreleasing *)reason {
    NSError *error = nil;
    NSData *bytes = [self horosVolumeMetalRenderWithWidth:width height:height scalarOut:nil error:&error];
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
    NSAssert([NSThread isMainThread], @"Volume rendering requires the main thread");
    NSDictionary *snapshot = [self horosVolumeSnapshot];
    if (camera.count == 12 && !snapshot[@"error"]) {
        NSMutableDictionary *overridden = [NSMutableDictionary dictionaryWithDictionary:snapshot];
        overridden[@"camera"] = camera; overridden[@"near"] = @(near); overridden[@"far"] = @(far);
        snapshot = overridden;
    }
    NSString *reason = snapshot[@"error"];
    HorosVolumeRenderer *renderer = objc_getAssociatedObject(self, &rendererKey);
    if (!reason && !renderer) {
        NSError *failure = nil;
        renderer = [HorosVolumeRenderer makeAndReturnError:&failure];
        if (renderer) {
            objc_setAssociatedObject(self, &rendererKey, renderer, OBJC_ASSOCIATION_RETAIN_NONATOMIC);
            [[NSNotificationCenter defaultCenter] addObserver:self selector:@selector(horosVolumeMetalWindowWillClose:)
                                                         name:NSWindowWillCloseNotification object:self.window];
        } else reason = failure.localizedDescription ?: @"Metal is unavailable.";
    }
    if (!reason) {
        NSData *volume = snapshot[@"volume"];
        NSInteger w = [snapshot[@"volumeWidth"] integerValue], h = [snapshot[@"volumeHeight"] integerValue], d = [snapshot[@"volumeDepth"] integerValue];
        NSUInteger expected = [HorosVolumeAllocation byteCountForWidth:w height:h slices:d bytesPerVoxel:4];
        if (expected == 0 || volume.length < expected) reason = @"The volume bytes do not match the slice list.";
        else if (objc_getAssociatedObject(self, &uploadedKey) != volume || !renderer.isReady) {
            NSData *slices = volume.length == expected ? volume : [NSData dataWithBytesNoCopy:(void *)volume.bytes length:expected freeWhenDone:NO];
            NSError *failure = nil;
            if ([renderer uploadVolume:slices width:w height:h depth:d transform:snapshot[@"transform"] error:&failure]) {
                objc_setAssociatedObject(self, &uploadedKey, volume, OBJC_ASSOCIATION_RETAIN_NONATOMIC);
            } else {
                objc_setAssociatedObject(self, &uploadedKey, nil, OBJC_ASSOCIATION_RETAIN_NONATOMIC);
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
                                      crop:snapshot[@"crop"] width:width height:height sampleStep:[snapshot[@"sampleStep"] doubleValue]
                          scalarBackground:[snapshot[@"scalarBackground"] doubleValue] imageRegion:imageRegion scalarOut:scalarOut error:&failure];
        if (bytes) objc_setAssociatedObject(self, &millisecondsKey, @(renderer.lastMilliseconds), OBJC_ASSOCIATION_RETAIN_NONATOMIC);
        else reason = failure.localizedDescription ?: @"The render produced no image.";
    }
    objc_setAssociatedObject(self, &reasonKey, reason, OBJC_ASSOCIATION_COPY_NONATOMIC);
    if (!bytes && error) *error = [NSError errorWithDomain:@"HorosVolumeMetal" code:1 userInfo:@{NSLocalizedDescriptionKey: reason ?: @""}];
    return bytes;
}

- (NSString *)horosVolumeMetalFallbackReason { return objc_getAssociatedObject(self, &reasonKey); }

- (double)horosVolumeMetalLastMilliseconds {
    NSNumber *value = objc_getAssociatedObject(self, &millisecondsKey);
    return value ? value.doubleValue : -1;
}

- (NSInteger)horosVolumeMetalBytes {
    HorosVolumeRenderer *renderer = objc_getAssociatedObject(self, &rendererKey);
    return renderer.volumeBytes;
}

- (void)horosVolumeMetalRelease {
    HorosVolumeRenderer *renderer = objc_getAssociatedObject(self, &rendererKey);
    [renderer releaseVolume];
    objc_setAssociatedObject(self, &uploadedKey, nil, OBJC_ASSOCIATION_RETAIN_NONATOMIC);
    objc_setAssociatedObject(self, &millisecondsKey, nil, OBJC_ASSOCIATION_RETAIN_NONATOMIC);
}

- (void)horosVolumeMetalWindowWillClose:(NSNotification *)note {
    [[NSNotificationCenter defaultCenter] removeObserver:self name:NSWindowWillCloseNotification object:note.object];
    [self horosVolumeMetalRelease];
    objc_setAssociatedObject(self, &rendererKey, nil, OBJC_ASSOCIATION_RETAIN_NONATOMIC);
}

@end
