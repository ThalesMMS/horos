#!/usr/bin/env python3
"""Verify binary-safe streaming extraction and all-or-nothing multipart staging."""
from pathlib import Path
import subprocess, tempfile
root=Path(__file__).resolve().parents[1]
source=r'''
import Foundation
let fm=FileManager.default
let root=URL(fileURLWithPath:CommandLine.arguments[1])
let input=root.appendingPathComponent("response")
let type="multipart/related; type=\"application/dicom\"; boundary=\"part197\""
let payload=Data([0,255,13,10])+Data("\r\n--part197XY\r\n--part197--X".utf8)+Data(repeating:42,count:1000)
var response=Data("--part197\r\nContent-Type: application/dicom; transfer-syntax=*\r\n\r\n".utf8)
response.append(payload)
response.append(Data("\r\n--part197\r\nContent-Type: application/dicom\r\n\r\nSECOND\r\n--part197--\r\n".utf8))
try response.write(to:input)
for size in 1...80 {
 let dir=root.appendingPathComponent("parts\(size)")
 let parts=try DICOMwebMultipart.extract(from:input,contentType:type,into:dir,chunkSize:size)
 precondition(parts.count==2)
 precondition(try Data(contentsOf:parts[0])==payload)
 precondition(try Data(contentsOf:parts[1])==Data("SECOND".utf8))
 try fm.removeItem(at:dir)
}
for (i,body) in [Data(),Data(response.dropLast(12)),Data("--part197\r\nContent-Type: text/html\r\n\r\nBAD\r\n--part197--\r\n".utf8)].enumerated(){
 try body.write(to:input);let dir=root.appendingPathComponent("bad\(i)")
 do {_ = try DICOMwebMultipart.extract(from:input,contentType:type,into:dir,chunkSize:3);fatalError("accepted malformed")}
 catch {precondition(!fm.fileExists(atPath:dir.path))}
}
try response.write(to:input)
let dir=root.appendingPathComponent("cancelled");var calls=0
 do {_ = try DICOMwebMultipart.extract(from:input,contentType:type,into:dir,chunkSize:7,cancelled:{calls+=1;return calls>20});fatalError("accepted cancellation")}
 catch {precondition(!fm.fileExists(atPath:dir.path))}
let owned=root.appendingPathComponent("owned");try fm.createDirectory(at:owned,withIntermediateDirectories:false)
do {_ = try DICOMwebMultipart.extract(from:input,contentType:type,into:owned);fatalError("accepted existing directory")}
catch {precondition(fm.fileExists(atPath:owned.path))}
print("PASS: binary payload, split headers/boundaries at 80 chunk sizes, truncation, content type, cancellation, owned-directory preservation")
'''.replace('precondition(try Data(contentsOf:parts[0])==payload)','let first=try Data(contentsOf:parts[0]); precondition(first==payload)').replace('precondition(try Data(contentsOf:parts[1])==Data("SECOND".utf8))','let second=try Data(contentsOf:parts[1]); precondition(second==Data("SECOND".utf8))')
with tempfile.TemporaryDirectory(prefix='horos-dicomweb-multipart-') as tmp:
 p=Path(tmp);(p/'main.swift').write_text(source)
 subprocess.run(['xcrun','swiftc',str(root/'Horos/Sources/DICOMwebMultipart.swift'),str(p/'main.swift'),'-o',str(p/'check')],check=True)
 subprocess.run([str(p/'check'),tmp],check=True)
