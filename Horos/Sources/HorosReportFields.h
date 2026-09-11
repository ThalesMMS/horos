#import <Foundation/Foundation.h>

static inline NSString *HorosEscapeReportXML(NSString *value)
{
    NSMutableString *escaped = [[value ?: @"" mutableCopy] autorelease];
    for (NSArray *pair in @[@[@"&", @"&amp;"], @[@"<", @"&lt;"], @[@">", @"&gt;"],
                             @[@"\"", @"&quot;"], @[@"'", @"&apos;"]])
        [escaped replaceOccurrencesOfString:pair[0] withString:pair[1] options:NSLiteralSearch range:NSMakeRange(0, escaped.length)];
    return escaped;
}

// Match only the original template. Values containing guillemets are patient data,
// not another template to evaluate. Reverse replacement preserves original ranges.
static inline void HorosFillReportXML(NSMutableString *xml, NSDictionary *values,
                                      NSString *(^dicomValue)(NSString *))
{
    if (!xml) return;
    NSRegularExpression *tokens = [NSRegularExpression regularExpressionWithPattern:@"(?:«|&#xAB;)(.*?)(?:»|&#xBB;)"
        options:NSRegularExpressionDotMatchesLineSeparators error:NULL];
    NSArray *matches = [tokens matchesInString:xml options:0 range:NSMakeRange(0, xml.length)];
    NSRegularExpression *tags = [NSRegularExpression regularExpressionWithPattern:@"<[^>]*>" options:0 error:NULL];
    for (NSTextCheckingResult *match in matches.reverseObjectEnumerator) {
        NSString *key = [xml substringWithRange:[match rangeAtIndex:1]];
        NSString *value = nil;
        if ([key hasPrefix:@"DICOM_FIELD:"]) {
            NSString *field = [key substringFromIndex:@"DICOM_FIELD:".length];
            field = [tags stringByReplacingMatchesInString:field options:0 range:NSMakeRange(0, field.length) withTemplate:@""];
            field = [field stringByReplacingOccurrencesOfString:@" " withString:@""];
            // Incomplete markup must not enter a retry loop or the DICOM parser.
            if ([field rangeOfCharacterFromSet:[NSCharacterSet characterSetWithCharactersInString:@"<>"]].location != NSNotFound) continue;
            value = dicomValue ? dicomValue(field) : @"";
            if (!value) value = @"";
        } else {
            value = [values objectForKey:key];
            if (!value) continue;
        }
        [xml replaceCharactersInRange:match.range withString:HorosEscapeReportXML(value)];
    }
}

// The same substitution on a plain string, for a document whose text is read
// and written back a paragraph at a time rather than edited in place.
static inline void HorosFillReportText(NSMutableString *text, NSDictionary *values,
                                       NSString *(^dicomValue)(NSString *))
{
    if (!text) return;
    NSRegularExpression *tokens = [NSRegularExpression regularExpressionWithPattern:@"«([^«»]*)»" options:0 error:NULL];
    NSArray *matches = [tokens matchesInString:text options:0 range:NSMakeRange(0, text.length)];
    for (NSTextCheckingResult *match in matches.reverseObjectEnumerator) {
        NSString *key = [text substringWithRange:[match rangeAtIndex:1]];
        NSString *value = nil;
        if ([key hasPrefix:@"DICOM_FIELD:"]) {
            value = dicomValue ? dicomValue([key substringFromIndex:@"DICOM_FIELD:".length]) : @"";
            if (!value) value = @"";
        } else {
            value = [values objectForKey:key];
            if (!value) continue;
        }
        [text replaceCharactersInRange:match.range withString:value];
    }
}

static inline void HorosFillAttributedReport(NSMutableAttributedString *report, NSDictionary *values,
                                             NSString *(^dicomValue)(NSString *))
{
    if (!report) return;
    NSRegularExpression *tokens = [NSRegularExpression regularExpressionWithPattern:@"«([^«»]*)»" options:0 error:NULL];
    NSArray *matches = [tokens matchesInString:report.string options:0 range:NSMakeRange(0, report.length)];
    for (NSTextCheckingResult *match in matches.reverseObjectEnumerator) {
        NSString *key = [report.string substringWithRange:[match rangeAtIndex:1]];
        NSString *value = nil;
        if ([key hasPrefix:@"DICOM_FIELD:"]) {
            value = dicomValue ? dicomValue([key substringFromIndex:@"DICOM_FIELD:".length]) : @"";
            if (!value) value = @"";
        } else {
            value = [values objectForKey:key];
            if (!value) continue;
        }
        [report replaceCharactersInRange:match.range withString:value];
    }
}
