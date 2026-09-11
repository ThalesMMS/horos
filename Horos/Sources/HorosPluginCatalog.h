#import <Foundation/Foundation.h>

// Accept numeric dotted releases and conventional alpha/beta/rc suffixes.
static inline NSArray *HorosPluginVersionParts(id version)
{
    if (![version isKindOfClass:NSString.class] || ![version length]) return nil;
    NSRegularExpression *pattern = [NSRegularExpression regularExpressionWithPattern:
        @"^([0-9]+(?:\\.[0-9]+)*)(?:-([0-9A-Za-z][0-9A-Za-z.-]*)|([A-Za-z][0-9A-Za-z.-]*))?(?:\\+[0-9A-Za-z.-]+)?$"
        options:0 error:NULL];
    NSTextCheckingResult *match = [pattern firstMatchInString:version options:0 range:NSMakeRange(0, [version length])];
    if (!match || match.range.length != [version length]) return nil;
    NSString *release = [version substringWithRange:[match rangeAtIndex:1]];
    NSRange suffixRange = [match rangeAtIndex:2];
    if (suffixRange.location == NSNotFound) suffixRange = [match rangeAtIndex:3];
    NSString *suffix = suffixRange.location == NSNotFound ? @"" : [version substringWithRange:suffixRange];
    return @[ [release componentsSeparatedByString:@"."], suffix ];
}

static inline BOOL HorosPluginVersionIsValid(id version)
{
    return HorosPluginVersionParts(version) != nil;
}

static inline NSComparisonResult HorosComparePluginVersions(id left, id right)
{
    NSArray *a = HorosPluginVersionParts(left), *b = HorosPluginVersionParts(right);
    if (!a || !b) return NSOrderedSame; // Invalid metadata must not advertise an update.
    NSArray *ap = a[0], *bp = b[0];
    for (NSUInteger index = 0; index < MAX(ap.count, bp.count); index++) {
        NSString *x = index < ap.count ? ap[index] : @"0";
        NSString *y = index < bp.count ? bp[index] : @"0";
        while (x.length > 1 && [x hasPrefix:@"0"]) x = [x substringFromIndex:1];
        while (y.length > 1 && [y hasPrefix:@"0"]) y = [y substringFromIndex:1];
        if (x.length != y.length) return x.length < y.length ? NSOrderedAscending : NSOrderedDescending;
        NSComparisonResult result = [x compare:y options:NSLiteralSearch];
        if (result != NSOrderedSame) return result;
    }
    NSString *as = a[1], *bs = b[1];
    if (!as.length && bs.length) return NSOrderedDescending;
    if (as.length && !bs.length) return NSOrderedAscending;
    return [as compare:bs options:NSNumericSearch | NSCaseInsensitiveSearch];
}

static inline NSURL *HorosPluginHTTPURL(id value)
{
    if (![value isKindOfClass:NSString.class] || ![value length]) return nil;
    NSURL *url = [NSURL URLWithString:value];
    NSString *scheme = url.scheme.lowercaseString;
    return (([scheme isEqualToString:@"https"] || [scheme isEqualToString:@"http"]) && url.host.length) ? url : nil;
}

static inline NSString *HorosPluginDownloadName(NSDictionary *plugin)
{
    NSURL *url = HorosPluginHTTPURL([plugin objectForKey:@"download_url"]);
    NSString *name = url.lastPathComponent.stringByDeletingPathExtension.stringByDeletingPathExtension;
    return name.length && [name rangeOfCharacterFromSet:[NSCharacterSet characterSetWithCharactersInString:@"/\\"]].location == NSNotFound ? name : nil;
}

// Validate before menus, version comparison or download code consumes the plist.
static inline NSMutableArray *HorosValidatedPluginCatalog(id catalog)
{
    if (![catalog isKindOfClass:NSArray.class]) {
        if (catalog) NSLog(@"Plugin catalog rejected: expected an array.");
        return nil;
    }
    NSMutableArray *result = [NSMutableArray array];
    NSUInteger rejected = 0;
    for (id item in catalog) {
        if (![item isKindOfClass:NSDictionary.class] || !HorosPluginVersionIsValid([item objectForKey:@"version"]) ||
            !HorosPluginDownloadName(item)) { rejected++; continue; }
        NSMutableDictionary *plugin = [[item mutableCopy] autorelease];
        id name = [plugin objectForKey:@"name"];
        if (![name isKindOfClass:NSString.class] || ![name length])
            [plugin setObject:HorosPluginDownloadName(plugin) forKey:@"name"];
        if (!HorosPluginHTTPURL([plugin objectForKey:@"url"])) [plugin setObject:@"about:blank" forKey:@"url"];
        id compatible = [plugin objectForKey:@"HorosCompatiblePlugin"];
        if (![compatible isKindOfClass:NSString.class] && ![compatible isKindOfClass:NSNumber.class])
            [plugin setObject:@NO forKey:@"HorosCompatiblePlugin"];
        [result addObject:plugin];
    }
    if (rejected) NSLog(@"Plugin catalog: skipped %lu malformed entries.", (unsigned long)rejected);
    return [catalog count] && !result.count ? nil : result;
}
