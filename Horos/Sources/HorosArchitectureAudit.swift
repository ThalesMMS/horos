import Foundation

/// Named architecture check for a product binary, helper, or plugin.
@objc(HorosArchitectureDecision)
public final class HorosArchitectureDecision: NSObject {
    @objc public let accepted: Bool
    @objc public let role: String
    @objc public let diagnosis: String
    @objc public let architectures: [String]

    @objc public init(accepted: Bool, role: String, diagnosis: String, architectures: [String]) {
        self.accepted = accepted
        self.role = role
        self.diagnosis = diagnosis
        self.architectures = architectures
    }
}

/// Apple Silicon publication policy. Product binaries are arm64-only;
/// Intel-only plugins are named before NSBundle loads them; an Intel-only
/// helper keeps its command but is not launched under Rosetta.
@objc(HorosArchitectureAudit)
public final class HorosArchitectureAudit: NSObject {
    @objc public static let productArchitecture = "arm64"
    private static let intelSlices = ["x86_64", "i386"]
    private static let excludedSlices = ["x86_64", "i386", "ppc", "ppc64"]

    @objc(machOArchitecturesAtPath:)
    public static func machOArchitectures(at path: String) -> [String] {
        guard let data = try? Data(contentsOf: URL(fileURLWithPath: path)), data.count >= 8 else {
            return []
        }
        func u32(_ offset: Int, swap: Bool) -> UInt32 {
            guard offset + 4 <= data.count else { return 0 }
            var value: UInt32 = 0
            _ = withUnsafeMutableBytes(of: &value) { data.copyBytes(to: $0, from: offset..<(offset + 4)) }
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

    @objc(machOArchitecturesInBundleAtPath:)
    public static func machOArchitectures(inBundleAt path: String) -> [String] {
        let url = URL(fileURLWithPath: path)
        var isDirectory: ObjCBool = false
        FileManager.default.fileExists(atPath: path, isDirectory: &isDirectory)
        if isDirectory.boolValue {
            let contents = url.appendingPathComponent("Contents")
            let info = (NSDictionary(contentsOf: contents.appendingPathComponent("Info.plist")) as? [String: Any]) ?? [:]
            let executable = (info["CFBundleExecutable"] as? String)
                ?? url.deletingPathExtension().lastPathComponent
            let binary = contents.appendingPathComponent("MacOS").appendingPathComponent(executable)
            let nested = machOArchitectures(at: binary.path)
            if !nested.isEmpty { return nested }
        }
        return machOArchitectures(at: path)
    }

    @objc(productDiagnosisAtPath:)
    public static func productDiagnosis(at path: String) -> HorosArchitectureDecision {
        let architectures = machOArchitectures(inBundleAt: path)
        let name = URL(fileURLWithPath: path).lastPathComponent
        if architectures.isEmpty {
            return HorosArchitectureDecision(accepted: false, role: "product",
                                            diagnosis: "\(name) is not a readable Mach-O",
                                            architectures: [])
        }
        let intel = architectures.filter { excludedSlices.contains($0) }
        if !intel.isEmpty {
            return HorosArchitectureDecision(
                accepted: false, role: "product",
                diagnosis: "\(name) still contains Intel slices (\(intel.joined(separator: "/"))). Horos is published arm64-only; do not ship a universal or x86_64 product.",
                architectures: architectures)
        }
        if !architectures.contains(productArchitecture) {
            return HorosArchitectureDecision(
                accepted: false, role: "product",
                diagnosis: "\(name) has no arm64 slice (\(architectures.joined(separator: "/"))).",
                architectures: architectures)
        }
        return HorosArchitectureDecision(accepted: true, role: "product",
                                        diagnosis: "arm64-only",
                                        architectures: architectures)
    }

    @objc(pluginDiagnosisAtPath:)
    public static func pluginDiagnosis(at path: String) -> String? {
        let architectures = machOArchitectures(inBundleAt: path)
        if architectures.isEmpty { return nil }
        if architectures.contains(productArchitecture) { return nil }
        let abi = architectures.joined(separator: "/")
        return "This plugin is Intel-only (\(abi)) and cannot load in this arm64 Horos process. Obtain an arm64 plugin from its author."
    }

    @objc(helperDiagnosisAtPath:)
    public static func helperDiagnosis(at path: String) -> String? {
        let architectures = machOArchitectures(at: path)
        if architectures.isEmpty { return nil }
        if architectures.contains(productArchitecture) { return nil }
        if architectures.contains(where: { intelSlices.contains($0) }) {
            let name = URL(fileURLWithPath: path).lastPathComponent
            let abi = architectures.joined(separator: "/")
            return "\(name) is Intel-only (\(abi)) and is not launched under Rosetta in this arm64 Horos process. Rebuild the helper for arm64; the command remains in the bundle."
        }
        return nil
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
}
