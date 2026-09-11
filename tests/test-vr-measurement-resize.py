#!/usr/bin/env python3
"""Verify projected world position and length survive parallel viewport resizing."""
from pathlib import Path
import subprocess
import tempfile
root=Path(__file__).resolve().parents[1]
code=r'''
import AppKit
func project(_ p: NSPoint, _ size: NSSize) -> NSPoint {
    // Independent orthographic camera: vertical world extent [-40, 40].
    let pixelsPerWorldUnit = size.height / 80
    return NSPoint(x: p.x * pixelsPerWorldUnit + size.width / 2,
                   y: p.y * pixelsPerWorldUnit + size.height / 2)
}
func close(_ p: NSPoint, _ q: NSPoint) {
    precondition(abs(p.x-q.x)<1e-8 && abs(p.y-q.y)<1e-8, "\(p) != \(q)")
}
let worlds = [NSPoint(x: -20,y: 3), NSPoint(x: 12,y: 17), .zero]
let sizes = [NSSize(width: 1695,height: 938),NSSize(width: 1527,height: 798),
             NSSize(width: 512,height: 512),NSSize(width: 768,height: 768),
             NSSize(width: 2100,height: 400),NSSize(width: 400,height: 1400)]
for scale in [1.0,2.0] {
    for before in sizes { for after in sizes {
        let old = NSSize(width:before.width*scale,height:before.height*scale)
        let new = NSSize(width:after.width*scale,height:after.height*scale)
        for w in worlds {
            // Internal viewport drag compensates the camera zoom: pixels/unit stay fixed.
            let zoom = old.height / new.height
            let movedInternally = VRMeasurementGeometry.resizedPoint(project(w,old),from:old,to:new,cameraZoom:zoom)
            let projectedAfterZoom = NSPoint(x:w.x*old.height/80+new.width/2,y:w.y*old.height/80+new.height/2)
            close(movedInternally,projectedAfterZoom)
            let original = project(w,old)
            let moved = VRMeasurementGeometry.resizedPoint(original,from:old,to:new)
            close(moved,project(w,new))
            close(VRMeasurementGeometry.resizedPoint(moved,from:new,to:old),original)
        }
        let a = VRMeasurementGeometry.resizedPoint(project(worlds[0],old),from:old,to:new)
        let b = VRMeasurementGeometry.resizedPoint(project(worlds[1],old),from:old,to:new)
        let physicalLength = hypot(b.x-a.x,b.y-a.y)*80/new.height
        precondition(abs(physicalLength-hypot(32,14))<1e-8)
    }}
}
let point=NSPoint(x:100,y:200)
for invalid in [NSSize.zero,NSSize(width:10,height:0),NSSize(width:-1,height:10),NSSize(width:CGFloat.infinity,height:10)] {
    close(VRMeasurementGeometry.resizedPoint(point,from:invalid,to:sizes[0]),point)
    close(VRMeasurementGeometry.resizedPoint(point,from:sizes[0],to:invalid),point)
}
print("PASS: world endpoints, physical length, resize/export roundtrips at 1x/2x and invalid sizes")
'''
with tempfile.TemporaryDirectory(prefix='horos-vr-resize-') as d:
    p=Path(d);(p/'main.swift').write_text(code)
    subprocess.run(['xcrun','swiftc',str(root/'Horos/Sources/VRMeasurementGeometry.swift'),str(p/'main.swift'),'-o',str(p/'test')],check=True)
    subprocess.run([str(p/'test')],check=True)
