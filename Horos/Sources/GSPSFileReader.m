#import "GSPSFileReader.h"
#import "Horos-Swift.h"
#import "DCM.h"
#import "DCMSequenceAttribute.h"

static NSDictionary *HorosGSPSDictionaryFromObject(DCMObject *object);

static id HorosGSPSValueFromAttribute(DCMAttribute *attribute)
{
    if ([attribute isKindOfClass:[DCMSequenceAttribute class]])
    {
        NSMutableArray *items = [NSMutableArray array];
        for (DCMObject *item in [(DCMSequenceAttribute *)attribute sequence])
        {
            if ([item isKindOfClass:[DCMObject class]])
                [items addObject:HorosGSPSDictionaryFromObject(item)];
        }
        return items;
    }
    return attribute.values ?: @[];
}

static NSDictionary *HorosGSPSDictionaryFromObject(DCMObject *object)
{
    NSMutableDictionary *dictionary = [NSMutableDictionary dictionary];
    for (id key in object.attributes)
    {
        DCMAttribute *attribute = [object.attributes objectForKey:key];
        NSString *name = attribute.attrTag.name;
        if (name.length == 0 || [name isEqualToString:@"Unknown"])
            continue;
        id value = HorosGSPSValueFromAttribute(attribute);
        if (value)
            [dictionary setObject:value forKey:name];
    }
    return dictionary;
}

@implementation HorosGSPSDocument (FileReading)

+ (NSDictionary *)dictionaryWithContentsOfFile:(NSString *)path
{
    if (path.length == 0)
        return nil;
    DCMObject *object = [DCMObject objectWithContentsOfFile:path decodingPixelData:NO];
    if (object == nil)
        return nil;
    return HorosGSPSDictionaryFromObject(object);
}

+ (instancetype)documentWithContentsOfFile:(NSString *)path
{
    NSDictionary *dictionary = [self dictionaryWithContentsOfFile:path];
    if (dictionary.count == 0)
        return nil;
    return [HorosGSPSDocument documentWithDictionary:dictionary];
}

@end
