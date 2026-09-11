#import <Foundation/Foundation.h>

// Names are already sanitized by the caller. Assign once per series object in
// this export, reserving full paths so missing/repeated metadata cannot merge
// distinct series. Selection retains the series objects for the whole operation.
static NSString *HorosRasterSeriesFolder(NSString *name, id number, NSString *parent,
                                        id series, NSMutableDictionary *assignments,
                                        NSMutableSet *reservedPaths)
{
    NSArray *key = @[parent, [NSValue valueWithNonretainedObject:series]];
    NSString *assigned = assignments[key];
    if (assigned) return assigned;
    NSString *base = name.length ? name : @"series";
    if ([number isKindOfClass:NSNumber.class])
        base = [base stringByAppendingFormat:@"_%@", [number stringValue]];
    NSString *candidate = base;
    NSUInteger suffix = 2;
    while ([reservedPaths containsObject:[[parent stringByAppendingPathComponent:candidate] precomposedStringWithCanonicalMapping].lowercaseString])
        candidate = [base stringByAppendingFormat:@"_%lu", (unsigned long)suffix++];
    [reservedPaths addObject:[[parent stringByAppendingPathComponent:candidate] precomposedStringWithCanonicalMapping].lowercaseString];
    assignments[key] = candidate;
    return candidate;
}
