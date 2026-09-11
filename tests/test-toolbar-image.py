#!/usr/bin/env python3
"""Toolbar artwork policy: aspect ratio, toolbar height, shared instances, replacement."""
from pathlib import Path
import subprocess,tempfile
root=Path(__file__).resolve().parents[1]
code=r'''
import AppKit

func ratio(_ s:NSSize)->CGFloat { s.width/s.height }

@main struct Test {
 static func main(){
  _=NSApplication.shared

  // Oversized, small and non-square artwork keep their proportions and never
  // make the item taller than the toolbar's logical size.
  for size in [NSSize(width:569,height:569),NSSize(width:200,height:100),
               NSSize(width:124,height:100),NSSize(width:16,height:16),
               NSSize(width:708.416,height:734)] {
   let source=NSImage(size:size)
   let item=NSToolbarItem(itemIdentifier:.init("test"));item.image=source
   ToolbarImage.normalize(for:item)
   precondition(source.size==size, "source must not be mutated")
   precondition(max(item.image!.size.width,item.image!.size.height)<=32)
   precondition(abs(ratio(item.image!.size)-ratio(size))<0.0001, "aspect ratio kept")
   let first=item.image;ToolbarImage.normalize(for:item);precondition(item.image===first, "idempotent")
  }

  // An item that swaps its image after insertion — play/stop, series sync,
  // plugin items rebuilt on demand — is normalized on the new artwork too.
  let item=NSToolbarItem(itemIdentifier:.init("swap"))
  item.image=NSImage(size:NSSize(width:16,height:16))
  ToolbarImage.normalize(for:item)
  item.image=NSImage(size:NSSize(width:124,height:100))
  ToolbarImage.normalize(for:item)
  precondition(item.image!.size==NSSize(width:32.0,height:32.0*100.0/124.0))

  // View-backed items own their layout; nil items are tolerated.
  let viewItem=NSToolbarItem(itemIdentifier:.init("view"))
  viewItem.view=NSView(frame:NSRect(x:0,y:0,width:80,height:40))
  viewItem.image=NSImage(size:NSSize(width:569,height:569))
  ToolbarImage.normalize(for:viewItem)
  precondition(viewItem.image!.size==NSSize(width:569,height:569))
  ToolbarImage.normalize(for:nil)

  // The named lookup returns a fitted copy, leaving the shared instance alone.
  let path=CommandLine.arguments[1]
  let shared=NSImage(contentsOfFile:path)!
  precondition(shared.size==NSSize(width:124,height:100))
  let fitted=ToolbarImage.fitting(shared)!
  precondition(shared.size==NSSize(width:124,height:100), "shared instance not resized")
  precondition(fitted !== shared)
  precondition(fitted.size==NSSize(width:32.0,height:32.0*100.0/124.0))

  // Fixed size-mode rendering scales in both directions, still proportional.
  let up=ToolbarImage.scaled(NSImage(size:NSSize(width:12,height:6)),toLongestEdge:24)!
  precondition(up.size==NSSize(width:24,height:12))

  // Real ROI artwork: square PDF still lands on the 32 point box.
  let roi=NSImage(contentsOfFile:CommandLine.arguments[2])!
  let roiItem=NSToolbarItem(itemIdentifier:.init("roi"));roiItem.image=roi
  ToolbarImage.normalize(for:roiItem)
  precondition(roi.size==NSSize(width:569,height:569))
  precondition(roiItem.image!.size==NSSize(width:32,height:32))

  // Raster check at 1x and 2x: the drawn artwork keeps the source proportions
  // instead of being stretched into a square box.
  func draw(_ image:NSImage,_ box:NSSize,_ scale:Int)->(w:Int,h:Int,filled:NSRect){
   let rep=NSBitmapImageRep(bitmapDataPlanes:nil,pixelsWide:Int(box.width)*scale,
     pixelsHigh:Int(box.height)*scale,bitsPerSample:8,samplesPerPixel:4,hasAlpha:true,
     isPlanar:false,colorSpaceName:.deviceRGB,bytesPerRow:0,bitsPerPixel:0)!
   rep.size=box
   NSGraphicsContext.saveGraphicsState()
   NSGraphicsContext.current=NSGraphicsContext(bitmapImageRep:rep)
   image.draw(in:NSRect(origin:.zero,size:image.size))
   NSGraphicsContext.restoreGraphicsState()
   var minX=rep.pixelsWide,minY=rep.pixelsHigh,maxX = -1,maxY = -1
   for y in 0..<rep.pixelsHigh { for x in 0..<rep.pixelsWide {
     if let c=rep.colorAt(x:x,y:y), c.alphaComponent>0.01 {
       minX=min(minX,x);maxX=max(maxX,x);minY=min(minY,y);maxY=max(maxY,y) } } }
   return (rep.pixelsWide,rep.pixelsHigh,
           NSRect(x:CGFloat(minX),y:CGFloat(minY),
                  width:CGFloat(maxX-minX+1),height:CGFloat(maxY-minY+1)))
  }
  for scale in [1,2] {
   let stretched=shared.copy() as! NSImage
   stretched.size=NSSize(width:32,height:32)          // the previous behaviour
   let before=draw(stretched,NSSize(width:32,height:32),scale)
   let after=draw(fitted,fitted.size,scale)
   let sourceRatio=ratio(NSSize(width:124,height:100))
   precondition(abs(ratio(before.filled.size)-sourceRatio)>0.15,
                "the square box really did stretch the artwork at \(scale)x")
   precondition(abs(ratio(after.filled.size)-sourceRatio)<0.05,
                "fitted artwork keeps the source proportions at \(scale)x")
   precondition(after.h<=32*scale, "fitted artwork never exceeds the toolbar box at \(scale)x")
  }

  print("PASS: aspect ratio kept for non-square art (measured on the 1x/2x raster), 32 point cap, shared instance intact, image swaps and view-backed items handled")
 }
}
'''
with tempfile.TemporaryDirectory(prefix='horos-toolbar-image-') as folder:
 p=Path(folder);(p/'test.swift').write_text(code)
 subprocess.run(['xcrun','swiftc','-swift-version','5','-parse-as-library',str(root/'Horos/Sources/ToolbarImage.swift'),str(p/'test.swift'),'-framework','AppKit','-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test'),str(root/'Horos/Resources/Icons/windows.tif'),str(root/'Horos/Resources/Icons/ROIManager.pdf')],check=True)
