#!/usr/bin/env python3
"""Patient-space ROI reorientation: axial/coronal/sagittal, oblique, spacing, parse vs transform."""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
code = r'''
import Foundation

func close(_ a: Double, _ b: Double, _ e: Double = 1e-6) {
    precondition(abs(a - b) < e, "\(a) != \(b)")
}

func image(sop: String?, z: Double, iop: [Double], ipp: [Double],
           spacingX: Double = 1, spacingY: Double = 1, rows: Int = 256,
           time: Int = 0, index: Int = 0) -> ROIAssociationImage {
    let image = ROIAssociationImage()
    image.index = index
    image.temporalIndex = time
    image.sopInstanceUID = sop
    image.frame = 0
    image.seriesInstanceUID = "1.2.series"
    image.frameOfReferenceUID = "1.2.for"
    image.rows = rows
    image.columns = 256
    image.pixelSpacingX = spacingX
    image.pixelSpacingY = spacingY
    image.imagePosition = ipp
    image.imageOrientation = iop
    image.hasImageOrigin = true
    if iop.count == 6, ipp.count == 3 {
        image.imageOriginX = ipp[0]*iop[0] + ipp[1]*iop[1] + ipp[2]*iop[2]
        image.imageOriginY = ipp[0]*iop[3] + ipp[1]*iop[4] + ipp[2]*iop[5]
    }
    return image
}

func lengthItem(sop: String?, points: [[Double]], patient: [[Double]], iop: [Double], ipp: [Double]) -> ROIAssociationItem {
    let item = ROIAssociationItem()
    item.name = "QA Length"
    item.typeCode = 5
    item.image = image(sop: sop, z: ipp[2], iop: iop, ipp: ipp)
    item.points = points
    item.patientPoints = patient
    return item
}

let axialIOP = [1.0, 0, 0, 0, 1.0, 0]
let coronalIOP = [1.0, 0, 0, 0, 0, -1.0]
let sagittalIOP = [0.0, 1.0, 0, 0, 0, -1.0]

let axial = image(sop: "sop-ax", z: 0, iop: axialIOP, ipp: [0, 0, 0], index: 0)
let coronal = image(sop: "sop-cor", z: 20, iop: coronalIOP, ipp: [0, 20, 50], index: 0)
let sagittal = image(sop: "sop-sag", z: 10, iop: sagittalIOP, ipp: [10, 0, 50], index: 0)

// Pixel (10,20) on axial origin 0 → patient (10, 20, 0).
let axialSource = lengthItem(sop: "sop-ax",
                             points: [[10, 20], [40, 20]],
                             patient: [[10, 20, 0], [40, 20, 0]],
                             iop: axialIOP, ipp: [0, 0, 0])

// Same orientation: points unchanged.
let same = ROIAssociation.plan(sources: [axialSource], targets: [axial])
precondition(same.canApply)
precondition(!same.bindings[0].reoriented)
close(same.bindings[0].points[0][0], 10)
close(same.bindings[0].points[0][1], 20)

// Axial → coronal through Y=20. Origin (0,20,50), col −Z: y = 50, x = 10 and 40.
let toCoronal = ROIAssociation.plan(sources: [axialSource], targets: [coronal])
precondition(toCoronal.canApply)
precondition(toCoronal.bindings[0].reoriented)
close(toCoronal.bindings[0].points[0][0], 10)
close(toCoronal.bindings[0].points[0][1], 50)
close(toCoronal.bindings[0].points[1][0], 40)
close(toCoronal.bindings[0].points[1][1], 50)

// Return to the original axial orientation.
let back = ROIAssociation.plan(sources: [axialSource], targets: [axial])
precondition(back.canApply)
close(back.bindings[0].points[0][0], 10)
close(back.bindings[0].points[0][1], 20)

// Sagittal at X=10 contains the first point; second point X=40 is 30 mm off-plane.
let toSagittal = ROIAssociation.plan(sources: [axialSource], targets: [sagittal])
precondition(!toSagittal.canApply)
precondition(toSagittal.bindings[0].status == .orientationIncompatible)
precondition(!toSagittal.summary.lowercased().contains("json"))
precondition(!toSagittal.summary.lowercased().contains("parse"))

// Coronal that does not contain Y=20 (origin Y=0 → through-plane 20 mm).
let otherCoronal = image(sop: "sop-cor2", z: 0, iop: coronalIOP, ipp: [0, 0, 50], index: 0)
let missPlane = ROIAssociation.plan(sources: [axialSource], targets: [otherCoronal])
precondition(!missPlane.canApply)
precondition(missPlane.bindings[0].status == .orientationIncompatible)

// Spacing on the coronal target: x = 10/0.5 = 20, y = 50/2 = 25.
let spaced = image(sop: "sop-cor-sp", z: 20, iop: coronalIOP, ipp: [0, 20, 50],
                   spacingX: 0.5, spacingY: 2)
let spacedPlan = ROIAssociation.plan(sources: [axialSource], targets: [spaced])
precondition(spacedPlan.canApply)
precondition(spacedPlan.bindings[0].reoriented)
close(spacedPlan.bindings[0].points[0][0], 20)
close(spacedPlan.bindings[0].points[0][1], 25)

// Oblique: same plane as a tilted IOP, matched by IPP / SOP.
let obliqueIOP = [0.70710678118, 0.70710678118, 0, 0, 0, -1]
let oblique = image(sop: "sop-ob", z: 0, iop: obliqueIOP, ipp: [0, 0, 0], index: 0)
let obliqueItem = lengthItem(sop: "sop-ob",
                             points: [[4, 2], [8, 2]],
                             patient: [[2.828427, 2.828427, -2], [5.656854, 5.656854, -2]],
                             iop: obliqueIOP, ipp: [0, 0, 0])
let obliquePlan = ROIAssociation.plan(sources: [obliqueItem], targets: [oblique])
precondition(obliquePlan.canApply)
precondition(obliquePlan.bindings[0].targetIndex == 0)

// Frame association after reorientation: temporal index 1 is the only matching plane.
let corT0 = image(sop: "c0", z: 20, iop: coronalIOP, ipp: [0, 20, 50], time: 0, index: 0)
let corT1 = image(sop: "c1", z: 20, iop: coronalIOP, ipp: [0, 20, 50], time: 1, index: 0)
axialSource.image.temporalIndex = 1
let timed = ROIAssociation.plan(sources: [axialSource], targets: [corT0, corT1])
precondition(timed.canApply)
precondition(timed.bindings[0].targetIndex == 1)
axialSource.image.temporalIndex = 0

// Rectangle is refused on orientation change, not parsed as success.
let rect = ROIAssociationItem()
rect.name = "box"
rect.typeCode = 6
rect.hasRect = true
rect.image = image(sop: "sop-ax", z: 0, iop: axialIOP, ipp: [0, 0, 0])
rect.points = [[1, 2]]
rect.patientPoints = [[1, 2, 0]]
let rectPlan = ROIAssociation.plan(sources: [rect], targets: [coronal])
precondition(!rectPlan.canApply)
precondition(rectPlan.bindings[0].status == .orientationIncompatible)

print("PASS: axial round-trip, coronal reproject, sagittal refuse, spacing, oblique, frame, rect vs parse")
'''
with tempfile.TemporaryDirectory(prefix='horos-roi-reorient-') as d:
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
