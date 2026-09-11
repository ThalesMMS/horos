#import "RegistrationHostBridge.h"
#import "ViewerController+ROIInterchange.h"
#import "Horos-Swift.h"
#import "DCMPix.h"
#import "DCMView.h"
#import "ROI.h"
#import "DicomStudy.h"
#import "DicomImage.h"
#import "Notifications.h"
#import <objc/runtime.h>

// Conversions the ROI interchange category implements without publishing.
@interface ViewerController (HorosRegistrationInterchangePrivate)
- (ROIInterchangeSeries *)interchangeSeriesIncludingROIs:(BOOL)includeROIs;
- (ROIInterchangeROI *)interchangeROIForROI:(ROI *)roi pix:(DCMPix *)pix;
- (ROI *)roiFromInterchangeROI:(ROIInterchangeROI *)record pix:(DCMPix *)pix;
@end

static char sessionKey;

static NSMenuItem *HorosRegistrationFindItem(NSMenu *menu, SEL action, NSMenu **owner)
{
    for (NSMenuItem *item in menu.itemArray) {
        if (item.action == action) { if (owner) *owner = menu; return item; }
        if (item.submenu) { NSMenuItem *found = HorosRegistrationFindItem(item.submenu, action, owner); if (found) return found; }
    }
    return nil;
}

@implementation ViewerController (HorosRegistration)

+ (void)installRegistrationMenuItems
{
    if (HorosRegistrationFindItem([NSApp mainMenu], @selector(copyROIsFromFusedSeries:), nil)) return;
    NSMenu *owner = nil;
    NSMenuItem *anchor = HorosRegistrationFindItem([NSApp mainMenu], @selector(roiExportInterchange:), &owner);
    if (!anchor || !owner) { NSLog(@"Registration: ROI export menu item not found; guided copy item not installed"); return; }
    NSMenuItem *item = [[[NSMenuItem alloc] initWithTitle:NSLocalizedString(@"Copy ROIs from Fused Series...", nil)
                                                   action:@selector(copyROIsFromFusedSeries:) keyEquivalent:@""] autorelease];
    item.target = nil; // first responder: the front 2D viewer
    [owner insertItem:item atIndex:[owner indexOfItem:anchor] + 1];
}

#pragma mark - Identity

- (NSString *)horosSeriesDICOMUID
{
    return [self interchangeSeriesIncludingROIs:NO].seriesInstanceUID ?: @"";
}

- (NSString *)horosFrameOfReferenceUID
{
    DCMPix *first = [[self pixList:0] count] ? [[self pixList:0] objectAtIndex:0] : nil;
    return first.frameofReferenceUID ?: @"";
}

- (HorosVolumeBounds *)horosVolumeBounds
{
    NSArray *pixes = [self pixList:0];
    if (pixes.count == 0) return nil;
    double lo[3] = {INFINITY, INFINITY, INFINITY}, hi[3] = {-INFINITY, -INFINITY, -INFINITY};
    for (DCMPix *pix in @[pixes.firstObject, pixes.lastObject]) {
        float corners[4][2] = {{0, 0}, {(float)pix.pwidth, 0}, {0, (float)pix.pheight}, {(float)pix.pwidth, (float)pix.pheight}};
        for (int c = 0; c < 4; c++) {
            float d[3] = {0, 0, 0};
            [pix convertPixX:corners[c][0] pixY:corners[c][1] toDICOMCoords:d pixelCenter:NO];
            for (int axis = 0; axis < 3; axis++) { lo[axis] = MIN(lo[axis], d[axis]); hi[axis] = MAX(hi[axis], d[axis]); }
        }
    }
    return [[[HorosVolumeBounds alloc] initWithMinimum:@[@(lo[0]), @(lo[1]), @(lo[2])] maximum:@[@(hi[0]), @(hi[1]), @(hi[2])]] autorelease];
}

- (HorosRegistrationSession *)horosRegistrationSession
{
    HorosRegistrationSession *session = objc_getAssociatedObject(self, &sessionKey);
    if (!session) {
        session = [[[HorosRegistrationSession alloc] initWithBaseSeriesInstanceUID:[self horosSeriesDICOMUID]
                                                           baseFrameOfReferenceUID:[self horosFrameOfReferenceUID]] autorelease];
        objc_setAssociatedObject(self, &sessionKey, session, OBJC_ASSOCIATION_RETAIN_NONATOMIC);
    }
    // The fused series is the companion; its blend is the host's fusion slider.
    ViewerController *fused = [self blendingController];
    if (fused) {
        NSString *uid = [fused horosSeriesDICOMUID];
        // The Fusion panel's blend slider spans -256...256 (shown as 0-100 %); the
        // image view keeps that value as its blending factor.
        double lo = [[self blendingSlider] minValue], hi = [[self blendingSlider] maxValue];
        double raw = [[self imageView] blendingFactor];
        double blend = hi > lo ? (raw - lo) / (hi - lo) : 0.5;
        [session addCompanionWithSeriesInstanceUID:uid frameOfReferenceUID:[fused horosFrameOfReferenceUID] blend:blend];
        [session setBlend:uid blend:blend];
        for (HorosCompanionOverlay *overlay in session.companions)
            if (![overlay.seriesInstanceUID isEqualToString:uid]) [session removeCompanion:overlay.seriesInstanceUID];
    } else {
        for (HorosCompanionOverlay *overlay in [session.companions copy]) [session removeCompanion:overlay.seriesInstanceUID];
    }
    return session;
}

#pragma mark - Landmarks

- (void)horosLandmarkNames:(NSMutableArray<NSString *> *)names points:(NSMutableArray<NSArray<NSNumber *> *> *)points
{
    for (ROI *roi in [self point2DList]) {
        DCMPix *pix = roi.pix;
        if (!pix || roi.type != t2DPoint) continue;
        float d[3] = {0, 0, 0};
        [pix convertPixX:roi.rect.origin.x pixY:roi.rect.origin.y toDICOMCoords:d pixelCenter:YES];
        [names addObject:roi.name ?: @""];
        [points addObject:@[@(d[0]), @(d[1]), @(d[2])]];
    }
}

- (HorosLandmarkRegistrationResult *)horosLandmarkRegistrationWithViewer:(ViewerController *)moving
{
    NSMutableArray *fixedNames = [NSMutableArray array], *fixedPoints = [NSMutableArray array];
    NSMutableArray *movingNames = [NSMutableArray array], *movingPoints = [NSMutableArray array];
    [self horosLandmarkNames:fixedNames points:fixedPoints];
    [moving horosLandmarkNames:movingNames points:movingPoints];
    return [HorosLandmarkRegistration solveWithFixedNames:fixedNames fixedPoints:fixedPoints movingNames:movingNames movingPoints:movingPoints
                                             movingBounds:[moving horosVolumeBounds] fixedBounds:[self horosVolumeBounds]];
}

- (HorosRegistrationTransform *)horosTransformFromViewer:(ViewerController *)source refusal:(NSString **)refusal
{
    if (refusal) *refusal = nil;
    if (!source) { if (refusal) *refusal = NSLocalizedString(@"No fused series. Fuse a series onto this viewer first (Fusion dialog).", nil); return nil; }
    NSString *base = [self horosFrameOfReferenceUID], *other = [source horosFrameOfReferenceUID];
    HorosRegistrationSession *session = [self horosRegistrationSession];
    NSString *uid = [source horosSeriesDICOMUID];
    if (base.length && [base isEqualToString:other]) {
        [session reset:uid];
        return [HorosRegistrationTransform identity];
    }
    HorosLandmarkRegistrationResult *result = [self horosLandmarkRegistrationWithViewer:source];
    if (result.refusal) {
        [session reject:uid];
        if (refusal) *refusal = [NSString stringWithFormat:NSLocalizedString(@"The series have different frames of reference and the landmark registration was refused: %@", nil), result.refusal];
        return nil;
    }
    BOOL usable = [session setRegistration:uid result:result];
    if (!usable) {
        if (refusal) *refusal = [NSString stringWithFormat:NSLocalizedString(@"The landmark registration was rejected: %@", nil), result.quality.summary];
        return nil;
    }
    return result.transform;
}

#pragma mark - Patient comparison

- (NSString *)horosPatientComparisonPendingWithViewer:(ViewerController *)other
{
    DicomStudy *a = [self currentStudy], *b = [other currentStudy];
    NSString *idA = a.patientID ?: @"", *idB = b.patientID ?: @"", *nameA = a.name ?: @"", *nameB = b.name ?: @"";
    NSString *studyA = a.studyInstanceUID ?: @"", *studyB = b.studyInstanceUID ?: @"";
    if (![HorosPatientComparisonSelection requiresExplicitChoiceWithPatientA:idA nameA:nameA patientB:idB nameB:nameB]) return nil;
    if ([HorosPatientComparisonSelection findIn:[NSUserDefaults standardUserDefaults] studyA:studyA patientA:idA studyB:studyB patientB:idB]) return nil;
    return [NSString stringWithFormat:@"%@ (%@) [%@]\n%@ (%@) [%@]", nameA, idA, studyA, nameB, idB, studyB];
}

- (void)horosConfirmPatientComparisonWithViewer:(ViewerController *)other
{
    DicomStudy *a = [self currentStudy], *b = [other currentStudy];
    HorosPatientComparisonSelection *selection =
        [[[HorosPatientComparisonSelection alloc] initWithFirstPatientID:a.patientID ?: @"" firstStudyInstanceUID:a.studyInstanceUID ?: @""
                                                          secondPatientID:b.patientID ?: @"" secondStudyInstanceUID:b.studyInstanceUID ?: @""
                                                              confirmedAt:[NSDate date]] autorelease];
    [selection storeIn:[NSUserDefaults standardUserDefaults]];
}

#pragma mark - Guided copy

- (HorosGuidedCopyPlan *)horosGuidedCopyPlanFromViewer:(ViewerController *)source offsetMM:(NSArray<NSNumber *> *)offsetMM refusal:(NSString **)refusal
{
    HorosRegistrationTransform *transform = [self horosTransformFromViewer:source refusal:refusal];
    if (!transform) return nil;
    ROIInterchangeSeries *sourceSeries = [source interchangeSeriesIncludingROIs:YES];
    ROIInterchangeSeries *targetSeries = [self interchangeSeriesIncludingROIs:NO];
    return [HorosGuidedROICopy planWithSource:sourceSeries target:targetSeries transform:transform offsetMM:offsetMM ?: @[@0, @0, @0]];
}

- (NSArray<ROI *> *)horosInterchangeableROIsOfViewer:(ViewerController *)viewer movie:(NSInteger)movie slice:(NSInteger)slice
{
    // The same filter the interchange export applies, so record j is ROI j here.
    NSMutableArray *out = [NSMutableArray array];
    if (movie < 0 || movie >= viewer.maxMovieIndex || slice < 0 || slice >= (NSInteger)[[viewer pixList:movie] count]) return out;
    DCMPix *pix = [[viewer pixList:movie] objectAtIndex:slice];
    NSArray *rois = slice < (NSInteger)[[viewer roiList:movie] count] ? [[viewer roiList:movie] objectAtIndex:slice] : @[];
    for (ROI *roi in rois) if ([viewer interchangeROIForROI:roi pix:pix]) [out addObject:roi];
    return out;
}

- (NSInteger)horosApplyGuidedCopyPlan:(HorosGuidedCopyPlan *)plan fromViewer:(ViewerController *)source
{
    if (!plan || plan.placed.count == 0 || !source) return 0;
    [self addToUndoQueue:@"roi"];
    [self roiSelectDeselectAll:nil];
    NSInteger added = 0;
    for (HorosGuidedCopyPlacement *placement in plan.placed) {
        NSArray<ROI *> *sources = [self horosInterchangeableROIsOfViewer:source movie:placement.sourceTemporalIndex slice:placement.sourceImageIndex];
        if (placement.sourceROIIndex < 0 || placement.sourceROIIndex >= (NSInteger)sources.count) continue;
        if (placement.targetTemporalIndex < 0 || placement.targetTemporalIndex >= self.maxMovieIndex) continue;
        NSArray *targetPixes = [self pixList:placement.targetTemporalIndex];
        if (placement.targetImageIndex < 0 || placement.targetImageIndex >= (NSInteger)targetPixes.count) continue;
        ROI *original = sources[placement.sourceROIIndex];
        DCMPix *sourcePix = [[source pixList:placement.sourceTemporalIndex] objectAtIndex:placement.sourceImageIndex];
        DCMPix *targetPix = targetPixes[placement.targetImageIndex];
        ROIInterchangeROI *record = [source interchangeROIForROI:original pix:sourcePix];
        if (!record) continue;
        if (record.typeCode == tPlain) {
            record.brushOriginX = (NSInteger)llround(placement.rect.origin.x);
            record.brushOriginY = (NSInteger)llround(placement.rect.origin.y);
        } else if (record.hasRect) {
            record.rect = placement.rect;
        } else {
            NSMutableArray *points = [NSMutableArray array];
            for (NSArray<NSNumber *> *xy in placement.points) [points addObject:[NSValue valueWithPoint:NSMakePoint(xy[0].doubleValue, xy[1].doubleValue)]];
            record.points = points;
        }
        record.comments = record.comments.length ? [NSString stringWithFormat:@"%@\n%@", record.comments, placement.provenance] : placement.provenance;
        ROI *roi = [self roiFromInterchangeROI:record pix:targetPix];
        if (!roi) continue;
        NSMutableArray *slice = [[self roiList:placement.targetTemporalIndex] objectAtIndex:placement.targetImageIndex];
        [slice addObject:roi];
        [[self imageView] roiSet:roi];
        [[NSNotificationCenter defaultCenter] postNotificationName:OsirixAddROINotification object:self
                                                          userInfo:@{@"ROI": roi, @"sliceNumber": @(placement.targetImageIndex)}];
        added++;
    }
    [[self imageView] setIndex:[[self imageView] curImage]];
    [[self imageView] setNeedsDisplay:YES];
    return added;
}

#pragma mark - UI

- (NSArray<NSNumber *> *)horosOffsetFromFields:(NSArray<NSTextField *> *)fields
{
    NSMutableArray *offset = [NSMutableArray array];
    for (NSTextField *field in fields) { double v = field.doubleValue; [offset addObject:@(isfinite(v) ? v : 0)]; }
    return offset;
}

- (IBAction)copyROIsFromFusedSeries:(id)sender
{
    ViewerController *source = [self blendingController];
    NSString *refusal = nil;
    if (!source) {
        NSAlert *alert = [[[NSAlert alloc] init] autorelease];
        alert.messageText = NSLocalizedString(@"Copy ROIs from Fused Series", nil);
        alert.informativeText = NSLocalizedString(@"No fused series. Fuse a series onto this viewer first (Fusion dialog).", nil);
        [alert runModal];
        return;
    }
    NSString *pending = [self horosPatientComparisonPendingWithViewer:source];
    if (pending) {
        NSAlert *alert = [[[NSAlert alloc] init] autorelease];
        alert.messageText = NSLocalizedString(@"Compare two different patients?", nil);
        alert.informativeText = [NSString stringWithFormat:NSLocalizedString(@"The fused series belongs to another patient. Confirm the comparison of these two studies explicitly; they are never matched by name:\n%@", nil), pending];
        [alert addButtonWithTitle:NSLocalizedString(@"Compare", nil)];
        [alert addButtonWithTitle:NSLocalizedString(@"Cancel", nil)];
        if ([alert runModal] != NSAlertFirstButtonReturn) return;
        [self horosConfirmPatientComparisonWithViewer:source];
    }
    NSArray<NSNumber *> *offset = @[@0, @0, @0];
    for (;;) {
        HorosGuidedCopyPlan *plan = [self horosGuidedCopyPlanFromViewer:source offsetMM:offset refusal:&refusal];
        if (!plan) {
            NSAlert *alert = [[[NSAlert alloc] init] autorelease];
            alert.messageText = NSLocalizedString(@"Copy ROIs from Fused Series", nil);
            alert.informativeText = refusal ?: @"";
            [alert runModal];
            return;
        }
        HorosCompanionOverlay *overlay = [[self horosRegistrationSession] companion:[source horosSeriesDICOMUID]];
        NSString *quality = overlay.quality ? overlay.quality.summary : NSLocalizedString(@"Shared frame of reference: identity transform, no registration estimated.", nil);
        NSAlert *alert = [[[NSAlert alloc] init] autorelease];
        alert.messageText = [NSString stringWithFormat:NSLocalizedString(@"Copy %lu ROI(s) by patient position?", nil), (unsigned long)plan.placed.count];
        alert.informativeText = [NSString stringWithFormat:@"%@\n%@ %@\n\n%@", quality, plan.transform.algorithm, plan.transform.version, plan.summary];
        NSView *accessory = [[[NSView alloc] initWithFrame:NSMakeRect(0, 0, 320, 48)] autorelease];
        NSTextField *label = [[[NSTextField alloc] initWithFrame:NSMakeRect(0, 26, 320, 18)] autorelease];
        label.stringValue = NSLocalizedString(@"Manual offset in target millimetres (x, y, z):", nil);
        label.editable = NO; label.bordered = NO; label.drawsBackground = NO;
        [accessory addSubview:label];
        NSMutableArray<NSTextField *> *fields = [NSMutableArray array];
        for (int i = 0; i < 3; i++) {
            NSTextField *field = [[[NSTextField alloc] initWithFrame:NSMakeRect(i * 108, 0, 100, 22)] autorelease];
            field.doubleValue = offset[i].doubleValue;
            [accessory addSubview:field]; [fields addObject:field];
        }
        alert.accessoryView = accessory;
        [alert addButtonWithTitle:NSLocalizedString(@"Copy", nil)];
        [alert addButtonWithTitle:NSLocalizedString(@"Preview with Offset", nil)];
        [alert addButtonWithTitle:NSLocalizedString(@"Cancel", nil)];
        NSModalResponse response = [alert runModal];
        if (response == NSAlertSecondButtonReturn) { offset = [self horosOffsetFromFields:fields]; continue; }
        if (response != NSAlertFirstButtonReturn) return;
        NSArray<NSNumber *> *finalOffset = [self horosOffsetFromFields:fields];
        if (![finalOffset isEqualToArray:offset]) {
            plan = [self horosGuidedCopyPlanFromViewer:source offsetMM:finalOffset refusal:&refusal];
            if (!plan) return;
        }
        NSInteger added = [self horosApplyGuidedCopyPlan:plan fromViewer:source];
        NSLog(@"Guided ROI copy: %ld ROI(s) added, %lu refused", (long)added, (unsigned long)plan.refused.count);
        return;
    }
}

@end
