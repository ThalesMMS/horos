#!/usr/bin/env python3
"""Turning propagation off must not flatten the series it is meant to un-flatten."""
from pathlib import Path
import re
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
source = (root / 'Horos/Sources/DCMView.m').read_bytes().decode('latin1')
start = source.index('- (void) writeCopySettingsInSeriesForPixels:')
method = source[start:source.index('\n}', start) + 2]

program = r'''
#import <Foundation/Foundation.h>

// The presentation state of one image, as key-value pairs. A nil value means
// the image has none of its own and falls back to what the file says.
@interface DicomImage : NSObject
@property(retain) NSMutableDictionary *values;
@end
@implementation DicomImage
- (id) init { if ((self = [super init])) self.values = [NSMutableDictionary dictionary]; return self; }
- (void) setValue:(id)value forKey:(NSString*)key {
    if (value) [self.values setObject:value forKey:key];
    else [self.values removeObjectForKey:key];
}
- (id) valueForKey:(NSString*)key { return [self.values objectForKey:key]; }
@end

@interface DCMPix : NSObject
@property(retain) DicomImage *imageObj;
@property BOOL isLoaded;
@property float appliedWL, appliedWW;
@property BOOL windowChanged;
@end
@implementation DCMPix
- (void) changeWLWW:(float)wl :(float)ww {
    self.appliedWL = wl; self.appliedWW = ww; self.windowChanged = YES;
}
@end

@interface ViewProbe : NSObject {
@public
    float curWL, curWW, scaleValue, rotation;
    BOOL yFlipped, xFlipped, COPYSETTINGSINSERIES, scaledFit;
    NSPoint origin;
    DicomImage *_imageObj;
}
@property(readonly) DicomImage *imageObj;
- (BOOL) isScaledFit;
@end
@implementation ViewProbe
- (DicomImage*) imageObj { return _imageObj; }
- (BOOL) isScaledFit { return scaledFit; }
METHOD
@end

#define check(...) do{ if(!(__VA_ARGS__)){ NSLog(@"FAIL: %s", #__VA_ARGS__); return 1; } }while(0)

static DCMPix *pixel(void) {
    DCMPix *pix = [DCMPix new];
    pix.imageObj = [DicomImage new];
    pix.isLoaded = YES;
    return pix;
}

int main(void) { @autoreleasepool {
    ViewProbe *view = [ViewProbe new];
    view->curWL = 1234; view->curWW = 88;
    view->scaleValue = 2.5; view->rotation = 90;
    view->yFlipped = YES; view->xFlipped = NO;
    view->origin = NSMakePoint(3, 4);
    view->scaledFit = NO;

    NSArray *pixels = @[ pixel(), pixel(), pixel() ];
    view->_imageObj = [(DCMPix*)pixels[1] imageObj];   // the image on screen

    // Off: only the image on screen records what is on screen. Every other
    // image keeps what it had, which for an untouched image is nothing, so it
    // falls back to its own window from the file. This is the whole point of
    // the option, and it used to write the current window onto all of them.
    view->COPYSETTINGSINSERIES = NO;
    [view writeCopySettingsInSeriesForPixels: pixels];

    DicomImage *shown = [(DCMPix*)pixels[1] imageObj];
    check([[shown valueForKey:@"windowWidth"] floatValue] == 88);
    check([[shown valueForKey:@"windowLevel"] floatValue] == 1234);
    check([[shown valueForKey:@"scale"] floatValue] == 2.5);
    check([[shown valueForKey:@"rotationAngle"] floatValue] == 90);
    check([[shown valueForKey:@"yFlipped"] boolValue] == YES);
    // This took its value from yFlipped, so turning propagation off flipped a
    // vertically flipped series horizontally.
    check([[shown valueForKey:@"xFlipped"] boolValue] == NO);
    check([[shown valueForKey:@"xOffset"] floatValue] == 3);
    check([[shown valueForKey:@"yOffset"] floatValue] == 4);

    for (DCMPix *pix in @[ pixels[0], pixels[2] ]) {
        check([[pix imageObj].values count] == 0);
        check(pix.windowChanged == NO);
    }

    // A window the user set on another image is not touched either.
    DicomImage *other = [(DCMPix*)pixels[0] imageObj];
    [other setValue:[NSNumber numberWithFloat:200] forKey:@"windowWidth"];
    [other setValue:[NSNumber numberWithFloat:300] forKey:@"windowLevel"];
    [view writeCopySettingsInSeriesForPixels: pixels];
    check([[other valueForKey:@"windowWidth"] floatValue] == 200);
    check([[other valueForKey:@"windowLevel"] floatValue] == 300);

    // Scale-to-fit is stored as "no scale of its own" rather than as a number.
    view->scaledFit = YES;
    [view writeCopySettingsInSeriesForPixels: pixels];
    check([shown valueForKey:@"scale"] == nil);

    // On: the flattening the option promises. Every image loses its own
    // settings and every loaded one takes the window on screen.
    view->COPYSETTINGSINSERIES = YES;
    [view writeCopySettingsInSeriesForPixels: pixels];
    for (DCMPix *pix in pixels) {
        check([[pix imageObj].values count] == 0);
        check(pix.appliedWL == 1234 && pix.appliedWW == 88);
    }

    // An image that is not loaded is not windowed, but is still cleared.
    DCMPix *unloaded = pixel();
    unloaded.isLoaded = NO;
    [[unloaded imageObj] setValue:[NSNumber numberWithFloat:1] forKey:@"windowWidth"];
    [view writeCopySettingsInSeriesForPixels: @[ unloaded ]];
    check(unloaded.windowChanged == NO);
    check([[unloaded imageObj].values count] == 0);

    NSLog(@"PASS: propagation off records only the image on screen, on flattens the series, xFlipped is xFlipped");
    return 0;
}}
'''.replace('METHOD', method)

# The database path that carries one series' presentation onto images gathered
# from several series asked whether the destination already had the setting.
browser = (root / 'Horos/Sources/BrowserController.m').read_bytes().decode('latin1')
block_start = browser.index('- (IBAction) viewerKeyImagesAndROIsImages:')
block = browser[block_start:browser.index('AUTOTILING', block_start)]
copies = re.findall(r'if\( \[(\w+) valueForKey: @"(\w+)"\]\)\s*\n\s*\[im setValue: \[d valueForKey: @"\2"\]',
                    block)
assert copies, 'the presentation copy loop was not found'
for guarded, key in copies:
    assert guarded == 'd', (
        f'the {key} copy asks whether the destination image already has one, '
        'so an image with no presentation of its own is skipped')

with tempfile.TemporaryDirectory(prefix='horos-copy-settings-') as tmp:
    p = Path(tmp)
    (p / 'test.m').write_text(program)
    subprocess.run(['xcrun', 'clang', '-fobjc-arc', '-framework', 'Foundation',
                    '-framework', 'AppKit', str(p / 'test.m'), '-o', str(p / 'test')],
                   check=True)
    subprocess.run([str(p / 'test')], check=True)
