#!/usr/bin/env python3
"""Exercise the real adapter with synthetic pixels, caller buffers and failures.

Requires OpenJPEG and DCMTK headers from a Debug/Release build. On macOS, leaks
also checks repeated decodes in a separate, unsanitized process. --source can
point to an earlier adapter to demonstrate the regression.
"""
import argparse
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--source', type=Path, default=ROOT/'Horos/Sources/OPJSupport.cpp')
args = parser.parse_args()
configuration = os.environ.get('HOROS_TEST_CONFIGURATION', 'Debug')
build = ROOT/'build/Build/Intermediates.noindex/Horos.build'/configuration
install = build/'OpenJPEG.build/Install'
archive = install/'lib/libopenjp2.a'
dcmtk = build/'DCMTK.build/Install/include'
if not archive.is_file() or not (install/'include/OpenJPEG/openjpeg.h').is_file():
    print('skipped: needs OpenJPEG from a current Debug/Release build')
    raise SystemExit(2)
if not (dcmtk/'dcmtk/ofstd/ofthread.h').is_file():
    print('skipped: needs DCMTK headers from a current Debug/Release build')
    raise SystemExit(2)

driver = r'''
#include "OPJSupport.h"
#include <OpenJPEG/openjpeg.h>
#include <algorithm>
#include <cassert>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <string>
#include <vector>

struct Fixture {
    std::vector<unsigned char> encoded, expected;
    int color;
};

Fixture makeFixture(const char *path, OPJ_CODEC_FORMAT format, int bits,
                    bool isSigned, int components) {
    const int width = 64, height = 48;
    opj_image_cmptparm_t parameters[4] = {};
    for (int c = 0; c < components; ++c) {
        parameters[c].dx = parameters[c].dy = 1;
        parameters[c].w = width; parameters[c].h = height;
        parameters[c].prec = bits; parameters[c].sgnd = isSigned;
    }
    opj_image_t *image = opj_image_create(components, parameters,
        components == 1 ? OPJ_CLRSPC_GRAY : OPJ_CLRSPC_SRGB);
    assert(image);
    image->x1 = width; image->y1 = height;
    Fixture fixture; fixture.color = components > 1;
    for (int y = 0; y < height; ++y) for (int x = 0; x < width; ++x) {
        for (int c = 0; c < components; ++c) {
            int value = (x * 17 + y * 31 + c * 73) % (1 << bits);
            if (isSigned) value -= 1 << (bits - 1);
            image->comps[c].data[y * width + x] = value;
            if (bits <= 8) fixture.expected.push_back((unsigned char)value);
            else {
                unsigned short sample = (unsigned short)value;
                const unsigned char *bytes = (const unsigned char *)&sample;
                fixture.expected.insert(fixture.expected.end(), bytes, bytes + 2);
            }
        }
    }
    opj_cparameters_t options; opj_set_default_encoder_parameters(&options);
    options.tcp_numlayers = 1; options.tcp_rates[0] = 0;
    options.cp_disto_alloc = 1; options.numresolution = 4;
    opj_codec_t *codec = opj_create_compress(format);
    opj_stream_t *stream = opj_stream_create_default_file_stream(path, OPJ_FALSE);
    assert(codec && stream && opj_setup_encoder(codec, &options, image));
    assert(opj_start_compress(codec, image, stream));
    assert(opj_encode(codec, stream) && opj_end_compress(codec, stream));
    opj_stream_destroy(stream); opj_destroy_codec(codec); opj_image_destroy(image);
    std::ifstream input(path, std::ios::binary);
    fixture.encoded.assign(std::istreambuf_iterator<char>(input), {});
    assert(fixture.encoded.size() > 32);
    return fixture;
}

void checkValid(OPJSupport &decoder, Fixture &fixture) {
    long length = -1; int color = -1;
    void *pixels = decoder.decompressJPEG2K(fixture.encoded.data(),
        fixture.encoded.size(), &length, &color);
    assert(pixels && length == fixture.expected.size() && color == fixture.color);
    assert(!memcmp(pixels, fixture.expected.data(), length));
    free(pixels);

    std::vector<unsigned char> storage(fixture.expected.size() + 64, 0xa5);
    void *callerBuffer = storage.data() + 32;
    pixels = decoder.decompressJPEG2KWithBuffer(callerBuffer, fixture.encoded.data(),
        fixture.encoded.size(), &length, &color);
    assert(pixels == callerBuffer && length == fixture.expected.size());
    assert(color == fixture.color && !memcmp(pixels, fixture.expected.data(), length));
    assert(std::all_of(storage.begin(), storage.begin() + 32,
        [](unsigned char v) { return v == 0xa5; }));
    assert(std::all_of(storage.end() - 32, storage.end(),
        [](unsigned char v) { return v == 0xa5; }));
}

void checkInvalid(OPJSupport &decoder, std::vector<unsigned char> &encoded) {
    long length = -1; int color = -1;
    unsigned char storage[64]; memset(storage, 0xa5, sizeof(storage));
    assert(!decoder.decompressJPEG2K(encoded.data(), encoded.size(), &length, &color));
    assert(!decoder.decompressJPEG2KWithBuffer(storage, encoded.data(),
        encoded.size(), &length, &color));
    for (unsigned char value : storage) assert(value == 0xa5);
}

int main(int argc, char **argv) {
    assert(argc == 2);
    std::vector<Fixture> fixtures;
    for (auto format : {OPJ_CODEC_J2K, OPJ_CODEC_JP2}) {
        for (int bits : {8, 12, 16})
            for (bool isSigned : {false, true})
                fixtures.push_back(makeFixture(argv[1], format, bits, isSigned, 1));
        for (int components : {3, 4})
            fixtures.push_back(makeFixture(argv[1], format, 8, false, components));
    }
    std::vector<std::vector<unsigned char>> invalid = {
        {}, {0}, std::vector<unsigned char>(11, 0), std::vector<unsigned char>(16, 0),
        {0,0,0,12,0x6a,0x50,0x20,0x20,13,10,0x87,10}
    };
    for (const auto &fixture : fixtures) {
        invalid.emplace_back(fixture.encoded.begin(), fixture.encoded.begin() + 16);
        invalid.emplace_back(fixture.encoded.begin(),
            fixture.encoded.begin() + fixture.encoded.size()/2);
    }
    OPJSupport decoder;
    for (int repetition = 0; repetition < 20; ++repetition) {
        for (auto &fixture : fixtures) checkValid(decoder, fixture);
        for (auto &encoded : invalid) checkInvalid(decoder, encoded);
    }
    long length = -1; int color = -1;
    assert(!decoder.decompressJPEG2K(NULL, 12, &length, &color));
    assert(!decoder.decompressJPEG2K(NULL, -1, &length, &color));
}
'''

with tempfile.TemporaryDirectory(prefix='horos-openjpeg-decoder-') as temporary:
    work = Path(temporary)
    (work/'check.cpp').write_text(driver)
    command = ['xcrun', 'clang++', '-std=c++11', '-g',
        '-I'+str(ROOT/'Horos/Sources'), '-I'+str(install/'include'), '-I'+str(dcmtk),
        str(work/'check.cpp'), str(args.source.resolve()), str(archive)]
    subprocess.run([*command, '-fsanitize=address,undefined', '-o', str(work/'sanitized')], check=True)
    result = subprocess.run([str(work/'sanitized'), str(work/'fixture.j2k')],
        capture_output=True, text=True, timeout=60)
    if result.returncode:
        raise SystemExit('Decoder checks failed:\n'+result.stdout[-2000:]+result.stderr[-6000:])
    print('PASS: 16 lossless formats, signed/unsigned pixels, caller buffers and 37 malformed inputs (ASan/UBSan)')
    subprocess.run([*command, '-o', str(work/'check')], check=True)
    result = subprocess.run(['/usr/bin/leaks', '-quiet', '-atExit', '--', str(work/'check'),
        str(work/'fixture.j2k')], env={**os.environ, 'MallocStackLogging': '1'},
        capture_output=True, text=True, timeout=60)
    if result.returncode or '0 leaks for 0 total leaked bytes' not in result.stdout:
        raise SystemExit('Decoder leak check failed:\n'+result.stdout+result.stderr)
    print('PASS: repeated successful and failed decodes leave no leaks')
