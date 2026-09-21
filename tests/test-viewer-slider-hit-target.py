#!/usr/bin/env python3
"""Every Viewer.xib slider must lay out tall enough to be drawn and clicked.

`HorosCellSliderCell` suppresses the macOS 26 visual provider, and the stock
`NSSliderCell` measures itself through exactly that provider: without a
replacement its `cellSize` is `NSZeroSize`, so `intrinsicContentSize` has no
height. Every slider in Viewer.xib that carries no explicit height constraint
then lays out zero points tall -- invisible, and missed by `hitTest:`, so the
click never reaches `mouseDown:` and the control does nothing at all. Twelve
sliders were in that state, among them the structuring element radius of the
brush ROI close/open/dilate/erode sheet.

The nib is neutralised (custom classes other than the sliders are dropped, so
the probe does not need the whole app linked in) and then instantiated for real:
the check is the laid-out frame, not the XML.
"""
import re
import subprocess
import tempfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
helper = root / 'Horos/Sources/HorosCellSlider.swift'
navigation = root / 'Horos/Sources/ImageNavigationSlider.swift'
xibs = [root / 'Horos/Resources/en.lproj/Viewer.xib',
        root / 'Horos/Resources/ja-JP.lproj/Viewer.xib']
for source in [helper, navigation, *xibs]:
    assert source.is_file(), f'missing {source}'

# The sliders that only Auto Layout sizes, i.e. the ones the zero cell size
# collapsed. Named by outlet so a future XIB edit that drops one is visible.
COLLAPSED_BEFORE = {
    '1498': 'structuringElementRadiusSlider',   # close/open/dilate/erode radius
    '15': 'speedSlider',                        # cine speed
    '508': 'moviePosSlider',                    # 4D frame position
    '1384': 'quicktimeFrom', '1386': 'quicktimeInterval', '1387': 'quicktimeTo',
    '1353': 'dcmFrom', '1351': 'dcmInterval', '1355': 'dcmTo',
    '1877': 'printFrom', '1878': 'printInterval', '1872': 'printTo',
}

KEEP_CLASSES = {'HorosCellSlider', 'HorosImageNavigationSlider', 'HorosCellSliderCell'}


def neutralise(text):
    """Drop every custom class the probe cannot link, and label each slider."""
    text = re.sub(r'\s*customClass="([^"]+)"',
                  lambda m: f' customClass="{m.group(1)}"' if m.group(1) in KEEP_CLASSES else '',
                  text)
    text = text.replace('<customObject id="-2" userLabel="File\'s Owner">',
                        '<customObject id="-2" userLabel="File\'s Owner" customClass="ForgivingOwner">')
    text = text.replace('<customObject id="-1" userLabel="First Responder"/>',
                        '<customObject id="-1" userLabel="First Responder" customClass="FirstResponder"/>')

    def label(match):
        whole = match.group(0)
        xid = re.search(r'\sid="([^"]+)"', whole).group(1)
        return whole[:-1] + f' identifier="xib{xid}">'

    return re.sub(r'<slider\s[^>]*>', label, text)


owner_header = '''
#import <AppKit/AppKit.h>
@interface ForgivingOwner : NSObject
@property (nonatomic, strong) NSMutableDictionary *values;
@property (nonatomic, assign) NSInteger radiusActionCalls;
- (IBAction) setStructuringElementRadius: (id) sender;
@end
'''

owner_source = '''
#import "Owner.h"
@implementation ForgivingOwner
- (instancetype) init { if ((self = [super init])) { _values = [NSMutableDictionary new]; } return self; }
- (void) setValue:(id)value forUndefinedKey:(NSString *)key { if (value) _values[key] = value; }
- (id) valueForUndefinedKey:(NSString *)key { return _values[key]; }
- (void) setNilValueForKey:(NSString *)key {}
- (IBAction) setStructuringElementRadius: (id) sender { _radiusActionCalls++; }
@end
'''

code = r'''
import AppKit

func fail(_ message: String) -> Never {
    print("FAIL: \(message)")
    exit(1)
}

func sliders(in view: NSView, into out: inout [NSSlider]) {
    if let slider = view as? NSSlider { out.append(slider) }
    for sub in view.subviews { sliders(in: sub, into: &out) }
}

let app = NSApplication.shared
app.setActivationPolicy(.accessory)

// A cell with no visual provider still has to measure itself, or Auto Layout
// gives the slider no height. The numbers are what a stock NSSlider reports.
for (size, ticked, bare) in [(NSControl.ControlSize.regular, CGFloat(16), CGFloat(16)),
                             (.small, 18, 14),
                             (.mini, 16, 12)] {
    for (ticks, expected) in [(20, ticked), (0, bare)] {
        let slider = HorosCellSlider(frame: NSRect(x: 0, y: 0, width: 200, height: 24))
        slider.controlSize = size
        slider.numberOfTickMarks = ticks
        let intrinsic = slider.intrinsicContentSize.height
        if intrinsic != expected {
            fail("controlSize \(size.rawValue) with \(ticks) ticks: intrinsic height \(intrinsic), expected \(expected)")
        }
        if slider.cell?.cellSize.height != expected {
            fail("controlSize \(size.rawValue) with \(ticks) ticks: cellSize \(slider.cell?.cellSize ?? .zero)")
        }
    }
}

var checked = 0
var probeSlider: HorosCellSlider?
var probeWindow: NSWindow?

for path in CommandLine.arguments.dropFirst() {
    let owner = ForgivingOwner()
    var top: NSArray?
    let nib = NSNib(nibData: try! Data(contentsOf: URL(fileURLWithPath: path)), bundle: nil)
    guard nib.instantiate(withOwner: owner, topLevelObjects: &top) else {
        fail("\(path): nib did not instantiate")
    }

    var roots: [(String, NSView)] = []
    for object in (top as! [Any]) {
        if let window = object as? NSWindow, let content = window.contentView {
            roots.append(("window \"\(window.title)\"", content))
        } else if let view = object as? NSView {
            roots.append(("top level view", view))
        }
    }

    for (label, root) in roots {
        var found: [NSSlider] = []
        sliders(in: root, into: &found)
        guard !found.isEmpty else { continue }
        root.layoutSubtreeIfNeeded()
        for slider in found {
            checked += 1
            let name = slider.identifier?.rawValue ?? "unnamed"
            if !(slider is HorosCellSlider) {
                fail("\(path) \(label): \(name) decoded as \(NSStringFromClass(type(of: slider)))")
            }
            if slider.frame.height < 1 || slider.frame.width < 1 {
                fail("\(path) \(label): \(name) laid out \(slider.frame.width)x\(slider.frame.height); "
                     + "a slider this size cannot be drawn or clicked")
            }
            if slider.identifier?.rawValue == "xib1498", probeSlider == nil {
                probeSlider = slider as? HorosCellSlider
                probeWindow = slider.window
                slider.target = owner
                slider.action = #selector(ForgivingOwner.setStructuringElementRadius(_:))
            }
        }
    }
}

// The reported bug, end to end: a click on the radius slider of the brush ROI
// morphology sheet has to move the knob and fire the action. Before the cell
// could measure itself the window's hitTest: returned the content view here.
guard let slider = probeSlider, let window = probeWindow else {
    fail("the structuring element radius slider (xib1498) is no longer in Viewer.xib")
}
let ownerOfSlider = slider.target as! ForgivingOwner
window.orderFront(nil)
window.layoutIfNeeded()

let target = NSPoint(x: slider.trackRect.minX + slider.trackRect.width * 0.75, y: slider.bounds.midY)
let inWindow = slider.convert(target, to: nil)
guard window.contentView?.hitTest(inWindow) === slider else {
    fail("a click in the middle of the radius slider lands on "
         + "\(window.contentView?.hitTest(inWindow).map { NSStringFromClass(type(of: $0)) } ?? "nothing")")
}

let before = slider.doubleValue
let down = NSEvent.mouseEvent(with: .leftMouseDown, location: inWindow, modifierFlags: [], timestamp: 0,
                              windowNumber: window.windowNumber, context: nil,
                              eventNumber: 1, clickCount: 1, pressure: 1)!
let up = NSEvent.mouseEvent(with: .leftMouseUp, location: inWindow, modifierFlags: [], timestamp: 0.1,
                            windowNumber: window.windowNumber, context: nil,
                            eventNumber: 2, clickCount: 1, pressure: 0)!
NSApp.postEvent(up, atStart: false)
window.sendEvent(down)

if slider.doubleValue != 15 {
    fail("a click at three quarters of the radius track gives \(slider.doubleValue), expected 15 (was \(before))")
}
if ownerOfSlider.radiusActionCalls != 1 {
    fail("the radius slider sent its action \(ownerOfSlider.radiusActionCalls) times, expected once")
}
window.orderOut(nil)

print("PASS: \(checked) Viewer.xib sliders lay out with a hit target; the morphology radius slider tracks a click")
'''

with tempfile.TemporaryDirectory(prefix='horos-viewer-slider-hit-') as folder:
    folder = Path(folder)
    (folder / 'Owner.h').write_text(owner_header)
    (folder / 'Owner.m').write_text(owner_source)
    (folder / 'main.swift').write_text(code)

    nibs = []
    for xib in xibs:
        source = folder / f'{xib.parent.name}.xib'
        compiled = folder / f'{xib.parent.name}.nib'
        source.write_text(neutralise(xib.read_text()))
        # Every slider the fix is about must still be one Auto Layout sizes on
        # its own, or the test would pass without exercising anything.
        text = source.read_text()
        for xid, outlet in COLLAPSED_BEFORE.items():
            assert f'identifier="xib{xid}"' in text, f'{xib}: {outlet} (id {xid}) is gone'
            assert not re.search(rf'firstItem="{xid}"[^>]*firstAttribute="height"', text), \
                f'{xib}: {outlet} gained a height constraint; drop it from COLLAPSED_BEFORE'
        subprocess.run(['ibtool', '--compile', str(compiled), str(source)], check=True)
        nibs.append(compiled)

    subprocess.run([
        'xcrun', 'swiftc', '-swift-version', '5',
        '-import-objc-header', str(folder / 'Owner.h'),
        str(helper), str(navigation), str(folder / 'Owner.m'), str(folder / 'main.swift'),
        '-framework', 'AppKit',
        '-o', str(folder / 'test'),
    ], check=True)
    subprocess.run([str(folder / 'test'), *[str(n) for n in nibs]], check=True)

print('PASS: no Viewer.xib slider collapses to a zero hit target in either locale')
