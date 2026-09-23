#!/usr/bin/env python3
"""An image file wrapped in Pixel Data under a private transfer syntax is DICOM and is drawn (#687).

VTServer stores scanned documents as a single-page CCITT Group 4 TIFF encapsulated
under 1.2.276.0.19.1.2.55.3. GDCM's scanner refused such a file, so the import said
it was not DICOM; no DICOM codec decodes it. The fixture is such an object with a
synthetic page written by ImageIO. The incoming triage must let its 1-bit object
through. Only a private syntax qualifies, the file inside has to have the object's
size, and fragments that are not an image file draw nothing.
"""
from pathlib import Path
import struct
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
PRIVATE = '1.2.276.0.19.1.2.55.3'

writer = r'''
import Foundation
import ImageIO
import CoreGraphics
let (w, h, row) = (96, 64, 12)
var bytes = [UInt8](repeating: 255, count: row * h)
for y in 16..<48 { for x in 24..<72 { bytes[y * row + x / 8] &= ~UInt8(0x80 >> (x % 8)) } }
let image = CGImage(width: w, height: h, bitsPerComponent: 1, bitsPerPixel: 1, bytesPerRow: row,
                    space: CGColorSpaceCreateDeviceGray(), bitmapInfo: CGBitmapInfo(rawValue: 0),
                    provider: CGDataProvider(data: Data(bytes) as CFData)!, decode: nil,
                    shouldInterpolate: false, intent: .defaultIntent)!
let destination = CGImageDestinationCreateWithURL(URL(fileURLWithPath: CommandLine.arguments[1]) as CFURL,
                                                  "public.tiff" as CFString, 1, nil)!
CGImageDestinationAddImage(destination, image, [kCGImagePropertyTIFFDictionary: [kCGImagePropertyTIFFCompression: 4]] as CFDictionary)
precondition(CGImageDestinationFinalize(destination))
'''


def element(tag, vr, value, length=None):
    length = len(value) if length is None else length
    header = struct.pack('<HH', *tag)
    if vr in ('OB', 'OW', 'SQ', 'UN', 'UT'):
        return header + vr.encode() + b'\0\0' + struct.pack('<I', length) + value
    return header + vr.encode() + struct.pack('<H', length) + value


def text(value):
    value = value.encode()
    return value + b'\0' * (len(value) % 2)


def wrapped(syntax, page, rows=64, columns=96, series=True):
    data = b'\0' * 128 + b'DICM' + element((2, 0x10), 'UI', text(syntax))
    data += element((8, 0x16), 'UI', text('1.2.840.10008.5.1.4.1.1.7'))
    data += element((8, 0x18), 'UI', text('2.25.687101'))
    data += element((0x20, 0x0D), 'UI', text('2.25.687102'))
    if series:
        data += element((0x20, 0x0E), 'UI', text('2.25.687103'))
    for tag, value in [(2, 1), (0x10, rows), (0x11, columns), (0x100, 1), (0x101, 1)]:
        data += element((0x28, tag), 'US', struct.pack('<H', value))
    page += b'\0' * (len(page) % 2)
    items = struct.pack('<HHI', 0xFFFE, 0xE000, 0) + struct.pack('<HHI', 0xFFFE, 0xE000, len(page)) + page
    items += struct.pack('<HHI', 0xFFFE, 0xE0DD, 0)
    return data + element((0x7FE0, 0x10), 'OB', items, length=0xFFFFFFFF)


main = r'''
import Foundation
import CoreGraphics
let directory = CommandLine.arguments[1]
func file(_ name: String) -> String { directory + "/" + name }
precondition(WrappedImageFragments.isPrivateTransferSyntax("1.2.276.0.19.1.2.55.3"))
precondition(!WrappedImageFragments.isPrivateTransferSyntax("1.2.840.10008.1.2.4.50"))
precondition(!WrappedImageFragments.isPrivateTransferSyntax(nil) && !WrappedImageFragments.isPrivateTransferSyntax(" "))
precondition(WrappedImageFragments.isDICOMFileWithPrivateTransferSyntax(atPath: file("private")),
             "a wrapped TIFF under a private syntax is not recognised as DICOM")
for name in ["standard", "no-series", "not-dicom"] {
    precondition(!WrappedImageFragments.isDICOMFileWithPrivateTransferSyntax(atPath: file(name)), "\(name) accepted")
}
let page = try Data(contentsOf: URL(fileURLWithPath: file("page.tif")))
let offsetTable = Data()
guard let image = WrappedImageFragments.cgImage(fromFragments: [offsetTable, page], width: 96, height: 64) else {
    preconditionFailure("the wrapped TIFF was not decoded")
}
// The black rectangle is where it was drawn, and white is around it.
let context = CGContext(data: nil, width: 96, height: 64, bitsPerComponent: 8, bytesPerRow: 96,
                        space: CGColorSpaceCreateDeviceGray(), bitmapInfo: 0)!
context.draw(image, in: CGRect(x: 0, y: 0, width: 96, height: 64))
let gray = context.data!.assumingMemoryBound(to: UInt8.self)
precondition(gray[32 * 96 + 48] < 64 && gray[2 * 96 + 2] > 192, "the page decoded to the wrong content")
// Split over two fragments, as a file larger than a fragment would be.
let half = page.count / 2
precondition(WrappedImageFragments.cgImage(fromFragments: [offsetTable, page.prefix(half), page.suffix(from: half)],
                                           width: 96, height: 64) != nil, "a page split over fragments was not decoded")
precondition(WrappedImageFragments.cgImage(fromFragments: [offsetTable, page], width: 64, height: 96) == nil,
             "a page of another size than the object's was drawn")
precondition(WrappedImageFragments.cgImage(fromFragments: [offsetTable, Data(repeating: 0x5A, count: 256)],
                                           width: 96, height: 64) == nil, "fragments that are not an image file were drawn")
precondition(WrappedImageFragments.cgImage(fromFragments: [page], width: 96, height: 64) == nil,
             "the Basic Offset Table was read as the image")
// The incoming triage takes it whatever BitsAllocated says; under a standard syntax a
// 1-bit object is still refused, and so is a wrapped page of another size.
precondition(EnhancedImportTriage.assessPath(file("private")).mayMergeIntoIncoming, "the incoming triage refused the wrapped TIFF")
let standard = EnhancedImportTriage.assessPath(file("standard"))
precondition(!standard.mayMergeIntoIncoming && standard.recordedError?.contains("BitsAllocated") == true,
             "a 1-bit object under a standard syntax was let through")
precondition(!EnhancedImportTriage.assessPath(file("private-other-size")).mayMergeIntoIncoming,
             "a wrapped page of another size than the object's was let through")
print("PASS: a TIFF wrapped under a private transfer syntax is DICOM, passes the incoming triage and decodes at the object's size; standard syntaxes, other sizes and non-images are not")
'''

with tempfile.TemporaryDirectory(prefix='horos-wrapped-image-') as directory:
    p = Path(directory)
    (p/'writer.swift').write_text(writer)
    subprocess.run(['xcrun', 'swift', str(p/'writer.swift'), str(p/'page.tif')], check=True)
    page = (p/'page.tif').read_bytes()
    (p/'private').write_bytes(wrapped(PRIVATE, page))
    (p/'standard').write_bytes(wrapped('1.2.840.10008.1.2.4.50', page))
    (p/'no-series').write_bytes(wrapped(PRIVATE, page, series=False))
    (p/'private-other-size').write_bytes(wrapped(PRIVATE, page, rows=96, columns=64))
    (p/'not-dicom').write_bytes(page)
    (p/'main.swift').write_text(main)
    sources = [root/'Horos/Sources'/name for name in ['DICOMTriageMetadata.swift', 'WrappedImageFragments.swift', 'EnhancedImportTriage.swift']]
    subprocess.run(['xcrun', 'swiftc', *map(str, sources), str(p/'main.swift'), '-o', str(p/'check')], check=True)
    subprocess.run([str(p/'check'), str(p)], check=True)


def between(source, start, end):
    begin = source.find(start)
    return source[begin:source.find(end, begin)] if begin != -1 else ''


dicom_file = (root/'Horos/Sources/DicomFile.mm').read_text(encoding='utf-8', errors='replace')
scan = between(dicom_file, '+ (BOOL) isDICOMFile:(NSString *) filePath compressed:(BOOL*) compressed image:(BOOL*) image',
               'theScanner.AddTag(gdcm::Tag(0x7FE0, 0x0010))')
assert scan.count('isDICOMFileWithPrivateTransferSyntax:') == 2, \
    'both ways the GDCM scan fails must fall back to the private transfer syntax check'
fallback = between(dicom_file, '+ (BOOL) isDICOMFileWithPrivateTransferSyntax:', '+ (BOOL) isDICOMFile:')
assert '*image = NO' in fallback and '*compressed = NO' in fallback, \
    'a file no codec can transcode must stay out of the incoming compression queue'

pix = (root/'Horos/Sources/DCMPix.m').read_text(encoding='latin-1')
branch = pix.find('else if ([self loadImageFileWrappedInPixelDataOf: dcmObject])')
assert branch != -1 and pix.rfind('#ifndef DECOMPRESS_APP', 0, branch) > pix.rfind('#endif', 0, branch), \
    'DCMPix must try the wrapped image file outside the Decompress helper'
assert branch < pix.find('[SOPClassUID hasPrefix: @"1.2.840.10008.5.1.4.1.1.88"]', branch - 2000), \
    'the wrapped image file must be tried before the SR and non-image branches'
print('PASS: GDCM refusals fall back to the private syntax check, and DCMPix draws the wrapped file')
