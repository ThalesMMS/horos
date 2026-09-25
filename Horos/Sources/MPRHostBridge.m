#import "MPRHostBridge.h"
#import "PlanarHostBridge.h"
#import "VRController.h"
#import "VRView.h"
#import "VRHostBridge.h"
#import "DCMPix.h"
#import "Horos-Swift.h"
#import <objc/runtime.h>

static char enabledKey, reslicerKey, uploadedKey, reasonKey, millisecondsKey, fusedReslicerKey, fusedUploadedKey, fusedPlaneKey;
static char displayPlaneKey;

static NSString * const HorosMPRCubicDisplayKey = @"HorosMPRCubicDisplay";
// The MPR always draws a slab: its thinnest, the one it opens with, is the
// slice interval up to 1 mm (-[MPRController initWithDCMPixList:...]). The
// cubic display plane covers that one; a thicker slab is a projection the
// user asked for, costs many samples per pixel, and stays linear (#702).
static const float HorosMPRCubicDisplayMaximumSlab = 1.0f + 1e-3f;

@interface MPRController (HorosMPRHostPrivate)
- (HorosMPRReslicer *)horosMPRReslicerForCurrentVolume:(NSString **)reason;
- (HorosMPRReslicer *)horosMPRFusedReslicerForVolume:(NSDictionary *)volume reason:(NSString **)reason;
- (DCMPix *)horosMPRFirstPix;
- (float)horosMPRBackground;
- (void)horosMPRWindowWillClose:(NSNotification *)note;
@end

@implementation MPRController (HorosMPRHost)

- (BOOL)horosMPRMetalEnabled {
    NSNumber *enabled = objc_getAssociatedObject(self, &enabledKey);
    return enabled ? enabled.boolValue : YES;
}

- (void)toggleMPRMetal:(id)sender {
    BOOL enabled = !self.horosMPRMetalEnabled;
    objc_setAssociatedObject(self, &enabledKey, @(enabled), OBJC_ASSOCIATION_RETAIN_NONATOMIC);
    if (!enabled) {
        [self horosMPRReleaseVolume];
        objc_setAssociatedObject(self, &reasonKey, nil, OBJC_ASSOCIATION_COPY_NONATOMIC);
    }
    // The same sequence the thick-slab mode change uses: a forced camera
    // update makes each view reconstruct its plane once.
    for (MPRDCMView *view in @[mprView1, mprView2, mprView3]) {
        if (!enabled) [view horosSetPlanarFallbackReason:nil];
        [view restoreCamera];
        view.camera.forceUpdate = YES;
        [view updateViewMPR];
    }
}

- (NSString *)horosMPRFallbackReason { return objc_getAssociatedObject(self, &reasonKey); }

- (BOOL)horosMPRCubicDisplay {
    return [[NSUserDefaults standardUserDefaults] boolForKey:HorosMPRCubicDisplayKey];
}

- (void)toggleMPRCubicDisplay:(id)sender {
    [[NSUserDefaults standardUserDefaults] setBool:!self.horosMPRCubicDisplay forKey:HorosMPRCubicDisplayKey];
    for (MPRDCMView *view in @[mprView1, mprView2, mprView3]) {
        [view restoreCamera];
        view.camera.forceUpdate = YES;
        [view updateViewMPR];
    }
}

- (double)horosMPRLastMilliseconds {
    NSNumber *value = objc_getAssociatedObject(self, &millisecondsKey);
    return value ? value.doubleValue : -1;
}

- (NSInteger)horosMPRVolumeBytes {
    HorosMPRReslicer *reslicer = objc_getAssociatedObject(self, &reslicerKey);
    HorosMPRReslicer *fused = objc_getAssociatedObject(self, &fusedReslicerKey);
    return reslicer.volumeBytes + fused.volumeBytes;
}

- (void)horosMPRReleaseVolume {
    HorosMPRReslicer *reslicer = objc_getAssociatedObject(self, &reslicerKey);
    [reslicer releaseVolume];
    [(HorosMPRReslicer *)objc_getAssociatedObject(self, &fusedReslicerKey) releaseVolume];
    objc_setAssociatedObject(self, &uploadedKey, nil, OBJC_ASSOCIATION_RETAIN_NONATOMIC);
    objc_setAssociatedObject(self, &fusedUploadedKey, nil, OBJC_ASSOCIATION_RETAIN_NONATOMIC);
    objc_setAssociatedObject(self, &millisecondsKey, nil, OBJC_ASSOCIATION_RETAIN_NONATOMIC);
}

- (void)horosMPRWindowWillClose:(NSNotification *)note {
    [[NSNotificationCenter defaultCenter] removeObserver:self name:NSWindowWillCloseNotification object:note.object];
    [self horosMPRReleaseVolume];
    objc_setAssociatedObject(self, &reslicerKey, nil, OBJC_ASSOCIATION_RETAIN_NONATOMIC);
    objc_setAssociatedObject(self, &fusedReslicerKey, nil, OBJC_ASSOCIATION_RETAIN_NONATOMIC);
}

/// The fused series' own reslicer (#658), uploaded once per buffer and placement.
- (HorosMPRReslicer *)horosMPRFusedReslicerForVolume:(NSDictionary *)volume reason:(NSString **)reason {
    HorosMPRReslicer *reslicer = objc_getAssociatedObject(self, &fusedReslicerKey);
    if (!reslicer) {
        NSError *error = nil;
        reslicer = [HorosMPRReslicer makeAndReturnError:&error];
        if (!reslicer) { *reason = error.localizedDescription ?: @"Metal is unavailable."; return nil; }
        objc_setAssociatedObject(self, &fusedReslicerKey, reslicer, OBJC_ASSOCIATION_RETAIN_NONATOMIC);
    }
    NSData *voxels = volume[@"volume"];
    NSArray *transform = volume[@"transform"];
    NSArray *uploaded = objc_getAssociatedObject(self, &fusedUploadedKey);
    if (!reslicer.isReady || uploaded.firstObject != voxels || ![uploaded.lastObject isEqual:transform]) {
        long width = [volume[@"width"] longValue], height = [volume[@"height"] longValue], depth = [volume[@"depth"] longValue];
        NSUInteger expected = [HorosVolumeAllocation byteCountForWidth:width height:height slices:depth bytesPerVoxel:4];
        NSData *slices = voxels.length == expected ? voxels : [NSData dataWithBytesNoCopy:(void *)voxels.bytes length:expected freeWhenDone:NO];
        NSError *error = nil;
        if (![reslicer uploadVolume:slices width:width height:height depth:depth voxelToWorld:transform error:&error]) {
            objc_setAssociatedObject(self, &fusedUploadedKey, nil, OBJC_ASSOCIATION_RETAIN_NONATOMIC);
            *reason = error.localizedDescription ?: @"The fused volume could not be uploaded.";
            return nil;
        }
        objc_setAssociatedObject(self, &fusedUploadedKey, @[voxels, transform], OBJC_ASSOCIATION_RETAIN_NONATOMIC);
    }
    return reslicer;
}

- (float)horosMPRBackground { return [hiddenVRController minimumValue]; }

- (DCMPix *)horosMPRFirstPix { return [pixList[curMovieIndex] firstObject]; }

/// Upload in the same world frame as the host's camera, including the volume's
/// position and orientation. Slice bytes stay in the viewer's existing order.
- (HorosMPRReslicer *)horosMPRReslicerForCurrentVolume:(NSString **)reason {
    NSArray *pix = pixList[curMovieIndex];
    NSData *volume = volumeData[curMovieIndex];
    DCMPix *first = pix.firstObject;
    if (!first || !volume) { *reason = @"The reconstruction has no volume."; return nil; }
    if (first.isRGB) { *reason = @"RGB volumes keep the original renderer."; return nil; }
    double dz = first.sliceInterval;
    if (dz == 0) dz = first.sliceThickness;
    if (dz < 0) { *reason = @"A reversed stack keeps the original renderer."; return nil; }
    double sx = first.pixelSpacingX, sy = first.pixelSpacingY;
    if (sx <= 0 || sy <= 0) { sx = 1; sy = 1; }
    if (dz <= 0 || !isfinite(dz) || !isfinite(sx) || !isfinite(sy)) { *reason = @"The volume spacing is not usable."; return nil; }
    NSUInteger expected = [HorosVolumeAllocation byteCountForWidth:first.pwidth height:first.pheight slices:pix.count bytesPerVoxel:4];
    // The viewer's buffer can be larger than the slices it holds; VTK imports
    // the first width × height × count values from it, and so does the engine.
    if (expected == 0 || volume.length < expected) { *reason = @"The volume bytes do not match the slice list."; return nil; }

    HorosMPRReslicer *reslicer = objc_getAssociatedObject(self, &reslicerKey);
    if (!reslicer) {
        NSError *error = nil;
        reslicer = [HorosMPRReslicer makeAndReturnError:&error];
        if (!reslicer) { *reason = error.localizedDescription ?: @"Metal is unavailable."; return nil; }
        objc_setAssociatedObject(self, &reslicerKey, reslicer, OBJC_ASSOCIATION_RETAIN_NONATOMIC);
        [[NSNotificationCenter defaultCenter] addObserver:self selector:@selector(horosMPRWindowWillClose:)
                                                     name:NSWindowWillCloseNotification object:self.window];
    }
    // One upload per volume buffer: a 4D phase change or a new series hands
    // the host a different NSData, which is what invalidates the texture.
    if (objc_getAssociatedObject(self, &uploadedKey) != volume || !reslicer.isReady) {
        NSError *error = nil;
        NSData *slices = volume.length == expected ? volume : [NSData dataWithBytesNoCopy:(void *)volume.bytes length:expected freeWhenDone:NO];
        NSArray *transform = [mprView1.vrView mprVoxelToWorldTransform];
        if (![reslicer uploadVolume:slices width:first.pwidth height:first.pheight depth:pix.count
                       voxelToWorld:transform ?: @[] error:&error]) {
            objc_setAssociatedObject(self, &uploadedKey, nil, OBJC_ASSOCIATION_RETAIN_NONATOMIC);
            *reason = error.localizedDescription ?: @"The volume could not be uploaded.";
            return nil;
        }
        objc_setAssociatedObject(self, &uploadedKey, volume, OBJC_ASSOCIATION_RETAIN_NONATOMIC);
    }
    return reslicer;
}

@end

/// VTK casts each ray through the centre of its ray-cast pixel; -getOrigin:
/// gives the image's upper-left corner. The reslicer samples pixel (0, 0) at
/// the origin it is given, so it gets that centre: half a pixel along the row
/// and the column (#658).
static NSArray *HorosMPRPixelCentre(const float corner[3], const float cosines[9], double spacing) {
    return @[@(corner[0] + 0.5 * spacing * (cosines[0] + cosines[3])),
             @(corner[1] + 0.5 * spacing * (cosines[1] + cosines[4])),
             @(corner[2] + 0.5 * spacing * (cosines[2] + cosines[5]))];
}

/// A fused plane resliced with the image's, owned until the host's blending
/// branch takes it: the malloc-owned buffer VTK's own path would hand over.
@interface HorosMPRFusedPlane : NSObject {
@public
    float *pixels;
    long width, height;
    double milliseconds;
}
@end
@implementation HorosMPRFusedPlane
- (void)dealloc { free(pixels); [super dealloc]; }
@end

@implementation MPRDCMView (HorosMPRHost)

- (NSMenu *)menuForEvent:(NSEvent *)event {
    NSMenu *menu = [super menuForEvent:event] ?: [[[NSMenu alloc] init] autorelease];
    if (menu.numberOfItems) [menu addItem:[NSMenuItem separatorItem]];
    NSMenuItem *item = [menu addItemWithTitle:NSLocalizedString(@"Use Metal in MPR", nil)
                                       action:@selector(toggleMPRMetal:) keyEquivalent:@""];
    item.target = windowController;
    item.state = windowController.horosMPRMetalEnabled ? NSControlStateValueOn : NSControlStateValueOff;
    NSMenuItem *cubic = [menu addItemWithTitle:NSLocalizedString(@"Cubic Interpolation for MPR Display", nil)
                                        action:@selector(toggleMPRCubicDisplay:) keyEquivalent:@""];
    cubic.target = windowController;
    cubic.state = windowController.horosMPRCubicDisplay ? NSControlStateValueOn : NSControlStateValueOff;
    return menu;
}

/// The series fused over this plane (#658), resliced in Metal where VTK
/// reslices it: on the blending mapper's own grid, origin and sample distance,
/// with the same camera, slab and mode, from the fused volume in its own frame.
/// Nil, with the reason, when that plane stays with VTK.
- (HorosMPRFusedPlane *)horosMPRFusedPlane:(NSString **)reason {
    MPRController *controller = windowController;
    NSDictionary *volume = [vrView horosMPRFusedVolume];
    if (volume[@"error"]) { *reason = volume[@"error"]; return nil; }
    long width = 0, height = 0;
    NSString *geometry = [vrView horosMPRFusedGeometryRefusalWidth:&width height:&height];
    if (geometry) { *reason = geometry; return nil; }
    HorosMPRReslicer *reslicer = [controller horosMPRFusedReslicerForVolume:volume reason:reason];
    if (!reslicer) return nil;
    float cosines[9];
    float position[3];
    [vrView getOrientation:cosines];
    [vrView getOrigin:position windowCentered:YES sliceMiddle:YES blendedView:YES];
    double spacing = [vrView getResolution] * [vrView blendingImageSampleDistance];
    HorosMPRFusedPlane *plane = [[[HorosMPRFusedPlane alloc] init] autorelease];
    plane->pixels = malloc((size_t)width * (size_t)height * sizeof(float));
    if (!plane->pixels) { *reason = @"The fused plane could not be allocated."; return nil; }
    NSError *error = nil;
    if (![reslicer resliceWithOrigin:HorosMPRPixelCentre(position, cosines, spacing)
                         orientation:@[@(cosines[0]), @(cosines[1]), @(cosines[2]), @(cosines[3]), @(cosines[4]), @(cosines[5]),
                                       @(cosines[6]), @(cosines[7]), @(cosines[8])]
                             spacing:spacing width:width height:height thickness:[vrView getClippingRangeThicknessInMm]
                          sampleStep:[volume[@"sampleStep"] doubleValue] projection:controller.clippingRangeMode
                          background:[volume[@"background"] floatValue] into:plane->pixels error:&error]) {
        *reason = error.localizedDescription ?: @"The fused reslice produced no plane.";
        return nil;
    }
    plane->width = width;
    plane->height = height;
    plane->milliseconds = reslicer.lastMilliseconds;
    return plane;
}

- (float *)horosMPRTakeFusedImageWidth:(long *)width height:(long *)height {
    HorosMPRFusedPlane *plane = objc_getAssociatedObject(self, &fusedPlaneKey);
    float *image = plane ? plane->pixels : NULL;
    if (image) {
        *width = plane->width;
        *height = plane->height;
        plane->pixels = NULL;
    }
    objc_setAssociatedObject(self, &fusedPlaneKey, nil, OBJC_ASSOCIATION_RETAIN_NONATOMIC);
    return image;
}

- (float *)horosMPRCopyImageWidth:(long *)width height:(long *)height {
    NSAssert([NSThread isMainThread], @"MPR reslice requires the main thread");
    MPRController *controller = windowController;
    objc_setAssociatedObject(controller, &millisecondsKey, nil, OBJC_ASSOCIATION_RETAIN_NONATOMIC);
    objc_setAssociatedObject(self, &fusedPlaneKey, nil, OBJC_ASSOCIATION_RETAIN_NONATOMIC);
    objc_setAssociatedObject(self, &displayPlaneKey, nil, OBJC_ASSOCIATION_RETAIN_NONATOMIC);
    if (!controller.horosMPRMetalEnabled) { [self horosSetPlanarFallbackReason:nil]; return NULL; }
    if (moveCenter) return NULL;
    NSString *reason = nil;
    if (controller.clippingRangeMode < 1 || controller.clippingRangeMode > 3) reason = @"Volume rendering keeps the original renderer.";
    else if (pix.isRGB) reason = @"RGB planes keep the original renderer.";
    HorosMPRReslicer *reslicer = reason ? nil : [controller horosMPRReslicerForCurrentVolume:&reason];
    // The host's share of a Metal plane, for the trace (#619): the geometry and
    // arguments before the reslice, and the copy after it.
    double preparedFrom = [HorosMetalPerformanceTrace now];
    // One reason per cause, so that the trace counts which camera or crop refuses (#664).
    NSString *geometry = reslicer ? [vrView horosMPRGeometryRefusalWidth:width height:height] : nil;
    if (geometry) {
        reslicer = nil;
        reason = geometry;
    }
    // A fused series is resliced in Metal with the plane or both stay with
    // VTK, so a view never mixes the two engines (#658). The plane waits for
    // the host's blending branch, which takes it instead of VTK's.
    HorosMPRFusedPlane *fused = reslicer && self.blendingView ? [self horosMPRFusedPlane:&reason] : nil;
    if (self.blendingView && !fused) reslicer = nil;
    if (reslicer) {
        float cosines[9];
        float position[3];
        [vrView getOrientation:cosines];
        [vrView getOrigin:position windowCentered:YES sliceMiddle:YES];
        double spacing = [vrView getResolution] * [vrView imageSampleDistance];
        NSArray *origin = HorosMPRPixelCentre(position, cosines, spacing);
        NSArray *orientation = @[@(cosines[0]), @(cosines[1]), @(cosines[2]), @(cosines[3]), @(cosines[4]), @(cosines[5]),
                                 @(cosines[6]), @(cosines[7]), @(cosines[8])];
        DCMPix *first = [controller horosMPRFirstPix];
        double dz = first.sliceInterval != 0 ? fabs(first.sliceInterval) : fabs(first.sliceThickness);
        double step = MIN(first.pixelSpacingX > 0 ? first.pixelSpacingX : 1, MIN(first.pixelSpacingY > 0 ? first.pixelSpacingY : 1, dz));
        NSError *error = nil;
        [HorosMetalPerformanceTrace recordHostOperation:@"mpr.host_prepare" startedAt:preparedFrom];
        // The view owns the image it is handed; the engine copies the plane into it, once (#620).
        float *image = *width > 0 && *height > 0 ? malloc((size_t)*width * (size_t)*height * sizeof(float)) : NULL;
        if (!image) {
            reason = @"The reconstructed plane could not be allocated.";
        } else if ([reslicer resliceWithOrigin:origin orientation:orientation spacing:spacing
                                         width:*width height:*height thickness:[vrView getClippingRangeThicknessInMm] sampleStep:step
                                    projection:controller.clippingRangeMode background:[controller horosMPRBackground]
                                          into:image error:&error]) {
            double milliseconds = reslicer.lastMilliseconds + (fused ? fused->milliseconds : 0);
            // The cubic display plane (#702): the same thin slab, no fused
            // series. The linear one above stays the pixels; this one is only drawn.
            float thickness = [vrView getClippingRangeThicknessInMm];
            if (controller.horosMPRCubicDisplay && !fused && thickness <= HorosMPRCubicDisplayMaximumSlab) {
                float *display = malloc((size_t)*width * (size_t)*height * sizeof(float));
                if (display && [reslicer resliceWithOrigin:origin orientation:orientation spacing:spacing
                                                     width:*width height:*height thickness:thickness sampleStep:step
                                                projection:controller.clippingRangeMode background:[controller horosMPRBackground]
                                             interpolation:1 into:display error:NULL]) {
                    milliseconds += reslicer.lastMilliseconds;
                    NSData *plane = [NSData dataWithBytesNoCopy:display length:(NSUInteger)*width * (NSUInteger)*height * sizeof(float)
                                                   freeWhenDone:YES];
                    objc_setAssociatedObject(self, &displayPlaneKey, plane, OBJC_ASSOCIATION_RETAIN_NONATOMIC);
                } else free(display);
            }
            objc_setAssociatedObject(controller, &millisecondsKey, @(milliseconds), OBJC_ASSOCIATION_RETAIN_NONATOMIC);
            objc_setAssociatedObject(self, &fusedPlaneKey, fused, OBJC_ASSOCIATION_RETAIN_NONATOMIC);
            objc_setAssociatedObject(controller, &reasonKey, nil, OBJC_ASSOCIATION_COPY_NONATOMIC);
            [self horosSetPlanarFallbackReason:nil];
            return image;
        } else {
            free(image);
            reason = error.localizedDescription ?: @"The reslice produced no plane.";
        }
    }
    if (reason) [HorosMetalPerformanceTrace recordRefusal:@"mpr.refusal" reason:reason];
    objc_setAssociatedObject(controller, &reasonKey, reason, OBJC_ASSOCIATION_COPY_NONATOMIC);
    [self horosSetPlanarFallbackReason:reason];
    return NULL;
}

- (void)horosMPRAttachDisplayPlaneTo:(DCMPix *)pix {
    pix.horosMPRDisplayPixels = objc_getAssociatedObject(self, &displayPlaneKey);
    objc_setAssociatedObject(self, &displayPlaneKey, nil, OBJC_ASSOCIATION_RETAIN_NONATOMIC);
}

@end
