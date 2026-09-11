#!/usr/bin/env python3
"""32-bit pixel data was copied into a float buffer and called floats.

`-[DCMPix loadDICOMDCMFramework]` has one branch for `BitsAllocated == 32`. It
memcpy'd the words into the float image and only converted them when a rescale
happened to be there:

    memcpy( fImage, oImage, height * width * sizeof( float));
    if( slope != 1.0 || offset != 0 || […@"32bitDICOMAreAlwaysIntegers"])

Pixel Data (7fe0,0010) holds integers - the standard gives floating point pixels
their own attributes, (7fe0,0008) and (7fe0,0009) - so reinterpreting an integer
as an IEEE float turns any ordinary value into a denormal. Measured through the
series thumbnails the application itself builds, on a 64x64 left-to-right ramp:

    control: 16-bit unsigned ramp                   68 levels, monotone
    32-bit unsigned ramp, no rescale                 1 level
    32-bit signed ramp, no rescale                   1 level
    32-bit unsigned ramp with RescaleSlope 2        68 levels, monotone

One flat grey, which is the "all zeros" of the reports, and it went away as soon
as a rescale gave the file a reason to be converted.

The other half is the diagnosis: a file whose pixels are in Float Pixel Data was
reported as carrying "no pixel data at all", which is a false statement about a
file that carries a picture this application does not read. Neither (7fe0,0008)
nor (7fe0,0009) was in the vendored dictionary at all.
"""
from pathlib import Path
from dcmtk_build import dcmtk_flags
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
failures = []
dcmtk = root / 'DCMTK'
pix = (root / 'Horos/Sources/DCMPix.m').read_bytes().decode('latin1')
reader = (root / 'Horos/Sources/DicomFileDCMTKCategory.mm').read_bytes().decode('latin1')

# --- the words are converted, not reinterpreted --------------------------------
at = pix.find('if( bitsAllocated == 32)')
branch = pix[at:at + 2600] if at >= 0 else ''
if not branch:
    failures.append('the 32-bit branch is gone')
else:
    if 'PixelRepresentation' not in branch:
        failures.append('nothing asks whether the object states Pixel Representation, which is '
                        'what says its Pixel Data holds integers')
    condition = branch[branch.find('if( statesIntegers'):branch.find('if( statesIntegers') + 200]
    if not condition:
        failures.append('a 32-bit integer image is still only converted when a rescale happens '
                        'to be present, so its values arrive as denormals')
    elif 'slope != 1.0' not in condition or '32bitDICOMAreAlwaysIntegers' not in condition:
        failures.append('the conversion no longer covers the cases it used to: %r' % condition)

# --- and a picture in another attribute is named, not denied -------------------
at = reader.find('NSString *problem = nil;')
diagnosis = reader[at:at + 2200] if at >= 0 else ''
if not diagnosis:
    failures.append('the pixel-data diagnosis is gone')
else:
    for tag, name in (('DCM_FloatPixelData', 'Float Pixel Data'),
                      ('DCM_DoubleFloatPixelData', 'Double Float Pixel Data')):
        if tag not in diagnosis:
            failures.append('a file whose pixels are in %s is still reported as carrying none'
                            % name)
    if 'it carries no pixel data at all' not in diagnosis:
        failures.append('a file that really has no pixel data is no longer named')

# --- the dictionary knows the attributes ---------------------------------------
DRIVER = '''
#include <dcmtk/dcmdata/dcdict.h>
#include <dcmtk/dcmdata/dcdeftag.h>
#include <dcmtk/dcmdata/dcdicent.h>
#include <cstdio>
int main() {
    DcmDataDictionary &dictionary = dcmDataDict.wrlock();
    const DcmTagKey keys[] = {DCM_PixelData, DCM_FloatPixelData, DCM_DoubleFloatPixelData};
    for (unsigned i = 0; i < 3; i++) {
        const DcmDictEntry *entry = dictionary.findEntry(keys[i], NULL);
        printf("%04x,%04x\\t%s\\n", keys[i].getGroup(), keys[i].getElement(),
               entry ? entry->getTagName() : "(absent)");
    }
    dcmDataDict.wrunlock();
    return 0;
}
'''
with tempfile.TemporaryDirectory(prefix='horos-pixeltags-') as directory:
    driver = Path(directory) / 'main.cc'
    driver.write_text(DRIVER)
    binary = Path(directory) / 'pixeltags'
    build = subprocess.run(
        ['xcrun', 'clang++', '-std=c++11', str(driver), *dcmtk_flags(), '-o', str(binary)],
        capture_output=True, text=True)
    if build.returncode != 0:
        failures.append('the dictionary does not build with the pixel-data attributes:\n%s'
                        % build.stderr[-1200:])
    else:
        run = subprocess.run([str(binary)], capture_output=True, text=True, timeout=120)
        named = dict(line.split('\t', 1) for line in run.stdout.splitlines() if '\t' in line)
        for tag, want in (('7fe0,0010', 'PixelData'),
                          ('7fe0,0008', 'FloatPixelData'),
                          ('7fe0,0009', 'DoubleFloatPixelData')):
            if named.get(tag) != want:
                failures.append('(%s) is %r, expected %r' % (tag, named.get(tag), want))

for failure in failures:
    print('FAIL: %s' % failure)
if failures:
    sys.exit(1)
print('ok: 32-bit Pixel Data is read as the integers it holds, and a picture stored in Float or '
      'Double Float Pixel Data is named rather than denied')
