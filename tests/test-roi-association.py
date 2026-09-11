#!/usr/bin/env python3
"""Identity matching for batch ROI import: SOP/frame/time, never name or file order."""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
code = r'''
import Foundation

func close(_ a: Double, _ b: Double, _ e: Double = 1e-6) {
    precondition(abs(a - b) < e, "\(a) != \(b)")
}

func axial(_ sop: String?, index: Int, z: Double, time: Int = 0, frame: Int = 0,
           originY: Double? = nil) -> ROIAssociationImage {
    let image = ROIAssociationImage()
    image.index = index
    image.temporalIndex = time
    image.sopInstanceUID = sop
    image.frame = frame
    image.seriesInstanceUID = "1.2.series"
    image.frameOfReferenceUID = "1.2.for"
    image.rows = 256
    image.columns = 256
    image.pixelSpacingX = 1
    image.pixelSpacingY = 1
    image.imagePosition = [0, 0, z]
    image.imageOrientation = [1, 0, 0, 0, 1, 0]
    image.imageOriginX = 0
    image.imageOriginY = originY ?? z
    image.hasImageOrigin = true
    return image
}

func item(name: String, sop: String?, z: Double, index: Int = 0, time: Int = 0,
          points: [[Double]] = [[10, 20]], patient: [[Double]] = [[10, 20, 0]],
          file: String? = nil) -> ROIAssociationItem {
    let source = ROIAssociationItem()
    source.sourceIndex = index
    source.name = name
    source.typeCode = 5
    source.fileName = file
    source.image = axial(sop, index: index, z: z, time: time)
    source.image.imagePosition = [0, 0, z]
    source.points = points
    source.patientPoints = patient.map { pts in
        var copy = pts
        if copy.count == 3 { copy[2] = z == 0 && pts[2] == 0 ? pts[2] : z }
        return copy
    }
    if z != 0 && patient.count == 1 && patient[0].count == 3 && patient[0][2] == 0 {
        source.patientPoints = [[patient[0][0], patient[0][1], z]]
    }
    source.red = 1; source.green = 0; source.blue = 0
    source.thickness = 2
    source.opacity = 1
    return source
}

let t0 = axial("sop-a", index: 0, z: 0)
let t1 = axial("sop-b", index: 1, z: 5)
let t2 = axial("sop-c", index: 0, z: 0, time: 1)
let targets = [t0, t1, t2]

// Unique SOP matches the image, not the listed index.
let bySOP = ROIAssociation.plan(sources: [item(name: "line", sop: "sop-a", z: 0, index: 99, file: "b.roi")],
                                targets: targets)
precondition(bySOP.canApply)
precondition(bySOP.bindings.count == 1)
precondition(bySOP.bindings[0].status == .mapped)
precondition(bySOP.bindings[0].targetIndex == 0)
precondition(bySOP.bindings[0].points[0][0] == 10)

// File order is reversed: first file is sop-b, second is sop-a.
let reversed = ROIAssociation.plan(
    sources: [item(name: "second", sop: "sop-b", z: 5, index: 0, file: "2.roi"),
              item(name: "first", sop: "sop-a", z: 0, index: 1, file: "1.roi")],
    targets: targets)
precondition(reversed.canApply)
precondition(reversed.bindings[0].targetIndex == 1)
precondition(reversed.bindings[1].targetIndex == 0)

// Homonyms: same display name, distinct SOP/frame.
let homonyms = ROIAssociation.plan(
    sources: [item(name: "lesion", sop: "sop-a", z: 0),
              item(name: "lesion", sop: "sop-b", z: 5)],
    targets: targets)
precondition(homonyms.canApply, homonyms.summary)
precondition(homonyms.bindings[0].targetIndex == 0, "homonym 0 -> \(homonyms.bindings[0].targetIndex) \(homonyms.bindings[0].reason)")
precondition(homonyms.bindings[1].targetIndex == 1, "homonym 1 -> \(homonyms.bindings[1].targetIndex) \(homonyms.bindings[1].reason)")

// Missing SOP reference is presented, not applied to slice 0.
let missing = ROIAssociation.plan(sources: [item(name: "gone", sop: "sop-missing", z: 0)],
                                  targets: targets)
precondition(!missing.canApply, missing.summary)
precondition(missing.bindings[0].status == .missingReference, "\(missing.bindings[0].status.rawValue) \(missing.bindings[0].reason)")
precondition(missing.bindings[0].targetIndex == -1)

// Duplicate SOP in the open series is ambiguous: never pick by order.
let dupA = axial("sop-a", index: 0, z: 0)
let dupA2 = axial("sop-a", index: 1, z: 5)
let ambiguous = ROIAssociation.plan(sources: [item(name: "lesion", sop: "sop-a", z: 0)],
                                    targets: [dupA, dupA2])
precondition(!ambiguous.canApply)
precondition(ambiguous.bindings[0].status == .ambiguous)
precondition(ambiguous.summary.lowercased().contains("ambigu"))

// No SOP/IPP/origin: insufficient, even with a unique name and index 0.
let bare = ROIAssociationItem()
bare.name = "lesion"
bare.typeCode = 5
bare.image = ROIAssociationImage()
bare.image.index = 0
bare.points = [[1, 1]]
let insufficient = ROIAssociation.plan(sources: [bare], targets: targets)
precondition(!insufficient.canApply)
precondition(insufficient.bindings[0].status == .insufficient)

// IPP + Frame of Reference when SOP is absent.
let byIPP = item(name: "ipp", sop: nil, z: 5)
byIPP.image.sopInstanceUID = nil
byIPP.image.imagePosition = [0, 0, 5]
byIPP.patientPoints = [[10, 20, 5]]
let ippPlan = ROIAssociation.plan(sources: [byIPP], targets: targets)
precondition(ippPlan.canApply)
precondition(ippPlan.bindings[0].targetIndex == 1)

// 4D: same IPP, different temporal index.
let tTime = item(name: "phase", sop: nil, z: 0, time: 1)
tTime.image.sopInstanceUID = nil
tTime.image.imagePosition = [0, 0, 0]
tTime.patientPoints = [[10, 20, 0]]
let timePlan = ROIAssociation.plan(sources: [tTime], targets: targets)
precondition(timePlan.canApply)
precondition(timePlan.bindings[0].targetIndex == 2)

// Archive 2D origin when SOP and IPP are absent.
let byOrigin = ROIAssociationItem()
byOrigin.name = "archive"
byOrigin.typeCode = 11
byOrigin.image.imageOriginX = 0
byOrigin.image.imageOriginY = 5
byOrigin.image.hasImageOrigin = true
byOrigin.image.pixelSpacingX = 1
byOrigin.image.pixelSpacingY = 1
byOrigin.image.temporalIndex = 0
byOrigin.image.rows = 256
byOrigin.image.columns = 256
byOrigin.points = [[3, 4]]
let originPlan = ROIAssociation.plan(sources: [byOrigin], targets: targets)
precondition(originPlan.canApply)
precondition(originPlan.bindings[0].targetIndex == 1)

// Reimport of the same identity stays mapped; the planner does not consume targets.
let again = ROIAssociation.plan(sources: [item(name: "line", sop: "sop-a", z: 0)], targets: targets)
precondition(again.canApply && again.bindings[0].targetIndex == 0)

// Mixed batch: one unique and one missing. Nothing is applied.
let mixed = ROIAssociation.plan(
    sources: [item(name: "ok", sop: "sop-a", z: 0),
              item(name: "bad", sop: "nope", z: 0)],
    targets: targets)
precondition(!mixed.canApply)
precondition(mixed.bindings[0].status == .mapped)
precondition(mixed.bindings[1].status == .missingReference)

print("PASS: SOP/frame/time identity, reversed files, homonyms, missing and ambiguous refs, origin fallback, reimport")
'''
with tempfile.TemporaryDirectory(prefix='horos-roi-assoc-') as d:
    p = Path(d)
    (p / 'main.swift').write_text(code)
    subprocess.run([
        'xcrun', 'swiftc',
        str(root / 'Horos/Sources/ROIIntersliceGeometry.swift'),
        str(root / 'Horos/Sources/ROIInterchange.swift'),
        str(root / 'Horos/Sources/ROIArchiveFormat.swift'),
        str(root / 'Horos/Sources/ROIAssociation.swift'),
        str(p / 'main.swift'), '-o', str(p / 'test')
    ], check=True)
    subprocess.run([str(p / 'test')], check=True)
