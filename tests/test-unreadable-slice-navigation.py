#!/usr/bin/env python3
"""An unreadable slice is shown as such, and navigation moves on from it (#604).

The host viewer's answer to a frame that cannot be decoded: `CheckLoadIn`
allocates an empty frame, marks the pix `notAbleToLoadImage`, records a reason
(`missingPixelsReason`) and `DCMView` draws that reason over the empty frame.
The index the operator asked for is the index shown, so the previous image is
never presented as the failed slice; `setIndex:` neither refuses nor skips an
unreadable pix, so the next step goes on from the failed request, past it and
back; and a later successful decode has no reason to draw.

Source level, on the real methods, plus the reason texts compiled from
`MissingPixelsReason.swift`.
"""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
pix = (root / 'Horos/Sources/DCMPix.m').read_bytes().decode('latin1')
view = (root / 'Horos/Sources/DCMView.m').read_bytes().decode('latin1')
failures = []


def method(source, signature, terminator='\n}\n'):
    start = source.find(signature)
    if start < 0:
        return ''
    return source[start:source.find(terminator, start) + len(terminator)]


check = pix[pix.find('- (void) CheckLoadIn\n'):pix.find('- (NSString*) parsedFileCacheKey')]
if 'notAbleToLoadImage = YES;' not in check or 'reasonForUnreadableFrame' not in check:
    failures.append('CheckLoadIn no longer marks an unreadable frame with a reason')
if 'memset( fImage, 0, (long) width * height * 4);' not in check:
    failures.append('an unreadable frame must be empty, not a gradient or the previous pixels')

set_index = method(view, '- (void) setIndex:(short) index\n')
if not set_index:
    failures.append('DCMView setIndex: is gone')
else:
    if 'notAbleToLoadImage' in set_index or 'missingPixelsReason' in set_index:
        failures.append('setIndex: must not skip or refuse an unreadable pix; the index asked for is the index shown')
    if 'curImage = index;' not in set_index or 'self.curDCM = [dcmPixList objectAtIndex:curImage];' not in set_index:
        failures.append('setIndex: no longer shows the pix at the requested index')

if 'if( self.curDCM.missingPixelsReason.length)' not in view or 'DrawNSStringGL: self.curDCM.missingPixelsReason' not in view:
    failures.append('DCMView does not draw the missing-pixels reason over the frame')

DRIVER = r'''
import Foundation
func expect(_ ok: Bool, _ reason: String) { if !ok { print("FAIL: " + reason); exit(1) } }
let unreadable = MissingPixelsReason.reasonForUnreadableFrame()
expect(!unreadable.isEmpty, "an unreadable frame has a reason")
expect(unreadable.lowercased().contains("read") || unreadable.lowercased().contains("decod"), "the reason says the frame could not be read: \(unreadable)")
expect(!MissingPixelsReason.reasonForAbsentPixelData().isEmpty, "absent pixel data has a reason")
print("ok: unreadable slices are shown as such and never as the previous image")
'''
if not failures:
    with tempfile.TemporaryDirectory() as tmp:
        driver = Path(tmp) / 'main.swift'
        driver.write_text(DRIVER)
        binary = Path(tmp) / 'driver'
        build = subprocess.run(['xcrun', 'swiftc', str(root / 'Horos/Sources/MissingPixelsReason.swift'), str(driver), '-o', str(binary)],
                               capture_output=True, text=True)
        if build.returncode != 0:
            failures.append('driver did not compile:\n' + build.stderr[-2000:])
        else:
            run = subprocess.run([str(binary)], capture_output=True, text=True)
            if run.returncode != 0:
                failures.append((run.stdout + run.stderr).strip())
            else:
                print(run.stdout.strip())

if failures:
    for failure in failures:
        print('FAIL:', failure)
    raise SystemExit(1)
