#!/usr/bin/env python3
"""An object whose only picture is its icon said it had none.

An Icon Image Sequence is a preview of the image, not the image (PS 3.3
C.7.6.1.1.6). A radiofluoroscopic object that declares 1024x1024, carries no
Pixel Data and carries a 32x32 icon was reported as carrying "no pixel data at
all" - which is a different claim, and a false one about a file that does hold a
small picture.

Beside it, the check that names such files asked whether the SOP class was one of
the ones the application lists as images. A hardcopy grayscale object - modality
HC, sitting in a mammography study, which is the shape of the crash report - is
not on that list, so it was indexed with no pixels and nothing was said.

Measured on a study of five: an ordinary mammography image, the RF with the icon,
the hardcopy with no pixels, an MR spectroscopy object and a private Siemens
non-image object. Nothing crashed, every file was kept, and now:

    ---- 3.dcm: it carries no pixel data at all; it is indexed and counted as an image anyway
    ---- 5.dcm: its only picture is a 32 x 32 preview icon in Icon Image Sequence
         (0088,0200), not the 1024 x 1024 image it declares; …
"""
from pathlib import Path
import re
import sys

root = Path(__file__).resolve().parents[1]
failures = []
reader = (root / 'Horos/Sources/DicomFileDCMTKCategory.mm').read_bytes().decode('latin1')
code = re.sub(r'//[^\n]*', '', reader)

at = code.find('claimsAPicture')
if at < 0:
    failures.append('the check that names an object with no pixels is gone, or still asks only '
                    'about the SOP classes the application lists as images')
else:
    window = code[max(at - 400, 0):at + 3000]
    if 'rows > 0 || columns > 0' not in window:
        failures.append('an object is no longer judged by whether it claims a picture, so a '
                        'hardcopy object with no pixels is indexed with nothing said')
    if 'DCM_IconImageSequence' not in window:
        failures.append('an object whose only picture is its icon is still reported as carrying '
                        'no pixel data at all')
    if 'Icon Image Sequence (0088,0200)' not in window:
        failures.append('the message does not name where the picture actually is')
    for fragment in ('DCM_Rows', 'DCM_Columns'):
        if fragment not in window:
            failures.append('the icon\'s own size is not read, so the message cannot say what '
                            'resolution the preview has')
    # The messages that were already there have to survive.
    for fragment in ('it carries no pixel data at all', 'its pixel data is empty',
                     'Float Pixel Data (7fe0,0008)', 'it declares a picture of'):
        if fragment not in window:
            failures.append('the diagnosis lost %r' % fragment)

# And nothing may invent a picture in place of one that is missing.
pix = re.sub(r'//[^\n]*', '', (root / 'Horos/Sources/DCMPix.m').read_bytes().decode('latin1'))
at = pix.find('if( oImage == nil)')
branch = pix[at:at + 900] if at >= 0 else ''
if not branch:
    failures.append('the branch for a frame that decoded to nothing is gone')
elif 'yo++' in branch:
    failures.append('a frame with no pixels is still filled with a ramp')

# --- an instance kept but not displayable says so, with its SOP class ----------
at = code.find('which this application keeps but cannot display')
if at < 0:
    failures.append('an instance that is not a picture and is not one of the kinds the '
                    'application shows is still kept and listed with nothing saying why')
else:
    window = code[max(at - 1400, 0):at + 400]
    if 'sopClassUID' not in window:
        failures.append('the message does not carry the SOP class the instance arrived as, which '
                        'is what lets it be found again')
    for predicate in ('isStructuredReport', 'isPDF', 'isPresentationState', 'isRadiotherapy',
                      'isWaveform', 'isDirectory'):
        if predicate not in window:
            failures.append('%s is no longer excluded, so a kind the application does show would '
                            'be reported as one it cannot' % predicate)

for failure in failures:
    print('FAIL: %s' % failure)
if failures:
    sys.exit(1)
print('ok: an object that claims a picture and has none is named whatever its SOP class, one '
      'whose only picture is an icon says so with the icon\'s size, and one that is kept but '
      'cannot be displayed says so with the class it arrived as')
