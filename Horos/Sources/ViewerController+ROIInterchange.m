/*
 ViewerController+ROIInterchange.m
 Horos
*/

#import "ViewerController+ROIInterchange.h"
#import "Horos-Swift.h"
#import "DCMPix.h"
#import "DCMView.h"
#import "ROI.h"
#import "MyPoint.h"
#import "DicomImage.h"
#import "DicomSeries.h"
#import "DicomStudy.h"
#import "Notifications.h"

static BOOL ROIImportSetError(NSError **error, NSInteger code, NSString *reason)
{
    if( error)
        *error = [NSError errorWithDomain: HorosROIAssociation.errorDomain code: code
                                 userInfo: @{ NSLocalizedDescriptionKey: reason ?: @"" }];
    return NO;
}

@implementation ViewerController (ROIInterchange)

#pragma mark - Menu

static NSMenuItem *ROIInterchangeFindItem( NSMenu *menu, SEL action, NSMenu **owner)
{
    for( NSMenuItem *item in menu.itemArray)
    {
        if( item.action == action)
        {
            if( owner) *owner = menu;
            return item;
        }

        if( item.submenu)
        {
            NSMenuItem *found = ROIInterchangeFindItem( item.submenu, action, owner);
            if( found) return found;
        }
    }
    return nil;
}

+ (void) installROIInterchangeMenuItems
{
    NSMenu *owner = nil;

    if( ROIInterchangeFindItem( [NSApp mainMenu], @selector( roiExportInterchange:), nil))
        return;

    NSMenuItem *anchor = ROIInterchangeFindItem( [NSApp mainMenu], @selector( roiSaveSeries:), &owner);

    if( anchor == nil || owner == nil)
    {
        NSLog( @"ROI interchange: 'Save All ROIs of this Series' menu item not found; export item not installed");
        return;
    }

    NSMenuItem *item = [[[NSMenuItem alloc] initWithTitle: NSLocalizedString( @"Export ROIs as JSON...", nil)
                                                   action: @selector( roiExportInterchange:)
                                            keyEquivalent: @""] autorelease];
    item.target = nil; // first responder: the front 2D viewer

    [owner insertItem: item atIndex: [owner indexOfItem: anchor] + 1];
}

#pragma mark - Conversion to interchange records

- (ROIInterchangeROI*) interchangeROIForROI:(ROI*) roi pix:(DCMPix*) pix
{
    if( roi.type == tLayerROI)
        return nil; // Layers carry an image, not a geometry; not part of the format.

    ROIInterchangeROI *record = [[[ROIInterchangeROI alloc] init] autorelease];

    record.name = roi.name ?: @"";
    record.typeCode = roi.type;
    record.comments = roi.comments;

    NSMutableArray *points = [NSMutableArray array];
    NSMutableArray *patientPoints = [NSMutableArray array];

    for( MyPoint *p in roi.points)
    {
        NSPoint pt = p.point;
        [points addObject: [NSValue valueWithPoint: pt]];

        float d[ 3] = {0, 0, 0};
        [pix convertPixX: pt.x pixY: pt.y toDICOMCoords: d pixelCenter: NO];
        [patientPoints addObject: @[@((double) d[ 0]), @((double) d[ 1]), @((double) d[ 2])]];
    }

    record.points = points;
    record.patientPoints = patientPoints;

    if( roi.type == tROI || roi.type == tOval || roi.type == t2DPoint)
    {
        record.hasRect = YES;
        record.rect = roi.rect;
    }

    record.thickness = roi.thickness;
    record.opacity = roi.opacity;

    RGBColor color = roi.rgbcolor;
    record.red = color.red / 65535.0;
    record.green = color.green / 65535.0;
    record.blue = color.blue / 65535.0;

    record.isSpline = roi.isSpline;
    record.groupID = roi.groupID;

    if( roi.type == tPlain)
    {
        if( roi.textureBuffer == nil || roi.textureWidth <= 0 || roi.textureHeight <= 0)
            return nil;

        record.brushWidth = roi.textureWidth;
        record.brushHeight = roi.textureHeight;
        record.brushOriginX = roi.textureUpLeftCornerX;
        record.brushOriginY = roi.textureUpLeftCornerY;
        record.brushMask = [NSData dataWithBytes: roi.textureBuffer length: (NSUInteger) roi.textureWidth * (NSUInteger) roi.textureHeight];
    }

    return record;
}

- (ROIInterchangeSeries*) interchangeSeriesIncludingROIs:(BOOL) includeROIs
{
    ROIInterchangeSeries *series = [[[ROIInterchangeSeries alloc] init] autorelease];

    DCMPix *first = [[self pixList: 0] count] ? [[self pixList: 0] objectAtIndex: 0] : nil;
    DicomImage *image = first.imageObj;

    series.studyInstanceUID = [image valueForKeyPath: @"series.study.studyInstanceUID"];
    // seriesDICOMUID is the DICOM Series Instance UID; seriesInstanceUID is Horos' composite key
    // (series number + UID) and must not leak into an interchange file.
    series.seriesInstanceUID = [image valueForKeyPath: @"series.seriesDICOMUID"];
    if( series.seriesInstanceUID.length == 0)
    {
        NSString *composite = [image valueForKeyPath: @"series.seriesInstanceUID"];
        NSRange space = [composite rangeOfString: @" "];
        series.seriesInstanceUID = (space.location != NSNotFound) ? [composite substringFromIndex: space.location + 1] : composite;
    }
    series.frameOfReferenceUID = first.frameofReferenceUID;
    series.modality = [image valueForKeyPath: @"series.modality"];
    series.seriesDescription = [image valueForKeyPath: @"series.name"];

    NSMutableArray *images = [NSMutableArray array];

    for( int y = 0; y < self.maxMovieIndex; y++)
    {
        NSArray *pixes = [self pixList: y];
        NSArray *rois = [self roiList: y];

        for( int x = 0; x < pixes.count; x++)
        {
            DCMPix *pix = [pixes objectAtIndex: x];
            ROIInterchangeImage *record = [[[ROIInterchangeImage alloc] init] autorelease];

            record.index = x;
            record.temporalIndex = y;
            record.sopInstanceUID = pix.imageObj.sopInstanceUID;
            record.frame = pix.frameNo;
            record.instanceNumber = pix.imageObj.instanceNumber ? [pix.imageObj.instanceNumber intValue] : -1;
            record.rows = pix.pheight;
            record.columns = pix.pwidth;
            record.pixelSpacingX = pix.pixelSpacingX;
            record.pixelSpacingY = pix.pixelSpacingY;
            record.sliceThickness = pix.sliceThickness;
            record.sliceLocation = pix.sliceLocation;
            record.imagePosition = @[@(pix.originX), @(pix.originY), @(pix.originZ)];

            float o[ 9] = {0, 0, 0, 0, 0, 0, 0, 0, 0};
            [pix orientation: o];
            if( o[ 0] != 0 || o[ 1] != 0 || o[ 2] != 0 || o[ 3] != 0 || o[ 4] != 0 || o[ 5] != 0)
                record.imageOrientation = @[@((double) o[ 0]), @((double) o[ 1]), @((double) o[ 2]), @((double) o[ 3]), @((double) o[ 4]), @((double) o[ 5])];

            if( includeROIs && x < rois.count)
            {
                NSMutableArray *converted = [NSMutableArray array];

                for( ROI *roi in [rois objectAtIndex: x])
                {
                    ROIInterchangeROI *r = [self interchangeROIForROI: roi pix: pix];
                    if( r) [converted addObject: r];
                }

                record.rois = converted;
            }

            [images addObject: record];
        }
    }

    series.images = images;
    return series;
}

#pragma mark - Conversion from interchange records

- (ROI*) roiFromInterchangeROI:(ROIInterchangeROI*) record pix:(DCMPix*) pix
{
    NSPoint origin = [DCMPix originCorrectedAccordingToOrientation: pix];
    ROI *roi = nil;

    if( record.typeCode == tPlain)
    {
        if( record.brushMask.length != (NSUInteger) record.brushWidth * (NSUInteger) record.brushHeight)
            return nil;

        unsigned char *buffer = malloc( record.brushMask.length);
        if( buffer == nil) return nil;
        memcpy( buffer, record.brushMask.bytes, record.brushMask.length);

        roi = [[[ROI alloc] initWithTexture: buffer textWidth: (int) record.brushWidth textHeight: (int) record.brushHeight textName: record.name
                                  positionX: (int) record.brushOriginX positionY: (int) record.brushOriginY
                                   spacingX: pix.pixelSpacingX spacingY: pix.pixelSpacingY imageOrigin: origin] autorelease];
        free( buffer);
    }
    else
    {
        roi = [[[ROI alloc] initWithType: (ToolMode) record.typeCode :pix.pixelSpacingX :pix.pixelSpacingY :origin] autorelease];
        roi.name = record.name;

        if( record.typeCode == tROI || record.typeCode == tOval || record.typeCode == t2DPoint)
        {
            [roi setROIRect: record.rect];
        }
        else
        {
            NSMutableArray *points = [NSMutableArray array];
            for( NSValue *v in record.points)
                [points addObject: [MyPoint point: v.pointValue]];
            [roi setPoints: points];
        }
    }

    if( roi == nil) return nil;

    roi.comments = record.comments;
    roi.thickness = record.thickness;
    roi.opacity = record.opacity;

    RGBColor color;
    color.red = (unsigned short) (MIN( MAX( record.red, 0), 1) * 65535.0);
    color.green = (unsigned short) (MIN( MAX( record.green, 0), 1) * 65535.0);
    color.blue = (unsigned short) (MIN( MAX( record.blue, 0), 1) * 65535.0);
    [roi setColor: color];

    roi.isSpline = record.isSpline;
    roi.groupID = record.groupID;
    roi.pix = pix;

    return roi;
}

#pragma mark - Export

- (BOOL) exportROIInterchangeToURL:(NSURL*) url error:(NSError**) error
{
    ROIInterchangeSeries *series = [self interchangeSeriesIncludingROIs: YES];
    NSString *generator = [NSString stringWithFormat: @"Horos %@", [[NSBundle mainBundle] objectForInfoDictionaryKey: @"CFBundleShortVersionString"] ?: @""];

    NSData *data = [ROIInterchange encode: series generator: generator error: error];
    if( data == nil)
        return NO;

    return [data writeToURL: url options: NSDataWritingAtomic error: error];
}

- (IBAction) roiExportInterchange:(id) sender
{
    NSSavePanel *panel = [NSSavePanel savePanel];

    [panel setCanSelectHiddenExtension: NO];
    panel.allowedFileTypes = @[ROIInterchange.fileExtension];

    NSString *seriesName = [[[self fileList] objectAtIndex: 0] valueForKeyPath: @"series.name"];
    panel.nameFieldStringValue = [NSString stringWithFormat: @"%@ ROIs.%@", seriesName.length ? seriesName : @"Series", ROIInterchange.fileExtension];

    [panel beginSheetModalForWindow: self.window completionHandler: ^(NSInteger result) {
        if( result != NSFileHandlingPanelOKButton)
            return;

        NSError *error = nil;
        if( [self exportROIInterchangeToURL: panel.URL error: &error] == NO)
        {
            NSAlert *alert = [[[NSAlert alloc] init] autorelease];
            alert.alertStyle = NSAlertStyleCritical;
            alert.messageText = NSLocalizedString( @"ROIs Export Error", nil);
            alert.informativeText = error.localizedDescription ?: NSLocalizedString( @"The ROIs could not be exported.", nil);
            [alert runModal];
        }
    }];
}

#pragma mark - Import

- (void) presentROIImportErrorForPath:(NSString*) path error:(NSError*) error
{
    NSAlert *alert = [[[NSAlert alloc] init] autorelease];
    alert.alertStyle = NSAlertStyleCritical;
    alert.messageText = NSLocalizedString( @"ROIs Import Error", nil);
    alert.informativeText = [NSString stringWithFormat: NSLocalizedString( @"%@ was not imported.\n\n%@", nil), path.lastPathComponent, error.localizedDescription ?: @""];
    [alert runModal];
}

- (void) appendROIList:(NSArray*) rois movieIndex:(int) movie sliceIndex:(int) slice
              fileName:(NSString*) fileName items:(NSMutableArray*) items rois:(NSMutableArray*) collected
{
    for( id object in rois)
    {
        if( [object isKindOfClass: [ROI class]] == NO)
            continue;

        ROI *roi = object;
        HorosROIAssociationItem *item = [[[HorosROIAssociationItem alloc] init] autorelease];
        item.sourceIndex = (int) items.count;
        item.name = roi.name ?: @"";
        item.typeCode = roi.type;
        item.fileName = fileName;
        item.image.temporalIndex = movie;
        item.image.index = slice;
        item.image.hasImageOrigin = YES;
        item.image.imageOriginX = roi.imageOrigin.x;
        item.image.imageOriginY = roi.imageOrigin.y;
        item.image.pixelSpacingX = roi.pixelSpacingX;
        item.image.pixelSpacingY = roi.pixelSpacingY;
        item.thickness = roi.thickness;
        item.opacity = roi.opacity;
        item.comments = roi.comments;
        item.isSpline = roi.isSpline;
        item.groupID = roi.groupID;

        RGBColor color = roi.rgbcolor;
        item.red = color.red / 65535.0;
        item.green = color.green / 65535.0;
        item.blue = color.blue / 65535.0;

        if( roi.type == tROI || roi.type == tOval || roi.type == t2DPoint)
        {
            item.hasRect = YES;
            item.rect = roi.rect;
        }

        NSMutableArray *points = [NSMutableArray array];
        for( MyPoint *point in roi.points)
            [points addObject: @[ @(point.x), @(point.y) ]];
        item.points = points;

        [items addObject: item];
        [collected addObject: roi];
    }
}

- (void) appendMovie:(NSArray*) slices movieIndex:(int) movie fileName:(NSString*) fileName
               items:(NSMutableArray*) items rois:(NSMutableArray*) collected
{
    for( int x = 0; x < (int) slices.count; x++)
    {
        id slice = [slices objectAtIndex: x];
        if( [slice isKindOfClass: [NSArray class]])
            [self appendROIList: slice movieIndex: movie sliceIndex: x fileName: fileName items: items rois: collected];
    }
}

- (void) appendAssociationItemsFromUnarchived:(id) object fileName:(NSString*) fileName
                                        items:(NSMutableArray*) items rois:(NSMutableArray*) collected
{
    if( [object isKindOfClass: [NSArray class]] == NO)
        return;

    NSArray *root = object;
    if( root.count == 0)
        return;

    id first = [root objectAtIndex: 0];
    if( [first isKindOfClass: [NSArray class]])
    {
        id inner = [(NSArray*) first count] ? [(NSArray*) first objectAtIndex: 0] : nil;
        if( [inner isKindOfClass: [NSArray class]])
        {
            for( int y = 0; y < (int) root.count; y++)
            {
                id movie = [root objectAtIndex: y];
                if( [movie isKindOfClass: [NSArray class]])
                    [self appendMovie: movie movieIndex: y fileName: fileName items: items rois: collected];
            }
        }
        else
            [self appendMovie: root movieIndex: 0 fileName: fileName items: items rois: collected];
    }
    else
        [self appendROIList: root movieIndex: 0 sliceIndex: 0 fileName: fileName items: items rois: collected];
}

- (BOOL) applyAssociationItems:(NSArray<HorosROIAssociationItem*>*) items rois:(NSArray*) rois error:(NSError**) error
{
    if( items.count == 0)
        return ROIImportSetError( error, HorosROIAssociationStatusInsufficient, @"The archive decoded but contains no ROIs.");

    ROIInterchangeSeries *targetSeries = [self interchangeSeriesIncludingROIs: NO];
    NSArray<HorosROIAssociationImage*> *targets = [HorosROIAssociation targetsFrom: targetSeries];
    HorosROIAssociationPlan *plan = [HorosROIAssociation planWithSources: items targets: targets];
    if( plan.canApply == NO)
    {
        if( error)
            *error = plan.error;
        return NO;
    }

    [self addToUndoQueue: @"roi"];
    [self roiSelectDeselectAll: nil];

    NSUInteger added = 0;
    for( NSUInteger i = 0; i < plan.bindings.count; i++)
    {
        HorosROIAssociationBinding *binding = [plan.bindings objectAtIndex: i];
        if( binding.targetIndex < 0 || binding.targetIndex >= (NSInteger) targets.count)
            continue;

        HorosROIAssociationImage *targetImage = [targets objectAtIndex: binding.targetIndex];
        long y = targetImage.temporalIndex, x = targetImage.index;
        if( y < 0 || y >= self.maxMovieIndex || x < 0 || x >= [[self pixList: y] count])
            continue;

        DCMPix *pix = [[self pixList: y] objectAtIndex: x];
        NSMutableArray *slice = [[self roiList: y] objectAtIndex: x];
        ROI *roi = [rois objectAtIndex: i];

        if( binding.reoriented)
        {
            NSMutableArray *points = [NSMutableArray array];
            for( NSArray *xy in binding.points)
            {
                if( xy.count < 2)
                    continue;
                [points addObject: [MyPoint point: NSMakePoint( [xy[0] doubleValue], [xy[1] doubleValue] )]];
            }
            [roi setPoints: points];
            roi.imageOrigin = [DCMPix originCorrectedAccordingToOrientation: pix];
            roi.pixelSpacingX = pix.pixelSpacingX;
            roi.pixelSpacingY = pix.pixelSpacingY;
        }
        else
        {
            [roi setOriginAndSpacing: pix.pixelSpacingX :pix.pixelSpacingY :[DCMPix originCorrectedAccordingToOrientation: pix]];
        }

        roi.pix = pix;
        [slice addObject: roi];
        [[self imageView] roiSet: roi];
        [[NSNotificationCenter defaultCenter] postNotificationName: OsirixAddROINotification object: self
                                                          userInfo: @{@"ROI": roi, @"sliceNumber": @(x)}];
        added++;
    }

    [[self imageView] setIndex: [[self imageView] curImage]];
    [[self imageView] setNeedsDisplay: YES];
    NSLog( @"ROI association: imported %lu ROI(s)", (unsigned long) added);
    return YES;
}

- (BOOL) importROIInterchangeFromPath:(NSString*) path error:(NSError**) error
{
    NSData *data = [NSData dataWithContentsOfFile: path options: 0 error: error];
    if( data == nil)
        return NO;

    HorosROIArchiveInspection *inspection = [HorosROIArchiveFormat inspectJSON: data];
    if( inspection.canImport == NO)
        return ROIImportSetError( error, inspection.payload, inspection.reason);

    ROIInterchangeSeries *document = [ROIInterchange decode: data error: error];
    if( document == nil)
        return NO;

    ROIInterchangeSeries *target = [self interchangeSeriesIncludingROIs: NO];
    HorosROIAssociationPlan *plan = [HorosROIAssociation planWithDocument: document against: target];
    if( plan.canApply == NO)
    {
        if( error)
            *error = plan.error;
        return NO;
    }

    [self addToUndoQueue: @"roi"];
    [self roiSelectDeselectAll: nil];

    NSUInteger added = 0, bindingIndex = 0;
    NSArray<HorosROIAssociationImage*> *targets = [HorosROIAssociation targetsFrom: target];

    for( ROIInterchangeImage *docImage in document.images)
    {
        for( ROIInterchangeROI *record in docImage.rois)
        {
            if( bindingIndex >= plan.bindings.count)
                break;

            HorosROIAssociationBinding *binding = [plan.bindings objectAtIndex: bindingIndex++];
            if( binding.targetIndex < 0 || binding.targetIndex >= (NSInteger) targets.count)
                continue;

            HorosROIAssociationImage *targetImage = [targets objectAtIndex: binding.targetIndex];
            long y = targetImage.temporalIndex, x = targetImage.index;
            if( y < 0 || y >= self.maxMovieIndex || x < 0 || x >= [[self pixList: y] count])
                continue;

            if( binding.reoriented)
            {
                NSMutableArray *points = [NSMutableArray array];
                for( NSArray *xy in binding.points)
                {
                    if( xy.count < 2)
                        continue;
                    [points addObject: [NSValue valueWithPoint: NSMakePoint( [xy[0] doubleValue], [xy[1] doubleValue] )]];
                }
                record.points = points;
            }

            DCMPix *pix = [[self pixList: y] objectAtIndex: x];
            ROI *roi = [self roiFromInterchangeROI: record pix: pix];
            if( roi == nil)
                continue;

            [[[self roiList: y] objectAtIndex: x] addObject: roi];
            [[self imageView] roiSet: roi];
            [[NSNotificationCenter defaultCenter] postNotificationName: OsirixAddROINotification object: self
                                                              userInfo: @{@"ROI": roi, @"sliceNumber": @(x)}];
            added++;
        }
    }

    [[self imageView] setIndex: [[self imageView] curImage]];
    [[self imageView] setNeedsDisplay: YES];
    NSLog( @"ROI interchange: imported %lu ROI(s) from %@", (unsigned long) added, path.lastPathComponent);
    return YES;
}

- (BOOL) importROIArchiveFromPath:(NSString*) path error:(NSError**) error
{
    NSData *data = [NSData dataWithContentsOfFile: path options: 0 error: error];
    if( data == nil)
        return NO;

    HorosROIArchiveKind kind = [HorosROIArchiveFormat classify: data];
    if( kind == HorosROIArchiveKindJsonInterchange)
        return [self importROIInterchangeFromPath: path error: error];
    if( kind == HorosROIArchiveKindEmpty)
        return ROIImportSetError( error, HorosROIArchiveKindEmpty, @"The archive decoded but contains no ROIs.");
    if( kind == HorosROIArchiveKindKeyedArchive)
        return ROIImportSetError( error, HorosROIArchiveKindKeyedArchive, @"NSKeyedArchiver is not a supported rois_series variant. Horos reads NSArchiver typedstreams and the JSON interchange format.");
    if( kind == HorosROIArchiveKindUnknown)
        return ROIImportSetError( error, HorosROIArchiveKindUnknown, @"This file is not a JSON ROI document or an NSArchiver .roi / .rois_series archive.");

    id object = nil;
    @try
    {
        object = [NSUnarchiver unarchiveObjectWithFile: path];
    }
    @catch( NSException *exception)
    {
        return ROIImportSetError( error, HorosROIArchivePayloadKindIncompatible,
                                 [NSString stringWithFormat: @"The archive could not be parsed (%@). Nothing was imported.", exception.reason ?: exception.name]);
    }

    HorosROIArchiveInspection *inspection = [HorosROIArchiveFormat inspectUnarchived: object];
    if( inspection.canImport == NO)
        return ROIImportSetError( error, inspection.payload, inspection.reason);

    NSMutableArray *items = [NSMutableArray array];
    NSMutableArray *rois = [NSMutableArray array];
    [self appendAssociationItemsFromUnarchived: object fileName: path.lastPathComponent items: items rois: rois];
    return [self applyAssociationItems: items rois: rois error: error];
}

- (BOOL) importROIFiles:(NSArray<NSString*>*) paths error:(NSError**) error
{
    NSMutableArray *items = [NSMutableArray array];
    NSMutableArray *rois = [NSMutableArray array];

    for( NSString *path in paths)
    {
        NSData *data = [NSData dataWithContentsOfFile: path options: 0 error: error];
        if( data == nil)
            return NO;

        HorosROIArchiveKind kind = [HorosROIArchiveFormat classify: data];
        if( kind != HorosROIArchiveKindTypedstream)
            return ROIImportSetError( error, kind, [NSString stringWithFormat: @"%@ is not an NSArchiver .roi file.", path.lastPathComponent]);

        id object = nil;
        @try
        {
            object = [NSUnarchiver unarchiveObjectWithFile: path];
        }
        @catch( NSException *exception)
        {
            return ROIImportSetError( error, HorosROIArchivePayloadKindIncompatible,
                                     [NSString stringWithFormat: @"%@ could not be parsed (%@). Nothing was imported.", path.lastPathComponent, exception.reason ?: exception.name]);
        }

        HorosROIArchiveInspection *inspection = [HorosROIArchiveFormat inspectUnarchived: object];
        if( inspection.canImport == NO)
            return ROIImportSetError( error, inspection.payload,
                                     [NSString stringWithFormat: @"%@: %@", path.lastPathComponent, inspection.reason]);

        [self appendAssociationItemsFromUnarchived: object fileName: path.lastPathComponent items: items rois: rois];
    }

    return [self applyAssociationItems: items rois: rois error: error];
}

- (void) roiLoadFromInterchangeFile:(NSString*) path
{
    NSError *error = nil;

    if( [self importROIInterchangeFromPath: path error: &error] == NO)
        [self presentROIImportErrorForPath: path error: error];
}

@end
