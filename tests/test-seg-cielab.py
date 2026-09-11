#!/usr/bin/env python3
"""Compare real SEG color bytes/display values with independent LittleCMS D50 PCS."""
from pathlib import Path
import argparse
import ctypes as c
import ctypes.util
import json
import math
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--baseline')
args = parser.parse_args()
library = ctypes.util.find_library('lcms2')
if not library:
    library = next((str(p) for p in (Path('/opt/homebrew/lib/liblcms2.dylib'),
                                   Path('/usr/local/lib/liblcms2.dylib')) if p.is_file()), None)
if not library:
    print('needs LittleCMS 2 shared library for an independent ICC color reference')
    raise SystemExit(2)
lcms = c.CDLL(library)
lcms.cmsCreate_sRGBProfile.restype = c.c_void_p
lcms.cmsCreateLab4Profile.argtypes = [c.c_void_p]
lcms.cmsCreateLab4Profile.restype = c.c_void_p
lcms.cmsCreateTransform.argtypes = [c.c_void_p,c.c_uint,c.c_void_p,c.c_uint,c.c_uint,c.c_uint]
lcms.cmsCreateTransform.restype = c.c_void_p
lcms.cmsDoTransform.argtypes = [c.c_void_p,c.c_void_p,c.c_void_p,c.c_uint]
lcms.cmsDeleteTransform.argtypes = [c.c_void_p]
lcms.cmsCloseProfile.argtypes = [c.c_void_p]
srgb = lcms.cmsCreate_sRGBProfile()
lab = lcms.cmsCreateLab4Profile(None)  # ICC PCS D50.
# lcms2.h: FLOAT_SH(1)|COLORSPACE_SH(PT_RGB/PT_Lab)|CHANNELS_SH(3)|BYTES_SH(0).
transform = lcms.cmsCreateTransform(srgb,(1<<22)|(4<<16)|(3<<3),
                                     lab,(1<<22)|(10<<16)|(3<<3),1,0)
assert transform

def reference(rgb):
    source, result = (c.c_double*3)(*rgb), (c.c_double*3)()
    lcms.cmsDoTransform(transform,source,result,1)
    return tuple(result)

def pcs(values):
    return [round(max(0,min(65535,v))) for v in
            (values[0]*65535/100,(values[1]+128)*65535/255,(values[2]+128)*65535/255)]

def unpack(values):
    return values[0]*100/65535, values[1]*255/65535-128, values[2]*255/65535-128

# Fixed before conversion: engine/profile differences may reach one DeltaE76;
# a same-profile sRGB round trip must remain within one 8-bit channel step.
delta_e_limit = 1.0
rgb_roundtrip_limit = 1/255
known = [((0,0,0),(0,0,0)), ((1,1,1),(100,0,0)),
         ((1,0,0),(54.28963304,80.81435990,69.88974851)),
         ((0,1,0),(87.81940937,-79.27494477,80.99272233)),
         ((0,0,1),(29.56593931,68.28620416,-112.03291669))]
for rgb, expected in known:
    assert math.dist(reference(rgb),expected) < 0.0001, 'independent D50 reference drifted'
colors = list(dict.fromkeys([rgb for rgb,_ in known] +
    [(r,g,b) for r in (0,0.5,1) for g in (0,0.5,1) for b in (0,0.5,1)] +
    [(x,x,x) for x in (0.01,0.1,0.25,0.75,0.9)] + [(0.1,0.4,0.8)]))
cases = [{'rgb':rgb,'pcs':pcs(reference(rgb))} for rgb in colors]
driver = r'''
import Foundation
func document(_ rgb: [Double]) -> DicomSEGDocument {
    let g = DicomSEGGeometry(rows:1,columns:1,frames:1,spacingRow:1,spacingCol:1,sliceThickness:1,
        origin:[0,0,0],orientation:[1,0,0,0,1,0],frameOfReferenceUID:"1.2.3.4",frameOrigins:[[0,0,0]])
    let segment = DicomSEGSegment(number:1,label:"Color",trackingUID:"1.2.3.7",color:(rgb[0],rgb[1],rgb[2]),
        visible:true,kind:.binary,algorithm:"MANUAL",provenance:"synthetic",referencedSOPInstanceUIDs:["1.2.3.9"],
        frames:[Data([1])],maximumFractionalValue:1)
    return DicomSEGDocument(identity:DicomSEGIdentity(sopInstanceUID:"1.2.3.5",seriesInstanceUID:"1.2.3.6",
        studyInstanceUID:"1.2.3",frameOfReferenceUID:"1.2.3.4",sourceSOPInstanceUIDs:["1.2.3.9"]),
        geometry:g,kind:.binary,segments:[segment],diagnoses:[],sourceBytes:nil)
}
let cases = try JSONSerialization.jsonObject(with:Data(contentsOf:URL(fileURLWithPath:CommandLine.arguments[1]))) as! [[String:[Double]]]
let checkPreservation = CHECK_PRESERVATION
var results: [[String:Any]] = []
for test in cases {
    let encoded = try DicomSEGCodec.encode(document(test["rgb"]!))
    let decoded = DicomSEGCodec.decode(encoded)
    precondition(decoded.diagnoses.isEmpty)
    let rgb = decoded.segments[0].color
    let values = DicomBinary.usArray(DicomBinary.sequence(DicomBinary.parse(encoded),0x0062,0x0002)[0],0x0062,0x000D)
    // Replace the wire element with PCS calculated by LittleCMS, not by this codec.
    var external = encoded
    let tag = Data([0x62,0,0x0d,0,0x55,0x53,6,0])
    let at = external.range(of:tag)!.upperBound
    for (index,value) in test["pcs"]!.enumerated() {
        let bits = UInt16(value); external[at+index*2] = UInt8(bits & 255); external[at+index*2+1] = UInt8(bits >> 8)
    }
    let imported = DicomSEGCodec.decode(external)
    precondition(imported.diagnoses.isEmpty)
    let color = imported.segments[0].color
    if checkPreservation {
        let store = DicomSEGStore(document:imported)
        let originalPCS = test["pcs"]!.map { UInt16($0) }
        func value(_ data: Data) -> [UInt16] {
            DicomBinary.usArray(DicomBinary.sequence(DicomBinary.parse(data),0x0062,0x0002)[0],0x0062,0x000D)
        }
        let unedited = try value(store.exportDerived())
        precondition(unedited == originalPCS, "unedited imported PCS changed on derived export")
        store.setColor((0.37,0.12,0.83),segment:1)
        let edited = try value(store.exportDerived())
        precondition(edited != originalPCS, "color edit retained stale original PCS")
        precondition(store.undo(), "color edit was not recorded")
        let undone = try value(store.exportDerived())
        precondition(undone == originalPCS, "undo failed to restore original PCS")
    }
    results.append(["pcs":values,"roundtrip":[rgb.r,rgb.g,rgb.b],"external":[color.r,color.g,color.b]])
}
// PCS may describe colors outside the sRGB display gamut. Preserve those bytes
// on unedited export instead of permanently exporting the clipped display color.
if checkPreservation {
    var outOfGamut = try DicomSEGCodec.encode(document([1,0,0]))
    let at = outOfGamut.range(of:Data([0x62,0,0x0d,0,0x55,0x53,6,0]))!.upperBound
    for index in 0..<6 { outOfGamut[at+index] = 255 }
    let retained = try DicomSEGStore(document:DicomSEGCodec.decode(outOfGamut)).exportDerived()
    precondition(DicomBinary.usArray(DicomBinary.sequence(DicomBinary.parse(retained),0x0062,0x0002)[0],0x0062,0x000D)
        == [65535,65535,65535], "out-of-gamut source PCS changed")
}
let json = try JSONSerialization.data(withJSONObject:results)
FileHandle.standardOutput.write(json)
'''.replace('CHECK_PRESERVATION', 'false' if args.baseline else 'true')
try:
    with tempfile.TemporaryDirectory(prefix='horos-seg-color-') as folder:
        tmp = Path(folder)
        source = 'Horos/Sources/DicomSEG.swift'
        (tmp/'DicomSEG.swift').write_bytes(subprocess.check_output(['git','show',f'{args.baseline}:{source}'],cwd=root)
            if args.baseline else (root/source).read_bytes())
        (tmp/'main.swift').write_text(driver)
        (tmp/'cases.json').write_text(json.dumps(cases))
        subprocess.run(['xcrun','swiftc',str(tmp/'DicomSEG.swift'),str(tmp/'main.swift'),'-o',str(tmp/'probe')],check=True)
        results = json.loads(subprocess.check_output([str(tmp/'probe'),str(tmp/'cases.json')]))
    worst_encode = worst_decode = worst_roundtrip = 0
    for case,result in zip(cases,results):
        if case['rgb'] in ((0,0,0),(1,1,1)):
            assert result['pcs'] == pcs(reference(case['rgb'])), 'black/white PCS must have neutral a,b = 0x8080'
        encode_error = math.dist(unpack(result['pcs']),reference(case['rgb']))
        decode_error = math.dist(reference(result['external']),unpack(case['pcs']))
        roundtrip_error = max(abs(a-b) for a,b in zip(case['rgb'],result['roundtrip']))
        assert encode_error <= delta_e_limit, (case,'encoded PCS DeltaE76',encode_error)
        assert decode_error <= delta_e_limit, (case,'decoded external PCS DeltaE76',decode_error)
        assert roundtrip_error <= rgb_roundtrip_limit, (case,'sRGB roundtrip',roundtrip_error)
        worst_encode = max(worst_encode,encode_error)
        worst_decode = max(worst_decode,decode_error)
        worst_roundtrip = max(worst_roundtrip,roundtrip_error)
    print(f'PASS: {len(cases)} colors; LittleCMS D50 encode/decode DeltaE76 {worst_encode:.6f}/{worst_decode:.6f}; sRGB roundtrip {worst_roundtrip:.6f}')
finally:
    lcms.cmsDeleteTransform(transform); lcms.cmsCloseProfile(lab); lcms.cmsCloseProfile(srgb)
