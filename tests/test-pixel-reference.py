#!/usr/bin/env python3
"""The samples the framework hands the viewer are the samples in the file.

Reads every instance of a fixture directory twice: once through the built DCM
framework - the same `-[DCMPixelDataAttribute decodeFrameAtIndex:]` the viewer
calls - and once with pydicom, which shares no code with it. Every sample has to
match. This is the file-reading half of the path; what DCMPix then makes of
those samples (rescale, window) is measured elsewhere, against the thumbnails
and in the 2D window.

Only monochrome instances are compared. `-decodeFrameAtIndex:` also converts
colour spaces - YBR and palette come back as RGB, three samples where the file
holds one or two - so for a colour object it is not the file's bytes that come
back and this is not the check to make; `tools/check-colour-thumbnails.py` is.

Neither the framework nor the fixtures are in this repository. Build with
`script/build_and_run.sh`, make fixtures with the generators in `tools/`.

Usage: python test-pixel-reference.py PRODUCTS_DIR FIXTURE_DIR [FIXTURE_DIR...]
       PRODUCTS_DIR is build/Build/Products/Debug, holding DCM.framework
"""
from pathlib import Path
import json
import subprocess
import sys
import tempfile

if len(sys.argv) < 3:
    print('skipped: needs the built DCM framework and a fixture directory: '
          'PRODUCTS_DIR FIXTURE_DIR', file=sys.stderr)
    raise SystemExit(2)
try:
    import numpy
    import pydicom
except ImportError:
    print('skipped: needs pydicom and numpy: PRODUCTS_DIR FIXTURE_DIR', file=sys.stderr)
    raise SystemExit(2)

products = Path(sys.argv[1]).resolve()
if not (products / 'DCM.framework').is_dir():
    print('skipped: no DCM.framework in %s: PRODUCTS_DIR FIXTURE_DIR' % products, file=sys.stderr)
    raise SystemExit(2)

program = r'''
#import <Foundation/Foundation.h>
#import <DCM/DCM.h>

// One frame, as bytes, written where the caller asked: the bytes the viewer is
// given, not a picture of them.
int main(int argc, char **argv) { @autoreleasepool {
    DCMObject *object = [DCMObject objectWithContentsOfFile:
                            [NSString stringWithUTF8String: argv[1]] decodingPixelData: NO];
    if (object == nil) { fprintf(stderr, "unreadable\n"); return 2; }
    DCMPixelDataAttribute *attribute = (DCMPixelDataAttribute*) [object attributeWithName:@"PixelData"];
    if (attribute == nil) { fprintf(stderr, "no pixel data\n"); return 3; }
    NSData *frame = [attribute decodeFrameAtIndex: atoi(argv[3])];
    if (frame == nil) { fprintf(stderr, "decoded to nothing\n"); return 4; }
    if (![frame writeToFile: [NSString stringWithUTF8String: argv[2]] atomically: YES]) {
        fprintf(stderr, "could not write\n"); return 5; }
    printf("%lu\n", (unsigned long) [frame length]);
    return 0;
}}
'''

UNCOMPRESSED = {'1.2.840.10008.1.2', '1.2.840.10008.1.2.1', '1.2.840.10008.1.2.2'}
failures = []
compared = 0

with tempfile.TemporaryDirectory(prefix='horos-pixel-reference-') as tmp:
    work = Path(tmp)
    (work / 'bin').mkdir()
    (work / 'Frameworks').symlink_to(products)
    (work / 'read.m').write_text(program)
    # -w: the framework's own headers use API deprecated since 10.10, and the
    # notes about it drown the result.
    subprocess.run(['xcrun', 'clang', '-fno-objc-arc', '-fmodules', '-w',
                    '-F', str(products), '-framework', 'DCM', '-framework', 'Foundation',
                    str(work / 'read.m'), '-o', str(work / 'bin/read')], check=True)

    for argument in sys.argv[2:]:
        fixture = Path(argument).resolve()
        for path in sorted(fixture.glob('*.dcm')):
            dataset = pydicom.dcmread(str(path))
            syntax = str(dataset.file_meta.TransferSyntaxUID)
            if syntax not in UNCOMPRESSED:
                continue                      # a codec's output is measured elsewhere
            if 'PixelData' not in dataset or not dataset.PixelData:
                continue
            if int(dataset.get('Rows', 0)) == 0 or int(dataset.get('Columns', 0)) == 0:
                continue
            photometric = str(dataset.get('PhotometricInterpretation', ''))
            if int(dataset.get('SamplesPerPixel', 1)) != 1 or not photometric.startswith('MONOCHROME'):
                continue

            out = work / 'frame.raw'
            result = subprocess.run([str(work / 'bin/read'), str(path), str(out), '0'],
                                    capture_output=True, text=True)
            if result.returncode != 0:
                failures.append('%s: %s' % (path.name, result.stderr.strip() or result.returncode))
                continue

            decoded = out.read_bytes()
            bits = int(dataset.BitsAllocated)
            samples = int(dataset.SamplesPerPixel)
            count = int(dataset.Rows) * int(dataset.Columns) * samples
            # What the header says the frame is, read straight out of the
            # element by a reader that knows nothing about the application.
            kind = {8: numpy.uint8, 16: numpy.uint16, 32: numpy.uint32}.get(bits)
            if kind is None:
                continue
            if dataset.PixelRepresentation:
                kind = {8: numpy.int8, 16: numpy.int16, 32: numpy.int32}[bits]
            expected = numpy.frombuffer(bytes(dataset.PixelData), dtype=kind)[:count]
            got = numpy.frombuffer(decoded, dtype=kind)[:count]
            if len(got) != len(expected):
                failures.append('%s: %d samples decoded, %d in the file'
                                % (path.name, len(got), len(expected)))
                continue
            if not numpy.array_equal(got, expected):
                where = int(numpy.argmax(got != expected))
                failures.append('%s: sample %d is %s, the file says %s'
                                % (path.name, where, got[where], expected[where]))
                continue
            compared += 1

print('%d uncompressed monochrome instance(s) read through the framework and compared '
      'with pydicom' % compared)
for failure in failures:
    print('FAIL: %s' % failure)
if failures:
    sys.exit(1)
if compared == 0:
    print('skipped: none of the given fixtures is uncompressed monochrome', file=sys.stderr)
    raise SystemExit(2)
print('ok: every sample matches')
