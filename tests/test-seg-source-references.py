#!/usr/bin/env python3
"""Prove frame-level provenance refusal and multiframe round trips in the real SEG codec."""
from pathlib import Path
import argparse
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--baseline', help='run the original-API refusal case against a Git revision')
args = parser.parse_args()
setup = r'''
import Foundation
func expect(_ ok: Bool, _ reason: String) { if !ok { fatalError(reason) } }
let domain = "org.horos.test.seg-source.\(UUID().uuidString)"
let preferences = UserDefaults(suiteName: domain)!
defer { preferences.removePersistentDomain(forName: domain) }
let registry = VolumeSessionRegistry()
let volume = registry.open(identity: VolumeIdentity(studyInstanceUID:"1.2.3",seriesInstanceUID:"1.2.3.8",
    frameOfReferenceUID:"1.2.3.4",timeIndex:0,generation:0)!,owner:"viewer")!
let refs = ["1.2.3.10", "1.2.3.11"]
let geometry = DicomSEGGeometry(rows:2,columns:2,frames:2,spacingRow:1,spacingCol:1,sliceThickness:2,
    origin:[0,0,0],orientation:[1,0,0,0,1,0],frameOfReferenceUID:"1.2.3.4",frameOrigins:[[0,0,0],[0,0,2]])
let identity = DicomSEGIdentity(sopInstanceUID:"1.2.3.5",seriesInstanceUID:"1.2.3.6",studyInstanceUID:"1.2.3",
    frameOfReferenceUID:"1.2.3.4",sourceSOPInstanceUIDs:refs)
let segment = DicomSEGSegment(number:1,label:"Original",trackingUID:"1.2.3.7",color:(1,0,0),visible:true,
    kind:.binary,algorithm:"MANUAL",provenance:"synthetic",referencedSOPInstanceUIDs:refs,
    frames:[Data([1,1,1,1]),Data([1,1,1,1])],maximumFractionalValue:1)
var document = DicomSEGDocument(identity:identity,geometry:geometry,kind:.binary,segments:[segment],diagnoses:[],sourceBytes:nil)
let session = SEGViewerSession(volume:volume,sourceSOPInstanceUIDs:refs,preferences:preferences)
expect(session.load(try DicomSEGCodec.encode(document)) == nil, "valid classic source")
document.segments[0].label = "Wrong source"
document.segments[0].referencedSOPInstanceUIDs[0] = "9.8.7"
expect(session.load(try DicomSEGCodec.encode(document)) != nil, "per-frame foreign SOP accepted despite valid general list")
expect(session.snapshots[0].label == "Original", "refusal replaced current state")
print("PASS: frame provenance is checked independently of the general reference list")
'''
multiframe = r'''
let enhancedCT = "1.2.840.10008.5.1.4.1.1.2.1"
func reference(_ uid: String, _ frames: [Int]) -> DicomSEGSourceReference {
    DicomSEGSourceReference(sopInstanceUID:uid,sopClassUID:enhancedCT,frameNumbers:frames)
}
document.segments = [segment]
document.segments[0].frameReferences = [[reference(refs[0],[]),reference("9.8.7",[])], [reference(refs[1],[])]]
expect(session.load(try DicomSEGCodec.encode(document)) != nil, "second SourceImage item escaped validation")
let uid = "1.2.3.20"
document.identity.sourceSOPInstanceUIDs = [uid]
document.segments[0].referencedSOPInstanceUIDs = [uid,uid]
document.segments[0].frameReferences = [[reference(uid,[1])], [reference(uid,[2])]]
let partial = SEGViewerSession(volume:volume,sourceFrames:[1,2].map {
    SEGSourceFrame(sopInstanceUID:uid,frameNumber:$0,frameCount:4)!
},preferences:preferences)
expect(partial.load(try DicomSEGCodec.encode(document)) == nil, "matching multiframe timepoint refused")
partial.rename(1,label:"Derived")
let derived = try partial.exportDerived()
let decoded = DicomSEGCodec.decode(derived)
expect(decoded.segments[0].frameReferences == document.segments[0].frameReferences, "derived SEG lost SOP class/frame numbers")
let general = DicomBinary.sequence(DicomBinary.parse(derived),0x0008,0x1115)[0]
expect(DicomBinary.sequence(general,0x0008,0x1140).allSatisfy {
    DicomBinary.string($0,0x0008,0x1150) == enhancedCT
}, "general reference changed the Enhanced CT SOP class")
expect(partial.load(derived) == nil, "derived multiframe SEG cannot reopen")
document.segments[0].frameReferences[0] = [reference(uid,[1,3])]
expect(partial.load(try DicomSEGCodec.encode(document)) != nil, "out-of-timepoint frame accepted")
expect(partial.snapshots[0].label == "Derived", "bad frame import changed prior document")
document.segments[0].frameReferences[0] = [reference(uid,[0])]
expect(DicomSEGCodec.decode(try DicomSEGCodec.encode(document)).diagnoses.contains(.invalidSourceReference), "zero DICOM frame accepted")
document.segments[0].frameReferences = [[reference(uid,[])], [reference(uid,[])]]
expect(partial.load(try DicomSEGCodec.encode(document)) != nil, "whole object accepted in partial timepoint")
let complete = SEGViewerSession(volume:volume,sourceFrames:(1...4).map {
    SEGSourceFrame(sopInstanceUID:uid,frameNumber:$0,frameCount:4)!
},preferences:preferences)
expect(complete.load(try DicomSEGCodec.encode(document)) == nil, "whole object refused with every source frame open")
document.segments[0].frameReferences = [[reference(uid,[1,2])], [reference(uid,[3,4])]]
expect(complete.load(try DicomSEGCodec.encode(document)) == nil, "valid frame list refused")
expect(DicomSEGCodec.decode(try complete.exportDerived()).segments[0].frameReferences == document.segments[0].frameReferences,
    "multi-valued frame list changed")
expect(SEGSourceFrame(sopInstanceUID:uid,frameNumber:0,frameCount:4) == nil, "zero-based native ID leaked")
expect(SEGSourceFrame(sopInstanceUID:uid,frameNumber:5,frameCount:4) == nil, "invalid source frame accepted")
print("PASS: all SourceImage items, multiframe timepoint boundaries, whole-object references and derived frame identity")
'''
with tempfile.TemporaryDirectory(prefix='horos-seg-source-') as folder:
    tmp = Path(folder)
    files = []
    for name in ('VolumeSession.swift', 'DicomSEG.swift', 'ROISurfaceAlgorithm.swift',
                 'HorosSEGSurface.swift', 'SEGViewerSession.swift',
                 'ROIInterchange.swift', 'ROIArchiveFormat.swift', 'HorosLegacyROISeg.swift'):
        path = tmp / name
        source = root / 'Horos/Sources' / name
        path.write_bytes(subprocess.check_output(['git','show',f'{args.baseline}:Horos/Sources/{name}'],cwd=root)
                         if args.baseline else source.read_bytes())
        files.append(str(path))
    (tmp/'main.swift').write_text(setup + ('' if args.baseline else multiframe))
    subprocess.run(['xcrun','swiftc',*files,str(tmp/'main.swift'),'-o',str(tmp/'probe')],check=True)
    subprocess.run([str(tmp/'probe')],check=True)
