#!/usr/bin/env python3
"""Exercise the shipped database nibs in AppKit, including real toolbar sizing."""
from copy import deepcopy
from pathlib import Path
import subprocess
import tempfile
import plistlib
import xml.etree.ElementTree as ET

root = Path(__file__).resolve().parents[1]
code = r'''
import AppKit

final class Host: NSObject, NSToolbarDelegate, NSTableViewDataSource {
    var items: [NSToolbarItem] = []
    func toolbarDefaultItemIdentifiers(_ toolbar: NSToolbar) -> [NSToolbarItem.Identifier] {
        items.map(\.itemIdentifier)
    }
    func toolbarAllowedItemIdentifiers(_ toolbar: NSToolbar) -> [NSToolbarItem.Identifier] {
        toolbarDefaultItemIdentifiers(toolbar)
    }
    func toolbar(_ toolbar: NSToolbar, itemForItemIdentifier id: NSToolbarItem.Identifier,
                 willBeInsertedIntoToolbar: Bool) -> NSToolbarItem? {
        items.first { $0.itemIdentifier == id }
    }
    func numberOfRows(in tableView: NSTableView) -> Int { 20 }
    func tableView(_ tableView: NSTableView, objectValueFor tableColumn: NSTableColumn?, row: Int) -> Any? {
        "Album \(row)"
    }
}
func descendants<T: NSView>(_ type: T.Type, in view: NSView) -> [T] {
    ((view as? T).map { [$0] } ?? []) + view.subviews.flatMap { descendants(type, in: $0) }
}
func settle(_ window: NSWindow) {
    window.contentView?.layoutSubtreeIfNeeded()
    RunLoop.current.run(until: Date(timeIntervalSinceNow: 0.1))
    window.contentView?.layoutSubtreeIfNeeded()
}
func checkPanes(_ split: NSSplitView) {
    for (index, pane) in split.subviews.enumerated() {
        precondition(!pane.isHidden && pane.frame.height > 0)
        precondition(split.bounds.contains(pane.frame))
        precondition(pane.frame.height >= DatabaseBrowserLayout.minimumPaneHeight(in: split, at: index) - 1)
        if index > 0 { precondition(split.subviews[index - 1].frame.maxY < pane.frame.minY) }
    }
}
@main struct Test {
    static func main() {
        _ = NSApplication.shared
        let host = Host()
        for path in CommandLine.arguments.dropFirst() {
            var objects: NSArray?
            let url = URL(fileURLWithPath: path)
            let bundle = Bundle(url: url.deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent())!
            let nib = NSNib(nibNamed: url.deletingPathExtension().lastPathComponent, bundle: bundle)!
            precondition(nib.instantiate(withOwner: nil, topLevelObjects: &objects))
            let views = objects!.compactMap { $0 as? NSView }
            let split = views.first { $0 is NSSplitView } as! NSSplitView
            let filters = views.filter { $0.subviews.first is NSPopUpButton }
            let searchView = views.first { $0.subviews.first is NSSearchField }!
            let search = searchView.subviews.first as! NSSearchField
            let buttons = searchView.subviews.compactMap { $0 as? NSButton }
            let soundex = buttons[0], results = buttons[1]
            results.isHidden = true
            for view in filters { DatabaseBrowserLayout.prepareFilterView(view) }
            DatabaseBrowserLayout.prepareSearchView(searchView)
            // Rebuilding/customizing the toolbar must not add duplicate constraints.
            DatabaseBrowserLayout.prepareSearchView(searchView)
            for view in filters { DatabaseBrowserLayout.prepareFilterView(view) }

            let window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 1100, height: 700),
                                  styleMask: [.titled, .closable, .resizable], backing: .buffered, defer: false)
            window.isReleasedWhenClosed = false
            let toolbar = NSToolbar(identifier: .init("DatabaseLayoutTest"))
            host.items = (filters + [searchView]).enumerated().map { index, view in
                let item = NSToolbarItem(itemIdentifier: .init("control\(index)"))
                item.label = "Filter \(index)"
                item.view = view
                return item
            }
            toolbar.delegate = host
            toolbar.displayMode = .iconAndLabel
            window.toolbar = toolbar
            split.frame = NSRect(x: 0, y: 0, width: 192, height: 600)
            window.contentView!.addSubview(split)
            DatabaseBrowserLayout.prepareSidebar(split)
            for (index, pane) in split.subviews.enumerated() {
                pane.frame = NSRect(x: 0, y: 0, width: 192, height: index == 2 ? 598 : 0)
            }
            DatabaseBrowserLayout.layoutSidebar(split)
            checkPanes(split)
            precondition(split.autosaveName == nil)
            let saved = split.subviews.map(\.frame)
            DatabaseBrowserLayout.layoutSidebar(split)
            precondition(split.subviews.map(\.frame) == saved)
            for height in [350.0, 200.0, 830.0] {
                split.setFrameSize(NSSize(width: 192, height: height))
                DatabaseBrowserLayout.layoutSidebar(split)
                checkPanes(split)
            }
            for table in descendants(NSTableView.self, in: split) {
                table.dataSource = host
                table.reloadData()
            }
            window.orderFront(nil)
            settle(window)
            for table in descendants(NSTableView.self, in: split) {
                let scroll = table.enclosingScrollView!
                precondition(scroll is DatabaseSidebarScrollView)
                table.scrollRowToVisible(19)
                table.selectRowIndexes(IndexSet(integer: 0), byExtendingSelection: false)
                table.scrollRowToVisible(0)
                settle(window)
                scroll.tile()
                let header = table.headerView!
                let headerFrame = header.convert(header.bounds, to: scroll)
                precondition(!headerFrame.intersects(scroll.contentView.frame), "Header overlaps scrollable rows")
                precondition(scroll.frame.width <= scroll.superview!.bounds.width)
            }
            for mode in [NSToolbar.DisplayMode.iconAndLabel, .iconOnly] {
                toolbar.displayMode = mode
                for showResults in [false, true] {
                    results.isHidden = !showResults
                    settle(window)
                    let searchFrame = search.convert(search.bounds, to: searchView)
                    let soundexFrame = soundex.convert(soundex.bounds, to: searchView)
                    precondition(searchFrame.maxX + 4 <= soundexFrame.minX, "Soundex overlaps search")
                    precondition(abs(searchFrame.midY - soundexFrame.midY) < 1)
                    precondition(search.frame.height >= search.intrinsicContentSize.height)
                    if showResults {
                        let resultFrame = results.convert(results.bounds, to: searchView)
                        precondition(soundexFrame.maxX + 4 <= resultFrame.minX)
                    }
                    for view in filters {
                        let popup = descendants(NSPopUpButton.self, in: view).first!
                        let frame = popup.convert(popup.bounds, to: view)
                        precondition(abs(frame.midY - view.bounds.midY) < 1)
                        precondition(popup.frame.height >= popup.intrinsicContentSize.height)
                        precondition(view.bounds.contains(frame))
                    }
                }
            }
            window.close()
            print("PASS: \(URL(fileURLWithPath: path).lastPathComponent): sidebar recovery, resize, headers, toolbar controls and result button")
        }
    }
}
'''

with tempfile.TemporaryDirectory(prefix='horos-database-browser-') as folder:
    work = Path(folder)
    resources = work / 'Probe.bundle/Contents/Resources'
    resources.mkdir(parents=True)
    (resources.parent / 'Info.plist').write_bytes(plistlib.dumps({
        'CFBundleIdentifier': 'org.horosproject.database-layout-test',
        'CFBundlePackageType': 'BNDL',
    }))
    nibs = []
    for locale in ('en', 'ja-JP', 'it-IT', 'es'):
        source = ET.parse(root / f'Horos/Resources/{locale}.lproj/MainMenu.xib').getroot()
        document = ET.Element('document', source.attrib)
        for dependency in source.findall('dependencies'):
            document.append(deepcopy(dependency))
        objects = ET.SubElement(document, 'objects')
        ET.SubElement(objects, 'customObject', id='-2', userLabel="File's Owner", customClass='NSObject')
        ET.SubElement(objects, 'customObject', id='-1', userLabel='First Responder', customClass='FirstResponder')
        ET.SubElement(objects, 'customObject', id='-3', userLabel='Application', customClass='NSObject')
        for identifier in ('11581', '14781', '11606', '14158'):
            view = deepcopy(source.find(f'.//*[@id="{identifier}"]'))
            for node in view.iter():
                if node.get('customClass') != 'HorosDatabaseSidebarScrollView':
                    node.attrib.pop('customClass', None)
                for connection in list(node.findall('connections')):
                    node.remove(connection)
            objects.append(view)
        xib = work / f'{locale}.xib'
        ET.ElementTree(document).write(xib, encoding='utf-8', xml_declaration=True)
        nib = resources / f'{locale}.nib'
        compiled = subprocess.run(['xcrun', 'ibtool', '--compile', str(nib), str(xib)], capture_output=True, text=True)
        if compiled.returncode:
            raise RuntimeError(compiled.stdout + compiled.stderr)
        nibs.append(nib)
    swift = work / 'Test.swift'
    swift.write_text(code)
    binary = work / 'test'
    subprocess.run(['xcrun', 'swiftc', str(root / 'Horos/Sources/DatabaseBrowserLayout.swift'),
                    str(swift), '-o', str(binary)], check=True)
    subprocess.run([str(binary), *map(str, nibs)], check=True)
