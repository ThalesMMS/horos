#!/usr/bin/env python3
"""Compile the actual Swift filename builder and exercise multi-image names."""
from pathlib import Path
import subprocess,tempfile
root=Path(__file__).resolve().parents[1]
program=r'''
import Foundation
let cases: [(String, Int, String, String)] = [
 ("/tmp/Series.0001.jpg", 2, "jpg", "/tmp/Series.0002.jpg"),
 ("/tmp/exam.v1.jpg", 1, "jpg", "/tmp/exam.v1.0001.jpg"),
 ("/tmp/exam.v1.0001.jpg", 16, "jpg", "/tmp/exam.v1.0016.jpg"),
 ("/tmp/exam.v1.tif", 3, "tif", "/tmp/exam.v1.0003.tif"),
 ("/tmp/folder.v2/exam.2026.jpg", 10000, "jpg", "/tmp/folder.v2/exam.2026.10000.jpg"),
 ("/tmp/Exame crânio.jpg", 1, "jpg", "/tmp/Exame crânio.0001.jpg")
]
for (selection, index, ext, expected) in cases {
 let actual = ImageExportPath.path(selection: selection, index: index, fileExtension: ext)
 precondition(actual == expected, "\(actual) != \(expected)")
}
let names = Set((1...10000).map { ImageExportPath.path(selection: "/tmp/exam.v1.0001.jpg", index: $0, fileExtension: "jpg") })
precondition(names.count == 10000)
print("PASS: dotted names, default sequence, TIFF, Unicode, and 10000 unique filenames")
'''
with tempfile.TemporaryDirectory(prefix='horos-image-path-') as folder:
 p=Path(folder);(p/'main.swift').write_text(program)
 subprocess.run(['xcrun','swiftc',str(root/'Horos/Sources/ImageExportPath.swift'),str(p/'main.swift'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
