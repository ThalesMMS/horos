// Switch the main display between its native 1x mode and a HiDPI mode whose
// backing scale is 2, so a validation can exercise a real WindowServer scale
// change instead of a simulated one.
//
// This is a genuine mode change on the same panel: AppKit posts
// NSWindowDidChangeBackingProperties, NSScreen.backingScaleFactor becomes 2 and
// the framebuffer is reallocated. It is not a second physical monitor and not a
// window dragged between screens; say so when recording a result.
//
//   xcrun swiftc -O tools/set-display-scale.swift -o build/set-display-scale
//   build/set-display-scale --list
//   build/set-display-scale --scale 2
//   build/set-display-scale --scale 1
//
// The configuration is applied for the login session, so a logout restores the
// display even if a run is interrupted.
import CoreGraphics
import Foundation

struct Mode {
    let mode: CGDisplayMode
    var scale: Double { Double(mode.pixelWidth) / Double(mode.width) }
}

func modes(of display: CGDirectDisplayID) -> [Mode] {
    let options = [kCGDisplayShowDuplicateLowResolutionModes: kCFBooleanTrue!] as CFDictionary
    let all = CGDisplayCopyAllDisplayModes(display, options) as? [CGDisplayMode] ?? []
    return all.filter { $0.isUsableForDesktopGUI() }.map { Mode(mode: $0) }
}

func describe(_ m: CGDisplayMode) -> String {
    String(format: "%dx%d points, %dx%d pixels, scale %.1f, id %d",
           m.width, m.height, m.pixelWidth, m.pixelHeight,
           Double(m.pixelWidth) / Double(m.width), m.ioDisplayModeID)
}

let display = CGMainDisplayID()
guard let current = CGDisplayCopyDisplayMode(display) else {
    FileHandle.standardError.write(Data("no current display mode\n".utf8))
    exit(1)
}

var arguments = Array(CommandLine.arguments.dropFirst())
if arguments.isEmpty || arguments == ["--list"] {
    print("display \(display) current: \(describe(current))")
    for m in modes(of: display).sorted(by: { $0.mode.pixelWidth * $0.mode.pixelHeight > $1.mode.pixelWidth * $1.mode.pixelHeight }) {
        print("  \(describe(m.mode))")
    }
    exit(0)
}

guard arguments.count == 2, arguments[0] == "--scale", let wanted = Double(arguments[1]) else {
    FileHandle.standardError.write(Data("usage: set-display-scale [--list | --scale 1|2]\n".utf8))
    exit(2)
}

// Keep the same pixel dimensions across the switch: the panel does not change,
// only how many points AppKit lays out over those pixels. Picking the widest
// candidate otherwise silently changes the visible area as well as the scale.
let candidates = modes(of: display).filter { abs($0.scale - wanted) < 0.01 }
let sameSize = candidates.filter {
    $0.mode.pixelWidth == current.pixelWidth && $0.mode.pixelHeight == current.pixelHeight
}
guard let target = (sameSize.first ?? candidates.max(by: {
    $0.mode.pixelWidth * $0.mode.pixelHeight < $1.mode.pixelWidth * $1.mode.pixelHeight
}))?.mode else {
    FileHandle.standardError.write(Data("no usable mode with scale \(wanted)\n".utf8))
    exit(1)
}

if target.ioDisplayModeID == current.ioDisplayModeID && target.pixelWidth == current.pixelWidth {
    print("already: \(describe(current))")
    exit(0)
}

var configuration: CGDisplayConfigRef?
guard CGBeginDisplayConfiguration(&configuration) == .success else {
    FileHandle.standardError.write(Data("cannot begin a display configuration\n".utf8))
    exit(1)
}
CGConfigureDisplayWithDisplayMode(configuration, display, target, nil)
guard CGCompleteDisplayConfiguration(configuration, .forSession) == .success else {
    FileHandle.standardError.write(Data("cannot complete the display configuration\n".utf8))
    exit(1)
}

// WindowServer applies the mode asynchronously; report what actually took hold.
for _ in 0..<40 {
    if let now = CGDisplayCopyDisplayMode(display),
       now.pixelWidth == target.pixelWidth, now.width == target.width {
        print("from: \(describe(current))")
        print("to:   \(describe(now))")
        exit(0)
    }
    usleep(250_000)
}
FileHandle.standardError.write(Data("the display did not adopt the requested mode\n".utf8))
exit(1)
