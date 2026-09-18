#!/usr/bin/env python3
"""The app's own filters have menu items (#653).

`+[PluginManager setMenus::::]` makes the plugin menu items from the loaded
bundles' Info.plist. T2 Fit Map and ROI Enhancement are filters the app registers
itself, with no bundle: they were in `plugins` and in no menu, so nothing in the
interface could run them.

`HorosNativeFilterMenus` adds their items - T2 Fit Map to the image filters, ROI
Enhancement to the ROI tools, each sending -executeFilter: to the first responder.
Compiled here with stand-in filters of the same class names:

* both registered: one item each, in its menu, with the action and no target;
* made again: no second item;
* a bundle that declares the title, in a submenu of its own: no second item;
* another filter registered under the title (a compatible external bundle): no item;
* nothing registered: no item.

The source checks that `setMenus::::` adds them before it decides a menu is empty,
and that the file is built into the app.
"""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
failures = []

manager = (root / 'Horos/Sources/PluginManager.m').read_bytes().decode('latin1')
method = manager[manager.index('+ (void) setMenus:(NSMenu*) filtersMenu :(NSMenu*) roisMenu :(NSMenu*) othersMenu :(NSMenu*) dbMenu'):]
call = '[HorosNativeFilterMenus addItemsForPlugins: plugins filtersMenu: filtersMenu roisMenu: roisMenu];'
if call not in method:
    failures.append('setMenus:::: does not add the native filters\' items')
elif method.index(call) > method.index('if( [filtersMenu numberOfItems] < 1)'):
    failures.append('the native items are added after the empty menus got their placeholder')
project = (root / 'Horos.xcodeproj/project.pbxproj').read_text()
if project.count('/* NativeFilterMenus.swift in Sources */') != 2 or 'path = "NativeFilterMenus.swift";' not in project:
    failures.append('NativeFilterMenus.swift is not built into the app')

driver = r'''
import AppKit

@objc(T2FitMapFilter) final class T2FitMapFilter: NSObject {}
@objc(ROIEnhancementFilter) final class ROIEnhancementFilter: NSObject {}
@objc(ExternalT2Filter) final class ExternalT2Filter: NSObject {}

var failed = false
func expect(_ condition: Bool, _ message: String) {
    if !condition { print("FAIL: \(message)"); failed = true }
}
func items(_ menu: NSMenu, _ title: String) -> [NSMenuItem] {
    menu.items.filter { $0.title == title } + menu.items.compactMap { $0.submenu }.flatMap { items($0, title) }
}

let natives: NSDictionary = ["T2 Fit Map": T2FitMapFilter(), "ROI Enhancement": ROIEnhancementFilter()]
var filters = NSMenu(title: "Image Filters"), rois = NSMenu(title: "ROI Tools")
let added = NativeFilterMenus.addItems(for: natives, filtersMenu: filters, roisMenu: rois)
expect(added.count == 2, "two items added, not \(added.count)")
let t2 = items(filters, "T2 Fit Map"), roi = items(rois, "ROI Enhancement")
expect(t2.count == 1 && roi.count == 1, "one item each: T2 \(t2.count), ROI \(roi.count)")
expect(items(rois, "T2 Fit Map").isEmpty && items(filters, "ROI Enhancement").isEmpty, "each item in its own menu")
for item in t2 + roi {
    expect(item.action == NSSelectorFromString("executeFilter:"), "\(item.title) sends \(String(describing: item.action))")
    expect(item.target == nil, "\(item.title) goes to the first responder")
}

NativeFilterMenus.addItems(for: natives, filtersMenu: filters, roisMenu: rois)
expect(items(filters, "T2 Fit Map").count == 1 && items(rois, "ROI Enhancement").count == 1, "made again, still one item each")

filters = NSMenu(title: "Image Filters"); rois = NSMenu(title: "ROI Tools")
let bundle = NSMenu(title: "T2 Fit Map bundle")
bundle.addItem(NSMenuItem(title: "T2 Fit Map", action: NSSelectorFromString("executeFilter:"), keyEquivalent: ""))
filters.addItem(withTitle: "T2 Fit Map bundle", action: nil, keyEquivalent: "").submenu = bundle
NativeFilterMenus.addItems(for: natives, filtersMenu: filters, roisMenu: rois)
expect(items(filters, "T2 Fit Map").count == 1, "a bundle's item of the same title is not duplicated")
expect(items(rois, "ROI Enhancement").count == 1, "the other native item is still added")

filters = NSMenu(title: "Image Filters"); rois = NSMenu(title: "ROI Tools")
let external: NSDictionary = ["T2 Fit Map": ExternalT2Filter(), "ROI Enhancement": ROIEnhancementFilter()]
NativeFilterMenus.addItems(for: external, filtersMenu: filters, roisMenu: rois)
expect(items(filters, "T2 Fit Map").isEmpty, "another filter registered under the title gets no native item")

filters = NSMenu(title: "Image Filters"); rois = NSMenu(title: "ROI Tools")
expect(NativeFilterMenus.addItems(for: NSDictionary(), filtersMenu: filters, roisMenu: rois).isEmpty
       && filters.items.isEmpty && rois.items.isEmpty, "nothing registered, no item")
print(failed ? "FAILED" : "ok")
exit(failed ? 1 : 0)
'''

if not failures:
    with tempfile.TemporaryDirectory(prefix='horos-native-menus-') as temporary:
        work = Path(temporary)
        (work / 'main.swift').write_text(driver)
        built = subprocess.run(['xcrun', 'swiftc', '-module-name', 'NativeMenus', str(root / 'Horos/Sources/NativeFilterMenus.swift'),
                                str(work / 'main.swift'), '-o', str(work / 'menus')], capture_output=True, text=True)
        if built.returncode != 0:
            failures.append('NativeFilterMenus.swift does not build: ' + built.stderr[-1500:])
        else:
            run = subprocess.run([str(work / 'menus')], capture_output=True, text=True, timeout=60)
            if run.returncode != 0:
                failures.append((run.stdout + run.stderr).strip())

if failures:
    print('\n'.join('FAIL: ' + f if not f.startswith('FAIL') else f for f in failures))
    raise SystemExit(1)
print('native filters: T2 Fit Map and ROI Enhancement items, once each, to the first responder')
