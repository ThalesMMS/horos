#import <Foundation/Foundation.h>

// Unknown/missing Pages keeps the database-local template location available.
// Only a positively identified pre-5 release selects the legacy iWork folder.
static inline BOOL HorosPagesUsesModernTemplates(NSDictionary *info)
{
    id version = [info objectForKey:@"CFBundleShortVersionString"];
    if (![version isKindOfClass:NSString.class]) return YES;
    NSString *major = [[version componentsSeparatedByString:@"."] firstObject];
    if (!major.length || [major rangeOfCharacterFromSet:NSCharacterSet.decimalDigitCharacterSet.invertedSet].location != NSNotFound)
        return YES;
    NSInteger number = major.integerValue;
    return number < 1 || number >= 5;
}
