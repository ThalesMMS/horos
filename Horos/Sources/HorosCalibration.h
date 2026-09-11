#pragma once
#import <Foundation/Foundation.h>
#include <math.h>
#include <float.h>

// Parse the entire entry, honoring the decimal separator of the user's locale.
// Also accept period-decimal values emitted by legacy setFloatValue: controls.
static inline BOOL HorosCalibrationFloat(NSString *text, NSLocale *locale, float *value)
{
    NSString *entry = [text stringByTrimmingCharactersInSet:[NSCharacterSet whitespaceAndNewlineCharacterSet]];
    if (!entry.length) return NO;
    for (NSLocale *candidate in @[locale, [[[NSLocale alloc] initWithLocaleIdentifier:@"en_US_POSIX"] autorelease]])
    {
        NSScanner *scanner = [NSScanner scannerWithString:entry];
        scanner.locale = candidate;
        double number = 0;
        if ([scanner scanDouble:&number] && scanner.isAtEnd && isfinite(number) && fabs(number) <= FLT_MAX)
        {
            float result = (float)number;
            if (number != 0 && result == 0) return NO;
            *value = result;
            return YES;
        }
    }
    return NO;
}

