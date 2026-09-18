#!/usr/bin/env python3
"""Check CPR draw lifecycle and the host viewport geometry at 1x and 2x."""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
mpr_source = (root / 'Horos/Sources/CPRMPRDCMView.m').read_text(encoding='latin1')
frame_start = mpr_source.index('- (void) checkForFrame\n')
frame_end = mpr_source.index('\n}', frame_start) + 2
code = r'''
#import <Cocoa/Cocoa.h>
#import "CPRRender-Swift.h"

static int superCalls;
static int repaintsAsked;

@interface CPRFrameView : NSView {
    NSView *vrView;
}
@property CGFloat backingScale;
@property (nonatomic, retain) NSView *vrView;
- (void)checkForFrame;
@end

@implementation CPRFrameView
@synthesize vrView;
- (NSRect)convertRectToBacking:(NSRect)rect
{
    return NSMakeRect(rect.origin.x * self.backingScale, rect.origin.y * self.backingScale,
                      rect.size.width * self.backingScale, rect.size.height * self.backingScale);
}
HOST_CHECK_FOR_FRAME
@end

// The real views take the lifecycle from their window controller, so a second
// Curved MPR window cannot gate this one.
@interface FakeCPRView : NSObject
@property (nonatomic, retain) HorosCPRRenderLifecycle *lifecycle;
- (void)drawRect;
@end

@implementation FakeCPRView
- (void)drawRect
{
    NSString *geo = [HorosCPRRenderLifecycle diagnoseSpacingX:1 spacingY:1];
    if ([geo isEqualToString:@"ready"] == NO) {
        NSLog(@"FAIL: ready geometry was refused: %@", geo);
        exit(1);
    }
    HorosCPRRenderDecision *decision = [self.lifecycle beginDrawNamed:@"mpr-native"];
    if (decision.accepted == NO) {
        // Returning paints nothing; the panel would stay blank unless the view
        // asks for another pass once this stack unwinds.
        if ([decision.phase isEqualToString:@"reentrant"])
            repaintsAsked++;
        return;
    }
    @try {
        superCalls++;
        [self drawRect];
    }
    @finally {
        [self.lifecycle endDrawNamed:@"mpr-native"];
    }
}
@end

int main(void) {
    @autoreleasepool {
        [NSApplication sharedApplication];
        NSWindow *host = [[NSWindow alloc] initWithContentRect:NSMakeRect(0, 0, 800, 600)
            styleMask:NSWindowStyleMaskBorderless backing:NSBackingStoreBuffered defer:NO];
        NSView *container = [[NSView alloc] initWithFrame:NSMakeRect(80, 30, 600, 500)];
        [[host contentView] addSubview:container];
        CPRFrameView *plane = [[CPRFrameView alloc] initWithFrame:NSMakeRect(20, 15, 400, 300)];
        [container addSubview:plane];
        plane.vrView = [[NSView alloc] initWithFrame:NSZeroRect];
        for (int scale = 1; scale <= 2; ++scale) {
            plane.backingScale = scale;
            [plane setFrame:NSMakeRect(20, 15, 400, 300)];
            [plane checkForFrame];
            NSRect expected = NSMakeRect(100, 45, 400, 300);
            if (!NSEqualRects([plane.vrView frame], expected)) {
                NSLog(@"FAIL: CPR renderer frame at %dx: %@, expected %@", scale,
                    NSStringFromRect([plane.vrView frame]), NSStringFromRect(expected));
                return 1;
            }
            [plane setFrame:NSMakeRect(30, 25, 320, 240)];
            [plane checkForFrame];
            expected = NSMakeRect(110, 55, 320, 240);
            if (!NSEqualRects([plane.vrView frame], expected)) {
                NSLog(@"FAIL: CPR renderer frame after resizing at %dx", scale);
                return 1;
            }
        }

        HorosCPRRenderLifecycle *window = [[HorosCPRRenderLifecycle alloc] init];
        [window reset];
        [window beginOpeningResampled:NO];
        [window markOpen];
        [window markCurveReady];
        FakeCPRView *view = [FakeCPRView new];
        view.lifecycle = window;
        [view drawRect];
        if (superCalls != 1) {
            NSLog(@"FAIL: nested drawRect was not gated, superCalls=%d", superCalls);
            return 1;
        }
        if (repaintsAsked != 1) {
            NSLog(@"FAIL: the refused nested draw did not ask for another pass, repaintsAsked=%d", repaintsAsked);
            return 1;
        }
        NSString *nan = [HorosCPRRenderLifecycle diagnoseSpacingX:NAN spacingY:1];
        if ([nan isEqualToString:@"not a number"] == NO) {
            NSLog(@"FAIL: NaN spacing diagnosis: %@", nan);
            return 1;
        }

        // A second window closing must not stop this one from drawing.
        HorosCPRRenderLifecycle *other = [[HorosCPRRenderLifecycle alloc] init];
        [other reset];
        [other markOpen];
        [other beginClosing];
        [other markClosed];
        superCalls = 0;
        [view drawRect];
        if (superCalls != 1) {
            NSLog(@"FAIL: closing another CPR window blanked this one, superCalls=%d", superCalls);
            return 1;
        }

        [window beginClosing];
        HorosCPRRenderDecision *duringClose = [window beginDrawNamed:@"mpr-native"];
        if (duringClose.accepted) {
            NSLog(@"FAIL: draw during close was accepted");
            return 1;
        }
        [window markClosed];
        NSLog(@"PASS: CPR viewport stays in points at 1x/2x and after resizing; nested draw repaints; window lifecycle is isolated");
    }
    return 0;
}
'''
code = code.replace('HOST_CHECK_FOR_FRAME', mpr_source[frame_start:frame_end])
with tempfile.TemporaryDirectory(prefix='horos-cpr-render-native-') as d:
    p = Path(d)
    (p / 'test.m').write_text(code)
    subprocess.run([
        'xcrun', 'swiftc',
        str(root / 'Horos/Sources/CPRRenderLifecycle.swift'),
        '-emit-library', '-module-name', 'CPRRender',
        '-emit-objc-header-path', str(p / 'CPRRender-Swift.h'),
        '-o', str(p / 'libCPRRender.dylib'),
    ], check=True)
    subprocess.run([
        'xcrun', 'clang', '-fno-objc-arc', '-framework', 'Cocoa',
        '-I', d, str(p / 'test.m'), '-L', d, '-lCPRRender',
        '-o', str(p / 'test'),
    ], check=True)
    subprocess.run([str(p / 'test')], check=True)
