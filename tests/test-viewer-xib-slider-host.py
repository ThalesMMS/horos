#!/usr/bin/env python3
"""Viewer.xib sliders must not grow AttributeGraph hosts (#388)."""
import re
import subprocess
import tempfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
helper = root / 'Horos/Sources/HorosCellSlider.swift'
assert helper.is_file(), 'HorosCellSlider.swift is the cell-drawn host that replaces NSSlider Aquaduck'

slider_tag = re.compile(r'<slider\s[^>]*>')
cell_tag = re.compile(r'<sliderCell\s[^>]*>')
for xib in (root / 'Horos/Resources/en.lproj/Viewer.xib',
            root / 'Horos/Resources/ja-JP.lproj/Viewer.xib'):
    text = xib.read_text()
    sliders = slider_tag.findall(text)
    cells = cell_tag.findall(text)
    assert sliders and cells, f'{xib}: Viewer.xib lost its sliders'
    assert len(sliders) == len(cells), f'{xib}: {len(sliders)} sliders, {len(cells)} cells'
    missing = [tag for tag in sliders if 'customClass="HorosCellSlider"' not in tag]
    assert not missing, f'{xib}: sliders still decode as stock NSSlider: {missing[:2]}'
    missing_cells = [tag for tag in cells if 'customClass="HorosCellSliderCell"' not in tag]
    assert not missing_cells, f'{xib}: slider cells still decode as NSSliderCell: {missing_cells[:2]}'

code = r'''
import AppKit
import Darwin
import Foundation

func residentMB() -> Double {
    var info = task_vm_info_data_t()
    var count = mach_msg_type_number_t(MemoryLayout<task_vm_info_data_t>.stride / MemoryLayout<natural_t>.size)
    let kr = withUnsafeMutablePointer(to: &info) {
        $0.withMemoryRebound(to: integer_t.self, capacity: Int(count)) {
            task_info(mach_task_self_, task_flavor_t(TASK_VM_INFO), $0, &count)
        }
    }
    guard kr == KERN_SUCCESS else { return -1 }
    return Double(info.phys_footprint) / (1024.0 * 1024.0)
}

func settle(_ seconds: Double) {
    let until = Date(timeIntervalSinceNow: seconds)
    while until.timeIntervalSinceNow > 0 {
        RunLoop.current.run(mode: .default, before: Date(timeIntervalSinceNow: 0.05))
    }
}

func hostingViews(in view: NSView) -> Int {
    var count = 0
    let name = NSStringFromClass(type(of: view))
    if name.contains("Hosting") || name.contains("SliderWrapper") || name.contains("LiftPortal") {
        count += 1
    }
    for sub in view.subviews { count += hostingViews(in: sub) }
    return count
}

func sliders(in view: NSView) -> [NSSlider] {
    var found: [NSSlider] = []
    if let slider = view as? NSSlider { found.append(slider) }
    for sub in view.subviews { found.append(contentsOf: sliders(in: sub)) }
    return found
}

@main
struct Probe {
    static func main() {
        _ = NSApplication.shared
        let count = Int(CommandLine.arguments[2])!
        let nib = NSNib(nibData: try! Data(contentsOf: URL(fileURLWithPath: CommandLine.arguments[1])), bundle: nil)

        var warmTop: NSArray?
        let warmOwner = NSWindowController()
        precondition(nib.instantiate(withOwner: warmOwner, topLevelObjects: &warmTop))
        let warmWindow = (warmTop as! [Any]).compactMap { $0 as? NSWindow }.first!
        warmWindow.orderFront(nil)
        warmWindow.displayIfNeeded()
        settle(0.2)
        let loaded = sliders(in: warmWindow.contentView!)
        precondition(loaded.count == count, "expected \(count) sliders, got \(loaded.count)")
        precondition(loaded.allSatisfy { $0 is HorosCellSlider }, "nib decoded stock NSSlider")
        precondition(loaded.allSatisfy { $0.cell is HorosCellSliderCell }, "nib decoded stock NSSliderCell")
        precondition(hostingViews(in: warmWindow.contentView!) == 0, "SwiftUI hosts survived decode")
        let probe = loaded.first { $0.numberOfTickMarks == 0 } ?? loaded[0]
        probe.doubleValue = 40
        precondition(abs(probe.doubleValue - 40) < 0.01, "cell-drawn slider dropped its value")
        warmWindow.close()
        warmTop = nil
        settle(0.4)

        let baseline = residentMB()
        var lastHosts = 0
        for cycle in 1...12 {
            var top: NSArray?
            let owner = NSWindowController()
            precondition(nib.instantiate(withOwner: owner, topLevelObjects: &top), "cycle \(cycle): nib load failed")
            let window = (top as! [Any]).compactMap { $0 as? NSWindow }.first!
            window.orderFront(nil)
            window.displayIfNeeded()
            settle(0.1)
            lastHosts = hostingViews(in: window.contentView!)
            precondition(lastHosts == 0, "cycle \(cycle): \(lastHosts) SwiftUI hosts")
            window.close()
            top = nil
            settle(0.25)
        }
        settle(0.8)
        let end = residentMB()
        let delta = end - baseline
        precondition(delta < 25, String(format: "12 cycles grew %.1f MB (baseline %.1f, end %.1f)", delta, baseline, end))
        print(String(format: "PASS: %d HorosCellSlider(s), 12 cycles, hosts=0, %+.1f MB", count, delta))
    }
}
'''

xib_sliders = []
# Match Viewer.xib: one 100-tick mini slider plus the rest of the panel.
specs = [
    (100, 'mini', 100),
    (45, 'mini', 128),
    (0, 'small', 60),
    (1, 'mini', 1),
    (50, 'mini', 50),
    (30, 'mini', 90),
    (30, 'mini', 90),
    (10, 'mini', 10),
    (0, 'mini', 1),
    (20, 'regular', 20),
    (50, 'mini', 50),
    (30, 'mini', 90),
    (30, 'mini', 90),
    (0, 'small', 256),
    (0, 'mini', 60),
    (50, 'mini', 50),
    (30, 'mini', 90),
    (30, 'mini', 90),
    (0, 'mini', 1),
    (0, 'mini', 1),
    (0, 'mini', 1),
]
for index, (ticks, size, max_value) in enumerate(specs):
    tick_attr = f' numberOfTickMarks="{ticks}"' if ticks else ''
    size_attr = '' if size == 'regular' else f' controlSize="{size}"'
    y = 8 + index * 18
    xib_sliders.append(f'''
                    <slider customClass="HorosCellSlider" verticalHuggingPriority="750" fixedFrame="YES" translatesAutoresizingMaskIntoConstraints="NO" id="s{index}">
                        <rect key="frame" x="8" y="{y}" width="480" height="16"/>
                        <sliderCell key="cell" customClass="HorosCellSliderCell"{size_attr} continuous="YES" alignment="left" maxValue="{max_value}" doubleValue="1" tickMarkPosition="below"{tick_attr} allowsTickMarkValuesOnly="YES" sliderType="linear" id="c{index}"/>
                    </slider>''')

xib = f'''<?xml version="1.0" encoding="UTF-8"?>
<document type="com.apple.InterfaceBuilder3.Cocoa.XIB" version="3.0" toolsVersion="24127" targetRuntime="MacOSX.Cocoa" propertyAccessControl="none" useAutolayout="YES">
    <objects>
        <customObject id="-2" userLabel="File's Owner" customClass="NSWindowController">
            <connections>
                <outlet property="window" destination="w1" id="o1"/>
            </connections>
        </customObject>
        <customObject id="-1" userLabel="First Responder" customClass="FirstResponder"/>
        <customObject id="-3" userLabel="Application" customClass="NSObject"/>
        <window title="Probe" releasedWhenClosed="YES" visibleAtLaunch="NO" id="w1">
            <windowStyleMask key="styleMask" titled="YES" closable="YES"/>
            <rect key="contentRect" x="0" y="0" width="500" height="400"/>
            <view key="contentView" id="cv">
                <rect key="frame" x="0" y="0" width="500" height="400"/>
                <subviews>
{''.join(xib_sliders)}
                </subviews>
            </view>
        </window>
    </objects>
</document>
'''

with tempfile.TemporaryDirectory(prefix='horos-viewer-slider-host-') as folder:
    folder = Path(folder)
    source_xib = folder / 'Sliders.xib'
    compiled = folder / 'Sliders.nib'
    source_xib.write_text(xib)
    subprocess.run(['ibtool', '--compile', str(compiled), str(source_xib)], check=True)
    (folder / 'test.swift').write_text(code)
    subprocess.run([
        'xcrun', 'swiftc', '-swift-version', '5', '-parse-as-library',
        str(helper), str(folder / 'test.swift'),
        '-framework', 'AppKit',
        '-o', str(folder / 'test'),
    ], check=True)
    subprocess.run([str(folder / 'test'), str(compiled), str(len(specs))], check=True)

print(f'PASS: Viewer.xib sliders are HorosCellSlider, twelve cycles keep AttributeGraph hosts at 0')
