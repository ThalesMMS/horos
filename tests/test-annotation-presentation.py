#!/usr/bin/env python3
"""Rasterize overlay/ROI text through Color LCD, sRGB, linear and attached displays."""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
code = r'''
import AppKit
import CoreGraphics
import Foundation

func fail(_ message: String) -> Never {
    FileHandle.standardError.write(Data("FAIL: \(message)\n".utf8))
    exit(1)
}

func expect(_ condition: Bool, _ message: String) {
    if !condition { fail(message) }
}

_ = NSApplication.shared
let profiles = AnnotationPresentation.matrixProfiles()
let names = Set(profiles.map { $0.name })
expect(names.contains("sRGB"), "sRGB profile missing")
expect(names.contains("linear"), "linear profile missing")
expect(names.contains("Color LCD"), "Color LCD family profile missing: \(names.sorted())")
expect(profiles.contains { $0.name.hasPrefix("display:") }, "no attached display profile: \(names.sorted())")
for profile in profiles {
    expect(profile.colorSpace.colorSpaceModel == .rgb, "\(profile.name) is not RGB")
    expect(!AnnotationPresentation.cacheToken(for: profile.colorSpace).isEmpty, "empty token for \(profile.name)")
}

let sRGB = profiles.first { $0.name == "sRGB" }!.colorSpace
let linear = profiles.first { $0.name == "linear" }!.colorSpace
let colorLCD = profiles.first { $0.name == "Color LCD" }!.colorSpace
expect(AnnotationPresentation.cacheToken(for: sRGB) != AnnotationPresentation.cacheToken(for: linear),
       "sRGB and linear must not share a cache token")
expect(AnnotationPresentation.cacheToken(for: colorLCD) != AnnotationPresentation.cacheToken(for: sRGB),
       "Color LCD and sRGB must not share a cache token")
expect(AnnotationPresentation.textureCacheToken(for: nil as Any?) == AnnotationPresentation.cacheToken(for: NSColorSpace.genericRGB)
        || AnnotationPresentation.textureCacheToken(for: nil as Any?) == AnnotationPresentation.cacheToken(for: NSScreen.main?.colorSpace ?? .genericRGB),
       "nil window token must be stable")

let captions = [
    AnnotationPresentation.windowLevelWidth(wl: 40, ww: 400),
    AnnotationPresentation.windowLevelWidth(wl: 40.125, ww: 12.5),
    AnnotationPresentation.imageSize(width: 32, height: 32),
    AnnotationPresentation.pixelValue(x: 8, y: 12, hu: 81, unit: "HU"),
    AnnotationPresentation.patientName("QA^PATIENT"),
    AnnotationPresentation.roiLength(centimeters: 2)
]
expect(captions[0] == "WL: 40 WW: 400", "WL/WW integer: \(captions[0])")
expect(captions[1] == "WL: 40.1250 WW: 12.5000", "WL/WW fractional: \(captions[1])")
expect(captions[2] == "Image size: 32 x 32", "image size: \(captions[2])")
expect(captions[3].contains("81.00") && captions[3].contains("HU"), "HU: \(captions[3])")
expect(captions[4] == "QA^PATIENT", "patient: \(captions[4])")
expect(captions[5] == "Length: 2.000 cm", "ROI length: \(captions[5])")

let font = NSFont.userFixedPitchFont(ofSize: 12) ?? NSFont.systemFont(ofSize: 12)
let appearances = [NSAppearance.Name.aqua, .darkAqua]
for appearance in appearances {
    NSAppearance(named: appearance)!.performAsCurrentDrawingAppearance {
        for scale: CGFloat in [1, 2] {
            for whiteBackground in [false, true] {
                for caption in captions {
                    let bitmap = AnnotationPresentation.rasterizeOverlay(
                        caption, font: font, scale: scale, whiteBackground: whiteBackground)
                    expect(bitmap.pixelsWide > 0 && bitmap.pixelsHigh > 0, "empty bitmap \(caption) @\(scale)")
                    expect(Double(bitmap.pixelsWide) >= Double(scale) * 4, "too narrow \(caption)")
                    let coverage = AnnotationPresentation.glyphCoverage(in: bitmap)
                    expect(coverage > 0.02, "lost glyphs '\(caption)' \(appearance.rawValue) bg=\(whiteBackground) scale=\(scale) coverage=\(coverage)")
                    let metrics = (caption as NSString).size(withAttributes: [.font: font])
                    expect(CGFloat(bitmap.pixelsWide) + 0.5 >= (metrics.width + 8) * scale * 0.5,
                           "clipped metrics '\(caption)' \(bitmap.pixelsWide) vs \(metrics.width)")
                    for profile in profiles {
                        for gray in [0.0, 0.18, 0.5, 0.85, 1.0] {
                            let contrast = AnnotationPresentation.overlayContrast(
                                caption, font: font, scale: scale, whiteBackground: whiteBackground,
                                backgroundGray: gray, profile: profile.colorSpace)
                            expect(contrast.isFinite && contrast >= 4.5,
                                   "contrast \(contrast) for '\(caption)' \(profile.name) gray=\(gray) \(appearance.rawValue) scale=\(scale) inverse=\(whiteBackground)")
                        }
                    }
                }
            }
        }
    }
}

let colors: [(String, UInt16, UInt16, UInt16)] = [
    ("red", 65535, 0, 0), ("green", 0, 65535, 0), ("blue", 0, 0, 65535),
    ("yellow", 65535, 65535, 0), ("white", 65535, 65535, 65535)
]
for (name, r, g, b) in colors {
    for opacity: CGFloat in [1.0, 0.5] {
        let source = AnnotationPresentation.roiColor(red: r, green: g, blue: b, opacity: opacity)
        expect(abs(source.alphaComponent - opacity) < 0.001, "\(name) opacity")
        var previous: [CGFloat] = []
        for profile in profiles {
            let converted = AnnotationPresentation.convert(source, to: profile.colorSpace)
            expect(abs(converted.alphaComponent - opacity) < 0.02, "\(name) alpha \(converted.alphaComponent) in \(profile.name)")
            let channels = [converted.redComponent, converted.greenComponent, converted.blueComponent]
            if name == "red" { expect(channels[0] > channels[1] && channels[0] > channels[2], "red lost in \(profile.name) \(channels)") }
            if name == "green" { expect(channels[1] > channels[0] && channels[1] > channels[2], "green lost in \(profile.name) \(channels)") }
            if name == "blue" { expect(channels[2] > channels[0] && channels[2] > channels[1], "blue lost in \(profile.name) \(channels)") }
            if name == "yellow" { expect(channels[0] > 0.4 && channels[1] > 0.4 && channels[2] < channels[0], "yellow lost in \(profile.name) \(channels)") }
            if previous.isEmpty { previous = channels }
            else {
                // Profile conversion may shift channels, but must not collapse a primary to black.
                expect(channels[0] + channels[1] + channels[2] > 0.05, "\(name) collapsed in \(profile.name)")
            }
        }
    }
}

let first = captions
NSAppearance(named: .darkAqua)!.performAsCurrentDrawingAppearance {
    expect(AnnotationPresentation.windowLevelWidth(wl: 40, ww: 400) == first[0], "WL/WW changed with appearance")
    expect(AnnotationPresentation.roiLength(centimeters: 2) == first[5], "length changed with appearance")
}
for profile in profiles {
    expect(AnnotationPresentation.windowLevelWidth(wl: 40, ww: 400) == first[0], "WL/WW changed with \(profile.name)")
    expect(AnnotationPresentation.imageSize(width: 32, height: 32) == first[2], "image size changed with \(profile.name)")
    expect(AnnotationPresentation.pixelValue(x: 8, y: 12, hu: 81, unit: "HU") == first[3], "HU changed with \(profile.name)")
    expect(AnnotationPresentation.patientName("QA^PATIENT") == first[4], "patient changed with \(profile.name)")
    expect(AnnotationPresentation.roiLength(centimeters: 2) == first[5], "length changed with \(profile.name)")
}

print("PASS: Color LCD/sRGB/linear/display profiles, 1x/2x, Aqua/Dark Aqua, inverse, max/half opacity, glyph coverage, contrast ≥ 4.5, RGBY channels and unchanged overlay values")
'''
with tempfile.TemporaryDirectory(prefix='horos-annotation-presentation-') as directory:
    path = Path(directory)
    (path / 'main.swift').write_text(code)
    subprocess.run([
        'xcrun', 'swiftc',
        str(root / 'Horos/Sources/AnnotationPresentation.swift'),
        str(path / 'main.swift'),
        '-o', str(path / 'test')
    ], check=True)
    subprocess.run([str(path / 'test')], check=True)
