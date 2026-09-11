#!/usr/bin/env python3
"""JPEG-LS round-trips losslessly, and the two CharLS copies still agree.

Both libCharLS.a and libGDCM.a are on the application's link line and both
export the same CharLS entry points, so whichever the linker reaches first
serves every caller. That is only safe while the two copies behave alike.
"""
import filecmp, re, subprocess, sys, tempfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
standalone = root / 'CharLS/src'
vendored = root / 'GDCM/Utilities/gdcmcharls'

# 1. The two trees must implement the same version. A drift here is what would
#    turn the symbol collision from harmless into a wrong-codec bug.
def version(cmake_text, prefix):
    parts = []
    for key in ['MAJOR', 'MINOR']:
        m = re.search(r'set\s*\(\s*%s%s_VERSION\s+(\d+)' % (prefix, key), cmake_text)
        parts.append(m.group(1) if m else '?')
    return '.'.join(parts)

standalone_version = version((root / 'CharLS/CMakeLists.txt').read_text(), 'CHARLS_LIB_')
vendored_version = version((vendored / 'CMakeLists.txt').read_text(), 'CHARLS_')
if standalone_version != vendored_version or '?' in standalone_version:
    print('FAIL: CharLS copies declare different versions: standalone %s, GDCM %s'
          % (standalone_version, vendored_version))
    sys.exit(1)

# 2. Every difference between the shared sources must be compilation hygiene.
#    Rather than listing exceptions line by line, normalise both files and
#    compare: what survives normalisation changes what the codec does.
def normalise(text):
    # A redundant 'virtual' next to 'override' says the same thing.
    text = re.sub(r'\bvirtual\b\s+(?=[^;{\n]*\boverride\b)', '', text)
    text = re.sub(r'\boverride\b', '', text)                 # explicit overrides
    text = re.sub(r'=\s*default\s*;', '{}', text)            # defaulted vs empty bodies
    text = re.sub(r'^\s*#\s*(pragma|if|ifdef|ifndef|else|elif|endif)\b.*$', '',
                  text, flags=re.M)                           # dialect and diagnostic guards
    text = re.sub(r'^\s*template class \w+<[^>]*>\s*;\s*$', '', text, flags=re.M)
    text = re.sub(r'template<typename T, typename\.\.\. Args>\s*'
                  r'std::unique_ptr<T> make_unique\(Args&&\.\.\. args\)\s*'
                  r'\{[^}]*\}', '', text)                     # the C++11 make_unique shim
    text = re.sub(r'\bWIN32\b', '_WIN32', text)               # same macro, Windows only
    text = re.sub(r'\s+', ' ', text)
    text = re.sub(r'\{\s*\}', '{}', text)                    # empty body, either spelling
    text = re.sub(r'\s+([;,)])', r'\1', text)                 # a removed keyword leaves a gap
    return text.strip()

divergent = []
for source in sorted(standalone.iterdir()):
    other = vendored / source.name
    if not (source.is_file() and other.exists()) or filecmp.cmp(source, other, shallow=False):
        continue
    left = normalise(source.read_bytes().decode('latin1'))
    right = normalise(other.read_bytes().decode('latin1'))
    if left != right:
        divergent.append(source.name)
if divergent:
    print('FAIL: the CharLS copies differ beyond compilation hygiene, so which one the'
          ' linker picks now matters: %s' % ', '.join(divergent))
    sys.exit(1)

# 3. And the codec itself round-trips, built from each copy in turn.
probe = r'''
#include <charls.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>

static int roundtrip(int width, int height, int bits, int components, const char *label)
{
    int bytesPerSample = bits > 8 ? 2 : 1;
    size_t sourceLength = (size_t)width * height * components * bytesPerSample;
    unsigned char *source = (unsigned char *)malloc(sourceLength);
    // A gradient with a repeating step: compressible, but not uniform.
    for (size_t i = 0; i < sourceLength; i++)
        source[i] = (unsigned char)((i * 7 + (i / 61) * 13) & 0xFF);

    struct JlsParameters params;
    memset(&params, 0, sizeof(params));
    params.width = width; params.height = height;
    params.bitsPerSample = bits; params.components = components;
    params.stride = width * components * bytesPerSample;
    // The buffer above interleaves the components, so say so; the default
    // expects planar input and would decode to something else.
    if (components > 1) params.interleaveMode = charls::InterleaveMode::Sample;

    size_t capacity = sourceLength * 2 + 8192;
    unsigned char *encoded = (unsigned char *)malloc(capacity);
    size_t encodedLength = 0;
    char message[256] = {0};

    if (JpegLsEncode(encoded, capacity, &encodedLength, source, sourceLength, &params, message) != charls::ApiResult::OK) {
        printf("FAIL %s: encode: %s\n", label, message); return 1;
    }
    if (encodedLength == 0 || encodedLength >= capacity) {
        printf("FAIL %s: encoded length %zu\n", label, encodedLength); return 1;
    }

    struct JlsParameters header;
    memset(&header, 0, sizeof(header));
    if (JpegLsReadHeader(encoded, encodedLength, &header, message) != charls::ApiResult::OK) {
        printf("FAIL %s: header: %s\n", label, message); return 1;
    }
    if (header.width != width || header.height != height
        || header.bitsPerSample != bits || header.components != components) {
        printf("FAIL %s: header describes %dx%d %d bits %d components\n",
               label, header.width, header.height, header.bitsPerSample, header.components);
        return 1;
    }

    unsigned char *decoded = (unsigned char *)malloc(sourceLength);
    memset(decoded, 0, sourceLength);
    if (JpegLsDecode(decoded, sourceLength, encoded, encodedLength, &params, message) != charls::ApiResult::OK) {
        printf("FAIL %s: decode: %s\n", label, message); return 1;
    }
    if (memcmp(source, decoded, sourceLength) != 0) {
        printf("FAIL %s: decoded image differs from the original\n", label); return 1;
    }

    // Report the encoded bytes so the two builds can be compared.
    unsigned long sum = 0;
    for (size_t i = 0; i < encodedLength; i++) sum = sum * 131 + encoded[i];
    printf("%s %dx%d bits=%d comp=%d encoded=%zu digest=%lu\n",
           label, width, height, bits, components, encodedLength, sum);

    free(source); free(encoded); free(decoded);
    return 0;
}

int main(int argc, char **argv)
{
    const char *label = argc > 1 ? argv[1] : "codec";
    if (roundtrip(64, 48, 8, 1, label)) return 1;
    if (roundtrip(64, 48, 16, 1, label)) return 1;
    if (roundtrip(37, 23, 8, 3, label)) return 1;   // odd size, colour
    if (roundtrip(1, 1, 8, 1, label)) return 1;     // smallest image
    return 0;
}
'''

results = {}
with tempfile.TemporaryDirectory(prefix='horos-jpegls-') as folder:
    p = Path(folder)
    (p / 'probe.c').write_text(probe)
    for label, tree in [('standalone', standalone), ('gdcm', vendored)]:
        sources = sorted(str(f) for f in tree.glob('*.cpp'))
        binary = p / ('probe-' + label)
        subprocess.run(['xcrun', 'clang++', '-std=c++14', '-O1', '-DCHARLS_STATIC',
                        '-I', str(tree), '-x', 'c++', str(p / 'probe.c'), *sources,
                        '-o', str(binary)], check=True)
        out = subprocess.run([str(binary), label], capture_output=True, text=True)
        if out.returncode != 0:
            print(out.stdout.strip() or out.stderr.strip())
            sys.exit(1)
        results[label] = [line.split(' ', 1)[1] for line in out.stdout.strip().split('\n')]

if results['standalone'] != results['gdcm']:
    print('FAIL: the two CharLS copies encode differently:')
    for a, b in zip(results['standalone'], results['gdcm']):
        if a != b:
            print('  standalone:', a)
            print('  gdcm      :', b)
    sys.exit(1)

print('PASS: CharLS %s in both copies, differences confined to compilation hygiene, '
      'and %d lossless round-trips produce byte-identical output from either build'
      % (standalone_version, len(results['standalone'])))
