#!/usr/bin/env python3
"""Preference panes must stay readable in both appearances."""
import re, subprocess, sys, tempfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
panes = root / 'Preference Panes'
failures = []

# 1. A cell that paints its own background must take that colour from the
#    system catalog, otherwise it keeps a light background under a dark
#    appearance while its text colour follows the appearance.
for xib in sorted(panes.rglob('*.xib')):
    text = xib.read_text(errors='replace')
    for m in re.finditer(r'<(\w*[Cc]ell|textView|tableView|outlineView|box)\b[^>]*drawsBackground="YES"[^>]*>', text):
        end = text.find('</' + m.group(1) + '>', m.end())
        for c in re.finditer(r'<color key="backgroundColor"([^>]*)/>', text[m.end():end]):
            if 'catalog="System"' not in c.group(1):
                failures.append(f'{xib.relative_to(root)}: painted background is not a system colour:{c.group(1)}')
    for c in re.finditer(r'<color key="textColor"([^>]*)/>', text):
        if 'catalog="System"' not in c.group(1):
            failures.append(f'{xib.relative_to(root)}: text colour is not a system colour:{c.group(1)}')

# 2. No pane may force a fixed text colour in code either.
static = re.compile(r'setTextColor:\s*\[NSColor (black|white)Color\]'
                    r'|textColor\s*=\s*\[NSColor (black|white)Color\]')
for source in sorted(list(panes.rglob('*.m')) + list(panes.rglob('*.mm'))):
    body = source.read_bytes().decode('latin1')
    for m in static.finditer(body):
        failures.append(f'{source.relative_to(root)}:{body[:m.start()].count(chr(10))+1}: fixed text colour {m.group(0)}')

if failures:
    print('FAIL:'); [print(' ', f) for f in failures]; sys.exit(1)

# 3. Compile the one pane that paints text field backgrounds and read those
#    fields back: the colour must actually resolve differently per appearance.
nib_source = panes / 'OSIHangingPreferencePane/Base.lproj/OSIHangingPreferencePanePref.xib'
nib_probe = r"""
import AppKit
// The pane's File's Owner exposes binding keys this harness does not provide.
final class Owner: NSObject {
    override func value(forUndefinedKey key: String) -> Any? { nil }
    override func setValue(_ value: Any?, forUndefinedKey key: String) {}
    override func value(forKey key: String) -> Any? { nil }
}
@main struct Probe {
 static func main() {
  _ = NSApplication.shared
  let url = URL(fileURLWithPath: CommandLine.arguments[1])
  let bundle = Bundle(url: url.deletingLastPathComponent()
                            .deletingLastPathComponent()
                            .deletingLastPathComponent())
  var objects: NSArray? = nil
  guard let nib = NSNib(nibNamed: url.deletingPathExtension().lastPathComponent, bundle: bundle),
        nib.instantiate(withOwner: Owner(), topLevelObjects: &objects) else {
    print("could not load the compiled pane"); exit(1)
  }
  func walk(_ view: NSView, _ found: inout [NSTextField]) {
    if let field = view as? NSTextField, field.drawsBackground { found.append(field) }
    view.subviews.forEach { walk($0, &found) }
  }
  var fields: [NSTextField] = []
  for object in objects ?? [] {
    if let window = object as? NSWindow, let content = window.contentView { walk(content, &fields) }
    if let view = object as? NSView { walk(view, &fields) }
  }
  precondition(fields.count >= 4, "expected the panel's painted fields, found \(fields.count)")
  for field in fields {
    var light = NSColor.black, dark = NSColor.black
    NSAppearance(named: .aqua)!.performAsCurrentDrawingAppearance {
      light = field.backgroundColor!.usingColorSpace(.sRGB)! }
    NSAppearance(named: .darkAqua)!.performAsCurrentDrawingAppearance {
      dark = field.backgroundColor!.usingColorSpace(.sRGB)! }
    precondition(light.redComponent > 0.9, "light background should stay light")
    precondition(dark.redComponent < 0.4,
      "a painted field keeps a light background under the dark appearance while its "
      + "text follows it: \(dark)")
  }
  print("nib fields: \(fields.count) painted backgrounds, all following the appearance")
 }
}
"""
with tempfile.TemporaryDirectory(prefix='horos-prefs-nib-') as folder:
    p = Path(folder)
    compiled = p / 'Bundle/Contents/Resources/Base.lproj'
    compiled.mkdir(parents=True)
    subprocess.run(['/usr/bin/ibtool', '--errors', '--compile',
                    str(compiled / 'OSIHangingPreferencePanePref.nib'), str(nib_source)],
                   check=True, stdout=subprocess.DEVNULL)
    (p / 'probe.swift').write_text(nib_probe)
    subprocess.run(['xcrun', 'swiftc', '-swift-version', '5', '-parse-as-library',
                    str(p / 'probe.swift'), '-framework', 'AppKit', '-o', str(p / 'probe')], check=True)
    subprocess.run([str(p / 'probe'), str(compiled / 'OSIHangingPreferencePanePref.nib')], check=True)

# 3. The semantic colours the panes now rely on have to actually contrast, in
#    both appearances, and the replaced pairing has to fail the same measure.
code = r'''
import AppKit

func srgb(_ color: NSColor) -> (Double, Double, Double) {
    let c = color.usingColorSpace(.sRGB) ?? .black
    return (Double(c.redComponent), Double(c.greenComponent), Double(c.blueComponent))
}
func luminance(_ c: (Double, Double, Double)) -> Double {
    func f(_ v: Double) -> Double { v <= 0.03928 ? v/12.92 : pow((v+0.055)/1.055, 2.4) }
    return 0.2126*f(c.0) + 0.7152*f(c.1) + 0.0722*f(c.2)
}
/// Flattens any alpha the colour carries onto the background it is drawn over.
func over(_ color: NSColor, _ backdrop: NSColor) -> NSColor {
    guard let c = color.usingColorSpace(.sRGB), let b = backdrop.usingColorSpace(.sRGB) else { return color }
    let a = c.alphaComponent
    return NSColor(srgbRed: c.redComponent*a + b.redComponent*(1-a),
                   green: c.greenComponent*a + b.greenComponent*(1-a),
                   blue: c.blueComponent*a + b.blueComponent*(1-a), alpha: 1)
}
func contrast(_ a: NSColor, _ b: NSColor) -> Double {
    let (l1, l2) = (luminance(srgb(a)), luminance(srgb(b)))
    return (max(l1, l2) + 0.05) / (min(l1, l2) + 0.05)
}

@main struct Test {
 static func main() {
  _ = NSApplication.shared
  var worstFixed = Double.greatestFiniteMagnitude
  for name in [NSAppearance.Name.aqua, .darkAqua] {
   let appearance = NSAppearance(named: name)!
   appearance.performAsCurrentDrawingAppearance {
    // The WW/WL preset fields: text on the background they now paint.
    let field = contrast(.controlTextColor, .textBackgroundColor)
    // The custom-annotation labels, enabled and disabled, on the pane.
    let label = contrast(.labelColor, .windowBackgroundColor)
    let disabled = contrast(.disabledControlTextColor, .windowBackgroundColor)
    // The drop placeholder wash over the layout view it sits on.
    let wash = contrast(over(.unemphasizedSelectedContentBackgroundColor, .controlBackgroundColor),
                        .controlBackgroundColor)
    precondition(field >= 4.5, "\(name.rawValue): field text contrast \(field)")
    precondition(label >= 4.5, "\(name.rawValue): label contrast \(label)")
    precondition(disabled >= 1.8, "\(name.rawValue): disabled label contrast \(disabled)")
    // Visible enough to mark the drop area, subtle enough not to be a block.
    precondition(wash > 1.1 && wash < 2.0, "\(name.rawValue): placeholder wash \(wash)")
    // The half-white wash it replaced was invisible in light and a block in dark.
    let previousWash = contrast(over(NSColor.white.withAlphaComponent(0.5), .controlBackgroundColor),
                                .controlBackgroundColor)
    precondition(previousWash <= 1.1 || previousWash >= 2.0, "previous wash \(previousWash)")

    // What the panes used to do, measured the same way.
    worstFixed = min(worstFixed, contrast(.controlTextColor, NSColor(white: 1, alpha: 1)))
    worstFixed = min(worstFixed, contrast(.black, .windowBackgroundColor))
   }
  }
  precondition(worstFixed < 4.5, "the replaced fixed colours should fail this measure, got \(worstFixed)")
  print("PASS: painted backgrounds and text colours are system colours in every pane; the compiled pane resolves them per appearance; measured contrast holds in light and dark, and the replaced fixed colours do not")
 }
}
'''
with tempfile.TemporaryDirectory(prefix='horos-prefs-dark-') as folder:
    p = Path(folder)
    (p / 'test.swift').write_text(code)
    subprocess.run(['xcrun', 'swiftc', '-swift-version', '5', '-parse-as-library',
                    str(p / 'test.swift'), '-framework', 'AppKit', '-o', str(p / 'test')], check=True)
    subprocess.run([str(p / 'test')], check=True)
