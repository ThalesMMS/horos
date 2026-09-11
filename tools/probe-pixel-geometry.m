// Diagnostic-only probe for #151: the geometry a viewer read out of a volume.
//
//   clang -shared -fobjc-arc -framework Cocoa tools/probe-pixel-geometry.m \
//     -o local-validation/work/nifti/probe.dylib
//
// HOROS_PIXEL_GEOMETRY=1, with a viewer open. It prints, per frame, the pixel
// spacing, the slice thickness and interval, the origin, and one pixel value -
// the numbers a fixture with known geometry can be checked against. Reads only.
#import <Cocoa/Cocoa.h>

@interface NSObject (PixelGeometryProbe)
+ (NSMutableArray*)getDisplayed2DViewers;
- (NSMutableArray*)pixList;
- (double)pixelSpacingX;
- (double)pixelSpacingY;
- (double)sliceThickness;
- (double)sliceInterval;
- (double)originX;
- (double)originY;
- (double)originZ;
- (long)pwidth;
- (long)pheight;
- (float)getPixelValueX:(long)x Y:(long)y;
- (NSString*)srcFile;
@end

__attribute__((constructor)) static void install(void) {
    if (!getenv("HOROS_PIXEL_GEOMETRY")) return;
    if (![NSBundle.mainBundle.bundleIdentifier isEqualToString:@"org.horosproject.horos.local-development"]) return;
    [[NSNotificationCenter defaultCenter] addObserverForName:NSApplicationDidFinishLaunchingNotification
                                                      object:nil queue:NSOperationQueue.mainQueue
                                                  usingBlock:^(NSNotification *n) {
        __block BOOL done = NO;
        NSTimer *wait = [NSTimer timerWithTimeInterval:3.0 repeats:YES block:^(NSTimer *timer) {
            if (done) { [timer invalidate]; return; }
            NSArray *viewers = [NSClassFromString(@"ViewerController") getDisplayed2DViewers];
            if (viewers.count == 0) return;
            id viewer = viewers.firstObject;
            NSArray *pixels = [viewer pixList];
            if (pixels.count == 0) return;
            done = YES;
            NSLog(@"GEOM151 %lu frame(s), source %@", (unsigned long)pixels.count,
                  [[pixels.firstObject srcFile] lastPathComponent]);
            for (NSUInteger index = 0; index < pixels.count; index++) {
                id pix = pixels[index];
                NSLog(@"GEOM151 frame %2lu  %ld x %ld  spacing %.3f x %.3f  thickness %.3f  "
                      @"interval %.3f  origin (%.3f, %.3f, %.3f)  value(0,0) %.1f",
                      (unsigned long)index, [pix pwidth], [pix pheight],
                      [pix pixelSpacingX], [pix pixelSpacingY], [pix sliceThickness],
                      [pix sliceInterval], [pix originX], [pix originY], [pix originZ],
                      [pix getPixelValueX:0 Y:0]);
            }
            NSLog(@"GEOM151 done");
        }];
        [NSRunLoop.mainRunLoop addTimer:wait forMode:NSRunLoopCommonModes];
    }];
}
