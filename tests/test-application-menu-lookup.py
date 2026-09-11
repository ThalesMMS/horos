#!/usr/bin/env python3
"""Validate stable menu lookup using all shipped MainMenu resource trees."""
import json
from pathlib import Path
import subprocess
import tempfile
import xml.etree.ElementTree as ET
root=Path(__file__).resolve().parents[1]
def tree(menu):
    return [{'title':i.get('title',''), 'identifier':i.get('identifier',''),
             'items':tree(i.find('menu')) if i.find('menu') is not None else None}
            for i in menu.findall('./items/menuItem')]
fixtures=[]
for lang in ['en','ja-JP','it-IT','es']:
    doc=ET.parse(root/f'Horos/Resources/{lang}.lproj/MainMenu.xib')
    menu=doc.find('.//menu[@systemMenu="main"]')
    assert menu is not None
    fixtures.append(tree(menu))
code=r'''
import AppKit
func makeMenu(_ entries: [[String: Any]]) -> NSMenu {
    let menu = NSMenu()
    for entry in entries {
        let item = NSMenuItem(title: entry["title"] as! String, action: nil, keyEquivalent: "")
        let id = entry["identifier"] as! String
        if !id.isEmpty { item.identifier = NSUserInterfaceItemIdentifier(id) }
        if let children = entry["items"] as? [[String: Any]] { item.submenu = makeMenu(children) }
        menu.addItem(item)
    }
    return menu
}
func checkTree(_ menu: NSMenu) {
    for item in menu.items {
        if let id = item.identifier, let submenu = item.submenu {
            precondition(ApplicationMenuLookup.submenu(in: menu, identifier: id.rawValue) === submenu)
        }
        if let submenu = item.submenu { checkTree(submenu) }
    }
    precondition(ApplicationMenuLookup.submenu(in: menu, identifier: "missing") == nil)
}
let fixtures = try JSONSerialization.jsonObject(with: Data(contentsOf: URL(fileURLWithPath: CommandLine.arguments[1]))) as! [[[String: Any]]]
for entries in fixtures {
    let menu = makeMenu(entries)
    let viewer = ApplicationMenuLookup.submenu(in: menu, identifier: "org.horos.menu.viewer")!
    let file = ApplicationMenuLookup.submenu(in: menu, identifier: "org.horos.menu.file")!
    precondition(ApplicationMenuLookup.submenu(in: file, identifier: "org.horos.menu.export") != nil)
    for key in ["image-tiling", "orientation", "opacity", "wlww", "convolution", "clut", "workspace"] {
        precondition(ApplicationMenuLookup.submenu(in: viewer, identifier: "org.horos.menu." + key) != nil)
    }
    checkTree(menu)
    func reorder(_ menu: NSMenu) {
        let items = menu.items
        menu.removeAllItems()
        for item in items.reversed() {
            item.title = "同じタイトル" // Titles cannot distinguish these entries.
            if let submenu = item.submenu { reorder(submenu) }
            menu.addItem(item)
        }
    }
    reorder(menu)
    precondition(ApplicationMenuLookup.submenu(in: menu, identifier: "org.horos.menu.viewer") === viewer)
    checkTree(menu)
    menu.removeAllItems()
    precondition(ApplicationMenuLookup.submenu(in: menu, identifier: "org.horos.menu.viewer") == nil)
}
precondition(ApplicationMenuLookup.submenu(in: nil, identifier: "org.horos.menu.viewer") == nil)
print("PASS: English/Japanese/Italian/Spanish resource menus, ten identities, reordered/identically translated titles, missing and empty menus")
'''
with tempfile.TemporaryDirectory(prefix='horos-menu-lookup-') as d:
    p=Path(d);(p/'main.swift').write_text(code);(p/'fixtures.json').write_text(json.dumps(fixtures))
    subprocess.run(['xcrun','swiftc',str(root/'Horos/Sources/ApplicationMenuLookup.swift'),str(p/'main.swift'),'-o',str(p/'test')],check=True)
    subprocess.run([str(p/'test'),str(p/'fixtures.json')],check=True)
