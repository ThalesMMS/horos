#import "RegisteredGIFHostBridge.h"
#import "RegistrationHostBridge.h"
#import "Horos-Swift.h"
#import "DCMView.h"

static NSMenuItem *HorosRegisteredGIFFindItem(NSMenu *menu, SEL action, NSMenu **owner)
{
    for (NSMenuItem *item in menu.itemArray) {
        if (item.action == action) { if (owner) *owner = menu; return item; }
        if (item.submenu) { NSMenuItem *found = HorosRegisteredGIFFindItem(item.submenu, action, owner); if (found) return found; }
    }
    return nil;
}

@implementation ViewerController (HorosRegisteredGIF)

+ (void)installRegisteredGIFMenuItems
{
    if (HorosRegisteredGIFFindItem([NSApp mainMenu], @selector(copyRegisteredComparisonGIF:), nil)) return;
    NSMenu *owner = nil;
    NSMenuItem *anchor = HorosRegisteredGIFFindItem([NSApp mainMenu], @selector(copyROIsFromFusedSeries:), &owner);
    if (!anchor) anchor = HorosRegisteredGIFFindItem([NSApp mainMenu], @selector(roiExportInterchange:), &owner);
    if (!anchor || !owner) { NSLog(@"Registered GIF: anchor menu item not found; item not installed"); return; }
    NSMenuItem *item = [[[NSMenuItem alloc] initWithTitle:NSLocalizedString(@"Copy Registered Comparison as GIF", nil)
                                                   action:@selector(copyRegisteredComparisonGIF:) keyEquivalent:@""] autorelease];
    item.target = nil; // first responder: the front 2D viewer
    [owner insertItem:item atIndex:[owner indexOfItem:anchor] + 1];
}

- (HorosRegisteredGIFResult *)horosRegisteredComparisonGIFWithBlendStops:(NSArray<NSNumber *> *)blendStops
                                                           delaySeconds:(double)delaySeconds
                                                                refusal:(NSString **)refusal
{
    if (refusal) *refusal = nil;
    HorosRegistrationSession *session = [self horosRegistrationSession];
    ViewerController *fused = [self blendingController];
    NSString *companion = [fused horosSeriesDICOMUID] ?: @"";
    NSMutableArray<NSNumber *> *stops = [NSMutableArray array];
    for (NSNumber *stop in blendStops) [stops addObject:@(stop.doubleValue)];

    HorosRegisteredGIFPlan *plan = [HorosRegisteredGIF planForSession:session
                                                            companion:companion
                                                           blendStops:stops
                                                         delaySeconds:delaySeconds];
    if (!plan.isUsable) {
        if (refusal) *refusal = plan.refusal;
        return [HorosRegisteredGIF dataForPlan:plan images:@[]];
    }

    // Move the host's own fusion blend, capture what the viewer draws, and put
    // the blend back exactly where the user had it.
    NSSlider *slider = [self blendingSlider];
    double previous = slider.doubleValue, low = slider.minValue, high = slider.maxValue;
    NSMutableArray<NSImage *> *frames = [NSMutableArray array];
    @try {
        for (NSNumber *stop in plan.blendValues) {
            [slider setDoubleValue:low + stop.doubleValue * (high - low)];
            [self blendingSlider:slider];
            [[self imageView] display];
            NSImage *capture = [[self imageView] nsimage:NO];
            if (!capture) break;
            [frames addObject:capture];
        }
    }
    @finally {
        [slider setDoubleValue:previous];
        [self blendingSlider:slider];
        [[self imageView] display];
    }

    // A comparison that changed while it was being captured is not this plan.
    NSString *moved = [HorosRegisteredGIF refusalForApplyingPlan:plan toSession:[self horosRegistrationSession]];
    if (moved.length) {
        if (refusal) *refusal = moved;
        return [HorosRegisteredGIF refusedResultWithReason:moved];
    }

    HorosRegisteredGIFResult *result = [HorosRegisteredGIF dataForPlan:plan images:frames];
    if (!result.isUsable && refusal) *refusal = result.refusal;
    return result;
}

- (IBAction)copyRegisteredComparisonGIF:(id)sender
{
    NSString *refusal = nil;
    HorosRegisteredGIFResult *result =
        [self horosRegisteredComparisonGIFWithBlendStops:[HorosRegisteredGIF blinkStops]
                                           delaySeconds:[HorosRegisteredGIF defaultDelaySeconds]
                                                refusal:&refusal];
    if (!result.isUsable || ![HorosRegisteredGIF copyData:result.data toPasteboard:[NSPasteboard generalPasteboard]]) {
        NSAlert *alert = [[[NSAlert alloc] init] autorelease];
        alert.messageText = NSLocalizedString(@"The Comparison Was Not Copied", nil);
        alert.informativeText = refusal.length ? refusal
            : NSLocalizedString(@"The registered comparison could not be copied to the clipboard.", nil);
        [alert addButtonWithTitle:NSLocalizedString(@"OK", nil)];
        [alert runModal];
        return;
    }
    NSLog(@"--- registered comparison copied to the clipboard: %ld frames, %ldx%ld",
          (long)result.frameCount, (long)result.width, (long)result.height);
}

@end
