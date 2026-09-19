#import "ScrollPositionPreview.h"
#import "ScrollPositionPreviewGeometry.h"
#import "OrthogonalReslice.h"
#import "ViewerController.h"
#import "Notifications.h"
#import <objc/runtime.h>

static char previewKey;

static BOOL HorosScrollPreviewIsEnabled(NSUserDefaults *defaults)
{
    // The argument domain stores command-line YES/NO as strings. Read using
    // the defaults boolean conversion, while keeping absence enabled.
    return ![defaults objectForKey:@"ShowScrollPositionPreview"] ||
           [defaults boolForKey:@"ShowScrollPositionPreview"];
}

@interface HorosScrollPositionPreview : NSView {
    DCMView *_host; // The host owns this view and detaches it before destruction.
    NSMutableArray *_slices;
    OrthogonalReslice *_reslicer;
    DCMPix *_plane;
    NSImage *_image;
    NSArray *_labels;
    HorosPreviewOrientation _orientation;
    NSSize _physicalSize;
    NSPoint _windowPoint, _marker;
    NSInteger _axis, _position;
    float _level, _width;
    BOOL _pending;
}
- (id)initWithHost:(DCMView *)host;
- (void)showAtWindowPoint:(NSPoint)point;
- (void)moveAtWindowPoint:(NSPoint)point;
- (void)hide;
- (void)detach;
@end

@implementation HorosScrollPositionPreview
- (id)initWithHost:(DCMView *)host
{
    if ((self = [super initWithFrame:NSZeroRect])) {
        _host = host;
        self.hidden = YES;
        self.wantsLayer = YES;
        self.autoresizingMask = NSViewMaxXMargin | NSViewMinYMargin;
        self.accessibilityLabel = NSLocalizedString(@"Scroll position preview", nil);
        [[NSNotificationCenter defaultCenter] addObserver:self selector:@selector(volumeChanged:)
                                                     name:OsirixUpdateVolumeDataNotification object:nil];
        [[NSNotificationCenter defaultCenter] addObserver:self selector:@selector(windowClosed:)
                                                     name:NSWindowWillCloseNotification object:host.window];
    }
    return self;
}
- (BOOL)isFlipped { return YES; }
- (NSView *)hitTest:(NSPoint)point { return nil; }
- (BOOL)acceptsFirstResponder { return NO; }

- (void)clearVolume
{
    [_reslicer release]; _reslicer = nil;
    [_slices release]; _slices = nil;
    [_plane release]; _plane = nil;
    [_image release]; _image = nil;
    [_labels release]; _labels = nil;
    _position = -1;
}
- (void)volumeChanged:(NSNotification *)note
{
    if (note.object != _slices) return;
    if (![NSThread isMainThread]) {
        [self performSelectorOnMainThread:@selector(volumeChanged:) withObject:note waitUntilDone:NO];
        return;
    }
    [self hide];
    [self clearVolume];
}
- (void)windowClosed:(NSNotification *)note { [self detach]; }
- (void)detach
{
    [NSObject cancelPreviousPerformRequestsWithTarget:self];
    [[NSNotificationCenter defaultCenter] removeObserver:self];
    _pending = NO;
    _host = nil;
    [self clearVolume];
    [self removeFromSuperview];
}
- (void)dealloc
{
    [[NSNotificationCenter defaultCenter] removeObserver:self];
    [self clearVolume];
    [super dealloc];
}
- (void)hide
{
    [NSObject cancelPreviousPerformRequestsWithTarget:self];
    _pending = NO;
    BOOL wasVisible = !self.hidden;
    self.hidden = YES;
    if (wasVisible) [_host setNeedsDisplay:YES];
}

// Validate once for this slice list. The existing orthogonal reslicer requires
// a loaded, regular parallel stack. Never trigger decoding during scrolling,
// repair the source series, or present a misleading scout for mixed geometry.
- (BOOL)prepareVolume
{
    NSMutableArray *slices = _host.dcmPixList;
    if (slices == _slices) return _reslicer != nil;
    [self clearVolume];
    if (slices.count < 2) return NO;
    DCMPix *first = slices.firstObject, *last = slices.lastObject;
    if (!first.isLoaded || first.isRGB || first.pwidth < 2 || first.pheight < 2 ||
        !isfinite(first.pixelSpacingX) || first.pixelSpacingX <= 0 ||
        !isfinite(first.pixelSpacingY) || first.pixelSpacingY <= 0) return NO;
    float o[9]; [first orientation:o];
    double step[3] = {(last.originX - first.originX) / (slices.count - 1),
                      (last.originY - first.originY) / (slices.count - 1),
                      (last.originZ - first.originZ) / (slices.count - 1)};
    double interval = step[0]*o[6] + step[1]*o[7] + step[2]*o[8];
    double usedInterval = first.sliceInterval ?: ((DCMPix *)slices[1]).sliceLocation - first.sliceLocation;
    if (!isfinite(interval) || fabs(interval) < 1e-6 || !isfinite(usedInterval) ||
        fabs(interval - usedInterval) > fmax(.01, fabs(interval)*.01)) return NO;
    for (int k = 0; k < 3; ++k)
        if (!isfinite(step[k]) || fabs(step[k] - interval*o[6+k]) > .01) return NO;
    NSUInteger index = 0;
    for (DCMPix *pix in slices) {
        if (!pix.isLoaded || pix.isRGB || pix.pwidth != first.pwidth || pix.pheight != first.pheight ||
            fabs(pix.pixelSpacingX - first.pixelSpacingX) > 1e-5 ||
            fabs(pix.pixelSpacingY - first.pixelSpacingY) > 1e-5) return NO;
        float orientation[9]; [pix orientation:orientation];
        for (int k = 0; k < 9; ++k)
            if (!isfinite(orientation[k]) || fabs(orientation[k] - o[k]) > 1e-4) return NO;
        double origins[3] = {pix.originX - first.originX, pix.originY - first.originY, pix.originZ - first.originZ};
        for (int k = 0; k < 3; ++k)
            if (!isfinite(origins[k]) || fabs(origins[k] - index*step[k]) > .01) return NO;
        ++index;
    }
    _axis = HorosPreviewResliceAxis(o);
    _slices = [slices retain];
    _reslicer = [[OrthogonalReslice alloc] initWithOriginalDCMPixList:slices];
    _reslicer.useYcache = NO;
    return YES;
}
- (void)scheduleUpdate
{
    if (_pending) return;
    _pending = YES;
    [self performSelector:@selector(updatePreview) withObject:nil afterDelay:1.0/30.0
                  inModes:@[NSRunLoopCommonModes]];
}
- (void)showAtWindowPoint:(NSPoint)point
{
    _windowPoint = point;
    [NSObject cancelPreviousPerformRequestsWithTarget:self selector:@selector(hide) object:nil];
    [self performSelector:@selector(hide) withObject:nil afterDelay:1.0 inModes:@[NSRunLoopCommonModes]];
    [self scheduleUpdate];
}
- (void)moveAtWindowPoint:(NSPoint)point
{
    if (self.hidden && !_pending) return;
    _windowPoint = point;
    [self scheduleUpdate];
}
- (void)updatePreview
{
    _pending = NO;
    if (!_host.window.isVisible || ![_host is2DViewer] || [_host.windowController windowWillClose] ||
        ![self prepareVolume]) { [self hide]; return; }
    NSPoint location = [_host convertPoint:_windowPoint fromView:nil];
    if (!NSPointInRect(location, _host.bounds)) { [self hide]; return; }
    NSPoint pixel = [_host ConvertFromNSView2GL:location];
    DCMPix *current = _host.curDCM;
    if (!isfinite(pixel.x) || !isfinite(pixel.y) || !current) { [self hide]; return; }
    pixel.x = fmax(.5, fmin(current.pwidth - .5, pixel.x));
    pixel.y = fmax(.5, fmin(current.pheight - .5, pixel.y));
    NSInteger position = (NSInteger)floor(_axis ? pixel.x : pixel.y);
    if (_position != position || !_plane) {
        [_reslicer axeReslice:(short)_axis :position];
        [_plane release];
        _plane = [(_axis ? _reslicer.yReslicedDCMPixList : _reslicer.xReslicedDCMPixList).firstObject retain];
        if (!_plane) { [self hide]; return; }
        _position = position;
        float o[9]; [_plane orientation:o];
        _orientation = HorosPreviewDisplayOrientation(o);
        _physicalSize = NSMakeSize(_plane.pwidth * _plane.pixelSpacingX, _plane.pheight * _plane.pixelSpacingY);
        if (_orientation.transpose) _physicalSize = NSMakeSize(_physicalSize.height, _physicalSize.width);
        NSMutableArray *labels = [NSMutableArray array];
        for (int edge = 0; edge < 4; ++edge) {
            BOOL vertical = edge >= 2;
            int axis = (vertical != _orientation.transpose) ? 3 : 0;
            float sign = (edge % 2 == 0 ? -1 : 1) * ((vertical ? _orientation.flipY : _orientation.flipX) ? -1 : 1);
            float vector[3] = {o[axis]*sign, o[axis+1]*sign, o[axis+2]*sign};
            char text[32] = {0}; [_host getOrientationText:text :vector :NO];
            [labels addObject:[NSString stringWithUTF8String:text] ?: @""];
        }
        [_labels release]; _labels = [labels copy];
        [_image release]; _image = nil;
    }
    if (!_image || _level != current.wl || _width != current.ww) {
        _level = current.wl; _width = current.ww;
        [_plane changeWLWW:_level :_width];
        [_image release]; _image = [[_plane image] retain];
    }
    // A point in patient space ties the marker to the actual slice, including
    // reversed acquisition order. DCMPix returns millimetres along the plane.
    double patient[3], local[3];
    [current convertPixDoubleX:pixel.x pixY:pixel.y toDICOMCoords:patient pixelCenter:YES];
    [_plane convertDICOMCoordsDouble:patient toSliceCoords:local pixelCenter:YES];
    _marker = NSMakePoint(local[0] / (_plane.pwidth * _plane.pixelSpacingX),
                          local[1] / (_plane.pheight * _plane.pixelSpacingY));
    CGFloat side = fmin(150, fmin(NSWidth(_host.bounds), NSHeight(_host.bounds)) * .3);
    if (side < 72) { [self hide]; return; }
    CGFloat y = _host.isFlipped ? NSMinY(_host.bounds) + 6 : NSMaxY(_host.bounds) - side - 6;
    BOOL annotationLayoutChanged = self.hidden || NSWidth(self.frame) != side;
    self.frame = NSMakeRect(NSMinX(_host.bounds) + 6, y, side, side);
    self.hidden = NO;
    [self setNeedsDisplay:YES];
    // Moving the marker must not submit the full diagnostic image again.
    // The host only needs a draw when its annotation margin changes.
    if (annotationLayoutChanged) [_host setNeedsDisplay:YES];
}
- (NSPoint)point:(NSPoint)point inImageRect:(NSRect)rect
{
    double x, y; HorosPreviewMapPoint(_orientation, point.x, point.y, &x, &y);
    return NSMakePoint(NSMinX(rect) + x*NSWidth(rect), NSMinY(rect) + y*NSHeight(rect));
}
- (void)drawRect:(NSRect)dirtyRect
{
    [[NSColor blackColor] setFill]; NSRectFill(self.bounds);
    if (!_image || _physicalSize.width <= 0 || _physicalSize.height <= 0) return;
    NSRect available = NSInsetRect(self.bounds, 13, 13);
    CGFloat scale = fmin(NSWidth(available)/_physicalSize.width, NSHeight(available)/_physicalSize.height);
    NSRect rect = NSMakeRect(NSMidX(available) - _physicalSize.width*scale/2,
                             NSMidY(available) - _physicalSize.height*scale/2,
                             _physicalSize.width*scale, _physicalSize.height*scale);
    NSPoint origin = [self point:NSZeroPoint inImageRect:rect];
    NSPoint x = [self point:NSMakePoint(1, 0) inImageRect:rect];
    NSPoint y = [self point:NSMakePoint(0, 1) inImageRect:rect];
    [NSGraphicsContext saveGraphicsState];
    NSAffineTransform *transform = [NSAffineTransform transform];
    transform.transformStruct = (NSAffineTransformStruct){x.x-origin.x, x.y-origin.y, y.x-origin.x, y.y-origin.y, origin.x, origin.y};
    [transform concat];
    [_image drawInRect:NSMakeRect(0, 0, 1, 1) fromRect:NSZeroRect operation:NSCompositingOperationCopy
             fraction:1 respectFlipped:YES hints:@{NSImageHintInterpolation:@(NSImageInterpolationHigh)}];
    [NSGraphicsContext restoreGraphicsState];
    [[NSColor redColor] set];
    NSBezierPath *line = [NSBezierPath bezierPath];
    [line moveToPoint:[self point:NSMakePoint(0, _marker.y) inImageRect:rect]];
    [line lineToPoint:[self point:NSMakePoint(1, _marker.y) inImageRect:rect]];
    NSPoint marker = [self point:_marker inImageRect:rect];
    [line moveToPoint:NSMakePoint(marker.x-3, marker.y-3)];
    [line lineToPoint:NSMakePoint(marker.x+3, marker.y+3)];
    [line moveToPoint:NSMakePoint(marker.x-3, marker.y+3)];
    [line lineToPoint:NSMakePoint(marker.x+3, marker.y-3)];
    line.lineWidth = 1; [line stroke];
    NSFrameRectWithWidth(NSInsetRect(self.bounds, .5, .5), 1);
    NSDictionary *attributes = @{NSForegroundColorAttributeName:NSColor.whiteColor, NSFontAttributeName:[NSFont systemFontOfSize:10]};
    for (NSUInteger edge = 0; edge < _labels.count; ++edge) {
        NSString *label = _labels[edge]; NSSize size = [label sizeWithAttributes:attributes];
        NSPoint p = NSMakePoint((NSWidth(self.bounds)-size.width)/2, (NSHeight(self.bounds)-size.height)/2);
        if (edge == 0) p.x = 3;
        if (edge == 1) p.x = NSWidth(self.bounds)-size.width-3;
        if (edge == 2) p.y = 1;
        if (edge == 3) p.y = NSHeight(self.bounds)-size.height-1;
        [label drawAtPoint:p withAttributes:attributes];
    }
}
@end

@implementation DCMView (HorosScrollPositionPreview)
- (void)horosShowScrollPreviewAtWindowPoint:(NSPoint)point
{
    if (![self is2DViewer] || self.dcmPixList.count < 2 ||
        !HorosScrollPreviewIsEnabled([NSUserDefaults standardUserDefaults])) return;
    HorosScrollPositionPreview *preview = objc_getAssociatedObject(self, &previewKey);
    if (!preview) {
        preview = [[[HorosScrollPositionPreview alloc] initWithHost:self] autorelease];
        objc_setAssociatedObject(self, &previewKey, preview, OBJC_ASSOCIATION_RETAIN_NONATOMIC);
        [self addSubview:preview];
    }
    [preview showAtWindowPoint:point];
}
- (void)horosMoveScrollPreviewAtWindowPoint:(NSPoint)point
{
    [(HorosScrollPositionPreview *)objc_getAssociatedObject(self, &previewKey) moveAtWindowPoint:point];
}
- (void)horosHideScrollPreview { [(HorosScrollPositionPreview *)objc_getAssociatedObject(self, &previewKey) hide]; }
- (void)horosDiscardScrollPreview
{
    [(HorosScrollPositionPreview *)objc_getAssociatedObject(self, &previewKey) detach];
    objc_setAssociatedObject(self, &previewKey, nil, OBJC_ASSOCIATION_RETAIN_NONATOMIC);
}
- (CGFloat)horosScrollPreviewAnnotationInset
{
    NSView *preview = objc_getAssociatedObject(self, &previewKey);
    return preview && !preview.isHidden ? NSMaxX(preview.frame) + 4 : 0;
}
@end
