#import <Foundation/Foundation.h>

// Validate components rather than removing traversal text and changing its meaning.
static inline BOOL HorosWebPathIsSafe(NSString *path)
{
    if (!path.length || [path rangeOfString:@"\\"].location != NSNotFound)
        return NO;
    for (NSUInteger i = 0; i < path.length; ++i)
        if ([path characterAtIndex:i] < 0x20 || [path characterAtIndex:i] == 0x7f)
            return NO;
    for (NSString *component in [path componentsSeparatedByString:@"/"])
        if ([component isEqualToString:@".."] || [component isEqualToString:@"."])
            return NO;
    return YES;
}

// Decode URL escaping once, before routing and private-template checks.
static inline NSString *HorosWebRequestPath(NSString *encodedPath)
{
    NSString *path = [encodedPath stringByRemovingPercentEncoding];
    return [path hasPrefix:@"/"] && HorosWebPathIsSafe(path) ? path : nil;
}

// Callers pass decoded paths. A URL's leading slash denotes the public root.
// Resolve symlinks before comparing components, including the separator boundary.
static inline NSString *HorosWebFilePath(NSString *root, NSString *relativePath)
{
    if (!root.length || !HorosWebPathIsSafe(relativePath))
        return nil;
    while ([relativePath hasPrefix:@"/"])
        relativePath = [relativePath substringFromIndex:1];
    if (!relativePath.length)
        return nil;
    NSString *canonicalRoot = [[root stringByStandardizingPath] stringByResolvingSymlinksInPath];
    if (![canonicalRoot isAbsolutePath])
        return nil;
    NSString *candidate = [[[canonicalRoot stringByAppendingPathComponent:relativePath]
                            stringByStandardizingPath] stringByResolvingSymlinksInPath];
    NSString *prefix = [canonicalRoot hasSuffix:@"/"] ? canonicalRoot : [canonicalRoot stringByAppendingString:@"/"];
    if (![candidate hasPrefix:prefix])
        return nil;
    NSDictionary *attributes = [NSFileManager.defaultManager attributesOfItemAtPath:candidate error:NULL];
    if (![attributes.fileType isEqualToString:NSFileTypeRegular])
        return nil;
    return candidate;
}
