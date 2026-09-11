#import "HorosDerivedUID.h"
#import <CommonCrypto/CommonDigest.h>

@implementation HorosDerivedUID

+ (NSString*) studyRoot  { return @"1.2.276.0.7230010.3.1.2"; }
+ (NSString*) seriesRoot { return @"1.2.276.0.7230010.3.1.3"; }

+ (NSString*) uidForKey:(NSString*) key root:(NSString*) root
{
    NSData *data = [(key ? key : @"") dataUsingEncoding: NSUTF8StringEncoding];
    unsigned char digest[CC_SHA256_DIGEST_LENGTH];
    CC_SHA256( data.bytes, (CC_LONG) data.length, digest);
    
    // The first sixteen bytes of the digest, in base ten. Long division, so no
    // integer type has to hold a 128 bit number.
    unsigned char value[16];
    memcpy( value, digest, sizeof( value));
    NSMutableString *digits = [NSMutableString string];
    BOOL any = YES;
    while( any)
    {
        int remainder = 0;
        any = NO;
        for( size_t i = 0; i < sizeof( value); i++)
        {
            int current = remainder * 256 + value[i];
            value[i] = (unsigned char) (current / 10);
            remainder = current % 10;
            if( value[i]) any = YES;
        }
        [digits insertString: [NSString stringWithFormat: @"%d", remainder] atIndex: 0];
    }
    if( digits.length == 0)
        [digits setString: @"0"];
    
    NSInteger room = 64 - (NSInteger) root.length - 1;
    if( room < 1)
        return root;
    if( (NSInteger) digits.length > room)
        [digits setString: [digits substringFromIndex: digits.length - room]];
    // A component may not have a leading zero; replacing it rather than
    // dropping it keeps two different keys apart.
    if( [digits hasPrefix: @"0"])
        [digits replaceCharactersInRange: NSMakeRange( 0, 1) withString: @"1"];
    
    return [NSString stringWithFormat: @"%@.%@", root, digits];
}

+ (NSString*) seriesUIDForKey:(NSString*) key
{
    return [self uidForKey: key root: [self seriesRoot]];
}

+ (NSString*) studyUIDForKey:(NSString*) key
{
    return [self uidForKey: key root: [self studyRoot]];
}

+ (BOOL) isConformantUID:(NSString*) value
{
    if( value.length == 0 || value.length > 64)
        return NO;
    
    NSArray *components = [value componentsSeparatedByString: @"."];
    if( components.count == 0)
        return NO;
    
    for( NSString *component in components)
    {
        if( component.length == 0)
            return NO;
        if( [component rangeOfCharacterFromSet: [[NSCharacterSet decimalDigitCharacterSet] invertedSet]].location != NSNotFound)
            return NO;
        if( component.length > 1 && [component hasPrefix: @"0"])
            return NO;
    }
    
    return YES;
}

@end
