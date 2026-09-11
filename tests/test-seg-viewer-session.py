#!/usr/bin/env python3
"""Run SEG import/identity/commands/persistence against the existing volume session."""
from pathlib import Path
import subprocess
import tempfile
root = Path(__file__).resolve().parents[1]
driver = r'''
import Foundation
func expect(_ ok: Bool, _ reason: String) { if !ok { fatalError(reason) } }
let preferences = UserDefaults(suiteName: "org.horos.test.seg.\(UUID().uuidString)")!
let geometry = DicomSEGGeometry(rows: 2, columns: 2, frames: 2,
    spacingRow: 1, spacingCol: 1, sliceThickness: 2, origin: [0,0,0],
    orientation: [1,0,0,0,1,0], frameOfReferenceUID: "1.2.3.4",
    frameOrigins: [[0,0,0],[0,0,2]])
let refs = ["1.2.3.10", "1.2.3.11"]
let identity = DicomSEGIdentity(sopInstanceUID: "1.2.3.5", seriesInstanceUID: "1.2.3.6",
    studyInstanceUID: "1.2.3", frameOfReferenceUID: geometry.frameOfReferenceUID, sourceSOPInstanceUIDs: refs)
let segment = DicomSEGSegment(number: 1, label: "Tube", trackingUID: "1.2.3.7",
    color: (1,0,0), visible: true, kind: .binary, algorithm: "MANUAL", provenance: "synthetic",
    referencedSOPInstanceUIDs: refs, frames: [Data([1,1,1,1]),Data([1,1,1,1])], maximumFractionalValue: 1)
var document = DicomSEGDocument(identity: identity, geometry: geometry, kind: .binary,
    segments: [segment], diagnoses: [], sourceBytes: nil)
let encoded = try DicomSEGCodec.encode(document)
let registry = VolumeSessionRegistry()
let volumeIdentity = VolumeIdentity(studyInstanceUID: "1.2.3", seriesInstanceUID: "1.2.3.8",
    frameOfReferenceUID: "1.2.3.4", timeIndex: 0, generation: 0)!
let volume = registry.open(identity: volumeIdentity, owner: "viewer")!
let session = SEGViewerSession(volume: volume, sourceSOPInstanceUIDs: refs, preferences: preferences)
expect(session.load(encoded) == nil, "matching source SEG opens")
expect(session.snapshots.count == 1 && session.snapshots[0].mesh.closed, "actual shared mesh")
expect(!session.canUndo, "load has no synthetic commands")
session.rename(1, label: "Edited")
session.recolor(1, red: 0, green: 1, blue: 0)
session.setOpacity(1, opacity: 0.3)
session.undo(); expect(session.snapshots[0].opacity == 1, "opacity uses store undo")
session.redo(); expect(session.snapshots[0].opacity == 0.3, "opacity redo")
session.duplicate(1); expect(session.snapshots.count == 2, "duplicate shared command")
expect(session.snapshots[1].trackingUID != session.snapshots[0].trackingUID, "duplicate own identity")
expect(session.snapshots[1].opacity == 0.3, "duplicate presentation follows source")
session.setVisible(1, visible: false)
let derived = try session.exportDerived()
let reopened = SEGViewerSession(volume: volume, sourceSOPInstanceUIDs: refs, preferences: preferences)
expect(reopened.load(derived) == nil, "derived SEG reopens")
expect(reopened.snapshots[0].label == "Edited", "name persists")
expect(abs(reopened.snapshots[0].green - 1) <= 1.0 / 255, "color persists through 16-bit PCS CIELab")
expect(reopened.snapshots[0].opacity == 0.3 && !reopened.snapshots[0].visible, "presentation persists by tracking UID")
expect(!reopened.canUndo, "restored presentation has no fake undo")
expect(DicomSEGCodec.decode(encoded).segments[0].label == "Tube", "source unchanged")
session.remove(1); expect(session.snapshots.count == 1, "remove shared command")
session.undo(); expect(session.snapshots.count == 2, "undo restores actor source")
let before = session.snapshots.map(\.trackingUID)
expect(session.load(Data([0])) != nil, "malformed refused")
expect(session.snapshots.map(\.trackingUID) == before, "failed import transactional")
document.identity.studyInstanceUID = "9.8.7"
expect(session.load(try DicomSEGCodec.encode(document)) != nil, "wrong study refused")
document.identity.studyInstanceUID = identity.studyInstanceUID
document.geometry.frameOfReferenceUID = "9.8.7"
expect(session.load(try DicomSEGCodec.encode(document)) != nil, "wrong frame refused")
document.identity = identity; document.geometry = geometry; document.identity.sourceSOPInstanceUIDs = ["9.8.7"]
expect(session.load(try DicomSEGCodec.encode(document)) != nil, "other source images refused")
// #377 B: an identified ROI interchange document becomes a derived SEG in the same session.
let roiSeries = ROIInterchangeSeries()
roiSeries.studyInstanceUID = "1.2.3"; roiSeries.seriesInstanceUID = "1.2.3.8"; roiSeries.frameOfReferenceUID = "1.2.3.4"
for (index, sop) in refs.enumerated() {
    let image = ROIInterchangeImage()
    image.index = index; image.sopInstanceUID = sop; image.rows = 2; image.columns = 2
    image.pixelSpacingX = 1; image.pixelSpacingY = 1; image.sliceThickness = 2
    image.imagePosition = [0, 0, Double(index) * 2]; image.imageOrientation = [1, 0, 0, 0, 1, 0]
    if index == 0 {
        let roi = ROIInterchangeROI(); roi.name = "Legacy rect"; roi.typeCode = ROIInterchangeType.rectangle.rawValue
        roi.hasRect = true; roi.rect = NSRect(x: 0, y: 0, width: 2, height: 2); roi.red = 0; roi.green = 0; roi.blue = 1
        image.rois = [roi]
    }
    roiSeries.images.append(image)
}
let roiJSON = try ROIInterchange.encode(roiSeries, generator: "test")
let roiSession = SEGViewerSession(volume: volume, sourceSOPInstanceUIDs: refs, preferences: preferences)
expect(roiSession.load(roiJSON) == nil, "ROI interchange JSON converts to a derived SEG in the session")
expect(roiSession.snapshots.count == 1 && roiSession.snapshots[0].label == "Legacy rect", "converted ROI keeps its name")
expect(HorosLegacyROISeg.originalROI(from: roiSession.store!.document.segments[0]) != nil, "conversion stays reversible")
let typedstream = Data("streamtyped".utf8) + Data([0x84, 0x01, 0x40, 0x84, 0x84, 0x84, 0x07, 0x4e, 0x53, 0x41, 0x72, 0x72, 0x61, 0x79])
let typedstreamDiagnosis = roiSession.load(typedstream)
expect(typedstreamDiagnosis?.contains("identity") == true, "typedstream archives are refused for missing identity, not matched by name")
expect(roiSession.snapshots.count == 1, "refused archive keeps the previous document")
roiSeries.studyInstanceUID = "9.9.9"
expect(roiSession.load(try ROIInterchange.encode(roiSeries, generator: "test")) != nil, "ROI document from another study refused")
roiSession.close()
registry.invalidateVolume(volumeIdentity)
expect(!session.isCurrent && session.load(encoded) != nil, "stale volume cannot load")
session.rename(1, label: "Invalid")
expect(session.snapshots[0].label == "Edited", "stale view cannot edit")
session.close(); expect(session.snapshots.isEmpty && session.store == nil, "close drops meshes/store")
registry.close(volume); expect(registry.openSessionCount == 0, "same registry closes owner")
print("PASS: ROI interchange JSON converts through the legacy converter and typedstream is refused; SEG session shares volume identity and commands; opacity undo, source preservation, transactional refusal, derived/presentation reopen and stale/close cleanup")
'''
with tempfile.TemporaryDirectory(prefix='horos-seg-session-') as folder:
    tmp = Path(folder); (tmp/'main.swift').write_text(driver)
    subprocess.run(['xcrun','swiftc',*[str(root/'Horos/Sources'/name) for name in
        ('VolumeSession.swift','DicomSEG.swift','ROISurfaceAlgorithm.swift','HorosSEGSurface.swift','SEGViewerSession.swift',
         'ROIInterchange.swift','ROIArchiveFormat.swift','HorosLegacyROISeg.swift')],
        str(tmp/'main.swift'),'-o',str(tmp/'test')],check=True)
    subprocess.run([str(tmp/'test')],check=True)
