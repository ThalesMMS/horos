#!/usr/bin/env python3
"""The field viewport must retain content height when the panel is compact."""
from pathlib import Path
import subprocess, tempfile
root = Path(__file__).resolve().parents[1]
main = r'''import AppKit
let box = NSBox(frame: NSRect(x: 0, y: 0, width: 560, height: 220))
let parent = box.contentView!
let grid = NSView(frame: NSRect(x: 10, y: 10, width: 520, height: 170))
grid.translatesAutoresizingMaskIntoConstraints = false
parent.addSubview(grid)
NSLayoutConstraint.activate([
 grid.leadingAnchor.constraint(equalTo: parent.leadingAnchor, constant: 10),
 grid.trailingAnchor.constraint(equalTo: parent.trailingAnchor, constant: -10),
 grid.topAnchor.constraint(equalTo: parent.topAnchor, constant: 10),
 grid.bottomAnchor.constraint(equalTo: parent.bottomAnchor, constant: -10)
])
AnonymizationFieldsScroll.install(in: box, document: grid)
box.layoutSubtreeIfNeeded()
let viewport = grid.enclosingScrollView!
let original = box.frame
AnonymizationFieldsScroll.update(document: grid, height: 468)
assert(box.frame == original)
assert(grid.frame.height == 468)
assert(viewport.documentView === grid && viewport.hasVerticalScroller)
assert(grid.frame.height > viewport.contentSize.height)
box.setFrameSize(NSSize(width: 700, height: 200))
box.layoutSubtreeIfNeeded()
AnonymizationFieldsScroll.update(document: grid, height: 468)
assert(grid.frame.height == 468)
assert(abs(grid.frame.width - viewport.contentSize.width) < 1)
AnonymizationFieldsScroll.update(document: grid, height: 36)
assert(grid.frame.height >= viewport.contentSize.height)
print("PASS: full field height, compact viewport, width resize and field removal")
'''
with tempfile.TemporaryDirectory(prefix="horos-fields-scroll-") as tmp:
    p = Path(tmp)
    (p/"main.swift").write_text(main)
    subprocess.run(["swiftc", str(root/"Horos/Sources/AnonymizationFieldsScroll.swift"), str(p/"main.swift"), "-o", str(p/"test")], check=True)
    subprocess.run([str(p/"test")], check=True)
