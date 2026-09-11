#!/usr/bin/env python3
"""Compile the host drawRect pattern against Swift and refuse nested display (#204)."""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
code = r'''
#import <Foundation/Foundation.h>
#import "CPRRender-Swift.h"

static int superCalls;

@interface FakeCPRView : NSObject
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
    HorosCPRRenderDecision *decision = [HorosCPRRenderLifecycle beginDrawNamed:@"mpr-native"];
    if (decision.accepted == NO)
        return;
    @try {
        superCalls++;
        [self drawRect];
    }
    @finally {
        [HorosCPRRenderLifecycle endDrawNamed:@"mpr-native"];
    }
}
@end

int main(void) {
    @autoreleasepool {
        [HorosCPRRenderLifecycle reset];
        [HorosCPRRenderLifecycle beginOpeningResampled:NO];
        [HorosCPRRenderLifecycle markOpen];
        [HorosCPRRenderLifecycle markCurveReady];
        FakeCPRView *view = [FakeCPRView new];
        [view drawRect];
        if (superCalls != 1) {
            NSLog(@"FAIL: nested drawRect was not gated, superCalls=%d", superCalls);
            return 1;
        }
        NSString *nan = [HorosCPRRenderLifecycle diagnoseSpacingX:NAN spacingY:1];
        if ([nan isEqualToString:@"not a number"] == NO) {
            NSLog(@"FAIL: NaN spacing diagnosis: %@", nan);
            return 1;
        }
        [HorosCPRRenderLifecycle beginClosing];
        HorosCPRRenderDecision *duringClose = [HorosCPRRenderLifecycle beginDrawNamed:@"mpr-native"];
        if (duringClose.accepted) {
            NSLog(@"FAIL: draw during close was accepted");
            return 1;
        }
        [HorosCPRRenderLifecycle markClosed];
        NSLog(@"PASS: nested drawRect skipped; NaN named; close refuses draw");
    }
    return 0;
}
'''
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
        'xcrun', 'clang', '-fno-objc-arc', '-framework', 'Foundation',
        '-I', d, str(p / 'test.m'), '-L', d, '-lCPRRender',
        '-o', str(p / 'test'),
    ], check=True)
    subprocess.run([str(p / 'test')], check=True)
