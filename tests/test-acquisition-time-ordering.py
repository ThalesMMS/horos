#!/usr/bin/env python3
"""Compile the production Swift sorter and verify DICOM temporal edge cases."""
from pathlib import Path
import subprocess, tempfile
root=Path(__file__).resolve().parents[1]
code=r'''
import Foundation
func check(_ records: [[String:String]], _ expected: [Int], ascending: Bool = true) {
 let result = AcquisitionTimeOrdering.orderedIndices(records: records, ascending: ascending).map(\.intValue)
 precondition(result == expected, "expected \(expected), got \(result)")
}
func dt(_ value: String) -> [String:String] { ["AcquisitionDateTime":value] }
check([dt("20260907120000.000002"), dt("20260907120000.000001"), dt("20260907120000.000001"), [:]], [1,2,0,3])
check([dt("20260907120000.000002"), dt("20260907120000.000001"), dt("20260907120000.000001"), [:]], [0,1,2,3], ascending:false)
check([dt("20260101003000+0100"), dt("20251231234500+0000")], [0,1])
check([dt("20260907120000-0030"), dt("20260907120000+0000")], [1,0])
check([["AcquisitionDate":"20260908","AcquisitionTime":"000000"], ["AcquisitionDate":"20260907","AcquisitionTime":"235959.999999"]], [1,0])
check([["AcquisitionDateTime":"invalid","AcquisitionDate":"20260907","AcquisitionTime":"12"],dt("202609071300")], [0,1])
check([["AcquisitionDateTime":"20260907120000+0000","TimezoneOffsetFromUTC":"+0200"], ["AcquisitionDate":"20260907","AcquisitionTime":"130000","TimezoneOffsetFromUTC":"+0200"]], [1,0])
check([dt("20240229000000"),dt("20230229000000"),dt("20260431000000"),dt("20260101240000"),dt("20260101000000."),dt("20260101000000.1234567"),dt("20260101000000-0000"),dt("20260101000000+1401")], Array(0...7))
let invalid = ["20230229000000", "20260431000000", "20260101240000", "20260101000000.", "20260101000000.1234567", "20260101000000-0000", "20260101000000+1401", "00000101000000"]
check(invalid.map(dt) + [dt("99991231235959")], [invalid.count] + Array(invalid.indices))
check([dt("20260101000000"),dt("20251231235960.5"),dt("20251231235959.999999")], [2,1,0])
check([dt("2026"),dt("202601"),dt("20260101"),dt("2026010100"),dt("202601010000"),dt("20260101000000   ")], Array(0...5))
check([dt(" 20260101000000"),dt("20260101000000"),["AcquisitionTime":"120000"],dt(""),dt("2026010100.5")], [1,0,2,3,4])
check([dt("20260907120000"),["AcquisitionDateTime":"20260907110000","AcquisitionDate":"20260908","AcquisitionTime":"120000"]], [1,0])
print("PASS: microseconds, stable ties, ascending/descending, midnight, zones, partial precision, invalid dates, fallback and missing values")
'''
with tempfile.TemporaryDirectory(prefix='horos-acquisition-time-') as directory:
 p=Path(directory);(p/'main.swift').write_text(code)
 subprocess.run(['xcrun','swiftc',str(root/'Horos/Sources/AcquisitionTimeOrdering.swift'),str(p/'main.swift'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
