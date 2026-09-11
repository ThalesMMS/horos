#!/usr/bin/env python3
"""#378/A237: each ROI lands on its own slice, not all on the active one.

A237, absorbed from #237: two **aligned** series with ROIs on distinct slices
must receive each ROI at the **physically correct position**, rather than all of
them on the slice that happens to be showing. The criterion also asks for
orientation and spacing transformation and per-frame references to be exercised.

Aligned series are the interesting case because their SOP Instance UIDs differ:
the binding cannot match by identity and has to fall through to Image Position
(Patient). If that fallthrough collapsed — to the first target, to the current
index, to anything constant — every ROI would arrive on one slice, which is
exactly the reported failure.

So every case below asserts two things: that each ROI lands where its physical
position says, **and** that the bindings are not all the same target.
"""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
source = root / 'Horos/Sources/ROIAssociation.swift'
assert source.is_file(), 'FAIL: ROIAssociation.swift is missing'

DRIVER = r'''
import Foundation

func image(sop: String?, z: Double, index: Int,
           orientation: [Double] = [1, 0, 0, 0, 1, 0],
           spacing: Double = 1, series: String = "1.2.series") -> ROIAssociationImage {
    let value = ROIAssociationImage()
    value.index = index
    value.sopInstanceUID = sop
    value.frame = 0
    value.seriesInstanceUID = series
    value.frameOfReferenceUID = "1.2.frame-of-reference"
    value.rows = 256
    value.columns = 256
    value.pixelSpacingX = spacing
    value.pixelSpacingY = spacing
    value.imagePosition = [0, 0, z]
    value.imageOrientation = orientation
    value.hasImageOrigin = false
    return value
}

func roi(named name: String, sop: String?, z: Double, index: Int) -> ROIAssociationItem {
    let item = ROIAssociationItem()
    item.sourceIndex = index
    item.name = name
    item.typeCode = 5
    item.image = image(sop: sop, z: z, index: index)
    item.points = [[10, 20]]
    item.patientPoints = [[10, 20, z]]
    return item
}

func describe(_ plan: ROIAssociationPlan) -> String {
    plan.bindings.map { "\($0.targetIndex)" }.joined(separator: ",")
}

@main struct Check {
    static func main() {
        // Four ROIs, one every other slice of the source series.
        let sourceZ = [0.0, 4.0, 8.0, 12.0]
        // No SOP reference: the aligned-series case, where identity cannot match
        // and the physical position has to decide.
        let sources = sourceZ.enumerated().map { offset, z in
            roi(named: "lesion \(offset)", sop: nil, z: z, index: offset)
        }

        // --- an aligned series at 2 mm: each ROI on its own slice
        let aligned = (0..<8).map { index in
            image(sop: "1.2.target.\(index)", z: Double(index) * 2, index: index,
                  series: "1.2.other-series")
        }
        let plan = ROIAssociation.plan(sources: sources, targets: aligned)
        precondition(plan.bindings.count == 4)
        for (offset, binding) in plan.bindings.enumerated() {
            let expected = Int(sourceZ[offset] / 2)
            precondition(binding.targetIndex == expected,
                         "ROI \(offset) at z=\(sourceZ[offset]) went to \(binding.targetIndex), expected \(expected): \(binding.reason)")
        }
        precondition(Set(plan.bindings.map(\.targetIndex)).count == 4,
                     "every ROI landed on one slice: \(describe(plan))")

        // --- the same ROIs against a series whose *slices* are 1 mm apart: the
        // physical position decides, not the index. A ROI at z = 8 goes to slice
        // 8, not to slice 2 where its own series had it. The pixel spacing stays
        // the same, because a different one is refused outright -- see below.
        let finer = (0..<16).map { index in
            image(sop: "1.2.fine.\(index)", z: Double(index), index: index,
                  series: "1.2.fine-series")
        }
        let finePlan = ROIAssociation.plan(sources: sources, targets: finer)
        for (offset, binding) in finePlan.bindings.enumerated() {
            precondition(binding.targetIndex == Int(sourceZ[offset]),
                         "fine ROI \(offset) went to \(binding.targetIndex): \(binding.reason)")
        }
        precondition(Set(finePlan.bindings.map(\.targetIndex)).count == 4,
                     "every ROI landed on one slice: \(describe(finePlan))")
        precondition(finePlan.bindings.map(\.targetIndex) != plan.bindings.map(\.targetIndex),
                     "a series with a different spacing must not give the same indices")

        // --- a series somewhere else entirely: nothing may be placed, and the
        // refusal has to say why. Falling back onto the showing slice is the
        // failure this criterion names.
        let elsewhere = (0..<8).map { index in
            image(sop: "1.2.away.\(index)", z: 500 + Double(index) * 2, index: index,
                  series: "1.2.away-series")
        }
        for binding in ROIAssociation.plan(sources: sources, targets: elsewhere).bindings {
            precondition(binding.targetIndex == -1,
                         "a ROI was placed on a series it does not belong to: \(binding.reason)")
            precondition(!binding.reason.isEmpty, "a refusal must say why")
        }

        // --- identity that does not resolve is refused, not guessed. An archive
        // naming SOP UIDs the open series does not have must not be spread over
        // it by order.
        let named = sourceZ.enumerated().map { offset, z in
            roi(named: "lesion \(offset)", sop: "1.2.absent.\(Int(z))", z: z, index: offset)
        }
        for binding in ROIAssociation.plan(sources: named, targets: aligned).bindings {
            precondition(binding.targetIndex == -1, "an unresolved identity was placed anyway")
            precondition(binding.reason.contains("not part of the open series"),
                         "the refusal must name the missing reference: \(binding.reason)")
        }

        // --- a differently oriented target: the same four ROIs share one
        // coronal plane, because they share a patient y, and differ *within* it
        // by their own z. Stacking them at one point would be the same defect
        // seen from another angle.
        let coronal = (0..<8).map { index -> ROIAssociationImage in
            let value = image(sop: "1.2.coronal.\(index)", z: 0, index: index,
                              orientation: [1, 0, 0, 0, 0, 1], series: "1.2.coronal-series")
            value.imagePosition = [0, Double(index) * 4, 0]
            return value
        }
        let coronalPlan = ROIAssociation.plan(sources: sources, targets: coronal)
        precondition(Set(coronalPlan.bindings.map(\.targetIndex)) == [5],
                     "all four share patient y = 20, which is coronal plane 5: \(describe(coronalPlan))")
        let rows = coronalPlan.bindings.map { $0.points.first?[1] ?? -1 }
        precondition(rows == sourceZ,
                     "each ROI must keep its own position within the plane: \(rows) against \(sourceZ)")

        // --- a target with a different *pixel* spacing is refused by name. The
        // points are in pixels, so placing them on a differently sampled image
        // would move them; the service says so instead of resampling silently.
        let rescaled = (0..<8).map { index in
            image(sop: "1.2.rescaled.\(index)", z: Double(index) * 2, index: index,
                  spacing: 0.5, series: "1.2.rescaled-series")
        }
        for binding in ROIAssociation.plan(sources: sources, targets: rescaled).bindings {
            precondition(binding.targetIndex == -1, "a ROI was placed on a differently sampled image")
            precondition(binding.reason.contains("pixel spacing"),
                         "the refusal must name the spacing: \(binding.reason)")
        }

        print("aligned \(describe(plan)); finer \(describe(finePlan)); coronal plane \(describe(coronalPlan)) at rows \(rows); unaligned, unresolved and rescaled refused")
    }
}
'''

with tempfile.TemporaryDirectory(prefix='horos-roi-copy-') as folder:
    path = Path(folder)
    (path / 'Check.swift').write_text(DRIVER)
    build = subprocess.run(['xcrun', 'swiftc', '-parse-as-library',
                            str(root / 'Horos/Sources/ROIIntersliceGeometry.swift'),
                            str(root / 'Horos/Sources/ROIInterchange.swift'),
                            str(root / 'Horos/Sources/ROIArchiveFormat.swift'),
                            str(source), str(path / 'Check.swift'), '-o', str(path / 'check')],
                           capture_output=True, text=True)
    if build.returncode:
        print('FAIL: the association does not compile')
        print(build.stderr.strip()[-1800:])
        raise SystemExit(1)
    run = subprocess.run([str(path / 'check')], capture_output=True, text=True)
    if run.returncode:
        print('FAIL: a ROI did not land where its physical position says')
        print(run.stderr.strip()[-1800:])
        raise SystemExit(1)

print('PASS: %s' % run.stdout.strip())
