#!/usr/bin/env python3
"""A NIfTI volume is indexed, and its slices sit where its header says.

Two defects, both measured against the running application before and after.

A valid .nii dropped into the incoming folder was called "not a DICOM file this
database can index" and, with DELETEFILELISTENER, deleted - although DCMPix reads
NIfTI and DicomFile has -isNIfTIFile:. The list of formats the importer accepts
named TIFF and NRRD and not this one.

And the slice position advanced by the in-plane spacing rather than by the
spacing between slices: with 0.5 mm pixels and 3 mm slices, the stack came out
six times too short. A fixture with cubic voxels cannot show that, which is why
the fixture here deliberately has none.

This checks the fixture generator against the NIfTI-1 header layout, and the two
call sites against the source. The geometry the application then reads is in
docs/nifti-import-geometry.md.
"""
from pathlib import Path
import re
import struct
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
failures = []

database = (root / 'Horos/Sources/DicomDatabase.mm').read_bytes().decode('latin1')
at = database.find('BOOL indexesAnything =')
accepted = database[at:at + 1200] if at >= 0 else ''
if not accepted:
    failures.append('the list of formats the importer accepts is gone')
elif 'isNIfTIFile:srcPath' not in accepted:
    failures.append('a NIfTI file is still refused by the importer, and deleted with '
                    'DELETEFILELISTENER')

dicomfile = (root / 'Horos/Sources/DicomFile.mm').read_bytes().decode('latin1')
at = dicomfile.find('+ (BOOL) isNIfTIFile:')
check = dicomfile[at:at + 1400] if at >= 0 else ''
if not check:
    failures.append('+[DicomFile isNIfTIFile:] is gone')
else:
    # It is now called for every incoming file with a .nii or .hdr name, so it has
    # to survive one that is not readable, and not leak the header it is given.
    if 'NIfTI != NULL' not in check:
        failures.append('isNIfTIFile: reads through the header without checking it was read')
    if 'free( NIfTI)' not in check and 'free(NIfTI)' not in check:
        failures.append('isNIfTIFile: drops the header it owns instead of freeing it')

pix = (root / 'Horos/Sources/DCMPix.m').read_bytes().decode('latin1')
at = pix.find('if(jcod == NIFTI_A2P || jcod == NIFTI_P2A)')
origins = pix[at:at + 1600] if at >= 0 else ''
if not origins:
    failures.append('the NIfTI origin block is gone')
else:
    if 'frameNo * pixelSpacingX' in origins:
        failures.append('a slice still advances by the in-plane spacing, so a volume whose '
                        'slices are not as thick as its pixels comes out the wrong length')
    if origins.count('frameNo * sliceInterval') != 3:
        failures.append('%d of the 3 orientations advance by the slice spacing'
                        % origins.count('frameNo * sliceInterval'))

for failure in failures:
    print('FAIL: %s' % failure)
reported = len(failures)

# --- the fixture is the specification, so check it against the layout ---------
try:
    import numpy                                    # noqa: F401
except ImportError:
    print('skipped: needs numpy to build the NIfTI fixture', file=sys.stderr)
    if failures:
        sys.exit(1)
    print('ok: NIfTI is indexed and its slices advance by the slice spacing')
    raise SystemExit(2)

with tempfile.TemporaryDirectory(prefix='horos-nifti-') as tmp:
    out = Path(tmp) / 'fixture'
    build = subprocess.run([sys.executable, str(root / 'tools/generate-nifti-fixture.py'),
                            str(out), '--slices', '8', '--size', '16'],
                           capture_output=True, text=True)
    if build.returncode:
        print(build.stderr.strip()[-1500:])
        sys.exit('the fixture generator failed')
    written = (out / 'geometry.nii').read_bytes()

    # NIfTI-1: a 348-byte header, magic at 344, data at vox_offset.
    header = written[:348]
    fields = {
        'sizeof_hdr': struct.unpack_from('<i', header, 0)[0],
        'dim': struct.unpack_from('<8h', header, 40),
        'datatype': struct.unpack_from('<h', header, 70)[0],
        'bitpix': struct.unpack_from('<h', header, 72)[0],
        'pixdim': struct.unpack_from('<8f', header, 76),
        'vox_offset': struct.unpack_from('<f', header, 108)[0],
        'scl_slope': struct.unpack_from('<f', header, 112)[0],
        'qform_code': struct.unpack_from('<h', header, 252)[0],
        'magic': header[344:348],
    }
    if fields['sizeof_hdr'] != 348:
        failures.append('sizeof_hdr is %d, not 348' % fields['sizeof_hdr'])
    if fields['magic'] != b'n+1\x00':
        failures.append('magic is %r, so nothing will take it for NIfTI-1' % fields['magic'])
    if fields['dim'][:4] != (3, 16, 16, 8):
        failures.append('dim is %s' % (fields['dim'][:4],))
    if (fields['datatype'], fields['bitpix']) != (4, 16):
        failures.append('datatype/bitpix are %d/%d, not 4/16'
                        % (fields['datatype'], fields['bitpix']))
    # The point of the fixture: the in-plane spacing and the slice spacing differ.
    if fields['pixdim'][1:4] != (0.5, 0.5, 3.0):
        failures.append('pixdim is %s; the fixture has to have slices thicker than its pixels'
                        % (fields['pixdim'][1:4],))
    if fields['qform_code'] < 1:
        failures.append('qform_code is %d, so the reader has no orientation to read'
                        % fields['qform_code'])
    if fields['scl_slope'] != 1.0:
        failures.append('scl_slope is %s, so the values are not what was written'
                        % fields['scl_slope'])
    if len(written) != int(fields['vox_offset']) + 16 * 16 * 8 * 2:
        failures.append('the file is %d bytes, which is not the header plus the voxels'
                        % len(written))

    # And the values: slice k holds 100 * (k + 1), which is how a frame read from
    # the wrong offset shows up as a number rather than as a picture.
    import numpy
    voxels = numpy.frombuffer(written[int(fields['vox_offset']):], dtype='<i2')
    voxels = voxels.reshape((8, 16, 16))
    for index in range(8):
        if not (voxels[index] == 100 * (index + 1)).all():
            failures.append('slice %d does not hold %d throughout' % (index, 100 * (index + 1)))
            break

    print('fixture: dim %s, pixdim %s, %d bytes, slices hold %s'
          % (fields['dim'][:4], fields['pixdim'][1:4], len(written),
             [int(voxels[i][0][0]) for i in range(8)]))

for failure in failures[reported:]:
    print('FAIL: %s' % failure)
if failures:
    sys.exit(1)
print('ok: NIfTI is indexed and its slices advance by the slice spacing')
