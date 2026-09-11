#!/usr/bin/env python3
"""Exercise window-to-view conversion through AppKit with controlled backing scales."""
from pathlib import Path
import subprocess
import tempfile
root=Path(__file__).resolve().parents[1]
code=r'''
import AppKit
final class BackingView: NSView {
    var scale: CGFloat = 1
    override func convertToBacking(_ point: NSPoint) -> NSPoint {
        NSPoint(x:point.x*scale,y:point.y*scale)
    }
}
let window = NSWindow(contentRect:NSRect(x:0,y:0,width:800,height:600),styleMask:.borderless,backing:.buffered,defer:false)
let container=NSView(frame:NSRect(x:80,y:30,width:600,height:500))
window.contentView!.addSubview(container)
let view=BackingView(frame:NSRect(x:20,y:15,width:400,height:300))
container.addSubview(view)
for scale in [CGFloat(1),CGFloat(2)] {
    view.scale=scale
    for origin in [NSPoint(x:20,y:15),NSPoint(x:200,y:120)] {
        view.setFrameOrigin(origin)
        for point in [NSPoint.zero,NSPoint(x:40,y:50),NSPoint(x:400,y:300),NSPoint(x:-10,y:8)] {
            let windowPoint=NSPoint(x:80+origin.x+point.x,y:30+origin.y+point.y)
            let actual=VRInteractionGeometry.backingPoint(windowPoint,in:view)
            precondition(abs(actual.x-point.x*scale)<1e-8 && abs(actual.y-point.y*scale)<1e-8)
            let legacy=view.convertToBacking(windowPoint)
            precondition(legacy != actual, "Fixture must expose missing window-to-view conversion")
        }
    }
}
print("PASS: AppKit nested/repositioned view coordinates, edges and outside points, controlled 1x/2x")
'''
with tempfile.TemporaryDirectory(prefix='horos-vr-interaction-') as d:
    p=Path(d);(p/'main.swift').write_text(code)
    subprocess.run(['xcrun','swiftc',str(root/'Horos/Sources/VRInteractionGeometry.swift'),str(p/'main.swift'),'-o',str(p/'test')],check=True)
    subprocess.run([str(p/'test')],check=True)
