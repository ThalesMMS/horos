#!/usr/bin/env python3
"""Check handle selection radius and nearest-endpoint behavior in the Swift helper."""
from pathlib import Path
import subprocess
import tempfile
root = Path(__file__).resolve().parents[1]
code = r'''
import AppKit
for backing in [1.0, 2.0] {
    func p(_ x: Double, _ y: Double) -> NSPoint { NSPoint(x:x*backing,y:y*backing) }
    let first=p(20,30), second=p(120,80)
    for (point, expected) in [(p(20,30),0), (p(120,80),1), (p(28,30),0),
                               (p(128.01,80),-1), (p(70,55),-1), (p(-20,-30),-1)] {
        precondition(VRMeasurementGeometry.editableEndpoint(at:point,first:first,second:second,tolerance:8*backing)==expected)
    }
    precondition(VRMeasurementGeometry.editableEndpoint(at:p(24,30),first:first,second:p(26,30),tolerance:8*backing)==1)
    precondition(VRMeasurementGeometry.editableEndpoint(at:first,first:first,second:first,tolerance:8*backing)==0)
}
for invalid in [CGFloat.zero, -1, .infinity, .nan] {
    precondition(VRMeasurementGeometry.editableEndpoint(at:.zero,first:.zero,second:.zero,tolerance:invalid)==(-1))
}
precondition(VRMeasurementGeometry.editableEndpoint(at:NSPoint(x:CGFloat.nan,y:0),first:.zero,second:.zero,tolerance:8)==(-1))
print("PASS: first/second handle hits, radius boundary, overlapping handles, empty space, 1x/2x and invalid input")
'''
with tempfile.TemporaryDirectory(prefix='horos-vr-handles-') as d:
    p=Path(d);(p/'main.swift').write_text(code)
    subprocess.run(['xcrun','swiftc',str(root/'Horos/Sources/VRMeasurementGeometry.swift'),str(p/'main.swift'),'-o',str(p/'test')],check=True)
    subprocess.run([str(p/'test')],check=True)
