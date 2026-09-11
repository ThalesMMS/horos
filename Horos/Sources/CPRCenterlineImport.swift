import Foundation

/// Result of reading an external CPR centerline in patient millimetres.
@objc(HorosCPRCenterlineImportResult)
public final class CPRCenterlineImportResult: NSObject {
    @objc public let accepted: Bool
    @objc public let phase: String
    @objc public let diagnosis: String
    @objc public let space: String
    @objc public let nodeCount: Int
    @objc public let packedNodes: [NSNumber]
    @objc public let viewIdentity: String

    @objc public init(accepted: Bool, phase: String, diagnosis: String, space: String,
                      nodeCount: Int, packedNodes: [NSNumber], viewIdentity: String) {
        self.accepted = accepted
        self.phase = phase
        self.diagnosis = diagnosis
        self.space = space
        self.nodeCount = nodeCount
        self.packedNodes = packedNodes
        self.viewIdentity = viewIdentity
    }
}

/// Import xyz centerlines in DICOM patient space and build the same view
/// contract as adding those nodes with the interactive Curved MPR session.
@objc(HorosCPRCenterlineImport)
public final class CPRCenterlineImport: NSObject {
    private static let patientSpaces: Set<String> = ["patient", "lps", "dicom"]
    private static let rejectedSpaces: Set<String> = ["pixel", "voxel", "index", "volume", "image"]
    private static let rejectedUnits: Set<String> = ["px", "pixel", "pixels", "voxel", "voxels"]
    private static let defaultTransversePosition = 0.5
    private static let defaultTransverseSpacingMm = 2.0

    @objc(importPatientSpaceText:)
    public static func importPatientSpaceText(_ text: String) -> CPRCenterlineImportResult {
        let parsed = parse(text)
        if let refusal = parsed.refusal {
            return refused(refusal, space: parsed.space)
        }
        return apply(parsed.nodes, space: parsed.space)
    }

    @objc(patientSpaceTextFromPackedNodes:)
    public static func patientSpaceText(from packedNodes: [NSNumber]) -> String {
        var lines = ["# space=patient", "# units=mm"]
        var index = 0
        while index + 2 < packedNodes.count {
            lines.append(String(format: "%.6f %.6f %.6f",
                                packedNodes[index].doubleValue,
                                packedNodes[index + 1].doubleValue,
                                packedNodes[index + 2].doubleValue))
            index += 3
        }
        return lines.joined(separator: "\n") + "\n"
    }

    @objc(viewIdentityFromPackedNodes:)
    public static func viewIdentity(from packedNodes: [NSNumber]) -> String {
        identity(nodes(from: packedNodes))
    }

    private struct ParsedFile {
        var space = "patient"
        var nodes: [(Double, Double, Double)] = []
        var refusal: String?
    }

    private static func parse(_ raw: String) -> ParsedFile {
        var parsed = ParsedFile()
        var text = raw
        if text.hasPrefix("\u{feff}") {
            text.removeFirst()
        }
        for original in text.split(whereSeparator: \.isNewline) {
            var line = original.trimmingCharacters(in: .whitespacesAndNewlines)
            if let hash = line.firstIndex(of: "#") {
                let comment = String(line[hash...].dropFirst()).trimmingCharacters(in: .whitespaces)
                applyMetadata(comment, to: &parsed)
                line = String(line[..<hash]).trimmingCharacters(in: .whitespaces)
            }
            if line.hasPrefix("//") {
                applyMetadata(String(line.dropFirst(2)), to: &parsed)
                continue
            }
            if line.isEmpty { continue }
            if applyMetadata(line, to: &parsed) { continue }
            if isHeaderRow(line) { continue }
            if parsed.refusal != nil { return parsed }
            let numbers = Doubles(in: line)
            if numbers.count < 3 {
                parsed.refusal = "malformed centerline line"
                return parsed
            }
            if numbers.count >= 6 && numbers.count.isMultiple(of: 3) {
                var index = 0
                while index + 2 < numbers.count {
                    parsed.nodes.append((numbers[index], numbers[index + 1], numbers[index + 2]))
                    index += 3
                }
            } else {
                parsed.nodes.append((numbers[0], numbers[1], numbers[2]))
            }
        }
        return parsed
    }

    @discardableResult
    private static func applyMetadata(_ raw: String, to parsed: inout ParsedFile) -> Bool {
        let text = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        guard let equal = text.firstIndex(of: "=") else { return false }
        let key = text[..<equal].trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        let value = text[text.index(after: equal)...]
            .trimmingCharacters(in: .whitespacesAndNewlines)
            .lowercased()
        if key == "space" || key == "frame" || key == "coords" {
            if rejectedSpaces.contains(value) {
                parsed.refusal = "coordinates are not patient space"
                return true
            }
            if patientSpaces.contains(value) {
                parsed.space = "patient"
                return true
            }
            parsed.refusal = "unknown coordinate space"
            return true
        }
        if key == "units" || key == "unit" {
            if rejectedUnits.contains(value) {
                parsed.refusal = "coordinates are not patient millimetres"
                return true
            }
            return true
        }
        return key == "x" || key.hasPrefix("x,")
    }

    private static func isHeaderRow(_ line: String) -> Bool {
        let tokens = line.lowercased()
            .components(separatedBy: CharacterSet(charactersIn: ",; \t"))
            .filter { !$0.isEmpty }
        return tokens == ["x", "y", "z"] || tokens.starts(with: ["x", "y", "z"])
    }

    private static func Doubles(in line: String) -> [Double] {
        line.replacingOccurrences(of: ",", with: " ")
            .replacingOccurrences(of: ";", with: " ")
            .split(whereSeparator: { $0.isWhitespace })
            .compactMap { Double($0) }
    }

    private static func apply(_ points: [(Double, Double, Double)],
                              space: String) -> CPRCenterlineImportResult {
        let session = CurvedMPRPathSession()
        var accepted: [(Double, Double, Double)] = []
        for point in points {
            let decision = session.addPatientNodeX(point.0, y: point.1, z: point.2)
            if decision.accepted {
                accepted.append(point)
                continue
            }
            if decision.diagnosis == "coincident with last node" {
                continue
            }
            return refused(decision.diagnosis, space: space)
        }
        let done = session.complete()
        if done.accepted == false {
            return refused(done.diagnosis, space: space)
        }
        let packed = packedNodes(from: accepted)
        return CPRCenterlineImportResult(
            accepted: true,
            phase: "complete",
            diagnosis: "imported patient-space centerline",
            space: space,
            nodeCount: accepted.count,
            packedNodes: packed,
            viewIdentity: identity(accepted)
        )
    }

    private static func refused(_ diagnosis: String, space: String) -> CPRCenterlineImportResult {
        CPRCenterlineImportResult(accepted: false, phase: "rejected", diagnosis: diagnosis,
                                  space: space, nodeCount: 0, packedNodes: [], viewIdentity: "")
    }

    private static func packedNodes(from nodes: [(Double, Double, Double)]) -> [NSNumber] {
        nodes.flatMap { [NSNumber(value: $0.0), NSNumber(value: $0.1), NSNumber(value: $0.2)] }
    }

    private static func nodes(from packed: [NSNumber]) -> [(Double, Double, Double)] {
        var result: [(Double, Double, Double)] = []
        var index = 0
        while index + 2 < packed.count {
            result.append((packed[index].doubleValue,
                           packed[index + 1].doubleValue,
                           packed[index + 2].doubleValue))
            index += 3
        }
        return result
    }

    private static func identity(_ nodes: [(Double, Double, Double)]) -> String {
        var length = 0.0
        var cumulative = [0.0]
        for index in 1..<nodes.count {
            let dx = nodes[index].0 - nodes[index - 1].0
            let dy = nodes[index].1 - nodes[index - 1].1
            let dz = nodes[index].2 - nodes[index - 1].2
            length += (dx * dx + dy * dy + dz * dz).squareRoot()
            cumulative.append(length)
        }
        let rel = cumulative.map { length > 0 ? $0 / length : 0 }
        var dir = (1.0, 0.0, 0.0)
        if nodes.count >= 2 {
            let dx = nodes[1].0 - nodes[0].0
            let dy = nodes[1].1 - nodes[0].1
            let dz = nodes[1].2 - nodes[0].2
            let norm = (dx * dx + dy * dy + dz * dz).squareRoot()
            if norm > 0 {
                dir = (dx / norm, dy / norm, dz / norm)
            }
        }
        let nodeText = nodes.map { String(format: "%.6f,%.6f,%.6f", $0.0, $0.1, $0.2) }
            .joined(separator: ";")
        let relText = rel.map { String(format: "%.6f", $0) }.joined(separator: ",")
        return [
            "space=patient",
            "units=mm",
            "nodes=\(nodes.count)",
            String(format: "length=%.6f", length),
            "rel=\(relText)",
            String(format: "transverse=%.1f", defaultTransversePosition),
            String(format: "spacing=%.1f", defaultTransverseSpacingMm),
            "thickness=0",
            "angle=0",
            String(format: "dir=%.6f,%.6f,%.6f", dir.0, dir.1, dir.2),
            "path=\(nodeText)",
        ].joined(separator: "\n")
    }
}
