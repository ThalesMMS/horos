#!/usr/bin/env python3
"""Compile production Swift geometry and verify restoration across display layouts."""
from pathlib import Path
import subprocess,tempfile
root=Path(__file__).resolve().parents[1]
source=r'''
import AppKit
let primary=NSRect(x:0,y:24,width:1440,height:876)
let left=NSRect(x:-1920,y:0,width:1920,height:1080)
let portrait=NSRect(x:1440,y:-400,width:900,height:1440)
let screens=[primary,left,portrait].map { NSValue(rect:$0) }
func recover(_ r:NSRect, _ frames:[NSValue]=screens, _ minimum:NSSize=NSSize(width:640,height:480))->NSRect {
 DatabaseWindowPlacement.recoveredFrame(r,visibleFrames:frames,minimumSize:minimum)
}
let valid=NSRect(x:-1800,y:150,width:1000,height:700)
precondition(recover(valid)==valid)
for saved in [NSRect(x:100000,y:100000,width:5000,height:3000), NSRect(x:-100000,y:-100000,width:900,height:600),NSRect(x:1400,y:800,width:1100,height:800),NSRect(x:10,y:10,width:1,height:1)] {
 let r=recover(saved)
 precondition([primary,left,portrait].contains { $0.contains(r) })
 precondition(r.width>=640 && r.height>=480)
 precondition(recover(r)==r)
}
let disconnected=recover(valid,[NSValue(rect:primary)])
precondition(primary.contains(disconnected))
precondition(recover(.zero)==primary)
precondition(recover(NSRect(x:CGFloat.nan,y:0,width:10,height:10))==primary)
precondition(recover(NSRect(x:0,y:0,width:CGFloat.infinity,height:10))==primary)
let small=NSRect(x:10,y:30,width:500,height:300)
precondition(recover(valid,[NSValue(rect:small)])==small)
precondition(recover(valid,[])==valid)
print("PASS: valid/negative-origin positions, disconnected and oversized windows, portrait displays, minimum sizes, invalid frames, no displays and idempotence")
'''
with tempfile.TemporaryDirectory(prefix='horos-window-placement-') as tmp:
 p=Path(tmp);(p/'main.swift').write_text(source)
 subprocess.run(['xcrun','swiftc',str(root/'Horos/Sources/DatabaseWindowPlacement.swift'),str(p/'main.swift'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
