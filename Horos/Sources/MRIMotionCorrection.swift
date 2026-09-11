import Foundation

/// One grayscale slice of a motion-correction stack. Row-major, one sample per pixel.
@objc(HorosMRIMotionSlice)
public final class MRIMotionSlice: NSObject {
    @objc public let width: Int
    @objc public let height: Int
    @objc public let pixels: [Double]
    @objc public let spacingX: Double
    @objc public let spacingY: Double

    @objc public init(width: Int, height: Int, pixels: [Double],
                      spacingX: Double, spacingY: Double) {
        self.width = width
        self.height = height
        self.pixels = pixels
        self.spacingX = spacingX
        self.spacingY = spacingY
    }
}

/// Estimated in-plane translation of one slice relative to the reference.
@objc(HorosMRIMotionShift)
public final class MRIMotionShift: NSObject {
    @objc public let dxPixels: Double
    @objc public let dyPixels: Double
    @objc public let dxMillimetres: Double
    @objc public let dyMillimetres: Double
    @objc public let peakNCC: Double
    @objc public let residualSSD: Double
    @objc public let reliable: Bool

    @objc public init(dxPixels: Double, dyPixels: Double,
                      dxMillimetres: Double, dyMillimetres: Double,
                      peakNCC: Double, residualSSD: Double, reliable: Bool) {
        self.dxPixels = dxPixels
        self.dyPixels = dyPixels
        self.dxMillimetres = dxMillimetres
        self.dyMillimetres = dyMillimetres
        self.peakNCC = peakNCC
        self.residualSSD = residualSSD
        self.reliable = reliable
    }
}

/// Bounded PoC report. `adopted` stays false: this is not a BTK/fbrain port.
@objc(HorosMRIMotionReport)
public final class MRIMotionReport: NSObject {
    @objc public let method: String
    @objc public let referenceIndex: Int
    @objc public let searchRadius: Int
    @objc public let shifts: [MRIMotionShift]
    @objc public let meanAbsErrorPixels: Double
    @objc public let meanResidualSSD: Double
    @objc public let elapsedMilliseconds: Double
    @objc public let adopted: Bool
    @objc public let limitation: String

    @objc public init(method: String, referenceIndex: Int, searchRadius: Int,
                      shifts: [MRIMotionShift], meanAbsErrorPixels: Double,
                      meanResidualSSD: Double, elapsedMilliseconds: Double,
                      adopted: Bool, limitation: String) {
        self.method = method
        self.referenceIndex = referenceIndex
        self.searchRadius = searchRadius
        self.shifts = shifts
        self.meanAbsErrorPixels = meanAbsErrorPixels
        self.meanResidualSSD = meanResidualSSD
        self.elapsedMilliseconds = elapsedMilliseconds
        self.adopted = adopted
        self.limitation = limitation
    }
}

/// External toolkit cited by #150. Identified, not vendored, not loaded as a plugin.
@objc(HorosMRIMotionDependency)
public final class MRIMotionDependency: NSObject {
    @objc public let name: String
    @objc public let sourceURL: String
    @objc public let license: String
    @objc public let version: String
    @objc public let commit: String
    @objc public let lastPush: String
    @objc public let language: String
    @objc public let libraries: String
    @objc public let abi: String
    @objc public let horosPluginABI: String
    @objc public let compatibleWithHorosPluginFilter: Bool
    @objc public let costSummary: String

    @objc public init(name: String, sourceURL: String, license: String,
                      version: String, commit: String, lastPush: String,
                      language: String, libraries: String, abi: String,
                      horosPluginABI: String,
                      compatibleWithHorosPluginFilter: Bool,
                      costSummary: String) {
        self.name = name
        self.sourceURL = sourceURL
        self.license = license
        self.version = version
        self.commit = commit
        self.lastPush = lastPush
        self.language = language
        self.libraries = libraries
        self.abi = abi
        self.horosPluginABI = horosPluginABI
        self.compatibleWithHorosPluginFilter = compatibleWithHorosPluginFilter
        self.costSummary = costSummary
    }

    /// Baby Brain Toolkit (fbrain). Pin: master @ 4486faf04a3a482541203a4621d078c9c7ca38c1 (2017-05-12).
    @objc public static var fbrain: MRIMotionDependency {
        MRIMotionDependency(
            name: "fbrain/BTK",
            sourceURL: "https://github.com/rousseau/fbrain",
            license: "CeCILL-B",
            version: "BTK 1.5 (NITRC) / git master",
            commit: "4486faf04a3a482541203a4621d078c9c7ca38c1",
            lastPush: "2017-05-12T16:06:03Z",
            language: "C++",
            libraries: "ITK, VTK, OpenMP, ANN, TCLAP",
            abi: "C++ executables and libraries (CMake 2.6, ITK/VTK, no C++11). NIfTI CLI, not a Mach-O PluginFilter bundle.",
            horosPluginABI: "ObjC PluginFilter (+filter, -filterImage:, -prepareFilter:) linked to Horos.framework on arm64.",
            compatibleWithHorosPluginFilter: false,
            costSummary: "A BTK port would need the 2013-era ITK/VTK/OpenMP/ANN/TCLAP stack, a NIfTI pipeline, and a new PluginFilter wrapper. There is no arm64 Horos plugin and no fetal slice-to-volume contract here. Estimate: weeks of ABI and CeCILL-B review, then a separate clinical validation. This PoC stays in-process Swift.")
    }
}

/// Synthetic disk stack with known integer translations. Not a clinical phantom.
@objc(HorosMRIMotionPhantom)
public final class MRIMotionPhantom: NSObject {
    @objc public static func diskStack(width: Int, height: Int, radius: Double,
                                       centerX: Double, centerY: Double,
                                       shifts: [[Double]],
                                       spacing: Double,
                                       foreground: Double,
                                       background: Double) -> [MRIMotionSlice] {
        guard width > 0, height > 0, radius > 0 else { return [] }
        var base = [Double](repeating: background, count: width * height)
        for y in 0..<height {
            for x in 0..<width {
                let dx = Double(x) - centerX
                let dy = Double(y) - centerY
                if dx * dx + dy * dy <= radius * radius {
                    base[y * width + x] = foreground
                }
            }
        }
        return shifts.map { pair in
            let dx = Int(pair.first?.rounded() ?? 0)
            let dy = Int((pair.count > 1 ? pair[1] : 0).rounded())
            let pixels = translate(base, width: width, height: height,
                                   dx: dx, dy: dy, fill: background)
            return MRIMotionSlice(width: width, height: height, pixels: pixels,
                                  spacingX: spacing, spacingY: spacing)
        }
    }

    static func translate(_ source: [Double], width: Int, height: Int,
                          dx: Int, dy: Int, fill: Double) -> [Double] {
        var output = [Double](repeating: fill, count: width * height)
        for y in 0..<height {
            for x in 0..<width {
                let sx = x - dx
                let sy = y - dy
                if sx >= 0, sx < width, sy >= 0, sy < height {
                    output[y * width + x] = source[sy * width + sx]
                }
            }
        }
        return output
    }
}

/// Rigid in-plane translation by integer normalized cross-correlation.
///
/// This is a feasibility gate for #150, not BTK slice-to-volume reconstruction.
@objc(HorosMRIMotionCorrection)
public final class MRIMotionCorrection: NSObject {
    public static let method = "ncc-integer"
    public static let limitation = "In-plane integer translation only; not fbrain/BTK slice-to-volume reconstruction (SVR), rotation, or deformable registration."

    public static func correct(slices: [MRIMotionSlice],
                               referenceIndex: Int = 0,
                               searchRadius: Int = 8,
                               expected: [(Double, Double)]? = nil) -> MRIMotionReport? {
        let started = CFAbsoluteTimeGetCurrent()
        guard !slices.isEmpty, searchRadius >= 1,
              slices.indices.contains(referenceIndex) else { return nil }
        let reference = slices[referenceIndex]
        guard valid(reference) else { return nil }
        for slice in slices where !valid(slice) ||
            slice.width != reference.width || slice.height != reference.height {
            return nil
        }
        let spacingX = resolvedSpacing(reference.spacingX)
        let spacingY = resolvedSpacing(reference.spacingY)
        var shifts: [MRIMotionShift] = []
        shifts.reserveCapacity(slices.count)
        for (index, slice) in slices.enumerated() {
            if index == referenceIndex {
                shifts.append(MRIMotionShift(
                    dxPixels: 0, dyPixels: 0, dxMillimetres: 0, dyMillimetres: 0,
                    peakNCC: 1, residualSSD: 0, reliable: true))
                continue
            }
            guard let match = bestShift(reference: reference.pixels, moving: slice.pixels,
                                        width: reference.width, height: reference.height,
                                        radius: searchRadius) else { return nil }
            shifts.append(MRIMotionShift(
                dxPixels: Double(match.dx), dyPixels: Double(match.dy),
                dxMillimetres: Double(match.dx) * spacingX,
                dyMillimetres: Double(match.dy) * spacingY,
                peakNCC: match.ncc, residualSSD: match.ssd,
                reliable: match.ncc.isFinite && match.ncc >= 0.99))
        }
        let meanSSD = shifts.map(\.residualSSD).reduce(0, +) / Double(shifts.count)
        let error: Double
        if let expected, expected.count == shifts.count {
            error = zip(shifts, expected).map {
                hypot($0.dxPixels - $1.0, $0.dyPixels - $1.1)
            }.reduce(0, +) / Double(shifts.count)
        } else {
            error = -1
        }
        return MRIMotionReport(
            method: method, referenceIndex: referenceIndex, searchRadius: searchRadius,
            shifts: shifts, meanAbsErrorPixels: error, meanResidualSSD: meanSSD,
            elapsedMilliseconds: (CFAbsoluteTimeGetCurrent() - started) * 1000,
            adopted: false, limitation: limitation)
    }

    private static func valid(_ slice: MRIMotionSlice) -> Bool {
        slice.width > 0 && slice.height > 0 &&
            slice.pixels.count == slice.width * slice.height &&
            slice.pixels.allSatisfy(\.isFinite)
    }

    private static func resolvedSpacing(_ value: Double) -> Double {
        value.isFinite && value != 0 ? value : 1
    }

    private static func bestShift(reference: [Double], moving: [Double],
                                  width: Int, height: Int,
                                  radius: Int) -> (dx: Int, dy: Int, ncc: Double, ssd: Double)? {
        var best: (dx: Int, dy: Int, ncc: Double, ssd: Double)?
        for dy in -radius...radius {
            for dx in -radius...radius {
                guard let score = score(reference: reference, moving: moving,
                                        width: width, height: height, dx: dx, dy: dy)
                else { continue }
                if let current = best {
                    if score.ncc < current.ncc { continue }
                    if score.ncc == current.ncc {
                        let newer = abs(dx) + abs(dy)
                        let older = abs(current.dx) + abs(current.dy)
                        if newer > older || (newer == older && abs(dx) >= abs(current.dx)) {
                            continue
                        }
                    }
                }
                best = (dx, dy, score.ncc, score.ssd)
            }
        }
        return best
    }

    /// Peak when `moving[x + dx, y + dy] == reference[x, y]` on the overlap.
    private static func score(reference: [Double], moving: [Double],
                              width: Int, height: Int,
                              dx: Int, dy: Int) -> (ncc: Double, ssd: Double)? {
        var pairs: [(Double, Double)] = []
        pairs.reserveCapacity(width * height)
        var ssd = 0.0
        for y in 0..<height {
            let my = y + dy
            guard my >= 0, my < height else { continue }
            for x in 0..<width {
                let mx = x + dx
                guard mx >= 0, mx < width else { continue }
                let r = reference[y * width + x]
                let m = moving[my * width + mx]
                pairs.append((r, m))
                let d = r - m
                ssd += d * d
            }
        }
        let count = Double(pairs.count)
        guard count > 0 else { return nil }
        let meanR = pairs.reduce(0) { $0 + $1.0 } / count
        let meanM = pairs.reduce(0) { $0 + $1.1 } / count
        var num = 0.0, denR = 0.0, denM = 0.0
        for (r, m) in pairs {
            let dr = r - meanR
            let dm = m - meanM
            num += dr * dm
            denR += dr * dr
            denM += dm * dm
        }
        let den = (denR * denM).squareRoot()
        let ncc = den > 0 ? num / den : 0
        return (ncc, ssd)
    }
}
