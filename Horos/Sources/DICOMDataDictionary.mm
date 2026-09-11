#include "HorosDictionaryLookup.h"
#import "DICOMDataDictionary.h"

#include <dcmtk/dcmdata/dcdict.h>
#include <dcmtk/dcmdata/dcdicent.h>

#if __has_include("Horos-Swift.h")
#import "Horos-Swift.h"
#define HOROS_KEYWORD_SPELLINGS 1
#endif

static NSString *HorosOtherDicomKeywordSpelling(NSString *keyword)
{
#ifdef HOROS_KEYWORD_SPELLINGS
    return [HorosDICOMKeyword otherSpellingFor: keyword];
#else
    static NSArray *words;
    static dispatch_once_t once;
    dispatch_once(&once, ^{
        words = @[@"Patient", @"Physician"];
    });
    for (NSString *word in words)
    {
        NSString *possessive = [word stringByAppendingString: @"s"];
        NSRange range = [keyword rangeOfString: possessive];
        if (range.location != NSNotFound)
        {
            NSUInteger after = NSMaxRange(range);
            if (after < keyword.length)
            {
                unichar next = [keyword characterAtIndex: after];
                if ([[NSCharacterSet uppercaseLetterCharacterSet] characterIsMember: next])
                    return [keyword stringByReplacingCharactersInRange: range withString: word];
            }
        }
    }
    for (NSString *word in words)
    {
        NSRange range = [keyword rangeOfString: word];
        if (range.location != NSNotFound)
        {
            NSUInteger after = NSMaxRange(range);
            if (after < keyword.length)
            {
                unichar next = [keyword characterAtIndex: after];
                if ([[NSCharacterSet uppercaseLetterCharacterSet] characterIsMember: next])
                    return [keyword stringByReplacingCharactersInRange: range
                                                           withString: [word stringByAppendingString: @"s"]];
            }
        }
    }
    return nil;
#endif
}

BOOL HorosLoadVendoredDicomDictionary(NSString *path)
{
    if (path.length == 0 || ![[NSFileManager defaultManager] isReadableFileAtPath:path]) return NO;
    DcmDataDictionary& dictionary = dcmDataDict.wrlock();
    const BOOL loaded = dictionary.loadDictionary([path fileSystemRepresentation], OFTrue);
    dcmDataDict.wrunlock();
    return loaded;
}

NSString *HorosVendoredDicomDictionaryPath(void)
{
    NSString *bundled = [[NSBundle mainBundle] pathForResource: @"dicom" ofType: @"dic"];
    if (bundled.length && [[NSFileManager defaultManager] isReadableFileAtPath: bundled])
        return bundled;

    NSString *executable = [[[NSProcessInfo processInfo] arguments] firstObject];
    if (executable.length)
    {
        NSString *beside = [[executable stringByDeletingLastPathComponent] stringByAppendingPathComponent: @"dicom.dic"];
        if ([[NSFileManager defaultManager] isReadableFileAtPath: beside])
            return beside;
    }
    return nil;
}

static void HorosEnsureVendoredDicomDictionary(void)
{
    static dispatch_once_t once;
    dispatch_once(&once, ^{
        NSString *path = HorosVendoredDicomDictionaryPath();
        if (path)
            HorosLoadVendoredDicomDictionary(path);
    });
}

static BOOL HorosStandardTagFromName(DcmDataDictionary& dictionary, const char *name,
                                    unsigned *group, unsigned *element)
{
    if (name == NULL || name[0] == 0)
        return NO;
    const DcmDictEntry *entry = HorosFindStandardDicomEntry(dictionary, name);
    if (entry == NULL || (entry->getGroup() % 2) != 0)
        return NO;
    *group = entry->getGroup();
    *element = entry->getElement();
    return YES;
}

BOOL HorosResolveDicomKeyword(NSString *keyword, unsigned *group, unsigned *element)
{
    if (keyword.length == 0 || group == NULL || element == NULL)
        return NO;

    HorosEnsureVendoredDicomDictionary();

    DcmDataDictionary& dictionary = dcmDataDict.wrlock();
    BOOL found = HorosStandardTagFromName(dictionary, [keyword UTF8String], group, element);
    if (!found)
    {
        NSString *other = HorosOtherDicomKeywordSpelling(keyword);
        if (other.length)
            found = HorosStandardTagFromName(dictionary, [other UTF8String], group, element);
    }
    dcmDataDict.wrunlock();
    return found;
}
