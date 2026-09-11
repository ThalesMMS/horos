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

/// Native T2 Fit Map, version and ABI of this checkout.
///
/// The public T2 1.3 plugin (`MappingT2FitFilter` at horosplugins
/// `6b4036242ca4f821679bcd83942a4b842d7ffb2c`) targets the 10.5 SDK and
/// Intel/PowerPC. It is not redistributed here. The log-linear fit matches that
/// controller: `ln(max(S − background, 1))` versus TE in seconds, then
/// `T2_ms = factor / −slope`, capped at 2000 ms.
public enum T2FitMap {
    public static let version = "1.0"
    public static let abi = "arm64-native"
    public static let menuTitle = "T2 Fit Map"
    public static let legacyVersion = "1.3"
    public static let legacyPrincipalClass = "MappingT2FitFilter"
    public static let sourceRevision = "6b4036242ca4f821679bcd83942a4b842d7ffb2c"

    public enum ErrorCode: Int {
        case success = 0
        case tooFewEchoes = 1
        case missingEchoTimes = 2
        case emptySeries = 3
        case sizeMismatch = 4
    }

    public struct Echo {
        public var teMilliseconds: Double
        public var signal: Double
        public init(teMilliseconds: Double, signal: Double) {
            self.teMilliseconds = teMilliseconds
            self.signal = signal
        }
    }

    public struct PixelFit {
        public var t2Milliseconds: Double
        public var protonDensity: Double
        public var slope: Double
        public var intercept: Double
    }

    public struct SeriesResult {
        public var code: Int
        public var reason: String
        public var t2Milliseconds: [Float]
        public var validCount: Int
    }

    public static func linearRegression(x: [Double], y: [Double]) -> (slope: Double, intercept: Double)? {
        let count = min(x.count, y.count)
        guard count >= 2 else { return nil }
        var sumX = 0.0, sumX2 = 0.0, sumXY = 0.0, sumY = 0.0
        for index in 0..<count {
            guard x[index].isFinite, y[index].isFinite else { return nil }
            sumX += x[index]
            sumX2 += x[index] * x[index]
            sumXY += x[index] * y[index]
            sumY += y[index]
        }
        let n = Double(count)
        let denominator = n * sumX2 - sumX * sumX
        guard denominator != 0, denominator.isFinite else { return nil }
        let slope = (n * sumXY - sumX * sumY) / denominator
        let intercept = (sumY * sumX2 - sumX * sumXY) / denominator
        guard slope.isFinite, intercept.isFinite else { return nil }
        return (slope, intercept)
    }

    public static func fitPixel(echoes: [Echo],
                                background: Double = 0,
                                factor: Double = 1000,
                                cap: Double = 2000) -> PixelFit? {
        let usable = echoes.filter { $0.teMilliseconds > 0 && $0.signal.isFinite }
        guard usable.count >= 2 else { return nil }
        let xs = usable.map { $0.teMilliseconds / 1000.0 }
        let ys = usable.map { log(max($0.signal - background, 1)) }
        guard let fit = linearRegression(x: xs, y: ys) else { return nil }
        var t2 = 0.0
        if fit.slope < 0 {
            t2 = min(factor / -fit.slope, cap)
            if !t2.isFinite { t2 = 0 }
        }
        return PixelFit(t2Milliseconds: t2,
                        protonDensity: exp(fit.intercept),
                        slope: fit.slope,
                        intercept: fit.intercept)
    }

    public static func fitSeries(signals: [[Float]],
                                 echoTimesMilliseconds: [Double],
                                 width: Int,
                                 height: Int,
                                 background: Double = 0,
                                 factor: Double = 1000,
                                 cap: Double = 2000) -> SeriesResult {
        let pixelCount = width * height
        guard width > 0, height > 0, pixelCount > 0 else {
            return SeriesResult(code: ErrorCode.emptySeries.rawValue,
                                reason: "T2 Fit Map needs a non-empty multi-echo series.",
                                t2Milliseconds: [],
                                validCount: 0)
        }
        guard signals.count >= 2 else {
            return SeriesResult(code: ErrorCode.tooFewEchoes.rawValue,
                                reason: "T2 Fit Map needs at least two echoes.",
                                t2Milliseconds: [],
                                validCount: 0)
        }
        guard echoTimesMilliseconds.count == signals.count else {
            return SeriesResult(code: ErrorCode.sizeMismatch.rawValue,
                                reason: "T2 Fit Map echo-time count does not match the echo frames.",
                                t2Milliseconds: [],
                                validCount: 0)
        }
        guard echoTimesMilliseconds.filter({ $0 > 0 }).count >= 2 else {
            return SeriesResult(code: ErrorCode.missingEchoTimes.rawValue,
                                reason: "T2 Fit Map needs at least two positive echo times (TE).",
                                t2Milliseconds: [],
                                validCount: 0)
        }
        guard signals.allSatisfy({ $0.count == pixelCount }) else {
            return SeriesResult(code: ErrorCode.sizeMismatch.rawValue,
                                reason: "T2 Fit Map frames must share the same width and height.",
                                t2Milliseconds: [],
                                validCount: 0)
        }

        var map = [Float](repeating: 0, count: pixelCount)
        var valid = 0
        for pixel in 0..<pixelCount {
            var echoes: [Echo] = []
            echoes.reserveCapacity(signals.count)
            for echo in signals.indices {
                echoes.append(Echo(teMilliseconds: echoTimesMilliseconds[echo],
                                   signal: Double(signals[echo][pixel])))
            }
            if let fit = fitPixel(echoes: echoes, background: background, factor: factor, cap: cap) {
                map[pixel] = Float(fit.t2Milliseconds)
                if fit.t2Milliseconds > 0 { valid += 1 }
            }
        }
        return SeriesResult(code: ErrorCode.success.rawValue,
                            reason: "",
                            t2Milliseconds: map,
                            validCount: valid)
    }

    public static func groupEchoSequences(origins: [(Double, Double, Double)]) -> [[Int]] {
        var order: [(Double, Double, Double)] = []
        var buckets: [[Int]] = []
        func same(_ a: (Double, Double, Double), _ b: (Double, Double, Double)) -> Bool {
            abs(a.0 - b.0) < 1e-4 && abs(a.1 - b.1) < 1e-4 && abs(a.2 - b.2) < 1e-4
        }
        for (index, origin) in origins.enumerated() {
            if let existing = order.firstIndex(where: { same($0, origin) }) {
                buckets[existing].append(index)
            } else {
                order.append(origin)
                buckets.append([index])
            }
        }
        if buckets.allSatisfy({ $0.count < 2 }) {
            return [Array(origins.indices)]
        }
        return buckets
    }
}

@objc(T2FitMapFilter)
public final class T2FitMapFilter: NSObject {
    @objc public private(set) var lastReason = ""
    @objc public private(set) var lastMap: [Float] = []
    @objc public var viewerController: AnyObject?

    private var prepared: (signals: [[Float]], tes: [Double], width: Int, height: Int)?

    @objc public static func filter() -> T2FitMapFilter {
        T2FitMapFilter()
    }

    @objc(registerIn:)
    public static func register(in plugins: NSMutableDictionary) {
        if plugins[T2FitMap.menuTitle] == nil {
            plugins[T2FitMap.menuTitle] = T2FitMapFilter()
        }
    }

    @objc public func prepareFilter(_ viewer: Any?) -> Int {
        viewerController = viewer as AnyObject?
        return 0
    }

    public func prepare(signals: [[Float]], echoTimesMilliseconds: [Double], width: Int, height: Int) {
        prepared = (signals, echoTimesMilliseconds, width, height)
    }

    @objc public func filterImage(_ menuName: String?) -> Int {
        if let series = prepared {
            let result = T2FitMap.fitSeries(signals: series.signals,
                                            echoTimesMilliseconds: series.tes,
                                            width: series.width,
                                            height: series.height)
            lastReason = result.reason
            lastMap = result.t2Milliseconds
            return result.code
        }
        let selector = #selector(T2FitMapViewerProcessing.t2FitMapProcessCurrentSeries)
        if let viewer = viewerController, viewer.responds(to: selector),
           let outcome = viewer.perform(selector)?.takeUnretainedValue() as? NSDictionary {
            lastReason = outcome["reason"] as? String ?? ""
            lastMap = outcome["t2Milliseconds"] as? [Float] ?? []
            return (outcome["code"] as? NSNumber)?.intValue ?? T2FitMap.ErrorCode.emptySeries.rawValue
        }
        lastReason = "T2 Fit Map needs an open multi-echo 2D viewer series, or prepared phantom frames."
        lastMap = []
        return T2FitMap.ErrorCode.emptySeries.rawValue
    }
}

@objc(T2FitMapViewerProcessing)
public protocol T2FitMapViewerProcessing {
    func t2FitMapProcessCurrentSeries() -> NSDictionary
}

public struct T2FitMapInspection {
    public var identified: Bool
    public var version: String
    public var principalClass: String
    public var architectures: [String]
    public var compatibleWithHost: Bool
    public var diagnostic: String
}

@objc(T2FitMapCompatibility)
public final class T2FitMapCompatibility: NSObject {
    public static func inspect(info: [String: Any],
                               architectures: [String],
                               hostArchitecture: String = "arm64") -> T2FitMapInspection {
        let version = string(info["CFBundleVersion"]) ?? string(info["CFBundleShortVersionString"]) ?? ""
        let principal = string(info["NSPrincipalClass"]) ?? ""
        let executable = string(info["CFBundleExecutable"]) ?? string(info["CFBundleName"]) ?? ""
        let titles = info["MenuTitles"] as? [String] ?? []
        let identified = principal == T2FitMap.legacyPrincipalClass
            || titles.contains(T2FitMap.menuTitle)
            || executable == T2FitMap.menuTitle
            || executable.localizedCaseInsensitiveContains("t2 fit")
        let host = hostArchitecture.isEmpty ? "arm64" : hostArchitecture
        let compatible = architectures.contains(host)
        var diagnostic = ""
        if identified && !compatible {
            let abi = architectures.isEmpty ? "unknown" : architectures.joined(separator: "/")
            diagnostic = "T2 Fit Map \(version.isEmpty ? T2FitMap.legacyVersion : version) (\(principal.isEmpty ? T2FitMap.legacyPrincipalClass : principal)) declares \(abi) ABI and cannot load in this \(host) Horos process. The built-in T2 Fit Map \(T2FitMap.version) (\(T2FitMap.abi)) processes a multi-echo series instead."
        } else if identified && compatible {
            diagnostic = "T2 Fit Map \(version) includes \(host) and can load in this process."
        }
        return T2FitMapInspection(identified: identified,
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

@objc(T2FitMapEngine)
public final class T2FitMapEngine: NSObject {
    @objc(fitWithFrames:echoTimesMilliseconds:width:height:)
    public static func fit(frames: [Data],
                                 echoTimesMilliseconds: [NSNumber],
                                 width: Int32,
                                 height: Int32) -> NSDictionary {
        let count = Int(width) * Int(height)
        let signals: [[Float]] = frames.map { data in
            data.withUnsafeBytes { raw in
                let buffer = raw.bindMemory(to: Float.self)
                return buffer.count == count ? Array(buffer) : []
            }
        }
        let result = T2FitMap.fitSeries(signals: signals,
                                        echoTimesMilliseconds: echoTimesMilliseconds.map { $0.doubleValue },
                                        width: Int(width),
                                        height: Int(height))
        return [
            "code": result.code,
            "reason": result.reason,
            "t2Milliseconds": result.t2Milliseconds,
            "validCount": result.validCount
        ]
    }
}
