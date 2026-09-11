#!/usr/bin/env python3
"""Check SEG bytes independently: Part 10 UL length and unaligned LSB-first frames."""
from pathlib import Path
import argparse
import struct
import subprocess
import tempfile
root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--source', type=Path, default=root/'Horos/Sources/DicomSEG.swift')
args = parser.parse_args()
driver = r'''
import Foundation
let geometry = DicomSEGGeometry(rows:1,columns:3,frames:3,spacingRow:1,spacingCol:1,sliceThickness:1,
    origin:[0,0,0],orientation:[1,0,0,0,1,0],frameOfReferenceUID:"1.2.3.4",frameOrigins:[[0,0,0],[0,0,1],[0,0,2]])
let frames = [Data([1,0,1]),Data([0,1,0]),Data([1,1,0])]
let refs = ["1.2.3.10","1.2.3.11","1.2.3.12"]
let segment = DicomSEGSegment(number:1,label:"Bits",trackingUID:"1.2.3.8",color:(1,0,0),visible:true,
    kind:.binary,algorithm:"MANUAL",provenance:"synthetic",referencedSOPInstanceUIDs:refs,frames:frames,maximumFractionalValue:1)
let identity = DicomSEGIdentity(sopInstanceUID:"1.2.3.5",seriesInstanceUID:"1.2.3.6",studyInstanceUID:"1.2.3",
    frameOfReferenceUID:geometry.frameOfReferenceUID,sourceSOPInstanceUIDs:refs)
let document = DicomSEGDocument(identity:identity,geometry:geometry,kind:.binary,segments:[segment],diagnoses:[],sourceBytes:nil)
if CommandLine.arguments.count == 2 {
    try DicomSEGCodec.encode(document).write(to:URL(fileURLWithPath:CommandLine.arguments[1]))
} else {
    let source = try Data(contentsOf:URL(fileURLWithPath:CommandLine.arguments[1]))
    let decoded = DicomSEGCodec.decode(source)
    if CommandLine.arguments[2] == "invalid" {
        precondition(decoded.diagnoses.contains(.notDICOM), "refuse malformed historical meta instead of changing old mask bits")
    } else {
        precondition(decoded.diagnoses.isEmpty && decoded.segments[0].frames == frames, "decode standard LSB-first frames")
    }
}
'''
with tempfile.TemporaryDirectory(prefix='horos-seg-wire-') as folder:
    tmp = Path(folder); (tmp/'main.swift').write_text(driver)
    subprocess.run(['xcrun','swiftc',str(args.source),str(tmp/'main.swift'),'-o',str(tmp/'test')],check=True)
    file = tmp/'surface.dcm'
    subprocess.run([str(tmp/'test'),str(file)],check=True)
    raw = file.read_bytes()
    assert raw[128:132] == b'DICM'
    offset = 132; elements = {}; failures = []
    while offset + 8 <= len(raw):
        group, element = struct.unpack_from('<HH',raw,offset)
        vr = raw[offset+4:offset+6]
        header = 12 if vr in (b'OB',b'OW',b'OF',b'SQ',b'UT',b'UN',b'UC',b'UR') else 8
        length = struct.unpack_from('<I' if header==12 else '<H',raw,offset+8 if header==12 else offset+6)[0]
        value = raw[offset+header:offset+header+length]
        elements[group,element] = (vr,value,offset,header)
        offset += header + length
    vr, value, _, _ = elements[2,0]
    if vr != b'UL' or len(value) != 4:
        failures.append('File Meta Information Group Length must be one UL with VL=4')
    else:
        meta_end = 144 + struct.unpack('<I',value)[0]
        if struct.unpack_from('<H',raw,meta_end)[0] == 2:
            failures.append('group length does not end at the dataset')
        if elements.get((2,0x10),(None,b''))[1].rstrip(b'\0') != b'1.2.840.10008.1.2.1':
            failures.append('Transfer Syntax UID is not separately readable')
    vr, value, pixel_at, header = elements[0x7fe0,0x10]
    if value != bytes([0xd5,0]):
        failures.append('three 3-bit frames must form D5 00, without per-frame padding or MSB-first order')
    if len(value)%2:
        failures.append('Pixel Data must have even value length')
    if failures:
        raise SystemExit('FAIL: '+'; '.join(failures))
    # Decode an explicitly supplied standard bit stream, independently of packBinary.
    raw = raw[:pixel_at+header] + bytes([0xd5,0]) + raw[pixel_at+header+len(value):]
    file.write_bytes(raw)
    subprocess.run([str(tmp/'test'),str(file),'decode'],check=True)
    meta_size = struct.unpack_from('<I',raw,140)[0]
    historical = raw[:138] + struct.pack('<H',meta_size) + raw[144:]
    file.write_bytes(historical)
    subprocess.run([str(tmp/'test'),str(file),'invalid'],check=True)
print('PASS: interoperable Part 10 meta, continuous LSB-first binary frames, even Pixel Data, standard bytes decoded')
