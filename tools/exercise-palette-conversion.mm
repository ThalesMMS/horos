/*
 * Drives -[DCMPixelDataAttribute convertPaletteToRGB:] - the real one, pasted in
 * by the test out of the compiled source - against palettes that are extreme,
 * truncated, contradictory or absent, under AddressSanitizer.
 *
 * The stand-ins below supply only what the method asks its object for: named
 * attributes, their values, and how many of them there are. Everything the
 * method does with the numbers is its own.
 */
#import <Foundation/Foundation.h>
#include <cstdio>

@interface DCMAttribute : NSObject
@property (retain) id value;
@property (retain) NSArray *values;
@property NSUInteger valueMultiplicity;
@end

@implementation DCMAttribute
@end

@interface PaletteObject : NSObject
@property (retain) NSMutableDictionary *attributes;
- (id) attributeValueWithName: (NSString*) name;
- (NSArray*) attributeArrayWithName: (NSString*) name;
- (DCMAttribute*) attributeWithName: (NSString*) name;
@end

@implementation PaletteObject
- (id) attributeValueWithName: (NSString*) name
{
    return [[self.attributes objectForKey: name] value];
}
- (NSArray*) attributeArrayWithName: (NSString*) name
{
    return [[self.attributes objectForKey: name] values];
}
- (DCMAttribute*) attributeWithName: (NSString*) name
{
    return [self.attributes objectForKey: name];
}
@end

@interface PaletteConverter : NSObject
{
@public
    PaletteObject *_dcmObject;
    long _rows, _columns, _pixelDepth;
}
- (NSData *)convertPaletteToRGB:(NSData *)data;
@end

@implementation PaletteConverter
CONVERT_PALETTE_TO_RGB
@end

static DCMAttribute *scalar( id value)
{
    DCMAttribute *attribute = [[DCMAttribute alloc] init];
    attribute.value = value;
    attribute.valueMultiplicity = 1;
    return attribute;
}

static DCMAttribute *list( NSArray *values)
{
    DCMAttribute *attribute = [[DCMAttribute alloc] init];
    attribute.values = values;
    attribute.value = values.firstObject;
    attribute.valueMultiplicity = values.count;
    return attribute;
}

static NSArray *descriptor( int entries, int first, int bits)
{
    return @[ @(entries), @(first), @(bits)];
}

static NSData *table8( int entries, int value)
{
    NSMutableData *data = [NSMutableData dataWithLength: entries];
    unsigned char *bytes = (unsigned char*) data.mutableBytes;
    for( int i = 0; i < entries; i++)
        bytes[ i] = (unsigned char) (value < 0 ? (i & 0xff) : value);
    return data;
}

static NSData *table16( int entries, int value, BOOL wide)
{
    NSMutableData *data = [NSMutableData dataWithLength: entries * 2];
    unsigned short *words = (unsigned short*) data.mutableBytes;
    for( int i = 0; i < entries; i++)
    {
        int level = (value < 0 ? (i & 0xff) : value);
        words[ i] = (unsigned short) (wide ? level * 257 : level);
    }
    return data;
}

static NSData *rampPixels8( long rows, long columns)
{
    NSMutableData *data = [NSMutableData dataWithLength: rows * columns];
    unsigned char *bytes = (unsigned char*) data.mutableBytes;
    for( long i = 0; i < rows * columns; i++)
        bytes[ i] = (unsigned char) (i % 256);
    return data;
}

static NSData *extremePixels16( long rows, long columns)
{
    NSMutableData *data = [NSMutableData dataWithLength: rows * columns * 2];
    unsigned short *words = (unsigned short*) data.mutableBytes;
    for( long i = 0; i < rows * columns; i++)
        words[ i] = (i % 3 == 0) ? 0 : ((i % 3 == 1) ? 65535 : (unsigned short) (i % 4096));
    return data;
}

static int failures = 0;

static void run( const char *what, long rows, long columns, long depth,
                 NSDictionary *attributes, NSData *pixels, long expected)
{
    @autoreleasepool
    {
        PaletteConverter *converter = [[PaletteConverter alloc] init];
        converter->_rows = rows;
        converter->_columns = columns;
        converter->_pixelDepth = depth;
        converter->_dcmObject = [[PaletteObject alloc] init];
        converter->_dcmObject.attributes = [NSMutableDictionary dictionaryWithDictionary: attributes];

        NSData *rgb = [converter convertPaletteToRGB: pixels];
        long got = rgb ? (long) rgb.length : -1;
        const char *verdict = "ok";
        if( expected >= 0 && got != expected)
        {
            verdict = "WRONG SIZE";
            failures++;
        }
        printf("%-46s %8ld bytes  (expected %ld)  %s\n", what, got, expected, verdict);
    }
}

int main()
{
    @autoreleasepool
    {
        const long rows = 24, columns = 32;
        NSDictionary *common = @{ @"PhotometricInterpretation": scalar( @"PALETTE COLOR")};

        NSMutableDictionary *eight = [NSMutableDictionary dictionaryWithDictionary: common];
        eight[@"RedPaletteColorLookupTableDescriptor"] = list( descriptor( 256, 0, 8));
        eight[@"GreenPaletteColorLookupTableDescriptor"] = list( descriptor( 256, 0, 8));
        eight[@"BluePaletteColorLookupTableDescriptor"] = list( descriptor( 256, 0, 8));
        eight[@"RedPaletteColorLookupTableData"] = scalar( table8( 256, -1));
        eight[@"GreenPaletteColorLookupTableData"] = scalar( table8( 256, -1));
        eight[@"BluePaletteColorLookupTableData"] = scalar( table8( 256, 96));
        run( "8-bit palette, 8-bit pixels", rows, columns, 8, eight,
             rampPixels8( rows, columns), rows * columns * 3);

        // A table that stops early, while the descriptor still claims 256 entries.
        NSMutableDictionary *truncated = [NSMutableDictionary dictionaryWithDictionary: eight];
        truncated[@"RedPaletteColorLookupTableData"] = scalar( table8( 8, -1));
        truncated[@"GreenPaletteColorLookupTableData"] = scalar( table8( 3, -1));
        truncated[@"BluePaletteColorLookupTableData"] = scalar( table8( 1, 96));
        run( "truncated 8-bit tables", rows, columns, 8, truncated,
             rampPixels8( rows, columns), rows * columns * 3);

        // Blue present, green absent: the blue table used to be read from green.
        NSMutableDictionary *noGreen = [NSMutableDictionary dictionaryWithDictionary: eight];
        [noGreen removeObjectForKey: @"GreenPaletteColorLookupTableData"];
        run( "green table missing, blue present", rows, columns, 8, noGreen,
             rampPixels8( rows, columns), rows * columns * 3);

        // No table data at all, only descriptors.
        NSMutableDictionary *bare = [NSMutableDictionary dictionaryWithDictionary: common];
        bare[@"RedPaletteColorLookupTableDescriptor"] = list( descriptor( 256, 0, 8));
        bare[@"GreenPaletteColorLookupTableDescriptor"] = list( descriptor( 256, 0, 8));
        bare[@"BluePaletteColorLookupTableDescriptor"] = list( descriptor( 256, 0, 8));
        run( "descriptors with no tables", rows, columns, 8, bare,
             rampPixels8( rows, columns), -1);

        // A descriptor with fewer than three values.
        NSMutableDictionary *shortDescriptor = [NSMutableDictionary dictionaryWithDictionary: eight];
        shortDescriptor[@"RedPaletteColorLookupTableDescriptor"] = list( @[ @256]);
        run( "descriptor with one value", rows, columns, 8, shortDescriptor,
             rampPixels8( rows, columns), -1);

        // 16-bit tables and 16-bit pixels, including 0 and 65535.
        NSMutableDictionary *sixteen = [NSMutableDictionary dictionaryWithDictionary: common];
        sixteen[@"RedPaletteColorLookupTableDescriptor"] = list( descriptor( 256, 0, 16));
        sixteen[@"GreenPaletteColorLookupTableDescriptor"] = list( descriptor( 256, 0, 16));
        sixteen[@"BluePaletteColorLookupTableDescriptor"] = list( descriptor( 256, 0, 16));
        sixteen[@"RedPaletteColorLookupTableData"] = scalar( table16( 256, -1, YES));
        sixteen[@"GreenPaletteColorLookupTableData"] = scalar( table16( 256, -1, YES));
        sixteen[@"BluePaletteColorLookupTableData"] = scalar( table16( 256, 96, YES));
        run( "16-bit palette, extreme 16-bit pixels", rows, columns, 16, sixteen,
             extremePixels16( rows, columns), rows * columns * 3);

        // Entry count zero, which the standard reads as 65536.
        NSMutableDictionary *full = [NSMutableDictionary dictionaryWithDictionary: sixteen];
        full[@"RedPaletteColorLookupTableDescriptor"] = list( descriptor( 0, 0, 16));
        full[@"GreenPaletteColorLookupTableDescriptor"] = list( descriptor( 0, 0, 16));
        full[@"BluePaletteColorLookupTableDescriptor"] = list( descriptor( 0, 0, 16));
        run( "entry count 0, 65536 entries implied", rows, columns, 16, full,
             extremePixels16( rows, columns), rows * columns * 3);

        // A first mapped value well above the pixels, and one well below.
        NSMutableDictionary *offsetHigh = [NSMutableDictionary dictionaryWithDictionary: sixteen];
        offsetHigh[@"RedPaletteColorLookupTableDescriptor"] = list( descriptor( 256, 60000, 16));
        offsetHigh[@"GreenPaletteColorLookupTableDescriptor"] = list( descriptor( 256, 60000, 16));
        offsetHigh[@"BluePaletteColorLookupTableDescriptor"] = list( descriptor( 256, 60000, 16));
        run( "first mapped value 60000", rows, columns, 16, offsetHigh,
             extremePixels16( rows, columns), rows * columns * 3);

        // Pixel data shorter than the picture it is supposed to fill.
        NSMutableDictionary *shortPixels = [NSMutableDictionary dictionaryWithDictionary: eight];
        run( "pixel data half as long as the picture", rows, columns, 8, shortPixels,
             [NSData dataWithBytes: ((unsigned char*) rampPixels8( rows, columns).bytes)
                            length: rows * columns / 2], -1);

        NSMutableDictionary *shortPixels16 = [NSMutableDictionary dictionaryWithDictionary: sixteen];
        run( "16-bit pixel data half as long", rows, columns, 16, shortPixels16,
             [NSData dataWithBytes: ((unsigned char*) extremePixels16( rows, columns).bytes)
                            length: rows * columns], -1);

        // A segmented table whose stream stops in the middle of a segment.
        NSMutableDictionary *segmented = [NSMutableDictionary dictionaryWithDictionary: common];
        segmented[@"RedPaletteColorLookupTableDescriptor"] = list( descriptor( 256, 0, 16));
        segmented[@"GreenPaletteColorLookupTableDescriptor"] = list( descriptor( 256, 0, 16));
        segmented[@"BluePaletteColorLookupTableDescriptor"] = list( descriptor( 256, 0, 16));
        unsigned short stream[] = { 0, 4, 10, 20, 30, 40, 1, 8 };  // discrete, then a linear that stops
        NSMutableData *segments = [NSMutableData dataWithBytes: stream length: sizeof( stream)];
        segmented[@"SegmentedRedPaletteColorLookupTableData"] = scalar( segments);
        segmented[@"SegmentedGreenPaletteColorLookupTableData"] = scalar( segments);
        segmented[@"SegmentedBluePaletteColorLookupTableData"] = scalar( segments);
        run( "segmented table truncated mid-segment", rows, columns, 16, segmented,
             extremePixels16( rows, columns), -1);

        // A discrete segment that says it holds far more than the stream does, and
        // far more than the table can take.
        NSMutableDictionary *lying = [NSMutableDictionary dictionaryWithDictionary: segmented];
        unsigned short overrun[] = { 0, 60000, 1, 2, 3 };
        NSMutableData *overrunning = [NSMutableData dataWithBytes: overrun length: sizeof( overrun)];
        lying[@"SegmentedRedPaletteColorLookupTableData"] = scalar( overrunning);
        lying[@"SegmentedGreenPaletteColorLookupTableData"] = scalar( overrunning);
        lying[@"SegmentedBluePaletteColorLookupTableData"] = scalar( overrunning);
        run( "segment longer than the stream and the table", rows, columns, 16, lying,
             extremePixels16( rows, columns), -1);

        // A linear segment first, with no earlier entry to interpolate from.
        NSMutableDictionary *linearFirst = [NSMutableDictionary dictionaryWithDictionary: segmented];
        unsigned short linear[] = { 1, 200, 4095, 0, 8, 100, 200, 300, 400, 500, 600, 700, 800 };
        NSMutableData *linearData = [NSMutableData dataWithBytes: linear length: sizeof( linear)];
        linearFirst[@"SegmentedRedPaletteColorLookupTableData"] = scalar( linearData);
        linearFirst[@"SegmentedGreenPaletteColorLookupTableData"] = scalar( linearData);
        linearFirst[@"SegmentedBluePaletteColorLookupTableData"] = scalar( linearData);
        run( "linear segment with nothing before it", rows, columns, 16, linearFirst,
             extremePixels16( rows, columns), -1);

        printf("%d case(s) produced the wrong size\n", failures);
    }
    return failures ? 1 : 0;
}
