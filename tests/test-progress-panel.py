#!/usr/bin/env python3
"""Check key/main eligibility of both actual progress panel nibs."""
from pathlib import Path
import subprocess,tempfile,sys
root=Path(__file__).resolve().parents[1]
code=r'''
import AppKit
@objc(Wait) final class Owner: NSWindowController {
 @IBOutlet var progress: NSProgressIndicator!
 @IBOutlet var text: NSTextField!
 @IBOutlet var elapsed: NSTextField!
 @IBOutlet var message: NSTextField!
 @IBOutlet var currentTimeText: NSTextField!
 @IBOutlet var lastTimeText: NSTextField!
 @IBOutlet var abort: NSButton!
 @IBAction func abortButton(_ sender: Any?) {}
 @objc(abort:) func cancelRendering(_ sender: Any?) {}
}
@main struct Test {
 static func main(){
  _ = NSApplication.shared
  for path in CommandLine.arguments.dropFirst(){
   let owner=Owner(window:nil);var objects:NSArray?
   let nib=NSNib(nibData:try! Data(contentsOf:URL(fileURLWithPath:path)),bundle:nil)
   precondition(nib.instantiate(withOwner:owner,topLevelObjects:&objects))
   precondition(owner.window!.canBecomeKey,"Progress panel rejects modal keyboard focus")
   precondition(!owner.window!.canBecomeMain,"Progress panel must not replace the main viewer")
   precondition(owner.abort.action != nil)
   print("PASS: \(URL(fileURLWithPath:path).lastPathComponent) accepts key focus, preserves main window, retains abort action")
   withExtendedLifetime(objects){}
  }
 }
}
'''
with tempfile.TemporaryDirectory(prefix='horos-progress-panel-') as folder:
 p=Path(folder);(p/'test.swift').write_text(code);nibs=[]
 for loc,kind in [(loc,kind) for loc in ['en','ja-JP'] for kind in ['Wait','WaitRendering']]:
  rel=f'Horos/Resources/{loc}.lproj/{kind}.xib'
  loc=loc+'-'+kind
  source=subprocess.check_output(['git','show',sys.argv[1]+':'+rel]) if len(sys.argv)>1 else (root/rel).read_bytes()
  (p/f'{loc}.xib').write_bytes(source);nib=p/f'{loc}.nib';nibs.append(str(nib))
  subprocess.run(['xcrun','ibtool','--compile',str(nib),str(p/f'{loc}.xib')],check=True,stdout=subprocess.DEVNULL)
 subprocess.run(['xcrun','swiftc','-swift-version','5','-parse-as-library',str(root/'Horos/Sources/ProgressPanel.swift'),str(p/'test.swift'),'-framework','AppKit','-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test'),*nibs],check=True)
