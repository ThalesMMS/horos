#!/usr/bin/env python3
"""Exercise the Swift export layout with real AppKit constraints and controlled scales."""
from pathlib import Path
import subprocess, tempfile, sys
root=Path(__file__).resolve().parents[1]
code=r'''
import AppKit
final class ScaledView: NSView {
    var scale: CGFloat = 1
    override func convertFromBacking(_ size: NSSize) -> NSSize {
        NSSize(width: size.width / scale, height: size.height / scale)
    }
}
@main struct Test {
    static func main() {
        _ = NSApplication.shared
        for scale: CGFloat in [1, 2] {
            for pixels: CGFloat in [0, 512, 768] {
                let root = NSView(frame: NSRect(x: 0, y: 0, width: 1000, height: 800))
                let view = ScaledView(frame: .zero)
                view.scale = scale
                view.translatesAutoresizingMaskIntoConstraints = false
                view.autoresizingMask = [.width, .height]
                root.addSubview(view)
                let constraints = [view.leadingAnchor.constraint(equalTo: root.leadingAnchor, constant: 7),
                    view.bottomAnchor.constraint(equalTo: root.bottomAnchor, constant: 8),
                    view.widthAnchor.constraint(equalTo: root.widthAnchor, constant: -14),
                    view.heightAnchor.constraint(equalTo: root.heightAnchor, constant: -28)]
                NSLayoutConstraint.activate(constraints)
                root.layoutSubtreeIfNeeded()
                let before = view.frame
                precondition(before.size == NSSize(width: 986, height: 772))
                let requestedFrame = pixels == 0 ? NSRect(x: 3, y: 9, width: 854, height: 503) : before
                if pixels == 0 { view.frame = requestedFrame }
                let layout = VRExportLayout(view: view, pixelSize: pixels)
                root.layoutSubtreeIfNeeded()
                if pixels == 0 {
                    for _ in 0..<5 {
                        root.needsLayout = true
                        root.layoutSubtreeIfNeeded()
                        precondition(view.frame == requestedFrame, "Current frame changed between exported frames")
                    }
                } else {
                    precondition(view.frame.width * scale == pixels && view.frame.height * scale == pixels)
                    precondition(view.frame.midX == root.bounds.midX && view.frame.midY == root.bounds.midY)
                }
                precondition(constraints.allSatisfy { !$0.isActive })
                layout.restore()
                precondition(view.frame == before)
                precondition(constraints.allSatisfy { $0.isActive })
                precondition(!view.translatesAutoresizingMaskIntoConstraints)
                precondition(view.autoresizingMask == [.width, .height])
                layout.restore()
                precondition(view.frame == before)
            }
        }
        print("PASS: Current and 512/768 pixel targets at controlled 1x/2x scales survive AppKit layout and restore frame, constraints and autoresizing")
    }
}
'''
with tempfile.TemporaryDirectory(prefix='horos-export-layout-') as d:
 p=Path(d);(p/'test.swift').write_text(code)
 source = subprocess.check_output(['git','show',sys.argv[1]+':Horos/Sources/VRExportLayout.swift']) if len(sys.argv)>1 else (root/'Horos/Sources/VRExportLayout.swift').read_bytes()
 (p/'layout.swift').write_bytes(source)
 subprocess.run(['xcrun','swiftc','-swift-version','5','-parse-as-library',str(p/'layout.swift'),str(p/'test.swift'),'-framework','AppKit','-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
