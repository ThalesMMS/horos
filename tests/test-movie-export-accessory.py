#!/usr/bin/env python3
"""Load both actual movie accessory nibs and verify their fitting geometry."""
from pathlib import Path
import subprocess, tempfile, sys
root=Path(__file__).resolve().parents[1]
code=r'''
import AppKit
@objc(QuicktimeExport) final class Owner: NSObject {
 @IBOutlet var view: NSView!
 @IBOutlet var type: NSPopUpButton!
 @IBOutlet var rateValue: NSTextField!
 @IBAction func changeExportType(_ sender: Any?) {}
}
@main struct Test {
 static func main() {
  _ = NSApplication.shared
  for path in CommandLine.arguments.dropFirst() {
   let owner=Owner()
   var top: NSArray?
   let nib=NSNib(nibData: try! Data(contentsOf: URL(fileURLWithPath:path)), bundle: nil)
   precondition(nib.instantiate(withOwner:owner,topLevelObjects:&top))
   let view=owner.view!
   let size=view.fittingSize
   precondition(size.height >= 50, "Movie accessory has no vertical fitting size")
   view.setFrameSize(size)
   view.layoutSubtreeIfNeeded()
   for control in view.subviews {
    precondition(control.frame.minY >= -1 && control.frame.maxY <= size.height+1,
                 "Movie accessory clips a control vertically")
   }
   print("PASS: \(URL(fileURLWithPath:path).lastPathComponent) fitting size \(size)")
   withExtendedLifetime(top) {}
  }
 }
}
'''
with tempfile.TemporaryDirectory(prefix='horos-movie-accessory-') as folder:
 p=Path(folder);(p/'test.swift').write_text(code)
 nibs=[]
 for loc in ['en','ja-JP']:
  rel=f'Horos/Resources/{loc}.lproj/QuicktimeExport.xib'
  source=subprocess.check_output(['git','show',sys.argv[1]+':'+rel]) if len(sys.argv)>1 else (root/rel).read_bytes()
  xib=p/f'{loc}.xib';xib.write_bytes(source);nib=p/f'{loc}.nib';nibs.append(str(nib))
  subprocess.run(['xcrun','ibtool','--compile',str(nib),str(xib)],check=True,stdout=subprocess.DEVNULL)
 subprocess.run(['xcrun','swiftc','-swift-version','5','-parse-as-library',str(p/'test.swift'),'-framework','AppKit','-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test'),*nibs],check=True)
