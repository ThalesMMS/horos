#import "BrowserController+GSPS.h"
#import "ViewerController+GSPS.h"
#import "GSPSFileReader.h"
#import "Horos-Swift.h"
#import "DicomSeries.h"
#import "DicomStudy.h"
#import "DicomImage.h"
#import "DCMAbstractSyntaxUID.h"

@implementation BrowserController (GSPS)

- (void)horos_presentGSPSFlags:(HorosGSPSDocument *)document missing:(NSArray<HorosGSPSImageReference *> *)missing
{
    NSMutableArray *lines = [NSMutableArray array];
    for (HorosGSPSImageReference *reference in missing)
        [lines addObject:[NSString stringWithFormat:NSLocalizedString(@"Missing referenced SOP Instance UID %@", nil), reference.sopInstanceUID]];
    for (NSString *flag in document.unsupportedFeatures)
        [lines addObject:flag];
    if (lines.count == 0)
        return;
    for (NSString *line in lines)
        NSLog(@"GSPS: %@", line);
    NSAlert *alert = [[[NSAlert alloc] init] autorelease];
    alert.alertStyle = NSAlertStyleInformational;
    alert.messageText = NSLocalizedString(@"Grayscale Presentation State", nil);
    alert.informativeText = [lines componentsJoinedByString:@"\n"];
    [alert runModal];
}

- (BOOL)horos_tryOpenGSPSSeries:(DicomSeries *)series
                         viewer:(ViewerController *)viewer
                  keyImagesOnly:(BOOL)keyImages
                  openedViewer:(ViewerController **)outViewer
{
    if (outViewer)
        *outViewer = nil;
    if ([series isKindOfClass:[DicomSeries class]] == NO)
        return NO;

    NSString *sopClass = series.seriesSOPClassUID;
    if ([HorosGSPSDocument isSoftcopyPresentationStateSOPClass:sopClass] == NO
        && [DCMAbstractSyntaxUID isPresentationState:sopClass] == NO)
        return NO;

    DicomImage *gspsImage = series.sortedImages.firstObject ?: [series.images anyObject];
    NSString *path = gspsImage.completePath;
    HorosGSPSDocument *document = [HorosGSPSDocument documentWithContentsOfFile:path];
    if (document == nil)
    {
        NSLog(@"GSPS: series %@ looks like a presentation state but the file could not be read", series.name);
        NSAlert *alert = [[[NSAlert alloc] init] autorelease];
        alert.alertStyle = NSAlertStyleInformational;
        alert.messageText = NSLocalizedString(@"Grayscale Presentation State", nil);
        alert.informativeText = NSLocalizedString(@"That series is a presentation state, but the file could not be read. The original images were not opened or changed.", nil);
        [alert runModal];
        return YES;
    }

    NSMutableArray *found = [NSMutableArray array];
    for (DicomImage *image in series.study.images)
    {
        if ([HorosGSPSDocument isSoftcopyPresentationStateSOPClass:image.series.seriesSOPClassUID]
            || [DCMAbstractSyntaxUID isPresentationState:image.series.seriesSOPClassUID])
            continue;

        BOOL matches = [document referencesSOPInstanceUID:image.sopInstanceUID frame:MAX(1, image.frameID.intValue)];
        if (matches == NO && image.numberOfFrames.intValue > 1)
        {
            for (int frame = 1; frame <= image.numberOfFrames.intValue; frame++)
            {
                if ([document referencesSOPInstanceUID:image.sopInstanceUID frame:frame])
                {
                    matches = YES;
                    break;
                }
            }
        }
        if (matches)
            [found addObject:image];
    }

    [found sortUsingDescriptors:@[
        [NSSortDescriptor sortDescriptorWithKey:@"instanceNumber" ascending:YES],
        [NSSortDescriptor sortDescriptorWithKey:@"frameID" ascending:YES],
    ]];

    NSMutableArray *missing = [NSMutableArray array];
    for (HorosGSPSImageReference *reference in document.referencedImages)
    {
        BOOL present = NO;
        for (DicomImage *image in found)
        {
            if ([document referencesSOPInstanceUID:image.sopInstanceUID frame:MAX(1, image.frameID.intValue)]
                || (image.numberOfFrames.intValue > 1 && [image.sopInstanceUID isEqualToString:reference.sopInstanceUID]))
            {
                present = YES;
                break;
            }
        }
        if (present == NO)
            [missing addObject:reference];
    }

    if (found.count == 0)
    {
        [self horos_presentGSPSFlags:document missing:missing.count ? missing : document.referencedImages];
        return YES;
    }

    ViewerController *opened = [self openViewerFromImages:@[ found ]
                                                    movie:NO
                                                   viewer:viewer
                                            keyImagesOnly:keyImages
                                           tryToFlipData:YES];
    if (opened)
        [opened applyGrayscaleSoftcopyPresentationStateFromPath:path];
    else
        [self horos_presentGSPSFlags:document missing:missing];

    if (outViewer)
        *outViewer = opened;
    return YES;
}

@end
