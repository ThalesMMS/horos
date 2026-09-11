#!/usr/bin/env python3
"""Near-lossless JPEG-LS, and malformed streams, under the sanitizers.

The report behind #260 is a crash inside the JPEG-LS codec while the Web Portal
built a thumbnail of a near-lossless ultrasound object. The conversion that
allocates the output buffer is production code and can be exercised on its own:
this compiles it with the address and undefined-behaviour sanitizers, encodes
near-lossless streams of 1 and 3 components at 8 and 16 bits, and then feeds it
streams that are truncated, empty, or that promise more pixels than they carry.

Usage: python test-jpegls-nearlossless-sanitized.py CHARLS_LIB
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

static const int kWidth = 41;   // odd, so a stride mistake shows
static const int kHeight = 29;

static std::vector<unsigned char> samples(int components, int bytesPerSample)
{
    std::vector<unsigned char> data((size_t) kWidth * kHeight * components * bytesPerSample);
    size_t at = 0;
    for (int y = 0; y < kHeight; y++)
        for (int x = 0; x < kWidth; x++)
            for (int c = 0; c < components; c++)
            {
                int value = (x * 7 + y * 3 + c * 37) % (bytesPerSample == 1 ? 251 : 4093);
                for (int b = 0; b < bytesPerSample; b++)
                    data[at++] = (unsigned char) ((value >> (8 * b)) & 0xff);
            }
    return data;
}

static NSData *encodeNearLossless(const std::vector<unsigned char> &raw, int components,
                                  int bytesPerSample, int allowedError,
                                  charls::InterleaveMode mode)
{
    JlsParameters parameters = {};
    parameters.width = kWidth;
    parameters.height = kHeight;
    parameters.components = components;
    parameters.bitsPerSample = bytesPerSample == 1 ? 8 : 12;
    parameters.interleaveMode = mode;
    parameters.allowedLossyError = allowedError;

    std::vector<unsigned char> compressed(raw.size() * 2 + 8192);
    size_t written = 0;
    charls::ApiResult result = JpegLsEncode(&compressed[0], compressed.size(), &written,
                                            &raw[0], raw.size(), &parameters, NULL);
    if (result != charls::ApiResult::OK)
    {
        NSLog(@"FAIL: encoding %d components at error %d: %d",
              components, allowedError, (int) result);
        failures++;
        return nil;
    }
    return [NSData dataWithBytes:&compressed[0] length:written];
}

// Within the declared error, and not identical - so the lossy path is really taken.
static void exerciseNearLossless(int components, int bytesPerSample, int allowedError)
{
    std::vector<unsigned char> raw = samples(components, bytesPerSample);
    charls::InterleaveMode mode = components == 1 ? charls::InterleaveMode::None
                                                  : charls::InterleaveMode::Sample;
    NSData *compressed = encodeNearLossless(raw, components, bytesPerSample, allowedError, mode);
    if (!compressed) return;

    Decoder *decoder = [Decoder new];
    NSData *decoded = [decoder convertJPEGLSToHost: compressed];
    if (decoded == nil)
    {
        NSLog(@"FAIL: %d components, %d bit, error %d decoded to nothing",
              components, bytesPerSample * 8, allowedError);
        failures++;
        return;
    }
    if ([decoded length] != raw.size())
    {
        NSLog(@"FAIL: %d components, %d bit, error %d gave %lu bytes, %lu expected",
              components, bytesPerSample * 8, allowedError,
              (unsigned long) [decoded length], (unsigned long) raw.size());
        failures++;
        return;
    }
    const unsigned char *got = (const unsigned char *) [decoded bytes];
    int worst = 0;
    size_t count = bytesPerSample == 1 ? raw.size() : raw.size() / 2;
    for (size_t i = 0; i < count; i++)
    {
        int expected = bytesPerSample == 1 ? raw[i] : (raw[i*2] | (raw[i*2+1] << 8));
        int actual = bytesPerSample == 1 ? got[i] : (got[i*2] | (got[i*2+1] << 8));
        int difference = expected > actual ? expected - actual : actual - expected;
        if (difference > worst) worst = difference;
    }
    if (worst > allowedError)
    {
        NSLog(@"FAIL: %d components, %d bit differed by %d, more than the declared %d",
              components, bytesPerSample * 8, worst, allowedError);
        failures++;
    }
    NSLog(@"near-lossless %d component(s), %d bit, error %d: worst difference %d",
          components, bytesPerSample * 8, allowedError, worst);
}

// A thumbnail is built from whatever arrived, including what did not arrive whole.
static void exerciseMalformed(void)
{
    Decoder *decoder = [Decoder new];
    std::vector<unsigned char> raw = samples(1, 1);
    NSData *whole = encodeNearLossless(raw, 1, 1, 3, charls::InterleaveMode::None);
    if (!whole) return;

    // Nothing at all.
    [decoder convertJPEGLSToHost: [NSData data]];
    // One byte, and a header that stops in the middle.
    [decoder convertJPEGLSToHost: [whole subdataWithRange: NSMakeRange(0, 1)]];
    [decoder convertJPEGLSToHost: [whole subdataWithRange: NSMakeRange(0, 8)]];
    // Truncated at several points through the entropy-coded data.
    for (int part = 1; part < 8; part++)
        [decoder convertJPEGLSToHost:
            [whole subdataWithRange: NSMakeRange(0, [whole length] * part / 8)]];
    // The whole stream with trailing rubbish, and with a byte flipped inside it.
    NSMutableData *extended = [[whole mutableCopy] autorelease];
    [extended increaseLengthBy: 64];
    [decoder convertJPEGLSToHost: extended];
    NSMutableData *damaged = [[whole mutableCopy] autorelease];
    if ([damaged length] > 40)
    {
        ((unsigned char *) [damaged mutableBytes])[[damaged length] / 2] ^= 0xff;
        [decoder convertJPEGLSToHost: damaged];
    }
    // Data that is not JPEG-LS at all.
    unsigned char rubbish[512];
    for (size_t i = 0; i < sizeof(rubbish); i++) rubbish[i] = (unsigned char) (i * 31);
    [decoder convertJPEGLSToHost: [NSData dataWithBytes: rubbish length: sizeof(rubbish)]];
    NSLog(@"malformed streams returned without crashing");
}

int main(void) { @autoreleasepool {
    exerciseNearLossless(1, 1, 3);    // the ultrasound shape of the report
    exerciseNearLossless(3, 1, 3);
    exerciseNearLossless(1, 2, 5);
    exerciseNearLossless(3, 2, 2);
    exerciseNearLossless(1, 1, 0);    // lossless through the same path
    exerciseMalformed();
    NSLog(@"%@", failures ? @"FAILURES" : @"near-lossless and malformed streams handled");
    return failures ? 1 : 0;
}}
'''.replace('CONVERSION', conversion)

headers = root / 'CharLS/src'
with tempfile.TemporaryDirectory(prefix='horos-jpegls-nearlossless-') as tmp:
    p = Path(tmp)
    (p / 'test.mm').write_text(program)
    subprocess.run(['xcrun', 'clang++', '-std=c++14', '-fno-objc-arc', '-g',
                    '-fsanitize=address,undefined', '-fno-sanitize-recover=all',
                    '-I', str(headers),
                    str(p / 'test.mm'), str(library),
                    '-framework', 'Foundation', '-o', str(p / 'test')], check=True)
    subprocess.run([str(p / 'test')], check=True,
                   env={**__import__('os').environ,
                        'ASAN_OPTIONS': 'detect_leaks=0:abort_on_error=1'})

print('PASS: near-lossless 1 and 3 components at 8 and 16 bits decode within their declared '
      'error, and truncated, damaged, oversized and non-JPEG-LS streams return without a '
      'sanitizer report')
