#!/usr/bin/env python3
"""Native identity reader must stay within each defined-length DICOM container."""
import argparse
import json
from pathlib import Path
import struct
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--baseline')
args = parser.parse_args()


def element(tag, vr, value, endian='<', implicit=False, undefined=False):
    if len(value) % 2:
        value += b'\0' if vr == 'UI' else b' '
    length = 0xffffffff if undefined else len(value)
    head = struct.pack(endian + 'HH', *tag)
    if implicit:
        head += struct.pack(endian + 'I', length)
    elif vr in ('SQ', 'UT', 'OB'):
        head += vr.encode() + b'\0\0' + struct.pack(endian + 'I', length)
    else:
        head += vr.encode() + struct.pack(endian + 'H', length)
    return head + value


def item(value, endian='<', undefined=False):
    result = struct.pack(endian + 'HHI', 0xfffe, 0xe000,
                         0xffffffff if undefined else len(value)) + value
    return result + (struct.pack(endian + 'HHI', 0xfffe, 0xe00d, 0) if undefined else b'')


def fixture(endian='<', implicit=False, undefined_sequence=False, undefined_item=False, count=1):
    def el(tag, vr, value, **kw):
        return element(tag, vr, value, endian, implicit, **kw)
    refs = [f'2.25.{200 + n}' for n in range(count)]
    value = b''.join(item(el((8, 0x1155), 'UI', uid.encode()), endian, undefined_item) for uid in refs)
    sequence = el((8, 0x1110), 'SQ', value, undefined=undefined_sequence)
    if undefined_sequence:
        sequence += struct.pack(endian + 'HHI', 0xfffe, 0xe0dd, 0)
    syntax = '1.2.840.10008.1.2' if implicit else ('1.2.840.10008.1.2.2' if endian == '>' else '1.2.840.10008.1.2.1')
    data = b'\0' * 128 + b'DICM' + element((2, 0x10), 'UI', syntax.encode())
    data += el((8, 0x16), 'UI', b'1.2.840.10008.5.1.4.1.1.88.11') + sequence
    # These tags are outside both the item and sequence, so they must not
    # become referenced StudyInstanceUIDs when a child reader reaches its end.
    data += el((8, 0x1155), 'UI', b'2.25.9000')
    data += el((0x20, 0x0d), 'UI', b'2.25.100')
    return data, refs


driver = '''
import Foundation
for path in CommandLine.arguments.dropFirst() {
    guard let result = CloudReportAssociation.identity(fromFileAtPath: path) else { exit(1) }
    let data = try JSONSerialization.data(withJSONObject: result, options: [.sortedKeys])
    print(String(data: data, encoding: .utf8)!)
}
'''
with tempfile.TemporaryDirectory(prefix='horos-cloud-sequence-') as directory:
    out = Path(directory)
    (out / 'main.swift').write_text(driver)
    source = root / 'Horos/Sources/CloudReportAssociation.swift'
    if args.baseline:
        source = out / 'CloudReportAssociation.swift'
        source.write_bytes(subprocess.check_output(['git', 'show',
            args.baseline + ':Horos/Sources/CloudReportAssociation.swift'], cwd=root))
    subprocess.run(['xcrun', 'swiftc', str(source), str(out / 'main.swift'),
                    '-o', str(out / 'probe')], check=True)
    cases = [dict(), dict(endian='>'), dict(implicit=True),
             dict(undefined_sequence=True), dict(undefined_item=True),
             dict(undefined_sequence=True, undefined_item=True), dict(count=512)]
    for index, options in enumerate(cases):
        data, refs = fixture(**options)
        path = out / f'case-{index}.dcm'
        path.write_bytes(data)
        try:
            run = subprocess.run([str(out / 'probe'), str(path)], check=True,
                                 text=True, capture_output=True, timeout=3)
        except subprocess.TimeoutExpired as exc:
            raise AssertionError('reader revisits siblings instead of making bounded progress') from exc
        identity = json.loads(run.stdout)
        assert identity['studyID'] == '2.25.100', identity
        assert set(identity.get('referencedStudyUIDs', [])) == set(refs), (
            'defined container leaked top-level tags into referenced studies', identity)
        assert identity['referencedSOPInstanceUIDs'] == ['2.25.9000'], identity
print('PASS: 7 native cases; LE/BE/implicit, defined/undefined scopes and 512 sibling items')
