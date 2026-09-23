#!/usr/bin/env python3
"""A DICOM file with unparseable bytes after its Pixel Data is imported without them (#687).

The fixtures reproduce two files an OsiriX server held and could not send: an
Explicit VR CT with an icon whose Pixel Data is followed by zeros and a stray
element, and an Implicit VR MR followed by zeros and part of another file. Only
the bytes after a complete Pixel Data are left out; a truncated image, open
fragments, a file without Pixel Data and a healthy file are not touched.
"""
from pathlib import Path
import struct
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
EXPLICIT, IMPLICIT = '1.2.840.10008.1.2.1', '1.2.840.10008.1.2'
LONG = ('OB', 'OW', 'SQ', 'UN', 'UT')


def element(tag, vr, value, implicit=False, length=None):
    length = len(value) if length is None else length
    header = struct.pack('<HH', *tag)
    if implicit:
        return header + struct.pack('<I', length) + value
    if vr in LONG:
        return header + vr.encode() + b'\0\0' + struct.pack('<I', length) + value
    return header + vr.encode() + struct.pack('<H', length) + value


def text(value):
    value = value.encode()
    return value + b'\0' * (len(value) % 2)


def fixture(syntax, pixel_data, extra=b''):
    implicit = syntax == IMPLICIT
    meta = element((2, 0x10), 'UI', text(syntax))
    data = b'\0' * 128 + b'DICM' + meta
    for tag, vr, value in [((8, 0x16), 'UI', text('1.2.840.10008.5.1.4.1.1.2')),
                           ((8, 0x18), 'UI', text('2.25.687001')),
                           ((0x20, 0x0D), 'UI', text('2.25.687002')),
                           ((0x20, 0x0E), 'UI', text('2.25.687003'))]:
        data += element(tag, vr, value, implicit)
    data += extra
    for tag, value in [(2, 1), (0x10, 4), (0x11, 4), (0x100, 16), (0x101, 12)]:
        data += element((0x28, tag), 'US', struct.pack('<H', value), implicit)
    return data + pixel_data


def icon():
    # Icon Image Sequence, undefined length, whose item carries its own Pixel Data.
    payload = element((0x28, 0x10), 'US', struct.pack('<H', 2)) + element((0x7FE0, 0x10), 'OB', b'\x7f' * 4)
    return (struct.pack('<HH', 0x88, 0x200) + b'SQ\0\0' + struct.pack('<I', 0xFFFFFFFF)
            + struct.pack('<HHI', 0xFFFE, 0xE000, 0xFFFFFFFF) + payload + struct.pack('<HHI', 0xFFFE, 0xE00D, 0)
            + struct.pack('<HHI', 0xFFFE, 0xE0DD, 0))


pixels = bytes(range(32))
native_explicit = element((0x7FE0, 0x10), 'OW', pixels)
native_implicit = element((0x7FE0, 0x10), 'OW', pixels, implicit=True)
fragments = (struct.pack('<HHI', 0xFFFE, 0xE000, 0) + struct.pack('<HHI', 0xFFFE, 0xE000, 4) + b'\xff\xd8\xff\xd9'
             + struct.pack('<HHI', 0xFFFE, 0xE0DD, 0))
encapsulated = struct.pack('<HH', 0x7FE0, 0x10) + b'OB\0\0' + struct.pack('<I', 0xFFFFFFFF) + fragments
zeros = b'\0' * 64

cases = {
    # name: (bytes, bytes left out or None when the file is not repaired)
    'ct-icon-trailing-zeros': (fixture(EXPLICIT, native_explicit, icon())
                               + zeros + struct.pack('<HHI', 0, 0x3B00, 58115) + b'\x11' * 40, 64 + 8 + 40),
    'mr-implicit-foreign-bytes': (fixture(IMPLICIT, native_implicit)
                                  + zeros + struct.pack('<HHI', 0x6D00, 0x6800, 1711302656) + 'mhxx'.encode('utf-16-le'),
                                  64 + 8 + 8),
    'encapsulated-trailing': (fixture(EXPLICIT, encapsulated) + zeros, 64),
    'healthy': (fixture(EXPLICIT, native_explicit, icon()), None),
    'truncated-pixel-data': (fixture(EXPLICIT, element((0x7FE0, 0x10), 'OW', pixels, length=4096)), None),
    'open-fragments': (fixture(EXPLICIT, encapsulated[:-8]) + b'\x11' * 7, None),
    'no-pixel-data': (fixture(EXPLICIT, b'') + zeros, None),
}

main = r'''
import Foundation
let directory = CommandLine.arguments[1]
let expectations = CommandLine.arguments.dropFirst(2).map { $0.split(separator: "=").map(String.init) }
for pair in expectations {
    let name = pair[0], dropped = Int64(pair[1])!
    let source = directory + "/" + name, copy = directory + "/" + name + ".intact"
    let before = try Data(contentsOf: URL(fileURLWithPath: source))
    let length = DICOMTrailingDataRepair.intactLength(ofFileAt: source)
    let written = DICOMTrailingDataRepair.writeIntactCopy(ofFileAt: source, to: copy)
    precondition(written == dropped, "\(name): left out \(written) bytes, expected \(dropped)")
    let after = try Data(contentsOf: URL(fileURLWithPath: source))
    precondition(after == before, "\(name): the source was modified")
    if dropped < 0 {
        precondition(length == nil && !FileManager.default.fileExists(atPath: copy), "\(name) was repaired")
        continue
    }
    let intact = try Data(contentsOf: URL(fileURLWithPath: copy))
    precondition(length?.intValue == intact.count && intact == before.prefix(intact.count),
                 "\(name): the copy is not the file up to the end of Pixel Data")
    precondition(DICOMTrailingDataRepair.writeIntactCopy(ofFileAt: source, to: copy) == -1,
                 "\(name): an existing copy was overwritten")
}
print("PASS: bytes after a complete Pixel Data are left out of a new copy; truncated, open, pixel-less and healthy files are not repaired")
'''

with tempfile.TemporaryDirectory(prefix='horos-trailing-repair-') as directory:
    p = Path(directory)
    arguments = []
    for name, (data, dropped) in cases.items():
        (p/name).write_bytes(data)
        arguments.append(f'{name}={-1 if dropped is None else dropped}')
    (p/'main.swift').write_text(main)
    sources = [root/'Horos/Sources'/name for name in ['DICOMTriageMetadata.swift', 'DICOMTrailingDataRepair.swift']]
    subprocess.run(['xcrun', 'swiftc', *map(str, sources), str(p/'main.swift'), '-o', str(p/'check')], check=True)
    subprocess.run([str(p/'check'), str(p), *arguments], check=True)

    # DCMTK is what the import reads with: it must refuse the damaged files and
    # read their copies. Skipped when no dcmdump has been built.
    dcmdump = next((d/'DCMTK/dcmdump' for d in [root/'build/Build/Products/Debug', root/'build/Build/Products/Release']
                    if (d/'DCMTK/dcmdump').is_file()), None)
    if dcmdump:
        read = lambda path: subprocess.run([str(dcmdump), str(path)], capture_output=True).returncode == 0
        for name, (_, dropped) in cases.items():
            if dropped is not None:
                assert not read(p/name), f'DCMTK reads the damaged {name}; the fixture does not reproduce the fault'
                assert read(p/(name + '.intact')), f'DCMTK cannot read the repaired copy of {name}'
        print('PASS: DCMTK refuses each damaged fixture and reads its repaired copy')
    else:
        print('NOTE: no dcmdump in build/; DCMTK cross-check not run')

source = (root/'Horos/Sources/DicomDatabase.mm').read_text(encoding='utf-8', errors='replace')
repair = source.find('writeIntactCopyOfFileAtPath:')
refusal = source.find('[refusals refuse: newFile];', repair)
assert repair != -1 and refusal != -1 and source.rfind('curFile = [[DicomFile alloc] init:newFile];', 0, repair) != -1, \
    'the import no longer tries the intact copy before refusing an unreadable file'
assert '[newFile hasPrefix: dataDirPath]' in source[repair:refusal], \
    'a file imported in place must not be deleted after its intact copy is indexed'
print('PASS: the import indexes the intact copy before it refuses an unreadable file')
