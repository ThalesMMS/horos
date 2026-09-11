/*
 ViewerController+ROIEnhancement.m
 Horos
*/

#import "ViewerController+ROIEnhancement.h"
#import "Horos-Swift.h"
#import "DCMPix.h"
#import "DCMView.h"
#import "ROI.h"

@interface ViewerController (ROIEnhancement) <ROIEnhancementViewerProcessing>
@end

@implementation ViewerController (ROIEnhancement)

- (DCMPix *)roiEnhancementPixAtMovie:(long)movie slice:(NSInteger)slice
{
    NSArray *list = self.maxMovieIndex > 1 ? [self pixList:movie] : [self pixList];
    if (slice < 0 || slice >= (NSInteger)list.count)
        return nil;
    return list[slice];
}

- (NSDictionary *)roiEnhancementProcessCurrentSeries
{
    if (self.maxMovieIndex < 2)
        return @{ @"code": @(1), @"reason": @"ROI Enhancement needs a dynamic (4D) series with at least two phases, or prepared phantom frames.", @"curves": @[] };

    NSInteger slice = [[self imageView] curImage];
    NSArray *roiSlices = [self roiList];
    if (slice < 0 || slice >= (NSInteger)roiSlices.count)
        return @{ @"code": @(3), @"reason": @"ROI Enhancement needs an open dynamic 2D viewer series with a ROI, or prepared phantom frames.", @"curves": @[] };

    NSMutableArray *usable = [NSMutableArray array];
    for (ROI *roi in roiSlices[slice])
    {
        if ([roi roiArea] > 0)
            [usable addObject:roi];
    }
    if (usable.count == 0)
        return @{ @"code": @(2), @"reason": @"ROI Enhancement needs at least one ROI with area.", @"curves": @[] };

    DCMPix *first = [self roiEnhancementPixAtMovie:0 slice:slice];
    NSTimeInterval origin = first.acquisitionTime ? [first.acquisitionTime timeIntervalSince1970] : 0;
    NSMutableArray *curves = [NSMutableArray arrayWithCapacity:usable.count];

    for (ROI *roi in usable)
    {
        NSMutableArray *times = [NSMutableArray arrayWithCapacity:(NSUInteger)self.maxMovieIndex];
        NSMutableArray *mins = [NSMutableArray arrayWithCapacity:(NSUInteger)self.maxMovieIndex];
        NSMutableArray *means = [NSMutableArray arrayWithCapacity:(NSUInteger)self.maxMovieIndex];
        NSMutableArray *maxs = [NSMutableArray arrayWithCapacity:(NSUInteger)self.maxMovieIndex];
        NSMutableArray *counts = [NSMutableArray arrayWithCapacity:(NSUInteger)self.maxMovieIndex];

        for (long movie = 0; movie < self.maxMovieIndex; movie++)
        {
            DCMPix *pix = [self roiEnhancementPixAtMovie:movie slice:slice];
            if (pix == nil)
                return @{ @"code": @(4), @"reason": @"ROI Enhancement frames must share the same width and height.", @"curves": @[] };

            float min = 0, mean = 0, max = 0;
            [pix computeROI:roi :&mean :NULL :NULL :&min :&max];
            NSTimeInterval time = pix.acquisitionTime ? [pix.acquisitionTime timeIntervalSince1970] - origin : (NSTimeInterval)movie;
            [times addObject:@(time)];
            [mins addObject:@(min)];
            [means addObject:@(mean)];
            [maxs addObject:@(max)];
            [counts addObject:@([roi roiArea] > 0 ? 1 : 0)];
        }

        [curves addObject:[ROIEnhancementEngine curveWithName:roi.name ?: @"ROI"
                                                        times:times
                                                         mins:mins
                                                        means:means
                                                         maxs:maxs
                                                       counts:counts]];
    }

    return [ROIEnhancementEngine resultWithCurves:curves];
}

@end
