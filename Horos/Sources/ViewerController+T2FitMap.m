/*
 ViewerController+T2FitMap.m
 Horos
*/

#import "ViewerController+T2FitMap.h"
#import "Horos-Swift.h"
#import "DCMPix.h"
#import "DCMView.h"

@interface ViewerController (T2FitMap) <T2FitMapViewerProcessing>
@end

@implementation ViewerController (T2FitMap)

static BOOL T2FitMapSameOrigin(DCMPix *a, DCMPix *b)
{
    return fabs(a.originX - b.originX) < 1e-4
        && fabs(a.originY - b.originY) < 1e-4
        && fabs(a.originZ - b.originZ) < 1e-4;
}

- (NSArray *)t2FitMapIndexGroups
{
    if (self.maxMovieIndex > 1)
    {
        NSArray *base = [self pixList:0];
        NSMutableArray *groups = [NSMutableArray arrayWithCapacity:base.count];
        for (NSUInteger slice = 0; slice < base.count; slice++)
        {
            NSMutableArray *group = [NSMutableArray arrayWithCapacity:(NSUInteger)self.maxMovieIndex];
            for (long movie = 0; movie < self.maxMovieIndex; movie++)
                [group addObject:@[ @(movie), @(slice) ]];
            [groups addObject:group];
        }
        return groups;
    }

    NSArray *pixList = [self pixList];
    NSMutableArray *groups = [NSMutableArray array];
    for (NSUInteger index = 0; index < pixList.count; index++)
    {
        DCMPix *pix = pixList[index];
        NSMutableArray *found = nil;
        for (NSMutableArray *group in groups)
        {
            NSUInteger first = [group[0][1] unsignedIntegerValue];
            if (T2FitMapSameOrigin(pixList[first], pix))
            {
                found = group;
                break;
            }
        }
        if (found)
            [found addObject:@[ @0, @(index) ]];
        else
            [groups addObject:[NSMutableArray arrayWithObject:@[ @0, @(index) ]]];
    }
    for (NSArray *group in groups)
    {
        if (group.count < 2)
        {
            NSMutableArray *all = [NSMutableArray arrayWithCapacity:pixList.count];
            for (NSUInteger index = 0; index < pixList.count; index++)
                [all addObject:@[ @0, @(index) ]];
            return @[ all ];
        }
    }
    return groups;
}

- (DCMPix *)t2FitMapPixAtMovie:(long)movie slice:(NSUInteger)slice
{
    NSArray *list = self.maxMovieIndex > 1 ? [self pixList:movie] : [self pixList];
    if (slice >= list.count)
        return nil;
    return list[slice];
}

- (id)t2FitMapFileAtMovie:(long)movie slice:(NSUInteger)slice
{
    NSArray *list = self.maxMovieIndex > 1 ? [self fileList:movie] : [self fileList];
    if (slice >= list.count)
        return nil;
    return list[slice];
}

- (NSDictionary *)t2FitMapProcessCurrentSeries
{
    NSArray *groups = [self t2FitMapIndexGroups];
    DCMPix *probe = [self t2FitMapPixAtMovie:0 slice:0];
    if (groups.count == 0 || probe == nil)
        return @{ @"code": @(3), @"reason": @"T2 Fit Map needs an open multi-echo 2D viewer series, or prepared phantom frames.", @"t2Milliseconds": @[] };

    int width = (int)probe.pwidth;
    int height = (int)probe.pheight;
    NSUInteger pixels = (NSUInteger)width * (NSUInteger)height;
    if (width <= 0 || height <= 0)
        return @{ @"code": @(3), @"reason": @"T2 Fit Map needs a non-empty multi-echo series.", @"t2Milliseconds": @[] };

    NSMutableArray *pixResult = [NSMutableArray arrayWithCapacity:groups.count];
    NSMutableArray *fileResult = [NSMutableArray arrayWithCapacity:groups.count];
    NSMutableData *volume = [NSMutableData dataWithLength:groups.count * pixels * sizeof(float)];
    float *dst = volume.mutableBytes;
    NSMutableArray *combined = [NSMutableArray array];
    NSInteger lastCode = 0;
    NSString *lastReason = @"";

    for (NSArray *group in groups)
    {
        NSMutableArray *frames = [NSMutableArray arrayWithCapacity:group.count];
        NSMutableArray *tes = [NSMutableArray arrayWithCapacity:group.count];
        for (NSArray *coordinate in group)
        {
            long movie = [coordinate[0] longValue];
            NSUInteger slice = [coordinate[1] unsignedIntegerValue];
            DCMPix *pix = [self t2FitMapPixAtMovie:movie slice:slice];
            if (pix == nil || pix.pwidth != width || pix.pheight != height || pix.fImage == NULL)
                return @{ @"code": @(4), @"reason": @"T2 Fit Map frames must share the same width and height.", @"t2Milliseconds": @[] };
            [frames addObject:[NSData dataWithBytes:pix.fImage length:pixels * sizeof(float)]];
            [tes addObject:@([pix.echotime floatValue])];
        }
        NSDictionary *fit = [T2FitMapEngine fitWithFrames:frames echoTimesMilliseconds:tes width:width height:height];
        lastCode = [fit[@"code"] integerValue];
        lastReason = fit[@"reason"] ?: @"";
        if (lastCode != 0)
            return @{ @"code": @(lastCode), @"reason": lastReason, @"t2Milliseconds": @[] };

        NSArray *map = fit[@"t2Milliseconds"];
        for (NSUInteger index = 0; index < pixels; index++)
        {
            float value = index < map.count ? [map[index] floatValue] : 0;
            dst[index] = value;
            [combined addObject:@(value)];
        }

        NSArray *first = group[0];
        DCMPix *template = [self t2FitMapPixAtMovie:[first[0] longValue] slice:[first[1] unsignedIntegerValue]];
        DCMPix *copy = [[template copy] autorelease];
        [copy setEchotime:nil];
        [copy setfImage:dst];
        [pixResult addObject:copy];
        id file = [self t2FitMapFileAtMovie:[first[0] longValue] slice:[first[1] unsignedIntegerValue]];
        if (file)
            [fileResult addObject:file];
        dst += pixels;
    }

    if (fileResult.count != pixResult.count)
        return @{ @"code": @(3), @"reason": @"T2 Fit Map needs the original files of the open series to present the map.", @"t2Milliseconds": combined };

    ViewerController *created = [self newWindow:pixResult :fileResult :volume];
    [created needsDisplayUpdate];
    [[created imageView] setWLWW:0 :0];
    return @{ @"code": @(0), @"reason": @"", @"t2Milliseconds": combined };
}

@end
