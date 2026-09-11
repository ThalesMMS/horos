import Foundation

/// Local helper contract for tumour segmentation (#381).
///
/// Horos launches `helper --job job.json`. The volume is float32 little-endian
/// in z, y, x order (x fastest). The helper writes a UInt8 labelmap of the same
/// voxel count. Labels are 0 background, 1 tumour core, 2 edema, 4 enhancing.
/// Shape-resize is not geometric registration. A mock or heuristic result is not
/// a trained-model prediction.
@objc(HorosTumorSegmentationJob)
public final class TumorSegmentationJob: NSObject {
    public enum Kind: String, Equatable {
        case mock
        case candidate
        case nnunet
        case external
    }

    public static let allowedLabels: [UInt8] = [0, 1, 2, 4]
    public static let timeoutSeconds: Int = 180
    public static let fallbackKindWhenModelMissing: Kind? = nil

    @objc public let width: Int
    @objc public let height: Int
    @objc public let depth: Int
    @objc public let expectedVoxelCount: Int
    @objc public let voxelOrder = "z,y,x"
    @objc public let inputScalar = "float32-le"
    @objc public let selectedSeriesCount: Int
    @objc public let seedCount: Int
    @objc public let registrationIsGeometric: Bool
    public let spacingMM: [Double]
    public let voxelToPatient: [[Double]]
    public let inputVolume: String
    public let outputLabelmap: String
    public let resultJSON: String?

    public init(width: Int, height: Int, depth: Int, expectedVoxelCount: Int,
                spacingMM: [Double], voxelToPatient: [[Double]],
                inputVolume: String, outputLabelmap: String, resultJSON: String?,
                selectedSeriesCount: Int, seedCount: Int, registrationIsGeometric: Bool) {
        self.width = width
        self.height = height
        self.depth = depth
        self.expectedVoxelCount = expectedVoxelCount
        self.spacingMM = spacingMM
        self.voxelToPatient = voxelToPatient
        self.inputVolume = inputVolume
        self.outputLabelmap = outputLabelmap
        self.resultJSON = resultJSON
        self.selectedSeriesCount = selectedSeriesCount
        self.seedCount = seedCount
        self.registrationIsGeometric = registrationIsGeometric
        super.init()
    }

    public static func voxelCount(width: Int, height: Int, depth: Int) -> Int? {
        guard width > 0, height > 0, depth > 0 else { return nil }
        let plane = width.multipliedReportingOverflow(by: height)
        guard !plane.overflow else { return nil }
        let voxels = plane.partialValue.multipliedReportingOverflow(by: depth)
        return voxels.overflow ? nil : voxels.partialValue
    }

    public static func inputByteCount(width: Int, height: Int, depth: Int) -> Int? {
        guard let voxels = voxelCount(width: width, height: height, depth: depth) else { return nil }
        let bytes = voxels.multipliedReportingOverflow(by: MemoryLayout<Float>.size)
        return bytes.overflow ? nil : bytes.partialValue
    }

    public static func labelmapByteCount(width: Int, height: Int, depth: Int) -> Int? {
        voxelCount(width: width, height: height, depth: depth)
    }

    public static func parse(_ json: [String: Any]) throws -> TumorSegmentationJob {
        if let reason = parseRefusal(json) {
            throw NSError(domain: "HorosTumorSegmentationJob", code: 1,
                           userInfo: [NSLocalizedDescriptionKey: reason])
        }
        let dimensions = intTriple(json["dimensions"])!
        let matrix = matrix4x4(json["referenceVoxelToPatientMatrix"] ?? json["voxelToPatientMatrix"])!
        let series = arrayOfDictionaries(json["selectedDICOMSeries"])
        let seeds = arrayOfDictionaries(json["tumourSeeds"] ?? json["tumorSeeds"])
        return TumorSegmentationJob(
            width: dimensions[0], height: dimensions[1], depth: dimensions[2],
            expectedVoxelCount: intValue(json["expectedVoxelCount"])!,
            spacingMM: doubleTriple(json["spacingMM"])!,
            voxelToPatient: matrix,
            inputVolume: stringValue(json["inputVolume"]) ?? "",
            outputLabelmap: stringValue(json["outputLabelmap"]) ?? "",
            resultJSON: stringValue(json["resultJSON"]),
            selectedSeriesCount: series.count,
            seedCount: seeds.count,
            registrationIsGeometric: series.allSatisfy { isGeometricRegistration($0["channelRegistration"]) }
        )
    }

    public static func parseRefusal(_ json: [String: Any]) -> String? {
        guard let dimensions = intTriple(json["dimensions"]) else {
            return "Job is missing dimensions [width, height, depth]."
        }
        guard let voxels = voxelCount(width: dimensions[0], height: dimensions[1], depth: dimensions[2]) else {
            return "Job dimensions must be positive."
        }
        guard let expected = intValue(json["expectedVoxelCount"]) else {
            return "Job is missing expectedVoxelCount."
        }
        if expected != voxels {
            return "expectedVoxelCount \(expected) does not match \(voxels) voxels (width×height×depth)."
        }
        guard doubleTriple(json["spacingMM"]) != nil else {
            return "Job is missing spacingMM [x, y, z]."
        }
        guard matrix4x4(json["referenceVoxelToPatientMatrix"] ?? json["voxelToPatientMatrix"]) != nil else {
            return "Job needs a finite 4×4 LPS voxel-to-patient matrix."
        }
        guard let input = stringValue(json["inputVolume"]), input.isEmpty == false else {
            return "Job is missing inputVolume."
        }
        guard let output = stringValue(json["outputLabelmap"]), output.isEmpty == false else {
            return "Job is missing outputLabelmap."
        }
        _ = input
        _ = output
        return nil
    }

    public static func importRefusal(for job: TumorSegmentationJob) -> String? {
        guard job.registrationIsGeometric else {
            return "Channel registration is a shape resize, not DICOM patient-space geometry. The labelmap will not be imported as a registered series."
        }
        return nil
    }

    public static func isGeometricRegistration(_ value: Any?) -> Bool {
        let mode = stringValue(value)?.lowercased() ?? ""
        if mode.isEmpty { return false }
        if mode.contains("resize") || mode.contains("fallback") { return false }
        return mode.contains("dicom") || mode.contains("patient") || mode == "geometric"
    }

    public static func seriesRole(fromDescription text: String) -> String {
        let folded = text.lowercased().replacingOccurrences(of: "_", with: " ").replacingOccurrences(of: "-", with: " ")
        if folded.contains("flair") || folded.contains("fluid attenuated") { return "flair" }
        if folded.contains("t2") && !["flair", "dwi", "diff", "adc", "localizer", "scout"].contains(where: { folded.contains($0) }) {
            return "t2"
        }
        if ["t1", "mprage", "spgr", "bravo", "ir fspgr"].contains(where: { folded.contains($0) }) {
            if ["post", "gad", "gadavist", "contrast", "ce", "+c", "c+", "t1c", "t1ce", "gd"].contains(where: { folded.contains($0) }) {
                return "t1c"
            }
            return "t1"
        }
        return "selected"
    }

    public static func kind(forHelperName name: String) -> Kind {
        let leaf = (name as NSString).lastPathComponent.lowercased()
        if leaf.contains("nnunet") { return .nnunet }
        if leaf.contains("candidate") { return .candidate }
        if leaf.contains("external") { return .external }
        return .mock
    }

    public static func displayKind(result: [String: Any], helperKind: Kind) -> Kind {
        let backend = stringValue(result["backend"])?.lowercased() ?? ""
        if backend.contains("nnunet") || backend.contains("trained") { return .nnunet }
        if backend.contains("candidate") || backend.contains("heuristic") { return .candidate }
        if backend.contains("external") { return .external }
        if backend.contains("mock") { return .mock }
        return helperKind
    }

    public static func promoteToTrained(result: [String: Any], helperKind: Kind) -> Bool {
        displayKind(result: result, helperKind: helperKind) == .nnunet
    }

    public static func nnunetModelFolder(environment: [String: String], config: [String: Any]) -> String? {
        let fromEnv = environment["HOROS_TUMOR_NNUNET_MODEL_FOLDER"]?.trimmingCharacters(in: .whitespacesAndNewlines)
        if let fromEnv, fromEnv.isEmpty == false { return fromEnv }
        for key in ["nnunet_model_folder", "model_folder"] {
            if let value = stringValue(config[key]), value.isEmpty == false { return value }
        }
        return nil
    }

    public static func nnunetRefusal(environment: [String: String], config: [String: Any]) -> String? {
        guard let folder = nnunetModelFolder(environment: environment, config: config) else {
            return "No local nnU-Net model folder configured. Set HOROS_TUMOR_NNUNET_MODEL_FOLDER or add nnunet_model_folder to the local config. This is not a mock or heuristic fallback."
        }
        if FileManager.default.fileExists(atPath: folder) == false {
            return "Configured nnU-Net model folder does not exist: \(folder)"
        }
        return nil
    }

    public static func launchArguments(helper: String, job: String) -> [String] {
        _ = helper
        return ["--job", job]
    }

    public static func sanitizeLog(_ text: String, patientName: String, patientID: String) -> String {
        var log = text
        if patientName.isEmpty == false {
            log = log.replacingOccurrences(of: patientName, with: "[patient]")
        }
        if patientID.isEmpty == false {
            log = log.replacingOccurrences(of: patientID, with: "[id]")
        }
        return log
    }

    public static func labelmapRefusal(_ data: Data, expectedVoxelCount: Int) -> String? {
        if data.count != expectedVoxelCount {
            return "Labelmap is truncated: \(data.count) bytes, expected \(expectedVoxelCount)."
        }
        if let invalid = data.first(where: { !allowedLabels.contains($0) }) {
            return "Label \(invalid) is not a Horos tumour label (0, 1, 2, 4)."
        }
        return nil
    }

    private static func intValue(_ value: Any?) -> Int? {
        switch value {
        case let number as Int: return number
        case let number as NSNumber: return number.intValue
        default: return nil
        }
    }

    private static func stringValue(_ value: Any?) -> String? {
        switch value {
        case let text as String: return text
        case let number as NSNumber: return number.stringValue
        default: return nil
        }
    }

    private static func intTriple(_ value: Any?) -> [Int]? {
        guard let values = value as? [Any], values.count >= 3,
              let width = intValue(values[0]), let height = intValue(values[1]),
              let depth = intValue(values[2]) else { return nil }
        return [width, height, depth]
    }

    private static func doubleTriple(_ value: Any?) -> [Double]? {
        guard let values = value as? [Any], values.count >= 3 else { return nil }
        let numbers = values.prefix(3).compactMap(doubleValue)
        guard numbers.count == 3, numbers.allSatisfy({ $0.isFinite && $0 > 0 }) else { return nil }
        return numbers
    }

    private static func doubleValue(_ value: Any) -> Double? {
        switch value {
        case let number as Double: return number
        case let number as Int: return Double(number)
        case let number as NSNumber: return number.doubleValue
        default: return nil
        }
    }

    private static func matrix4x4(_ value: Any?) -> [[Double]]? {
        guard let rows = value as? [Any], rows.count == 4 else { return nil }
        var matrix: [[Double]] = []
        for row in rows {
            guard let cells = row as? [Any], cells.count == 4 else { return nil }
            let numbers = cells.compactMap(doubleValue)
            guard numbers.count == 4, numbers.allSatisfy(\.isFinite) else { return nil }
            matrix.append(numbers)
        }
        return matrix
    }

    private static func arrayOfDictionaries(_ value: Any?) -> [[String: Any]] {
        (value as? [Any])?.compactMap { $0 as? [String: Any] } ?? []
    }
}
