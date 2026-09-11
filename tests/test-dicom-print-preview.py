#!/usr/bin/env python3
from pathlib import Path
import subprocess
import tempfile
root=Path(__file__).resolve().parent.parent
program=r'''
import AppKit
setbuf(stdout,nil)
let bitmap = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: 64, pixelsHigh: 32, bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true, isPlanar: false, colorSpaceName: .deviceRGB, bytesPerRow: 256, bitsPerPixel: 32)!
for y in 0..<32 { for x in 0..<64 {
 let value = CGFloat((y < 16 ? 40 : 120) + (x < 32 ? 0 : 60)) / 255
 bitmap.setColor(NSColor(deviceRed: value, green: value, blue: value, alpha: 1), atX: x, y: y)
} }
let source = NSImage(size: NSSize(width: 64, height: 32)); source.addRepresentation(bitmap)
let before = Array(UnsafeBufferPointer(start: bitmap.bitmapData!, count: bitmap.bytesPerRow * bitmap.pixelsHigh))
func pixels(_ image: NSImage) -> NSBitmapImageRep { NSBitmapImageRep(data: image.tiffRepresentation!)! }
func level(_ rep: NSBitmapImageRep, _ x: Int, _ y: Int) -> Int { var pixel = [UInt](repeating: 0, count: 4); rep.getPixel(&pixel, atX: x, y: y); return Int(pixel[0]) }
let identity = pixels(DICOMPrintPreview.render(source, zoom: 1, quarterTurns: 0))
for y in 0..<32 { for x in 0..<64 { precondition(abs(level(identity,x,y)-level(bitmap,x,y)) <= 1) } }
let turned = pixels(DICOMPrintPreview.render(source, zoom: 1, quarterTurns: 2))
for (x,y) in [(8,8),(48,8),(8,24),(48,24)] { precondition(abs(level(turned,x,y)-level(bitmap,63-x,31-y)) <= 1) }
let odd = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: 65, pixelsHigh: 33, bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true, isPlanar: false, colorSpaceName: .deviceRGB, bytesPerRow: 260, bitsPerPixel: 32)!
for y in 0..<33 { for x in 0..<65 { let v = CGFloat((x * 13 + y * 7) % 256) / 255; odd.setColor(NSColor(deviceRed: v, green: v, blue: v, alpha: 1), atX: x, y: y) } }
let oddImage = NSImage(size: NSSize(width: 65, height: 33)); oddImage.addRepresentation(odd)
let oddTurned = pixels(DICOMPrintPreview.render(oddImage, zoom: 1, quarterTurns: 2))
for y in 0..<33 { for x in 0..<65 { precondition(level(oddTurned,x,y) == level(odd,64-x,32-y)) } }
let zoomed = pixels(DICOMPrintPreview.render(source, zoom: 0.5, quarterTurns: 0))
precondition(level(zoomed,1,1) == 0)
precondition(zoomed.pixelsWide == 64 && zoomed.pixelsHigh == 32)
let invalid = pixels(DICOMPrintPreview.render(source, zoom: .nan, quarterTurns: 4))
precondition(abs(level(invalid,8,8)-level(bitmap,8,8)) <= 1)
precondition(before == Array(UnsafeBufferPointer(start: bitmap.bitmapData!, count: before.count)))
precondition(abs(DICOMPrintPreview.filmAspectRatio("14INX17IN", landscape: false) - 14.0/17.0) < 0.00001)
precondition(abs(DICOMPrintPreview.filmAspectRatio("8_5INX11IN", landscape: true) - 11.0/8.5) < 0.00001)
precondition(abs(DICOMPrintPreview.filmAspectRatio("A4", landscape: false) - 1/sqrt(2)) < 0.00001)
print("PASS: exact identity pixels, rotation, zoom canvas, invalid-value handling, unchanged source and film aspect ratios")
'''
with tempfile.TemporaryDirectory(prefix='horos-print-preview-') as directory:
 p=Path(directory);(p/'main.swift').write_text(program)
 subprocess.run(['xcrun','swiftc','-sanitize=address',str(root/'Horos/Sources/DICOMPrintPreview.swift'),str(p/'main.swift'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
