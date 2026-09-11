#!/usr/bin/env python3
"""Verify overflow preserves localized commands and original target/tag routing."""
from pathlib import Path
import subprocess,tempfile
root=Path(__file__).resolve().parents[1]
code=r'''
import AppKit
final class Receiver:NSObject {
 var received:[Int]=[]
 @objc func exportFormat(_ sender:NSMenuItem){received.append(sender.tag)}
}
@main struct Test {
 static func main(){
  _=NSApplication.shared
  for label in ["Export 3D-SR","Exportar superfície 3D","Dreidimensionale Oberfläche exportieren"] {
   let receiver=Receiver();let toolbar=NSToolbarItem(itemIdentifier:.init("export"));toolbar.label=label
   let container=NSView();let nested=NSView();container.addSubview(nested)
   let popup=NSPopUpButton(frame:.zero,pullsDown:true);nested.addSubview(popup)
   let source=NSMenu();source.autoenablesItems=false
   let placeholder=NSMenuItem();placeholder.isHidden=true;source.addItem(placeholder)
   for i in 1...5 {let command=NSMenuItem(title:"Format \(i)",action:#selector(Receiver.exportFormat(_:)),keyEquivalent:"");command.target=receiver;command.tag=i;source.addItem(command)}
   popup.menu=source;toolbar.view=container
   ToolbarMenuBridge.install(for:toolbar)
   let representation=toolbar.menuFormRepresentation!
   precondition(representation.title==label)
   let overflow=representation.submenu!
   precondition(overflow !== source && overflow.items.count==6 && overflow.items[0].isHidden)
   for i in 1...5 {precondition(overflow.items[i].target === receiver);overflow.performActionForItem(at:i)}
   precondition(receiver.received == [1,2,3,4,5])
   precondition(source.items[1].menu === source)
  }
  let plain=NSToolbarItem(itemIdentifier:.init("plain"));ToolbarMenuBridge.install(for:plain)
  print("PASS: nested popup copies preserve labels, hidden placeholder, five actions, target/tag routing and source menu ownership")
 }
}
'''
with tempfile.TemporaryDirectory(prefix='horos-toolbar-menu-') as folder:
 p=Path(folder);(p/'test.swift').write_text(code)
 subprocess.run(['xcrun','swiftc','-swift-version','5','-parse-as-library',str(root/'Horos/Sources/ToolbarMenuBridge.swift'),str(p/'test.swift'),'-framework','AppKit','-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
