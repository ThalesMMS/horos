#import "ViewerVolumeSession.h"
#import "PlanarHostBridge.h"
#import "Horos-Swift.h"
#import "DicomImage.h"
#import "DicomSeries.h"
#import "DCMPix.h"
#import <objc/runtime.h>

static char planarEnabledKey, planarRendererKey, planarFallbackKey, scalarCLUTKey, performanceTraceKey;

@interface DCMPix (HorosPlanarPresentation)
- (BOOL)horosPlanarHasPresentationFilter;
- (BOOL)horosPlanarUsesFixedWindow;
@end
@implementation DCMPix (HorosPlanarPresentation)
- (BOOL)horosPlanarHasPresentationFilter { return convolution; }
- (BOOL)horosPlanarUsesFixedWindow { return fixed8bitsWLWW; }
@end

@interface ViewerController (HorosPlanarComparison) <HorosPlanarSource>
- (void)openPlanarMetalComparison:(id)sender;
@end

/// The comparison consumes immutable decoded bytes. No managed object or raw
/// host pixel pointer crosses into a GPU command or a background callback.
@implementation ViewerController (HorosPlanarComparison)
- (void)openPlanarMetalComparison:(id)sender {
    [HorosPlanarComparison openWithSource:(id<HorosPlanarSource>)self];
}
- (NSWindow *)planarHostWindow { return self.window; }
- (NSView *)planarHostView { return self.imageView; }
- (NSDictionary *)planarSnapshot {
    return [self.imageView horosPlanarSnapshot];
}
@end

@implementation ViewerController (HorosPlanarHost)
- (BOOL)horosPlanarMetalEnabled {
    // Absent means on, as in the MPR: Metal is the viewer's default, and a frame
    // it declines falls back to the original path with a visible reason.
    NSNumber *enabled = objc_getAssociatedObject(self, &planarEnabledKey);
    return enabled ? enabled.boolValue : YES;
}
- (void)togglePlanarMetal:(id)sender {
    objc_setAssociatedObject(self, &planarEnabledKey, @(!self.horosPlanarMetalEnabled), OBJC_ASSOCIATION_RETAIN_NONATOMIC);
    for (DCMView *view in self.imageViews) {
        [view horosInvalidatePlanar];
        [view loadTextures];
        [view setNeedsDisplay:YES];
    }
}
@end

@implementation DCMView (HorosPlanarHost)
- (HorosPlanarPerformanceTrace *)horosPlanarPerformanceTrace {
    if (!HorosPlanarPerformanceTrace.enabled) return nil;
    HorosPlanarPerformanceTrace *trace = objc_getAssociatedObject(self, &performanceTraceKey);
    if (!trace) {
        trace = [[[HorosPlanarPerformanceTrace alloc] init] autorelease];
        objc_setAssociatedObject(self, &performanceTraceKey, trace, OBJC_ASSOCIATION_RETAIN_NONATOMIC);
    }
    return trace;
}
- (double)horosPlanarLastCommandMilliseconds {
    HorosPlanarHostRenderer *renderer = objc_getAssociatedObject(self, &planarRendererKey);
    return renderer.encodedGPUCommand && renderer.gpuMilliseconds > 0 ? renderer.gpuMilliseconds : -1;
}
- (HorosScalarCLUTDraw *)horosScalarCLUTForLens {
    unsigned char rgba[1024];
    for (NSUInteger i = 0; i < 256; ++i) {
        rgba[4*i] = fminf(255, fmaxf(0, redTable[i] * redFactor));
        rgba[4*i+1] = fminf(255, fmaxf(0, greenTable[i] * greenFactor));
        rgba[4*i+2] = fminf(255, fmaxf(0, blueTable[i] * blueFactor));
        rgba[4*i+3] = 255;
    }
    return [self horosScalarCLUTWithTable:[NSData dataWithBytes:rgba length:sizeof(rgba)]
        windowed:self.horosScalarCLUTState.lensIsWindowed];
}
- (HorosScalarCLUTDraw *)horosScalarCLUTWithTable:(NSData *)table windowed:(BOOL)windowed {
    BOOL fixedWindow = noScale || [self.curDCM horosPlanarUsesFixedWindow];
    return [self.horosScalarCLUTState prepareTable:table level:windowed ? 0.5 : (fixedWindow ? 127 : self.curWL)
        width:windowed ? 1 : (self.curDCM.displayInverted ? -1 : 1) * (fixedWindow ? 256 : self.curWW) nearest:[[NSUserDefaults standardUserDefaults] boolForKey:@"NOINTERPOLATION"]
        context:[NSOpenGLContext currentContext]];
}
- (HorosLegacyScalarCLUTState *)horosScalarCLUTState {
    HorosLegacyScalarCLUTState *state = objc_getAssociatedObject(self, &scalarCLUTKey);
    if (!state) {
        state = [[[HorosLegacyScalarCLUTState alloc] init] autorelease];
        objc_setAssociatedObject(self, &scalarCLUTKey, state, OBJC_ASSOCIATION_RETAIN_NONATOMIC);
    }
    return state;
}
- (void)horosInvalidatePlanar {
    [objc_getAssociatedObject(self, &planarRendererKey) invalidate];
    objc_setAssociatedObject(self, &planarRendererKey, nil, OBJC_ASSOCIATION_RETAIN_NONATOMIC);
    objc_setAssociatedObject(self, &planarFallbackKey, nil, OBJC_ASSOCIATION_COPY_NONATOMIC);
}
- (NSString *)horosPlanarFallbackReason { return objc_getAssociatedObject(self, &planarFallbackKey); }
- (NSString *)horosPlanarBackendName {
    HorosPlanarHostRenderer *renderer = objc_getAssociatedObject(self, &planarRendererKey);
    return renderer.backendName ?: @"";
}
- (double)horosPlanarGPUMilliseconds {
    HorosPlanarHostRenderer *renderer = objc_getAssociatedObject(self, &planarRendererKey);
    return renderer ? renderer.gpuMilliseconds : 0;
}
- (void)horosSetPlanarFallbackReason:(NSString *)reason {
    objc_setAssociatedObject(self, &planarFallbackKey, reason, OBJC_ASSOCIATION_COPY_NONATOMIC);
}
- (BOOL)horosDrawPlanarInContext:(NSOpenGLContext *)context size:(NSSize)size {
    NSAssert([NSThread isMainThread], @"Planar rendering requires the main thread");
    if (![self is2DViewer] || ![[self windowController] horosPlanarMetalEnabled]) return NO;
    NSDictionary *snapshot = [self horosPlanarSnapshot];
    HorosVolumeSession *session = [[self windowController] horosVolumeSession];
    NSString *reason = snapshot[@"error"];
    if (!session && !reason) reason = NSLocalizedString(@"This display mode is available in the original viewer. Metal comparison is paused.", nil);
    if (reason) {
        [self horosInvalidatePlanar];
        objc_setAssociatedObject(self, &planarFallbackKey, reason, OBJC_ASSOCIATION_COPY_NONATOMIC);
        return NO;
    }
    HorosPlanarHostRenderer *renderer = objc_getAssociatedObject(self, &planarRendererKey);
    if (!renderer) {
        renderer = [[[HorosPlanarHostRenderer alloc] init] autorelease];
        objc_setAssociatedObject(self, &planarRendererKey, renderer, OBJC_ASSOCIATION_RETAIN_NONATOMIC);
    }
    BOOL drawn = [renderer drawSnapshot:snapshot session:session context:context width:size.width height:size.height];
    objc_setAssociatedObject(self, &planarFallbackKey, drawn ? nil :
        NSLocalizedString(@"Metal comparison is unavailable. Use the original viewer.", nil), OBJC_ASSOCIATION_COPY_NONATOMIC);
    return drawn;
}
- (NSDictionary *)horosPlanarSnapshot {
    NSAssert([NSThread isMainThread], @"Planar snapshots require the main thread");
    DCMView *view = self;
    DCMPix *pix = view.curDCM;
    NSString *unsupported = NSLocalizedString(@"This display mode is available in the original viewer. Metal comparison is paused.", nil);
    if (!pix || [pix horosPlanarHasPresentationFilter] || view.blendingView || pix.transferFunctionPtr || pix.subtractedfImage ||
        pix.thickSlabVRActivated || pix.stackMode || pix.shutterEnabled || pix.isLUT12Bit ||
        redFactor != 1 || greenFactor != 1 || blueFactor != 1 || ([view softwareInterpolation] && pix.isRGB))
        return @{@"error": unsupported};
    long width = pix.pwidth, height = pix.pheight;
    NSUInteger count = [HorosVolumeAllocation byteCountForWidth:width height:height slices:1 bytesPerVoxel:4];
    if (width <= 0 || height <= 0 || width > 16384 || height > 16384 || count > 512*1024*1024)
        return @{@"error": unsupported};
    float *pixels = pix.fImage;
    if (!pixels) return @{@"error": unsupported};
    NSRect bounds = view.bounds;
    NSPoint topLeft = [view ConvertFromNSView2GL:NSMakePoint(NSMinX(bounds), NSMaxY(bounds))];
    NSPoint topRight = [view ConvertFromNSView2GL:NSMakePoint(NSMaxX(bounds), NSMaxY(bounds))];
    NSPoint bottomLeft = [view ConvertFromNSView2GL:NSMakePoint(NSMinX(bounds), NSMinY(bounds))];
    unsigned char *r, *g, *b, rgba[1024];
    [view getCLUT:&r :&g :&b];
    for (NSUInteger i = 0; i < 256; ++i) {
        rgba[4*i] = r[i]; rgba[4*i+1] = g[i]; rgba[4*i+2] = b[i]; rgba[4*i+3] = 255;
    }
    DicomImage *image = view.curImage >= 0 && view.curImage < view.dcmFilesList.count ? view.dcmFilesList[view.curImage] : nil;
    NSString *identifier = [NSString stringWithFormat:@"%@/%@/%ld", image.sopInstanceUID ?: image.objectID.URIRepresentation.absoluteString,
        image.frameID ?: @0, (long)view.curImage];
    return @{@"width": @(width), @"height": @(height), @"isColor": @(pix.isRGB),
        @"pixels": [NSData dataWithBytes:pixels length:count], @"clut": [NSData dataWithBytes:rgba length:sizeof(rgba)],
        @"frameIdentity": identifier, @"level": @(noScale || [pix horosPlanarUsesFixedWindow] ? 127 : view.curWL),
        @"widthWindow": @((pix.displayInverted ? -1 : 1) * (noScale || [pix horosPlanarUsesFixedWindow] ? 256 : view.curWW)),
        @"background": @(view.whiteBackground ? 1 : 0),
        @"softwareScale": @([view softwareInterpolation] ? (width <= 256 ? 3 : 2) : 1),
        @"screenToPixel": @[@(topLeft.x), @(topLeft.y), @(topRight.x), @(topRight.y), @(bottomLeft.x), @(bottomLeft.y)],
        @"viewSize": @[@(NSWidth(bounds)), @(NSHeight(bounds))],
        @"nearest": @([[NSUserDefaults standardUserDefaults] boolForKey:@"NOINTERPOLATION"])};
}
@end
