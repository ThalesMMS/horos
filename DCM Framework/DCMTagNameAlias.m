#import "DCMTagNameAlias.h"

static BOOL DCMTagNameFollowedByCapital(NSString *name, NSRange range)
{
    NSUInteger after = range.location + range.length;
    if (after >= name.length) return NO;
    unichar character = [name characterAtIndex:after];
    return character >= 'A' && character <= 'Z';
}

static BOOL DCMTagNameIs2011Suffix(NSString *name, NSUInteger after)
{
    NSString *suffix = [name substringFromIndex:after];
    return [suffix isEqualToString:@"Name"]
        || [suffix isEqualToString:@"BirthDate"]
        || [suffix isEqualToString:@"Sex"]
        || [suffix isEqualToString:@"BirthName"]
        || [suffix isEqualToString:@"Address"];
}

NSString *DCMTagNameOtherSpelling(NSString *name)
{
    if (name.length == 0) return nil;

    static NSString *const words[] = { @"Patient", @"Physician" };
    const NSUInteger wordCount = sizeof(words) / sizeof(words[0]);

    for (NSUInteger index = 0; index < wordCount; index++) {
        NSString *possessive = [words[index] stringByAppendingString:@"s"];
        NSRange range = [name rangeOfString:possessive];
        if (range.location != NSNotFound
            && DCMTagNameFollowedByCapital(name, range)
            && DCMTagNameIs2011Suffix(name, range.location + range.length)) {
            return [name stringByReplacingCharactersInRange:range withString:words[index]];
        }
    }

    for (NSUInteger index = 0; index < wordCount; index++) {
        NSRange range = [name rangeOfString:words[index]];
        if (range.location != NSNotFound
            && DCMTagNameFollowedByCapital(name, range)
            && DCMTagNameIs2011Suffix(name, range.location + range.length)) {
            return [name stringByReplacingCharactersInRange:range
                                                withString:[words[index] stringByAppendingString:@"s"]];
        }
    }
    return nil;
}
