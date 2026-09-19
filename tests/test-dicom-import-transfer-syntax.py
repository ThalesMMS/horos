#!/usr/bin/env python3
"""Incoming gates agree on native byte order/VR, SR and embedded icons."""
from pathlib import Path
import struct
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]

def element(tag, vr, value, order='<', implicit=False):
    header = struct.pack(order + 'HH', *tag)
    if implicit:
        return header + struct.pack(order + 'I', len(value)) + value
    if vr in ('OB', 'OW', 'SQ', 'UN', 'UT'):
        return header + vr.encode() + b'\0\0' + struct.pack(order + 'I', len(value)) + value
    return header + vr.encode() + struct.pack(order + 'H', len(value)) + value

def fixture(syntax, sop='1.2.840.10008.5.1.4.1.1.2', image=True, frame_count=None, private=b''):
    implicit = syntax == '1.2.840.10008.1.2'
    order = '>' if syntax.endswith('.2.2') else '<'
    def entry(tag, vr, value):
        if isinstance(value, int):
            value = struct.pack(order + 'H', value)
        elif isinstance(value, str):
            value = value.encode(); value += b'\0' * (len(value) % 2)
        return element(tag, vr, value, order, implicit)
    uid = syntax.encode(); uid += b'\0' * (len(uid) % 2)
    data = b'\0' * 128 + b'DICM' + element((2, 0x10), 'UI', uid)
    data += entry((8, 0x16), 'UI', sop)
    data += private
    if frame_count is not None:
        data += entry((0x28, 8), 'IS', str(frame_count))
    if image:
        for tag, value in [(2, 1), (0x10, 7), (0x11, 9), (0x100, 16), (0x101, 12)]:
            data += entry((0x28, tag), 'US', value)
        data += entry((0x7FE0, 0x10), 'OW', b'\0' * 126)
    return data


def item(payload, undefined=False, order='<'):
    return (struct.pack(order + 'HHI', 0xFFFE, 0xE000, 0xFFFFFFFF if undefined else len(payload))
            + payload + (struct.pack(order + 'HHI', 0xFFFE, 0xE00D, 0) if undefined else b''))


def unknown_sequence(syntax, undefined_item=False, nesting=0):
    # CP-246: UN's value, including item headers, is Implicit VR Little Endian
    # even when the enclosing dataset is Explicit VR Big Endian.
    payload = element((0x11, 0x10), 'LO', b'SYNTHETIC ', implicit=True)
    # Nested image dimensions must not replace the root's dimensions.
    payload += element((0x28, 0x10), 'US', struct.pack('<H', 1), implicit=True)
    for _ in range(nesting):
        payload = (struct.pack('<HHI', 0x11, 0x1010, 0xFFFFFFFF) + item(payload, True)
                   + struct.pack('<HHI', 0xFFFE, 0xE0DD, 0))
    order = '>' if syntax.endswith('.2.2') else '<'
    return (struct.pack(order + 'HH', 9, 0x105F) + b'UN\0\0' + struct.pack(order + 'I', 0xFFFFFFFF)
            + item(payload, undefined_item) + struct.pack('<HHI', 0xFFFE, 0xE0DD, 0))


main = r'''
import Foundation
let path = CommandLine.arguments[1]
for name in ["implicit", "explicit", "big"] {
    let result = EnhancedImportTriage.assessPath(path + "/" + name)
    precondition(result.rows == 7 && result.columns == 9 && result.bitsAllocated == 16)
    precondition(result.pixelDataBytes == 126 && result.mayMergeIntoIncoming)
    let ultrasound = IVUSImportTriage.assessPath(path + "/us-" + name)
    precondition(ultrasound.rows == 7 && ultrasound.columns == 9 && ultrasound.mayMergeIntoIncoming)
}
let sr = EnhancedImportTriage.assessPath(path + "/sr")
precondition(sr.mayMergeIntoIncoming && sr.rows == 0 && sr.columns == 0)
let huge = EnhancedImportTriage.assessPath(path + "/overflow")
precondition(!huge.mayMergeIntoIncoming && huge.recordedError?.contains("byte count") == true)
let missing = EnhancedImportTriage.assessPath(path + "/missing")
precondition(!missing.mayMergeIntoIncoming)
for name in try FileManager.default.contentsOfDirectory(atPath: path) where name.hasPrefix("un-") || name.hasPrefix("sq-") {
    let result = EnhancedImportTriage.assessPath(path + "/" + name)
    precondition(result.mayMergeIntoIncoming && result.rows == 7 && result.columns == 9,
                 "UN/SQ sequence lost the outer dataset: \(name)")
    precondition(result.pixelDataBytes == 126)
    let ultrasound = IVUSImportTriage.assessPath(path + "/" + name)
    precondition(ultrasound.mayMergeIntoIncoming && ultrasound.rows == 7 && ultrasound.columns == 9)
}
for name in try FileManager.default.contentsOfDirectory(atPath: path) where name.hasPrefix("invalid-un-") {
    let data = try Data(contentsOf: URL(fileURLWithPath: path + "/" + name))
    precondition(DICOMTriageMetadata.parse(data) == nil, "Malformed UN sequence accepted: \(name)")
}
print("PASS: incoming gates accept native transfer syntaxes and CP-246 UN sequences; malformed lengths, delimiters and excessive nesting are refused")
'''
with tempfile.TemporaryDirectory(prefix='horos-import-syntax-') as directory:
    p = Path(directory)
    for name, syntax in [('implicit', '1.2.840.10008.1.2'), ('explicit', '1.2.840.10008.1.2.1'), ('big', '1.2.840.10008.1.2.2')]:
        (p/name).write_bytes(fixture(syntax))
        (p/('us-'+name)).write_bytes(fixture(syntax, '1.2.840.10008.5.1.4.1.1.6.1'))
    (p/'sr').write_bytes(fixture('1.2.840.10008.1.2', '1.2.840.10008.5.1.4.1.1.88.11', image=False))
    (p/'missing').write_bytes(fixture('1.2.840.10008.1.2.1', image=False))
    (p/'overflow').write_bytes(fixture('1.2.840.10008.1.2.1', frame_count=9223372036854775807))
    ultrasound_sop = '1.2.840.10008.5.1.4.1.1.6.1'
    for name, syntax in [('le', '1.2.840.10008.1.2.1'), ('be', '1.2.840.10008.1.2.2')]:
        for undefined in (False, True):
            for nesting in (0, 2):
                private = unknown_sequence(syntax, undefined, nesting)
                (p/f'un-{name}-{undefined}-{nesting}').write_bytes(fixture(syntax, ultrasound_sop, private=private))
        order = '>' if name == 'be' else '<'
        (p/f'un-{name}-opaque').write_bytes(fixture(syntax, ultrasound_sop,
            private=element((9, 0x105F), 'UN', b'opaque value', order)))
        explicit_item = item(element((0x28, 0x10), 'US', struct.pack(order + 'H', 1), order), order=order)
        (p/f'sq-{name}-explicit').write_bytes(fixture(syntax, ultrasound_sop,
            private=element((9, 0x105F), 'SQ', explicit_item, order)))
        valid = unknown_sequence(syntax, True)
        bad_item_length = valid[:16] + struct.pack('<I', len(valid) * 8) + valid[20:]
        bad_item_delimiter = valid[:-12] + struct.pack('<I', 1) + valid[-8:]
        malformed = {'missing-sequence-delimiter': valid[:-8],
                     'missing-item-delimiter': valid[:-16] + valid[-8:],
                     'item-overrun': bad_item_length, 'bad-item-delimiter': bad_item_delimiter,
                     'nesting': unknown_sequence(syntax, True, 17)}
        for case, private in malformed.items():
            (p/f'invalid-un-{name}-{case}').write_bytes(fixture(syntax, ultrasound_sop, private=private))
    (p/'main.swift').write_text(main)
    sources = [root/'Horos/Sources'/name for name in ['DICOMTriageMetadata.swift', 'EnhancedImportTriage.swift', 'IVUSImportTriage.swift']]
    subprocess.run(['xcrun', 'swiftc', *map(str, sources), str(p/'main.swift'), '-o', str(p/'check')], check=True)
    subprocess.run([str(p/'check'), str(p)], check=True)
