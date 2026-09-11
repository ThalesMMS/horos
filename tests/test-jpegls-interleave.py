#!/usr/bin/env python3
"""The three JPEG-LS interleave modes have to decode to the same samples.

Encodes one known RGB picture three times - interleave none, line and sample -
with the vendored CharLS, then runs the production conversion on each and
compares the bytes. Needs the built CharLS, which this repository does not carry.

Usage: python test-jpegls-interleave.py CHARLS_LIB
       CHARLS_LIB is the built libCharLS.a, or a directory holding it
"""
from pathlib import Path
import subprocess
import sys
import tempfile

if len(sys.argv) < 2:
    print('skipped: needs the built CharLS: CHARLS_LIB', file=sys.stderr)
    raise SystemExit(2)

root = Path(__file__).resolve().parents[1]
given = Path(sys.argv[1]).resolve()
if given.is_dir():
    libraries = sorted(given.rglob('libCharLS*.a'))
    if not libraries:
        raise SystemExit(f'no libCharLS*.a under {given}')
    library = libraries[0]
else:
    library = given

source = (root / 'DCM Framework/DCMPixelDataAttribute.mm').read_bytes().decode('latin1')
start = source.index('// Rewrites planes into samples')
conversion = source[start:source.index('\n}\n', source.index('- (NSData *)convertJPEGLSToHost:')) + 2]

program = r'''
#import <Foundation/Foundation.h>
#include <cstring>
#include <vector>
#include "charls.h"

@interface Decoder : NSObject
- (NSData *)convertJPEGLSToHost:(NSData *)jpegLsData;
@end
@implementation Decoder
CONVERSION
@end

static int failures = 0;
#define check(...) do{ if(!(__VA_ARGS__)){ NSLog(@"FAIL: %s", #__VA_ARGS__); failures++; } }while(0)

static const int kWidth = 37;   // odd, so a stride mistake shows
static const int kHeight = 23;

// One known picture: each component a different function of the position, so a
// plane written where a sample belongs is visible as a wrong colour rather than
// as a shift.
static std::vector<unsigned char> samples(int components, int bytesPerSample)
{
    std::vector<unsigned char> data((size_t) kWidth * kHeight * components * bytesPerSample);
    size_t at = 0;
    for (int y = 0; y < kHeight; y++)
        for (int x = 0; x < kWidth; x++)
            for (int c = 0; c < components; c++)
            {
                int value = (x * 3 + y * 5 + c * 61) % (bytesPerSample == 1 ? 251 : 4093);
                for (int b = 0; b < bytesPerSample; b++)
                    data[at++] = (unsigned char) ((value >> (8 * b)) & 0xff);
            }
    return data;
}

// The same picture as planes, which is what an interleave-none stream encodes.
static std::vector<unsigned char> planes(const std::vector<unsigned char> &interleaved,
                                         int components, int bytesPerSample)
{
    std::vector<unsigned char> data(interleaved.size());
    size_t pixels = (size_t) kWidth * kHeight;
    for (int c = 0; c < components; c++)
        for (size_t p = 0; p < pixels; p++)
            memcpy(&data[((size_t) c * pixels + p) * bytesPerSample],
                   &interleaved[(p * components + c) * bytesPerSample], bytesPerSample);
    return data;
}

static NSData *encode(const std::vector<unsigned char> &raw, int components,
                      int bytesPerSample, charls::InterleaveMode mode)
{
    JlsParameters parameters = {};
    parameters.width = kWidth;
    parameters.height = kHeight;
    parameters.components = components;
    parameters.bitsPerSample = bytesPerSample == 1 ? 8 : 12;
    parameters.interleaveMode = mode;

    std::vector<unsigned char> compressed(raw.size() * 2 + 8192);
    size_t written = 0;
    charls::ApiResult result = JpegLsEncode(&compressed[0], compressed.size(), &written,
                                            &raw[0], raw.size(), &parameters, NULL);
    if (result != charls::ApiResult::OK)
    {
        NSLog(@"FAIL: encoding %d components, interleave %d: %d",
              components, (int) mode, (int) result);
        failures++;
        return nil;
    }
    return [NSData dataWithBytes:&compressed[0] length:written];
}

static void exercise(int components, int bytesPerSample)
{
    std::vector<unsigned char> interleaved = samples(components, bytesPerSample);
    std::vector<unsigned char> planar = planes(interleaved, components, bytesPerSample);
    NSData *expected = [NSData dataWithBytes:&interleaved[0] length:interleaved.size()];
    Decoder *decoder = [Decoder new];

    charls::InterleaveMode modes[] = { charls::InterleaveMode::None,
                                       charls::InterleaveMode::Line,
                                       charls::InterleaveMode::Sample };
    for (int m = 0; m < (components == 1 ? 1 : 3); m++)
    {
        charls::InterleaveMode mode = modes[m];
        const std::vector<unsigned char> &raw =
            (mode == charls::InterleaveMode::None) ? planar : interleaved;
        NSData *compressed = encode(raw, components, bytesPerSample, mode);
        if (!compressed) continue;

        NSData *decoded = [decoder convertJPEGLSToHost: compressed];
        if (decoded == nil)
        {
            NSLog(@"FAIL: %d components, %d bit, interleave %d decoded to nothing",
                  components, bytesPerSample * 8, (int) mode);
            failures++;
            continue;
        }
        if ([decoded length] != expected.length)
        {
            NSLog(@"FAIL: %d components, %d bit, interleave %d gave %lu bytes, %lu expected",
                  components, bytesPerSample * 8, (int) mode,
                  (unsigned long) [decoded length], (unsigned long) expected.length);
            failures++;
            continue;
        }
        if (![decoded isEqualToData: expected])
        {
            NSLog(@"FAIL: %d components, %d bit, interleave %d gave different samples",
                  components, bytesPerSample * 8, (int) mode);
            failures++;
        }
    }
}

int main(void) { @autoreleasepool {
    exercise(3, 1);   // RGB, 8 bit
    exercise(3, 2);   // RGB, 12 bit in 16
    exercise(1, 1);   // grayscale, 8 bit: interleave has no meaning
    exercise(1, 2);   // grayscale, 16 bit
    NSLog(@"%@", failures ? @"FAILURES" : @"same samples from every interleave mode");
    return failures ? 1 : 0;
}}
'''.replace('CONVERSION', conversion)

# The buffer has to grow for interleave none, and the planes have to be joined.
assert 'uncompressedLength *= (size_t) components' in source, (
    'the buffer is still one plane for an interleave-none stream')
assert 'HorosInterleaveJPEGLSPlanes' in source, 'the planes are not joined'
# And the caller has to stop asking the header how the samples are laid out.
planar_branch = source[source.index(
    'int numberofPlanes = [[_dcmObject attributeValueWithName:@"PlanarConfiguration"] intValue]'):]
assert 'JPEGLSLosslessTransferSyntax' in planar_branch[:1200], (
    'a JPEG-LS frame is still interleaved a second time when the header says planar')

headers = root / 'CharLS/src'
with tempfile.TemporaryDirectory(prefix='horos-jpegls-interleave-') as tmp:
    p = Path(tmp)
    (p / 'test.mm').write_text(program)
    subprocess.run(['xcrun', 'clang++', '-std=c++14', '-fno-objc-arc',
                    '-I', str(headers),
                    str(p / 'test.mm'), str(library),
                    '-framework', 'Foundation', '-o', str(p / 'test')], check=True)
    subprocess.run([str(p / 'test')], check=True)

print('PASS: interleave none, line and sample decode to the same samples for '
      '1 and 3 components at 8 and 16 bits')
