//  Copyright (c) 2026 Horos Project. All rights reserved.
//
//  This file is part of the Horos Project.
//
//  Horos is free software: you can redistribute it and/or modify it under the
//  terms of the GNU Lesser General Public License as published by the Free
//  Software Foundation, version 3 of the License.
//
//  Horos is distributed in the hope that it will be useful, but WITHOUT ANY
//  WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR
//  A PARTICULAR PURPOSE. See the GNU Lesser General Public License for details.

import Foundation

/// Native ROI Enhancement time-attenuation curves, version and ABI of this checkout.
///
/// The public ROI Enhancement II plugin (`ROI_Enhancement_II` at horosplugins
/// `6b4036242ca4f821679bcd83942a4b842d7ffb2c`) targets the 10.6 SDK and
/// i386/x86_64, and draws through GraphX. It is not redistributed here. The
/// curve matches that chart: for each 4D phase, `computeROI` min/mean/max of
/// the same ROI on the current slice.
public enum ROIEnhancement {
    public static let version = "1.0"
    public static let abi = "arm64-native"
    public static let menuTitle = "ROI Enhancement"
    public static let legacyVersion = "2.3.1"
    public static let legacyPrincipalClass = "ROI_Enhancement_II"
    public static let sourceRevision = "6b4036242ca4f821679bcd83942a4b842d7ffb2c"

    public enum ErrorCode: Int {
        case success = 0
        case tooFewPhases = 1
        case missingROI = 2
        case emptySeries = 3
        case sizeMismatch = 4
    }

    public struct Phase {
        public var timeSeconds: Double
        public var pixels: [Float]
        public var width: Int
        public var height: Int
        public init(timeSeconds: Double, pixels: [Float], width: Int, height: Int) {
            self.timeSeconds = timeSeconds
            self.pixels = pixels
            self.width = width
            self.height = height
        }
    }

    public struct Region {
        public var name: String
        public var column: Int
        public var row: Int
        public var width: Int
        public var height: Int
        public init(name: String, column: Int, row: Int, width: Int, height: Int) {
            self.name = name
            self.column = column
            self.row = row
            self.width = width
            self.height = height
        }
    }

    public struct Sample {
        public var timeSeconds: Double
        public var min: Double
        public var mean: Double
        public var max: Double
        public var count: Int
    }

    public struct Curve {
        public var name: String
        public var samples: [Sample]
    }

    public struct Result {
        public var code: Int
        public var reason: String
        public var curves: [Curve]
    }

    public static func statistics(pixels: [Float], width: Int, height: Int, region: Region) -> Sample? {
        guard width > 0, height > 0, pixels.count == width * height else { return nil }
        var total = 0.0
        var imin = Double.greatestFiniteMagnitude
        var imax = -Double.greatestFiniteMagnitude
        var count = 0
        let rowEnd = region.row + region.height
        let columnEnd = region.column + region.width
        var row = region.row
        while row < rowEnd {
            var column = region.column
            while column < columnEnd {
                if row >= 0, row < height, column >= 0, column < width {
                    let value = Double(pixels[row * width + column])
                    total += value
                    if value < imin { imin = value }
                    if value > imax { imax = value }
                    count += 1
                }
                column += 1
            }
            row += 1
        }
        guard count > 0 else { return nil }
        return Sample(timeSeconds: 0, min: imin, mean: total / Double(count), max: imax, count: count)
    }

    public static func curves(phases: [Phase], regions: [Region]) -> Result {
        guard phases.count >= 2 else {
            return Result(code: ErrorCode.tooFewPhases.rawValue,
                          reason: "ROI Enhancement needs a dynamic (4D) series with at least two phases.",
                          curves: [])
        }
        guard !regions.isEmpty else {
            return Result(code: ErrorCode.missingROI.rawValue,
                          reason: "ROI Enhancement needs at least one ROI with area.",
                          curves: [])
        }
        let width = phases[0].width
        let height = phases[0].height
        let pixelCount = width * height
        guard width > 0, height > 0, pixelCount > 0 else {
            return Result(code: ErrorCode.emptySeries.rawValue,
                          reason: "ROI Enhancement needs a non-empty dynamic series.",
                          curves: [])
        }
        guard phases.allSatisfy({ $0.width == width && $0.height == height && $0.pixels.count == pixelCount }) else {
            return Result(code: ErrorCode.sizeMismatch.rawValue,
                          reason: "ROI Enhancement frames must share the same width and height.",
                          curves: [])
        }

        var curves: [Curve] = []
        curves.reserveCapacity(regions.count)
        for region in regions {
            var samples: [Sample] = []
            samples.reserveCapacity(phases.count)
            for phase in phases {
                guard var sample = statistics(pixels: phase.pixels, width: width, height: height, region: region) else {
                    return Result(code: ErrorCode.sizeMismatch.rawValue,
                                  reason: "ROI Enhancement needs the ROI to cover pixels on every phase.",
                                  curves: [])
                }
                sample.timeSeconds = phase.timeSeconds
                samples.append(sample)
            }
            curves.append(Curve(name: region.name, samples: samples))
        }
        return Result(code: ErrorCode.success.rawValue, reason: "", curves: curves)
    }
}

@objc(ROIEnhancementFilter)
public final class ROIEnhancementFilter: NSObject {
    @objc public private(set) var lastReason = ""
    public private(set) var lastCurves: [ROIEnhancement.Curve] = []
    @objc public var viewerController: AnyObject?

    private var prepared: (phases: [ROIEnhancement.Phase], regions: [ROIEnhancement.Region])?

    @objc public static func filter() -> ROIEnhancementFilter {
        ROIEnhancementFilter()
    }

    @objc(registerIn:)
    public static func register(in plugins: NSMutableDictionary) {
        if plugins[ROIEnhancement.menuTitle] == nil {
            plugins[ROIEnhancement.menuTitle] = ROIEnhancementFilter()
        }
    }

    @objc public func prepareFilter(_ viewer: Any?) -> Int {
        viewerController = viewer as AnyObject?
        return 0
    }

    public func prepare(phases: [ROIEnhancement.Phase], regions: [ROIEnhancement.Region]) {
        prepared = (phases, regions)
    }

    @objc public func filterImage(_ menuName: String?) -> Int {
        if let series = prepared {
            let result = ROIEnhancement.curves(phases: series.phases, regions: series.regions)
            lastReason = result.reason
            lastCurves = result.curves
            return result.code
        }
        let selector = #selector(ROIEnhancementViewerProcessing.roiEnhancementProcessCurrentSeries)
        if let viewer = viewerController, viewer.responds(to: selector),
           let outcome = viewer.perform(selector)?.takeUnretainedValue() as? NSDictionary {
            lastReason = outcome["reason"] as? String ?? ""
            lastCurves = ROIEnhancementEngine.curves(from: outcome)
            return (outcome["code"] as? NSNumber)?.intValue ?? ROIEnhancement.ErrorCode.emptySeries.rawValue
        }
        lastReason = "ROI Enhancement needs an open dynamic 2D viewer series with a ROI, or prepared phantom frames."
        lastCurves = []
        return ROIEnhancement.ErrorCode.emptySeries.rawValue
    }
}

@objc(ROIEnhancementViewerProcessing)
public protocol ROIEnhancementViewerProcessing {
    func roiEnhancementProcessCurrentSeries() -> NSDictionary
}

public struct ROIEnhancementInspection {
    public var identified: Bool
    public var version: String
    public var principalClass: String
    public var architectures: [String]
    public var compatibleWithHost: Bool
    public var diagnostic: String
}

@objc(ROIEnhancementCompatibility)
public final class ROIEnhancementCompatibility: NSObject {
    public static func inspect(info: [String: Any],
                               architectures: [String],
                               hostArchitecture: String = "arm64") -> ROIEnhancementInspection {
        let version = string(info["CFBundleVersion"]) ?? string(info["CFBundleShortVersionString"]) ?? ""
        let principal = string(info["NSPrincipalClass"]) ?? ""
        let executable = string(info["CFBundleExecutable"]) ?? string(info["CFBundleName"]) ?? ""
        let identifier = string(info["CFBundleIdentifier"]) ?? ""
        let titles = info["MenuTitles"] as? [String] ?? []
        let identified = principal == ROIEnhancement.legacyPrincipalClass
            || titles.contains(ROIEnhancement.menuTitle)
            || executable == "ROI-Enhancement"
            || executable.localizedCaseInsensitiveContains("roi enhancement")
            || identifier.localizedCaseInsensitiveContains("roienhancement")
        let host = hostArchitecture.isEmpty ? "arm64" : hostArchitecture
        let compatible = architectures.contains(host)
        var diagnostic = ""
        if identified && !compatible {
            let abi = architectures.isEmpty ? "unknown" : architectures.joined(separator: "/")
            diagnostic = "ROI Enhancement \(version.isEmpty ? ROIEnhancement.legacyVersion : version) (\(principal.isEmpty ? ROIEnhancement.legacyPrincipalClass : principal)) declares \(abi) ABI and cannot load in this \(host) Horos process. The built-in ROI Enhancement \(ROIEnhancement.version) (\(ROIEnhancement.abi)) computes a 4D time-attenuation curve instead."
        } else if identified && compatible {
            diagnostic = "ROI Enhancement \(version) includes \(host) and can load in this process."
        }
        return ROIEnhancementInspection(identified: identified,
                                        version: version,
                                        principalClass: principal,
                                        architectures: architectures,
                                        compatibleWithHost: compatible,
                                        diagnostic: diagnostic)
    }

    @objc public static func diagnostic(forBundleAtPath path: String,
                                        loadErrorDomain: String?,
                                        loadErrorCode: Int) -> String? {
        let url = URL(fileURLWithPath: path)
        let contents = url.appendingPathComponent("Contents")
        let infoURL = contents.appendingPathComponent("Info.plist")
        let info = (NSDictionary(contentsOf: infoURL) as? [String: Any]) ?? [:]
        let executableName = string(info["CFBundleExecutable"]) ?? url.deletingPathExtension().lastPathComponent
        let binary = contents.appendingPathComponent("MacOS").appendingPathComponent(executableName)
        let architectures = machOArchitectures(at: binary.path)
        let inspection = inspect(info: info, architectures: architectures)
        if !inspection.diagnostic.isEmpty {
            return inspection.diagnostic
        }
        if inspection.identified,
           loadErrorDomain == NSCocoaErrorDomain,
           loadErrorCode == NSExecutableArchitectureMismatchError {
            return inspect(info: info, architectures: ["incompatible"], hostArchitecture: "arm64").diagnostic
        }
        return nil
    }

    public static func machOArchitectures(at path: String) -> [String] {
        guard let data = try? Data(contentsOf: URL(fileURLWithPath: path)), data.count >= 8 else {
            return []
        }
        func u32(_ offset: Int, swap: Bool) -> UInt32 {
            guard offset + 4 <= data.count else { return 0 }
            var value: UInt32 = 0
            _ = withUnsafeMutableBytes(of: &value) { data.copyBytes(to: $0, from: offset..<offset + 4) }
            return swap ? UInt32(bigEndian: value) : UInt32(littleEndian: value)
        }
        let magic = u32(0, swap: false)
        let fat = magic == 0xCAFEBABE || magic == 0xBEBAFECA || magic == 0xCAFED00D || magic == 0x0DD0FECA
        if fat {
            let swapped = magic == 0xBEBAFECA || magic == 0x0DD0FECA
            let count = Int(u32(4, swap: swapped))
            var names: [String] = []
            var offset = 8
            let stride = magic == 0xCAFED00D || magic == 0x0DD0FECA ? 32 : 20
            for _ in 0..<count {
                if let name = cpuName(u32(offset, swap: swapped)), !names.contains(name) {
                    names.append(name)
                }
                offset += stride
            }
            return names
        }
        let swapped = magic == 0xCFFAEDFE || magic == 0xCEFAEDFE
        if let name = cpuName(u32(4, swap: swapped)) {
            return [name]
        }
        return []
    }

    private static func cpuName(_ type: UInt32) -> String? {
        switch Int32(bitPattern: type) {
        case 7: return "i386"
        case 7 | Int32(bitPattern: 0x01000000): return "x86_64"
        case 12: return "arm"
        case 12 | Int32(bitPattern: 0x01000000): return "arm64"
        case 18: return "ppc"
        case 18 | Int32(bitPattern: 0x01000000): return "ppc64"
        default: return nil
        }
    }

    private static func string(_ value: Any?) -> String? {
        if let text = value as? String, !text.isEmpty { return text }
        return nil
    }
}

@objc(ROIEnhancementEngine)
public final class ROIEnhancementEngine: NSObject {
    @objc(curveWithName:times:mins:means:maxs:counts:)
    public static func curve(name: String,
                             times: [NSNumber],
                             mins: [NSNumber],
                             means: [NSNumber],
                             maxs: [NSNumber],
                             counts: [NSNumber]) -> NSDictionary {
        let count = min(times.count, min(mins.count, min(means.count, min(maxs.count, counts.count))))
        var samples: [[String: Any]] = []
        samples.reserveCapacity(count)
        for index in 0..<count {
            samples.append([
                "timeSeconds": times[index],
                "min": mins[index],
                "mean": means[index],
                "max": maxs[index],
                "count": counts[index]
            ])
        }
        return ["name": name, "samples": samples]
    }

    @objc(resultWithCurves:)
    public static func result(curves: [NSDictionary]) -> NSDictionary {
        guard !curves.isEmpty else {
            return [
                "code": ROIEnhancement.ErrorCode.missingROI.rawValue,
                "reason": "ROI Enhancement needs at least one ROI with area.",
                "curves": []
            ]
        }
        for curve in curves {
            let samples = curve["samples"] as? [Any] ?? []
            if samples.count < 2 {
                return [
                    "code": ROIEnhancement.ErrorCode.tooFewPhases.rawValue,
                    "reason": "ROI Enhancement needs a dynamic (4D) series with at least two phases.",
                    "curves": []
                ]
            }
        }
        return ["code": ROIEnhancement.ErrorCode.success.rawValue, "reason": "", "curves": curves]
    }

    static func curves(from outcome: NSDictionary) -> [ROIEnhancement.Curve] {
        let raw = outcome["curves"] as? [NSDictionary] ?? []
        return raw.map { dictionary in
            let name = dictionary["name"] as? String ?? ""
            let samples = (dictionary["samples"] as? [NSDictionary] ?? []).map { sample in
                ROIEnhancement.Sample(timeSeconds: number(sample["timeSeconds"]),
                                      min: number(sample["min"]),
                                      mean: number(sample["mean"]),
                                      max: number(sample["max"]),
                                      count: Int(number(sample["count"])))
            }
            return ROIEnhancement.Curve(name: name, samples: samples)
        }
    }

    private static func number(_ value: Any?) -> Double {
        (value as? NSNumber)?.doubleValue ?? 0
    }
}
