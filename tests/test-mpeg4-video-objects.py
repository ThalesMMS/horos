#!/usr/bin/env python3
"""An object whose Pixel Data is a whole video is recognised as one.

Transfer syntaxes 1.2.840.10008.1.2.4.100 and up carry the entire stream in one
encapsulated value rather than one compressed frame per fragment, so asking the
framework for a frame of one hands back the compressed bytes for every index -
and the colour conversion after it then read a compressed stream as though it
were pixels. This checks the three things that decide where such an object goes:
which syntaxes are treated as video, which of them are decoded here, and that
the video SOP classes are listed among the ones the browser will display.
"""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]

# Three video SOP classes exist; only the endoscopic one was listed, so a video
# recorded by a camera or a microscope was in the database and in no window.
syntaxes = (root / 'DCM Framework/DCMAbstractSyntaxUID.m').read_bytes().decode('utf-8')
listed = syntaxes[syntaxes.index('+ (NSArray *)imageSyntaxes'):]
listed = listed[:listed.index('nil];')]
for name in ('VideoEndoscopicImageStorage', 'VideoMicroscopicImageStorage',
             'VideoPhotographicImageStorage'):
    assert name in listed, '%s is not displayable, so its series is not shown' % name

# Both MPEG-2 syntaxes, not just Main Level: the viewer decodes neither, and the
# one that was not recognised reached it instead of the external player.
for source in ('Horos/Sources/DicomFileDCMTKCategory.mm', 'Horos/Sources/DicomDatabase+Scan.mm'):
    text = (root / source).read_bytes().decode('utf-8')
    assert '1.2.840.10008.1.2.4.100' in text and '1.2.840.10008.1.2.4.101' in text, \
        '%s recognises only one of the two MPEG-2 transfer syntaxes' % source

# The fragment decoder must not be asked for a frame of a video, and an object
# whose stream cannot be decoded must say so rather than show whatever came back.
pix = (root / 'Horos/Sources/DCMPix.m').read_bytes().decode('latin1')
assert 'isVideoTransferSyntax' in pix, 'DCMPix does not recognise a video stream'
assert 'if( carriesAVideoStream == NO)\n                pixData = [pixelAttr decodeFrameAtIndex:imageNb];' in pix, \
    'a video stream still reaches the per-fragment decoder'
assert 'reasonForUndecodableVideoStream' in pix and 'reasonForVideoSizeMismatch' in pix, \
    'a stream that cannot be decoded no longer names the reason'
# An empty frame of a colour object is read three bytes per pixel by the RGB
# path below it, and the buffers it passes through are shortened to the length
# of the frame: at two bytes, or unzeroed, the leftover was drawn.
assert 'oImage = calloc( height * width, 3);' in pix, \
    'an empty frame is allocated smaller than the RGB path reads'
assert 'tmpImage = calloc (loop, 4L);' in pix, \
    'the RGB buffer is not zeroed, so a short frame draws uninitialised memory'

source = r'''
import Foundation

// The syntaxes that carry a video rather than frames, and the ones decoded here.
for uid in ["1.2.840.10008.1.2.4.100", "1.2.840.10008.1.2.4.101",
            "1.2.840.10008.1.2.4.102", "1.2.840.10008.1.2.4.103",
            "1.2.840.10008.1.2.4.104", "1.2.840.10008.1.2.4.105",
            "1.2.840.10008.1.2.4.106", "1.2.840.10008.1.2.4.107",
            "1.2.840.10008.1.2.4.108"] {
    precondition(H264StreamDecoder.isVideo(transferSyntax: uid), uid)
}
// H.264, one view. MPEG-2 is another codec, HEVC another parameter-set layout,
// and the stereo syntax carries two views per picture.
for uid in ["1.2.840.10008.1.2.4.102", "1.2.840.10008.1.2.4.103",
            "1.2.840.10008.1.2.4.104", "1.2.840.10008.1.2.4.105"] {
    precondition(H264StreamDecoder.handles(transferSyntax: uid), uid)
}
for uid in ["1.2.840.10008.1.2.4.100", "1.2.840.10008.1.2.4.101",
            "1.2.840.10008.1.2.4.106", "1.2.840.10008.1.2.4.107",
            "1.2.840.10008.1.2.4.108"] {
    precondition(!H264StreamDecoder.handles(transferSyntax: uid), uid)
}
// The syntaxes that are frames, and nothing at all.
for uid in ["1.2.840.10008.1.2.1", "1.2.840.10008.1.2.4.70", "1.2.840.10008.1.2.4.80",
            "1.2.840.10008.1.2.4.90", "1.2.840.10008.1.2.5", "1.2.840.10008.1.2.4.1000"] {
    precondition(!H264StreamDecoder.isVideo(transferSyntax: uid), uid)
}
precondition(!H264StreamDecoder.isVideo(transferSyntax: nil))
precondition(!H264StreamDecoder.isVideo(transferSyntax: ""))
// A UID read off the wire keeps its padding to an even length.
precondition(H264StreamDecoder.handles(transferSyntax: "1.2.840.10008.1.2.4.102\0"))
precondition(H264StreamDecoder.handles(transferSyntax: " 1.2.840.10008.1.2.4.102 "))

// Bytes that are not an H.264 stream are refused rather than decoded to noise.
precondition(H264StreamDecoder(annexBStream: Data()) == nil)
precondition(H264StreamDecoder(annexBStream: Data(repeating: 0, count: 4096)) == nil)
precondition(H264StreamDecoder(annexBStream: Data("not a stream".utf8)) == nil)
// A start code and a slice, but no parameter sets: nothing says the frame size.
precondition(H264StreamDecoder(annexBStream: Data([0, 0, 0, 1, 0x65, 0x88, 0x84])) == nil)

print("PASS: the video transfer syntaxes are named, only H.264 is claimed, and bytes that are not a stream are refused")
'''
with tempfile.TemporaryDirectory(prefix='horos-mpeg4-syntaxes-') as tmp:
    p = Path(tmp)
    (p / 'main.swift').write_text(source)
    subprocess.run(['xcrun', 'swiftc',
                    str(root / 'Horos/Sources/H264StreamDecoder.swift'),
                    str(root / 'Horos/Sources/H264PictureOrder.swift'),
                    str(p / 'main.swift'), '-o', str(p / 'test')], check=True)
    subprocess.run([str(p / 'test')], check=True)
