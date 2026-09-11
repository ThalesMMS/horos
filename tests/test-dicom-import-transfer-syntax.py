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
    if vr in ('OB', 'OW', 'SQ', 'UT'):
        return header + vr.encode() + b'\0\0' + struct.pack(order + 'I', len(value)) + value
    return header + vr.encode() + struct.pack(order + 'H', len(value)) + value

def fixture(syntax, sop='1.2.840.10008.5.1.4.1.1.2', image=True, frame_count=None):
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
    if frame_count is not None:
        data += entry((0x28, 8), 'IS', str(frame_count))
    if image:
        for tag, value in [(2, 1), (0x10, 7), (0x11, 9), (0x100, 16), (0x101, 12)]:
            data += entry((0x28, tag), 'US', value)
        data += entry((0x7FE0, 0x10), 'OW', b'\0' * 126)
    return data

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
print("PASS: both incoming gates accept Explicit LE, Implicit LE and Explicit BE; SR persists without invented dimensions")
'''
with tempfile.TemporaryDirectory(prefix='horos-import-syntax-') as directory:
    p = Path(directory)
    for name, syntax in [('implicit', '1.2.840.10008.1.2'), ('explicit', '1.2.840.10008.1.2.1'), ('big', '1.2.840.10008.1.2.2')]:
        (p/name).write_bytes(fixture(syntax))
        (p/('us-'+name)).write_bytes(fixture(syntax, '1.2.840.10008.5.1.4.1.1.6.1'))
    (p/'sr').write_bytes(fixture('1.2.840.10008.1.2', '1.2.840.10008.5.1.4.1.1.88.11', image=False))
    (p/'missing').write_bytes(fixture('1.2.840.10008.1.2.1', image=False))
    (p/'overflow').write_bytes(fixture('1.2.840.10008.1.2.1', frame_count=9223372036854775807))
    (p/'main.swift').write_text(main)
    sources = [root/'Horos/Sources'/name for name in ['DICOMTriageMetadata.swift', 'EnhancedImportTriage.swift', 'IVUSImportTriage.swift']]
    subprocess.run(['xcrun', 'swiftc', *map(str, sources), str(p/'main.swift'), '-o', str(p/'check')], check=True)
    subprocess.run([str(p/'check'), str(p)], check=True)
