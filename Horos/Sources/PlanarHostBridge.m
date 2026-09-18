#import "ViewerVolumeSession.h"
#import "PlanarHostBridge.h"
#import "Horos-Swift.h"
#import "DicomImage.h"
#import "DicomSeries.h"
#import "DCMPix.h"
#import <objc/runtime.h>

static char planarEnabledKey, planarRendererKey, planarFallbackKey, scalarCLUTKey, performanceTraceKey, slabKeyKey, slabDataKey;

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
    return [self horosPlanarSnapshotDrawnIn:self];
}

/// The pixel of this view's image under `point` of `host`'s bounds, as `host`
/// draws it. For the view's own image that is `ConvertFromNSView2GL:`. A series
/// fused over `host` is drawn by drawRectIn: with this view's origin, scale,
/// rotation, flips and pixel ratio in the frame it is handed, `host`'s drawing
/// frame (#658): the same conversion, `ConvertFromUpLeftView2GL:` statement for
/// statement, with that frame for this view's own.
- (NSPoint)horosPixelAt:(NSPoint)point drawnIn:(DCMView *)host {
    if (host == self) return [self ConvertFromNSView2GL:point];
    static double deg2rad = M_PI / 180.0;
    NSRect size = host.drawingFrameRect;
    NSPoint a = [host convertPointToBacking:point];
    a.y = size.size.height - a.y;
    if( xFlipped) a.x = size.size.width - a.x;
    if( yFlipped) a.y = size.size.height - a.y;
    a.x -= size.size.width/2;
    a.x /= scaleValue;
    a.y -= size.size.height/2;
    a.y /= scaleValue;
    float xx = a.x*cos(rotation*deg2rad) + a.y*sin(rotation*deg2rad);
    float yy = -a.x*sin(rotation*deg2rad) + a.y*cos(rotation*deg2rad);
    a.y = yy;
    a.x = xx;
    a.x -= (origin.x)/scaleValue;
    a.y += (origin.y)/scaleValue;
    if( self.curDCM)
    {
        a.x += self.curDCM.pwidth * 0.5f;
        a.y += self.curDCM.pheight * self.curDCM.pixelRatio * 0.5f;
        a.y /= self.curDCM.pixelRatio;
    }
    return a;
}

/// What this view's image contributes when `host` draws: its own image when
/// `host` is this view, or the series this view fuses over `host` (#658).
- (NSDictionary *)horosPlanarSnapshotDrawnIn:(DCMView *)host {
    NSAssert([NSThread isMainThread], @"Planar snapshots require the main thread");
    DCMView *view = self;
    DCMPix *pix = view.curDCM;
    BOOL fused = host != view;
    NSString *unsupported = NSLocalizedString(@"This display mode is available in the original viewer. Metal comparison is paused.", nil);
    // A thick slab in mean, maximum or minimum is a reduction the Metal path
    // runs itself (#659). The volume-rendering slab (modes 4 and 5) is VTK's
    // composite and a colour slab has its own RGB reduction: both stay here.
    // Channel factors and a colour image's enlargement are the host's own
    // tables and vImage calls, reproduced below (#660). A fused series is drawn
    // through the host's scalar CLUT program; a colour one stays here.
    // The 12-bit LUT mode draws a buffer that a display vendor's plugin packs,
    // and turns on only with the automatic12BitTotoku preference and
    // +[AppController canDisplay12Bit], which only that plugin sets. Nothing
    // here can produce or check those bits, so it stays here by design (#663).
    if (!pix ||
        pix.thickSlabVRActivated || pix.stackMode > 3 || (pix.stackMode && pix.isRGB) || pix.isLUT12Bit || (fused && pix.isRGB))
        return @{@"error": unsupported};
    long width = pix.pwidth, height = pix.pheight;
    NSUInteger count = [HorosVolumeAllocation byteCountForWidth:width height:height slices:1 bytesPerVoxel:4];
    if (width <= 0 || height <= 0 || width > 16384 || height > 16384 || count > 512*1024*1024)
        return @{@"error": unsupported};
    float *pixels = pix.fImage;
    if (!pixels) return @{@"error": unsupported};
    NSRect bounds = host.bounds;
    NSPoint topLeft = [view horosPixelAt:NSMakePoint(NSMinX(bounds), NSMaxY(bounds)) drawnIn:host];
    NSPoint topRight = [view horosPixelAt:NSMakePoint(NSMaxX(bounds), NSMaxY(bounds)) drawnIn:host];
    NSPoint bottomLeft = [view horosPixelAt:NSMakePoint(NSMinX(bounds), NSMinY(bounds)) drawnIn:host];
    unsigned char *r, *g, *b, *alpha = NULL, rgba[1024];
    if (fused) {
        // The fused series' colours: those the PET CLUT mode gives (the PET
        // blending CLUT under B/W Inverse, the series' own otherwise), and its
        // alpha table, which the fusion factor and mode set (#658).
        unsigned char *unused;
        [host blendingColorTables:&unused :&r :&g :&b];
        [view colorTables:&alpha :&unused :&unused :&unused];
    } else {
        [view getCLUT:&r :&g :&b];
    }
    // The table loadTextureIn: gives the scalar CLUT program: the colours times
    // this view's channel factors (#660), and the alpha table, opaque for the
    // view's own image.
    for (NSUInteger i = 0; i < 256; ++i) {
        rgba[4*i] = fminf(255, fmaxf(0, r[i] * redFactor));
        rgba[4*i+1] = fminf(255, fmaxf(0, g[i] * greenFactor));
        rgba[4*i+2] = fminf(255, fmaxf(0, b[i] * blueFactor));
        rgba[4*i+3] = alpha ? alpha[i] : 255;
    }
    DicomImage *image = view.curImage >= 0 && view.curImage < view.dcmFilesList.count ? view.dcmFilesList[view.curImage] : nil;
    NSString *identifier = [NSString stringWithFormat:@"%@/%@/%ld", image.sopInstanceUID ?: image.objectID.URIRepresentation.absoluteString,
        image.frameID ?: @0, (long)view.curImage];
    // Subtraction and the DICOM shutter (#662) are presentations of the host's
    // own bytes: the subtraction through vImage's half-precision gamma, the
    // window through vImage's conversion, the polarity, and the shutter's
    // rectangle, circle and polygon masked over them with the CLUT's black
    // index. So is every colour image (#660): the host windows its ARGB bytes
    // through its conversion table, opacity table and filter included, and
    // interpolates those. The original renderer draws those bytes; so does
    // Metal, with the same interpolation. The accessor brings the 8-bit
    // representation up to date first, as DCMView does before drawing.
    NSData *hostBytes = nil;
    if (pix.isRGB || pix.subtractedfImage || pix.shutterEnabled) {
        char *bytes = pix.baseAddr;
        if (!bytes) return @{@"error": unsupported};
        hostBytes = [NSData dataWithBytes:bytes length:(NSUInteger)width * height * (pix.isRGB ? 4 : 1)];
    }
    // A colour frame is drawn from its bytes alone; they stand in for the
    // samples, the same size, rather than a second copy of them.
    NSMutableDictionary *snapshot = [NSMutableDictionary dictionaryWithDictionary:@{@"width": @(width), @"height": @(height), @"isColor": @(pix.isRGB),
        @"pixels": pix.isRGB ? hostBytes : [NSData dataWithBytes:pixels length:count], @"clut": [NSData dataWithBytes:rgba length:sizeof(rgba)],
        @"frameIdentity": identifier, @"level": @(noScale || [pix horosPlanarUsesFixedWindow] ? 127 : view.curWL),
        @"widthWindow": @((pix.displayInverted ? -1 : 1) * (noScale || [pix horosPlanarUsesFixedWindow] ? 256 : view.curWW)),
        @"background": @(view.whiteBackground ? 1 : 0),
        @"softwareScale": @([view softwareInterpolation] ? (width <= 256 ? 3 : 2) : 1),
        @"screenToPixel": @[@(topLeft.x), @(topLeft.y), @(topRight.x), @(topRight.y), @(bottomLeft.x), @(bottomLeft.y)],
        @"viewSize": @[@(NSWidth(bounds)), @(NSHeight(bounds))],
        @"nearest": @([[NSUserDefaults standardUserDefaults] boolForKey:@"NOINTERPOLATION"])}];
    if (hostBytes) {
        snapshot[@"hostBytes"] = hostBytes;
        if (pix.isRGB && (colorTransfer || redFactor != 1.0 || greenFactor != 1.0 || blueFactor != 1.0)) {
            // loadTextureIn: tables a colour image's bytes before they are
            // interpolated: vImageTableLookUp_ARGB8888 with the opaque alpha
            // table and the CLUT, or the CLUT times the channel factors converted
            // to bytes as C converts them, unclamped. Alpha, red, green, blue.
            unsigned char table[1024];
            for (NSUInteger i = 0; i < 256; ++i) {
                table[i] = opaqueTable[i];
                if (redFactor != 1.0 || greenFactor != 1.0 || blueFactor != 1.0) {
                    table[256 + i] = r[i] * redFactor;
                    table[512 + i] = g[i] * greenFactor;
                    table[768 + i] = b[i] * blueFactor;
                } else {
                    table[256 + i] = r[i]; table[512 + i] = g[i]; table[768 + i] = b[i];
                }
            }
            snapshot[@"colourTable"] = [NSData dataWithBytes:table length:sizeof(table)];
        }
    }
    if ([pix horosPlanarHasPresentationFilter]) {
        // The menu's convolution filter runs before the window, on these source
        // values, as the host runs it (#661): the kernel as the host holds it and
        // its normalisation. PlanarConvolution does the arithmetic.
        snapshot[@"convolutionSize"] = @(pix.kernelsize);
        snapshot[@"convolutionKernel"] = [NSData dataWithBytes:pix.kernel length:25 * sizeof(float)];
        snapshot[@"convolutionNormalization"] = @(pix.normalization);
    }
    if (pix.transferFunctionPtr) {
        // The opacity table and what the host reads with it (#657): the image's
        // own WL/WW, not the view's, which noScale has set to 127/256 before the
        // host computes, and the polarity it applies afterwards. PlanarFrame
        // reproduces the arithmetic; nothing is computed here.
        snapshot[@"transferFunction"] = pix.transferFunction;
        snapshot[@"transferLevel"] = @(noScale ? 127 : pix.wl);
        snapshot[@"transferWidth"] = @(noScale ? 256 : pix.ww);
        snapshot[@"transferInverted"] = @(pix.displayInverted);
    }
    NSData *slab = nil;
    NSString *slabKey = nil;
    NSArray *series = pix.pixArray;
    if (pix.stackMode >= 1 && pix.stackMode <= 3 && pix.stack > 1 && series.count > 1) {
        // The slices computeThickSlab reduces with this one, in its order; a
        // slice with no pixels is skipped there and here.
        NSMutableArray *slices = [NSMutableArray array];
        NSMutableString *key = [NSMutableString string];
        HorosVolumeSession *session = [[view windowController] respondsToSelector:@selector(horosVolumeSession)] ?
            [(ViewerController *)[view windowController] horosVolumeSession] : nil;
        [key appendFormat:@"%ld/%ld/%ld/%ld", (long)session.sessionID, (long)session.identity.generation, width, height];
        for (NSNumber *index in [HorosPlanarThickSlab sliceIndicesWithPosition:pix.pixPos stack:pix.stack
                                                                     direction:pix.stackDirection count:series.count]) {
            DCMPix *slice = series[index.integerValue];
            float *samples = slice.fImage;
            if (!samples) continue;
            if (slice.pwidth != width || slice.pheight != height) return @{@"error": unsupported};
            [slices addObject:slice];
            [key appendFormat:@"/%p:%p", slice, samples];
        }
        if (slices.count) {
            // Every redraw builds a snapshot; the other slices are copied only
            // when they, or the volume's generation, change. The same NSData on
            // every draw compares equal without reading it.
            slabKey = key;
            slab = [objc_getAssociatedObject(view, &slabKeyKey) isEqualToString:key] ? objc_getAssociatedObject(view, &slabDataKey) : nil;
            if (!slab) {
                NSMutableData *others = [NSMutableData dataWithCapacity:slices.count * count];
                for (DCMPix *slice in slices) [others appendBytes:slice.fImage length:count];
                slab = others;
            }
            snapshot[@"slabMode"] = @(pix.stackMode);
            snapshot[@"slabSlices"] = slab;
            snapshot[@"slabCount"] = @(slices.count + 1);
        }
    }
    objc_setAssociatedObject(view, &slabKeyKey, slabKey, OBJC_ASSOCIATION_COPY_NONATOMIC);
    objc_setAssociatedObject(view, &slabDataKey, slab, OBJC_ASSOCIATION_RETAIN_NONATOMIC);
    // Under a fusion drawRect: adds the image to the clear colour (GL_ONE,
    // GL_ONE), white under the B/W Inverse CLUT: every entry then draws white,
    // and only the fused series shows (#658).
    if (!fused && view.blendingView && !syncOnLocationImpossible && view.whiteBackground) {
        memset(rgba, 255, sizeof(rgba));
        snapshot[@"clut"] = [NSData dataWithBytes:rgba length:sizeof(rgba)];
    }
    // The series fused over the image, where drawRect: draws it: in the key
    // view of a 2D viewer, while the two series' locations are in sync.
    if (!fused && view.blendingView && !syncOnLocationImpossible && view.isKeyView) {
        NSDictionary *layer = [view.blendingView horosPlanarSnapshotDrawnIn:view];
        if (layer[@"error"]) return layer;
        snapshot[@"fusion"] = layer;
    }
    return snapshot;
}
@end
