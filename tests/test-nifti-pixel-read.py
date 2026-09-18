#!/usr/bin/env python3
"""NIfTI voxels as the library reads them: byte order, every datatype, one slice a frame (#643).

`-[DCMPix CheckLoadIn]` read the `.img` of a two-file NIfTI pair as it is on disk,
so a big-endian pair came out with its bytes swapped (the one-file `.nii` used the
library's buffer, already in host order). It also turned int32 into shorts, left
the image unwritten for uint16, uint32 and RGB, and loaded the whole volume for
every frame without freeing it.

The frame is now the slice nifti1_io reads (`nifti_read_collapsed_image`, after
`nifti_image_read` without data): in host order, from either file layout, each
integer or floating type turned into floats and RGB24 into four bytes a pixel.

Checked here: the source of that path, and the same library calls and conversion
on files written by this test - a big-endian `ni1` pair, uint16 above 32767, a
big-endian int32 below -32768, RGB24 - against the values written.
"""
from pathlib import Path
import struct
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
failures = []

source = (root / 'Horos/Sources/DCMPix.m').read_bytes().decode('latin1')
begin = source.index('// NIfTI support developed by Zack Mahdavi')
end = source.index("else if( [extension isEqualToString:@\"hdr\"]) // 'old' ANALYZE", begin)
nifti = source[begin:end]
tail = source[end:source.index('else if( [extension isEqualToString:@"jpg"]', end)]
if 'initWithContentsOfFile' in nifti:
    failures.append('the .img of a pair is still read as it is on disk')
if 'nifti_image_read([self.srcFile UTF8String], 0)' not in nifti:
    failures.append('the whole volume is still loaded for every frame')
if 'nifti_read_collapsed_image( nifti_imagedata, slice, &voxels)' not in nifti:
    failures.append("the frame is not the slice the library reads")
for datatype in ('DT_UINT8', 'DT_INT8', 'DT_INT16', 'DT_UINT16', 'DT_INT32', 'DT_UINT32', 'DT_FLOAT32', 'DT_FLOAT64'):
    if f'case {datatype}:' not in nifti:
        failures.append(f'{datatype} is not turned into floats')
if 'datatype == DT_RGB24' not in nifti:
    failures.append('RGB24 is not kept as colour')
if 'short *ptr' in nifti:
    failures.append('a datatype still goes through a short')
if 'nifti_image_free( nifti_imagedata);' not in tail:
    failures.append('the nifti_image of a frame is not freed')

X, Y, Z = 5, 4, 3


def header(datatype, bitpix, magic, endian, vox_offset):
    data = bytearray(348)
    put = lambda offset, form, *values: struct.pack_into(endian + form, data, offset, *values)
    put(0, 'i', 348)
    put(40, '8h', 3, X, Y, Z, 1, 1, 1, 1)
    put(70, 'h', datatype)
    put(72, 'h', bitpix)
    put(76, '8f', 1.0, 1.0, 1.0, 1.0, 0, 0, 0, 0)
    put(108, 'f', vox_offset)
    put(112, '2f', 1.0, 0.0)
    data[344:348] = magic
    return bytes(data)


def voxels(formula, form, endian):
    return b''.join(struct.pack(endian + form, formula(i, j, k)) for k in range(Z) for j in range(Y) for i in range(X))


def rgb(i, j, k):
    return ((20 * k + i) % 256, (3 * j + 40) % 256, (100 + 7 * k) % 256)


cases = {
    'pair-ni1-be.hdr': dict(datatype=4, bitpix=16, form='h', endian='>', pair=True,
                            formula=lambda i, j, k: 1000 * (k + 1) + 5 * j + i),
    'uint16.nii': dict(datatype=512, bitpix=16, form='H', endian='<', pair=False,
                       formula=lambda i, j, k: 40000 + 1000 * k + 10 * j + i),
    'int32-be.nii': dict(datatype=8, bitpix=32, form='i', endian='>', pair=False,
                         formula=lambda i, j, k: -200000 + 50000 * k + 100 * j + i),
    'rgb24.nii': dict(datatype=128, bitpix=24, form=None, endian='<', pair=False, formula=None),
}

program = r'''
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include "nifti1_io.h"

/* The frame as -[DCMPix CheckLoadIn] reads it: the header without data, then one slice. */
int main(int argc, char **argv) {
    for (int a = 1; a < argc; a++) {
        nifti_image *nim = nifti_image_read(argv[a], 0);
        if (!nim) { printf("%s unreadable\n", argv[a]); continue; }
        long count = (long) nim->nx * nim->ny;
        for (int k = 0; k < nim->nz; k++) {
            int slice[8] = { 0, -1, -1, k, 0, 0, 0, 0 };
            void *voxels = NULL;
            int bytes = nifti_read_collapsed_image(nim, slice, &voxels);
            if (bytes < count * nim->nbyper) { printf("%s %d short\n", argv[a], k); free(voxels); continue; }
            for (long p = 0; p < count; p++) {
                double value;
                switch (nim->datatype) {
                    case DT_INT16: value = ((int16_t *) voxels)[p]; break;
                    case DT_UINT16: value = ((uint16_t *) voxels)[p]; break;
                    case DT_INT32: value = ((int32_t *) voxels)[p]; break;
                    case DT_RGB24: { unsigned char *c = (unsigned char *) voxels + 3 * p;
                                     value = c[0] * 65536.0 + c[1] * 256.0 + c[2]; } break;
                    default: value = 0; break;
                }
                printf("%s %d %ld %.1f\n", argv[a], k, p, value);
            }
            free(voxels);
        }
        nifti_image_free(nim);
    }
    return 0;
}
'''

if subprocess.run(['xcrun', '--find', 'clang'], capture_output=True).returncode != 0:
    print('skipped: needs clang to build the library', file=sys.stderr)
    raise SystemExit(2)

with tempfile.TemporaryDirectory() as temporary:
    work = Path(temporary)
    expected = {}
    for name, case in cases.items():
        if case['datatype'] == 128:
            data = b''.join(bytes(rgb(i, j, k)) for k in range(Z) for j in range(Y) for i in range(X))
            values = {(k, j * X + i): c[0] * 65536 + c[1] * 256 + c[2]
                      for k in range(Z) for j in range(Y) for i in range(X) for c in [rgb(i, j, k)]}
        else:
            data = voxels(case['formula'], case['form'], case['endian'])
            values = {(k, j * X + i): case['formula'](i, j, k) for k in range(Z) for j in range(Y) for i in range(X)}
        path = work / name
        if case['pair']:
            path.write_bytes(header(case['datatype'], case['bitpix'], b'ni1\0', case['endian'], 0.0))
            path.with_suffix('.img').write_bytes(data)
        else:
            path.write_bytes(header(case['datatype'], case['bitpix'], b'n+1\0', case['endian'], 352.0) + b'\0' * 4 + data)
        expected[str(path)] = values
    (work / 'read.c').write_text(program)
    library = root / 'NIfTI_Library'
    built = subprocess.run(['xcrun', 'clang', '-std=c11', '-O2', '-Wno-unused-variable', '-I', str(library),
                            str(work / 'read.c'), str(library / 'nifti1_io.c'), str(library / 'znzlib.c'),
                            '-o', str(work / 'read')], capture_output=True, text=True)
    if built.returncode != 0:
        failures.append('the reader does not build against the library: ' + built.stderr[-600:])
    else:
        run = subprocess.run([str(work / 'read')] + list(expected), capture_output=True, text=True)
        seen = {path: 0 for path in expected}
        for line in run.stdout.splitlines():
            parts = line.split()
            if len(parts) != 4:
                failures.append('the library did not read: ' + line)
                continue
            path, k, p, value = parts[0], int(parts[1]), int(parts[2]), float(parts[3])
            want = expected[path][(k, p)]
            seen[path] += 1
            if abs(value - want) > 0.5:
                failures.append(f'{Path(path).name}: slice {k}, voxel {p} reads {value}, written {want}')
                expected[path] = {key: v for key, v in expected[path].items() if key[0] != k}  # one line a slice
        for path, count in seen.items():
            if count != X * Y * Z and not any(Path(path).name in f for f in failures):
                failures.append(f'{Path(path).name}: {count} of {X * Y * Z} voxels read')

if failures:
    print('\n'.join('FAIL: ' + f for f in failures))
    raise SystemExit(1)
print('NIfTI frames: the slice the library reads, in host order, every datatype as floats or colour')
