#import "ViewerController+GSPS.h"
#import "BrowserController+GSPS.h"
#import "GSPSFileReader.h"
#import "Horos-Swift.h"
#import "DCMPix.h"
#import "DCMView.h"
#import "ROI.h"
#import "MyPoint.h"
#import "DicomImage.h"

@implementation ViewerController (GSPS)

static NSMenuItem *HorosGSPSFindItem(NSMenu *menu, SEL action, NSMenu **owner)
{
    for (NSMenuItem *item in menu.itemArray)
    {
        if (item.action == action)
        {
            if (owner)
                *owner = menu;
            return item;
        }
        if (item.submenu)
        {
            NSMenuItem *found = HorosGSPSFindItem(item.submenu, action, owner);
            if (found)
                return found;
        }
    }
    return nil;
}

+ (void)installGSPSMenuItems
{
    NSMenu *owner = nil;
    if (HorosGSPSFindItem([NSApp mainMenu], @selector(applyGrayscaleSoftcopyPresentationState:), nil))
        return;

    NSMenuItem *anchor = HorosGSPSFindItem([NSApp mainMenu], @selector(roiExportInterchange:), &owner);
    if (anchor == nil)
        anchor = HorosGSPSFindItem([NSApp mainMenu], @selector(roiSaveSeries:), &owner);
    if (anchor == nil || owner == nil)
    {
        NSLog(@"GSPS: ROI menu item not found; Apply Grayscale Presentation State was not installed");
        return;
    }

    NSMenuItem *item = [[[NSMenuItem alloc] initWithTitle:NSLocalizedString(@"Apply Grayscale Presentation State…", nil)
                                                   action:@selector(applyGrayscaleSoftcopyPresentationState:)
                                            keyEquivalent:@""] autorelease];
    item.target = nil;
    [owner insertItem:item atIndex:[owner indexOfItem:anchor] + 1];
}

- (HorosGSPSImagePresentation *)horos_presentation:(HorosGSPSApplicationResult *)result
                                             sop:(NSString *)sop
                                          frames:(NSArray<NSNumber *> *)frames
{
    for (NSNumber *frame in frames)
    {
        for (HorosGSPSImagePresentation *presentation in result.presentations)
        {
            if ([presentation.sopInstanceUID isEqualToString:sop] && presentation.frameNumber == frame.intValue)
                return presentation;
        }
    }
    return nil;
}

- (ROI *)horos_roiFromAnnotation:(HorosGSPSAnnotation *)annotation pix:(DCMPix *)pix
{
    NSPoint origin = [DCMPix originCorrectedAccordingToOrientation:pix];
    NSString *kind = annotation.kind.uppercaseString;
    NSArray<NSValue *> *points = annotation.pointValues;
    if ([kind isEqualToString:@"TEXT"])
    {
        ROI *roi = [[[ROI alloc] initWithType:tText :pix.pixelSpacingX :pix.pixelSpacingY :origin] autorelease];
        roi.name = annotation.text.length ? annotation.text : @"GSPS";
        if (points.count)
        {
            NSPoint point = [points.firstObject pointValue];
            [roi setROIRect:NSMakeRect(point.x, point.y, 0, 0)];
        }
        roi.pix = pix;
        return roi;
    }
    if ([kind isEqualToString:@"POINT"] && points.count)
    {
        ROI *roi = [[[ROI alloc] initWithType:t2DPoint :pix.pixelSpacingX :pix.pixelSpacingY :origin] autorelease];
        NSPoint point = [points.firstObject pointValue];
        [roi setROIRect:NSMakeRect(point.x, point.y, 0, 0)];
        roi.name = @"GSPS";
        roi.pix = pix;
        return roi;
    }
    if (([kind isEqualToString:@"CIRCLE"] || [kind isEqualToString:@"ELLIPSE"]) && points.count)
    {
        CGFloat minX = CGFLOAT_MAX, minY = CGFLOAT_MAX, maxX = -CGFLOAT_MAX, maxY = -CGFLOAT_MAX;
        if ([kind isEqualToString:@"CIRCLE"] && points.count >= 2)
        {
            NSPoint center = [points[0] pointValue];
            NSPoint rim = [points[1] pointValue];
            CGFloat radius = hypot(rim.x - center.x, rim.y - center.y);
            minX = center.x - radius;
            minY = center.y - radius;
            maxX = center.x + radius;
            maxY = center.y + radius;
        }
        else
        {
            for (NSValue *value in points)
            {
                NSPoint point = value.pointValue;
                minX = MIN(minX, point.x);
                minY = MIN(minY, point.y);
                maxX = MAX(maxX, point.x);
                maxY = MAX(maxY, point.y);
            }
        }
        ROI *roi = [[[ROI alloc] initWithType:tOval :pix.pixelSpacingX :pix.pixelSpacingY :origin] autorelease];
        [roi setROIRect:NSMakeRect(minX, minY, maxX - minX, maxY - minY)];
        roi.name = @"GSPS";
        roi.pix = pix;
        return roi;
    }
    if ([kind isEqualToString:@"POLYLINE"] && points.count)
    {
        ROI *roi = [[[ROI alloc] initWithType:tOPolygon :pix.pixelSpacingX :pix.pixelSpacingY :origin] autorelease];
        NSMutableArray *vertices = [NSMutableArray array];
        for (NSValue *value in points)
            [vertices addObject:[MyPoint point:value.pointValue]];
        [roi setPoints:vertices];
        roi.name = @"GSPS";
        roi.pix = pix;
        return roi;
    }
    return nil;
}

- (void)horos_reportGSPSResult:(HorosGSPSApplicationResult *)result
{
    for (HorosGSPSImageReference *missing in result.missingReferences)
    {
        NSString *frames = missing.frameNumbers.count
            ? [missing.frameNumbers componentsJoinedByString:@","]
            : @"all";
        NSLog(@"GSPS: referenced SOP Instance UID %@ frame %@ is not in the open images; original pixels were not changed",
              missing.sopInstanceUID, frames);
    }
    for (NSString *flag in result.unsupportedFeatures)
        NSLog(@"GSPS: %@", flag);
    if (result.originalPixelsUnchanged == NO)
        NSLog(@"GSPS: apply reported a pixel-buffer change; that is a defect in the documented subset");
}

- (HorosGSPSApplicationResult *)applyGrayscaleSoftcopyPresentationStateFromPath:(NSString *)path
{
    HorosGSPSDocument *document = [HorosGSPSDocument documentWithContentsOfFile:path];
    if (document == nil)
    {
        NSLog(@"GSPS: %@ is not a Softcopy Presentation State this application can read", path.lastPathComponent);
        return nil;
    }

    NSMutableArray *available = [NSMutableArray array];
    NSMutableArray *pixList = [self pixList];
    NSMutableArray *fileList = [self fileList];
    NSUInteger count = MIN(pixList.count, fileList.count);
    float *firstSample = NULL;
    float firstValue = 0;
    BOOL sampled = NO;

    for (NSUInteger index = 0; index < count; index++)
    {
        DCMPix *pix = [pixList objectAtIndex:index];
        DicomImage *image = [fileList objectAtIndex:index];
        HorosGSPSAvailableImage *availableImage = [[[HorosGSPSAvailableImage alloc] init] autorelease];
        availableImage.sopInstanceUID = image.sopInstanceUID ?: pix.imageObj.sopInstanceUID ?: @"";
        NSInteger frameNo = pix.frameNo;
        availableImage.frameNumber = (int)frameNo + 1;
        availableImage.columns = (int)pix.pwidth;
        availableImage.rows = (int)pix.pheight;
        if (sampled == NO && pix.fImage)
        {
            firstSample = pix.fImage;
            firstValue = pix.fImage[0];
            sampled = YES;
            availableImage.pixelFingerprint = [NSData dataWithBytes:pix.fImage length:sizeof(float)];
        }
        [available addObject:availableImage];
    }

    HorosGSPSApplicationResult *result = [document applyToImages:available];
    [self horos_reportGSPSResult:result];

    DCMView *view = self.imageView;
    for (NSUInteger index = 0; index < count; index++)
    {
        DCMPix *pix = [pixList objectAtIndex:index];
        DicomImage *image = [fileList objectAtIndex:index];
        NSString *sop = image.sopInstanceUID ?: pix.imageObj.sopInstanceUID ?: @"";
        HorosGSPSImagePresentation *presentation = [self horos_presentation:result
                                                                        sop:sop
                                                                     frames:@[ @((int)pix.frameNo + 1),
                                                                               @(MAX(1, (int)pix.frameNo)),
                                                                               @(MAX(1, image.frameID.intValue)) ]];
        if (presentation == nil)
            continue;

        if (presentation.hasVOI)
            [pix changeWLWW:presentation.windowCenter :presentation.windowWidth];

        NSMutableArray *rois = [[self roiList] objectAtIndex:index];
        for (HorosGSPSAnnotation *annotation in presentation.annotations)
        {
            ROI *roi = [self horos_roiFromAnnotation:annotation pix:pix];
            if (roi)
                [rois addObject:roi];
        }

        if (view.curDCM == pix)
        {
            if (presentation.hasVOI)
                [view setWLWW:presentation.windowCenter :presentation.windowWidth];
            [view setRotation:presentation.rotationDegrees];
            view.xFlipped = presentation.horizontalFlip;
            if (presentation.displayedArea && [presentation.displayedArea.sizeMode isEqualToString:@"MAGNIFY"] && presentation.displayedArea.magnification > 0)
                view.scaleValue = (float)presentation.displayedArea.magnification;
        }
    }

    if (sampled && firstSample && firstSample[0] != firstValue)
        NSLog(@"GSPS: stored samples changed while applying a presentation state");

    [view setNeedsDisplay:YES];

    if (result.missingReferences.count || result.unsupportedFeatures.count)
    {
        NSMutableArray *lines = [NSMutableArray array];
        for (HorosGSPSImageReference *missing in result.missingReferences)
            [lines addObject:[NSString stringWithFormat:NSLocalizedString(@"Missing referenced SOP Instance UID %@", nil), missing.sopInstanceUID]];
        [lines addObjectsFromArray:result.unsupportedFeatures];
        NSAlert *alert = [[[NSAlert alloc] init] autorelease];
        alert.alertStyle = NSAlertStyleInformational;
        alert.messageText = NSLocalizedString(@"Grayscale Presentation State", nil);
        alert.informativeText = [lines componentsJoinedByString:@"\n"];
        [alert beginSheetModalForWindow:self.window completionHandler:nil];
    }
    return result;
}

- (IBAction)applyGrayscaleSoftcopyPresentationState:(id)sender
{
    NSOpenPanel *panel = [NSOpenPanel openPanel];
    panel.canChooseDirectories = NO;
    panel.allowsMultipleSelection = NO;
    panel.message = NSLocalizedString(@"Choose a Grayscale Softcopy Presentation State", nil);
    [panel beginSheetModalForWindow:self.window completionHandler:^(NSInteger result) {
        if (result != NSFileHandlingPanelOKButton)
            return;
        [self applyGrayscaleSoftcopyPresentationStateFromPath:panel.URL.path];
    }];
}

@end
