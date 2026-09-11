#!/usr/bin/env python3
"""Verify the Swift report retains every source/result in large local batches."""
from pathlib import Path
import subprocess,tempfile
root=Path(__file__).resolve().parents[1]
code=r'''
import Foundation
@main struct Test {
 static func main() {
    let rows: [[String: Any]] = (0..<29329).map { i in
        ["source": "/synthetic/series-\(i / 100)/image-\(i).dcm",
         "outcome": i == 173 ? "failed" : "not-exported",
         "detail": i == 173 ? "Invalid DICOM" : "Batch did not complete; original preserved."]
    }
    let error = NSError(domain: "fixture", code: 1, userInfo: [NSLocalizedDescriptionKey: "Incomplete batch", "HorosAnonymizationFileResults": rows])
    let text = AnonymizationErrorPresenter.reportText(error)
    precondition(text.hasPrefix("Incomplete batch"))
    precondition(text.contains("174. /synthetic/series-1/image-173.dcm\nInvalid DICOM"))
    precondition(text.contains("29329. /synthetic/series-293/image-29328.dcm"))
    precondition(text.components(separatedBy: ".dcm\n").count == 29330)
    precondition(AnonymizationErrorPresenter.reportText(NSError(domain: "fixture", code: 2, userInfo: [NSLocalizedDescriptionKey: "No inputs"])) == "No inputs")
    print("PASS: 29329 ordered results, exact failed source, final entry retained, empty report")
 }
}
'''
with tempfile.TemporaryDirectory(prefix='horos-file-results-') as tmp:
 p=Path(tmp);(p/'test.swift').write_text(code)
 subprocess.run(['xcrun','swiftc',str(root/'Horos/Sources/AnonymizationErrorPresenter.swift'),str(p/'test.swift'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
