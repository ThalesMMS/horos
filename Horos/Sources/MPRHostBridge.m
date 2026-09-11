#import "MPRHostBridge.h"
#import "PlanarHostBridge.h"
#import "VRController.h"
#import "VRView.h"
#import "DCMPix.h"
#import "Horos-Swift.h"
#import <objc/runtime.h>

static char enabledKey, reslicerKey, uploadedKey, reasonKey, millisecondsKey;

@interface MPRController (HorosMPRHostPrivate)
- (HorosMPRReslicer *)horosMPRReslicerForCurrentVolume:(NSString **)reason;
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

- (double)horosMPRLastMilliseconds {
    NSNumber *value = objc_getAssociatedObject(self, &millisecondsKey);
    return value ? value.doubleValue : -1;
}

- (NSInteger)horosMPRVolumeBytes {
    HorosMPRReslicer *reslicer = objc_getAssociatedObject(self, &reslicerKey);
    return reslicer.volumeBytes;
}

- (void)horosMPRReleaseVolume {
    HorosMPRReslicer *reslicer = objc_getAssociatedObject(self, &reslicerKey);
    [reslicer releaseVolume];
    objc_setAssociatedObject(self, &uploadedKey, nil, OBJC_ASSOCIATION_RETAIN_NONATOMIC);
    objc_setAssociatedObject(self, &millisecondsKey, nil, OBJC_ASSOCIATION_RETAIN_NONATOMIC);
}

- (void)horosMPRWindowWillClose:(NSNotification *)note {
    [[NSNotificationCenter defaultCenter] removeObserver:self name:NSWindowWillCloseNotification object:note.object];
    [self horosMPRReleaseVolume];
    objc_setAssociatedObject(self, &reslicerKey, nil, OBJC_ASSOCIATION_RETAIN_NONATOMIC);
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

@implementation MPRDCMView (HorosMPRHost)

- (NSMenu *)menuForEvent:(NSEvent *)event {
    NSMenu *menu = [super menuForEvent:event] ?: [[[NSMenu alloc] init] autorelease];
    if (menu.numberOfItems) [menu addItem:[NSMenuItem separatorItem]];
    NSMenuItem *item = [menu addItemWithTitle:NSLocalizedString(@"Use Metal in MPR", nil)
                                       action:@selector(toggleMPRMetal:) keyEquivalent:@""];
    item.target = windowController;
    item.state = windowController.horosMPRMetalEnabled ? NSControlStateValueOn : NSControlStateValueOff;
    return menu;
}

- (float *)horosMPRCopyImageWidth:(long *)width height:(long *)height {
    NSAssert([NSThread isMainThread], @"MPR reslice requires the main thread");
    MPRController *controller = windowController;
    objc_setAssociatedObject(controller, &millisecondsKey, nil, OBJC_ASSOCIATION_RETAIN_NONATOMIC);
    if (!controller.horosMPRMetalEnabled) { [self horosSetPlanarFallbackReason:nil]; return NULL; }
    if (moveCenter) return NULL;
    NSString *reason = nil;
    if (controller.clippingRangeMode < 1 || controller.clippingRangeMode > 3) reason = @"Volume rendering keeps the original renderer.";
    else if (self.blendingView) reason = @"Fusion keeps the original renderer.";
    else if (pix.isRGB) reason = @"RGB planes keep the original renderer.";
    HorosMPRReslicer *reslicer = reason ? nil : [controller horosMPRReslicerForCurrentVolume:&reason];
    if (reslicer && ![vrView prepareMPRGeometryWidth:width height:height]) {
        reslicer = nil;
        reason = @"The current camera or crop keeps the original renderer.";
    }
    if (reslicer) {
        float cosines[9];
        float position[3];
        [vrView getOrientation:cosines];
        [vrView getOrigin:position windowCentered:YES sliceMiddle:YES];
        double spacing = [vrView getResolution] * [vrView imageSampleDistance];
        NSArray *origin = @[@(position[0]), @(position[1]), @(position[2])];
        NSArray *orientation = @[@(cosines[0]), @(cosines[1]), @(cosines[2]), @(cosines[3]), @(cosines[4]), @(cosines[5]),
                                 @(cosines[6]), @(cosines[7]), @(cosines[8])];
        DCMPix *first = [controller horosMPRFirstPix];
        double dz = first.sliceInterval != 0 ? fabs(first.sliceInterval) : fabs(first.sliceThickness);
        double step = MIN(first.pixelSpacingX > 0 ? first.pixelSpacingX : 1, MIN(first.pixelSpacingY > 0 ? first.pixelSpacingY : 1, dz));
        NSError *error = nil;
        NSData *plane = [reslicer resliceWithOrigin:origin orientation:orientation spacing:spacing
                                               width:*width height:*height thickness:[vrView getClippingRangeThicknessInMm] sampleStep:step
                                          projection:controller.clippingRangeMode background:[controller horosMPRBackground] error:&error];
        if (plane.length && plane.length == (NSUInteger)(*width * *height * sizeof(float))) {
            float *image = malloc(plane.length);
            if (!image) {
                reason = @"The reconstructed plane could not be allocated.";
            } else {
                memcpy(image, plane.bytes, plane.length);
                objc_setAssociatedObject(controller, &millisecondsKey, @(reslicer.lastMilliseconds), OBJC_ASSOCIATION_RETAIN_NONATOMIC);
                objc_setAssociatedObject(controller, &reasonKey, nil, OBJC_ASSOCIATION_COPY_NONATOMIC);
                [self horosSetPlanarFallbackReason:nil];
                return image;
            }
        } else {
            reason = error.localizedDescription ?: @"The reslice produced no plane.";
        }
    }
    objc_setAssociatedObject(controller, &reasonKey, reason, OBJC_ASSOCIATION_COPY_NONATOMIC);
    [self horosSetPlanarFallbackReason:reason];
    return NULL;
}

@end
