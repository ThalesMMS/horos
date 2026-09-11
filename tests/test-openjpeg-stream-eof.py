#!/usr/bin/env python3
"""The real OpenJPEG reader must stop when the host memory callback reaches EOF.

An optional --source permits verifying the regression against an older file.
The malformed input is constructed in memory; no fixture is published.
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
install = ROOT/'build/Build/Intermediates.noindex/Horos.build'/configuration/'OpenJPEG.build/Install'
headers = list((install/'include').glob('*/openjpeg.h'))
archive = install/'lib/libopenjp2.a'
if len(headers) != 1 or not archive.is_file():
    print('skipped: needs the OpenJPEG library from a current Debug/Release build')
    raise SystemExit(2)
source = args.source.read_bytes().decode('latin1')
callbacks = source[source.index('struct opj_memory_stream'):source.index('typedef struct decode_info')]
driver = r'''
#include <openjpeg.h>
#include <cassert>
#include <cstdlib>
#include <cstring>
#include <cstdio>
CALLBACKS
int main() {
    unsigned char input[] = {1,2,3}, output[8] = {};
    opj_memory_stream memory = {input, sizeof(input), 0};
    assert(opj_read_from_memory(output, 2, &memory) == 2);
    assert(output[0] == 1 && output[1] == 2);
    assert(opj_read_from_memory(output, 4, &memory) == 1 && output[0] == 3);
    assert(opj_read_from_memory(output, 1, &memory) == OPJ_SIZE_T(-1));
    assert(opj_read_from_memory(output, 1, &memory) == OPJ_SIZE_T(-1));
    memory.offset = 100;
    assert(opj_read_from_memory(output, 1, &memory) == OPJ_SIZE_T(-1));
    assert(opj_read_from_memory(output, 1, NULL) == OPJ_SIZE_T(-1));
    memory.offset = 0;
    assert(opj_read_from_memory(output, 0, &memory) == 0 && memory.offset == 0);

    // A JP2 signature with no subsequent boxes makes the library request EOF.
    unsigned char jp2[] = {0,0,0,12,0x6a,0x50,0x20,0x20,13,10,0x87,10};
    opj_stream_t* stream = opj_stream_create_memory_stream(jp2, sizeof(jp2));
    opj_codec_t* codec = opj_create_decompress(OPJ_CODEC_JP2);
    opj_dparameters_t parameters; opj_set_default_decoder_parameters(&parameters);
    assert(stream && codec && opj_setup_decoder(codec, &parameters));
    opj_image_t* image = NULL;
    assert(!opj_read_header(stream, codec, &image));
    if (image) opj_image_destroy(image);
    opj_destroy_codec(codec); opj_stream_destroy(stream);
    puts("PASS: partial reads, EOF sentinel and real JP2 parser terminate correctly");
}
'''.replace('CALLBACKS', callbacks)
with tempfile.TemporaryDirectory(prefix='horos-openjpeg-eof-') as temporary:
    work = Path(temporary)
    (work/'check.cpp').write_text(driver)
    subprocess.run(['xcrun', 'clang++', '-std=c++11', '-fsanitize=address,undefined',
        '-I'+str(headers[0].parent), str(work/'check.cpp'), str(archive),
        '-o', str(work/'check')], check=True)
    subprocess.run([str(work/'check')], check=True, timeout=5)
