import Foundation

/// Application-owned DIMSE/C-GET policy (#371).
///
/// The app and bundled tools share the pinned upstream DCMTK tree. Transfer
/// syntax selection, roles and final retrieve status remain application policy.
@objc(HorosDIMSEPolicy)
public final class HorosDIMSEPolicy: NSObject {
    @objc public static let compiledLibraryPath = "DCMTK"
    @objc public static let compiledLibraryVersion = "3.7.0+"
    @objc public static let bundledToolsPath = "DCMTK"
    @objc public static let bundledToolsVersion = "3.7.0+"
    @objc public static let ystarrevDCMTKVersion = "3.7.0"
    @objc public static let implementationClassUID = "1.2.276.0.7230010.3.0.3.7.0"
    @objc public static let licenseIdentifier = "dcmtk"
    @objc public static let cmakeToolsTree = bundledToolsPath
    @objc public static let compiledAppTree = compiledLibraryPath
    @objc public static let pinnedUpstreamVersion = bundledToolsVersion

    @objc public static let implicitLittleEndian = "1.2.840.10008.1.2"
    @objc public static let explicitLittleEndian = "1.2.840.10008.1.2.1"
    @objc public static let explicitBigEndian = "1.2.840.10008.1.2.2"
    @objc public static let jpegBaseline = "1.2.840.10008.1.2.4.50"
    @objc public static let jpegLossless = "1.2.840.10008.1.2.4.70"
    @objc public static let rleLossless = "1.2.840.10008.1.2.5"

    @objc public static let patientRootGet = "1.2.840.10008.5.1.4.1.2.1.3"
    @objc public static let studyRootGet = "1.2.840.10008.5.1.4.1.2.2.3"
    @objc public static let patientStudyOnlyGet = "1.2.840.10008.5.1.4.1.2.3.3"

    @objc public static let success: UInt = 0x0000
    @objc public static let pending: UInt = 0xFF00
    @objc public static let cancel: UInt = 0xFE00
    @objc public static let outOfResourcesMatches: UInt = 0xA701
    @objc public static let outOfResourcesSubOperations: UInt = 0xA702
    @objc public static let warningSuboperations: UInt = 0xB000

    public enum Role: String, Equatable {
        case none
        case scu
        case scp
        case scuScp
        public static let defaultRole = Role.none
    }

    public enum Outcome: String, Equatable {
        case success
        case warning
        case refused
        case cancel
        case noPresentation
    }

    public enum CGetSendPath: String, Equatable {
        case fileStream
        case convertedDataset
    }

    public enum RetrieveRefusal: String, Equatable {
        case unwritableFolder
        case incompatiblePresentation
        case partialFailure
        case none
    }

    public struct Context: Equatable {
        public var id: UInt8
        public var abstractSyntax: String
        public var transferSyntax: String
        public var role: Role
        public var accepted: Bool
        public var codecAvailable: Bool

        public init(id: UInt8, abstractSyntax: String, transferSyntax: String,
                    role: Role, accepted: Bool, codecAvailable: Bool = true) {
            self.id = id
            self.abstractSyntax = abstractSyntax
            self.transferSyntax = transferSyntax
            self.role = role
            self.accepted = accepted
            self.codecAvailable = codecAvailable
        }
    }

    public typealias AcceptedContext = Context

    public struct Choice: Equatable {
        public var presentationID: UInt8
        public var transferSyntax: String
        public var convert: Bool
        public var streamSourceFile: Bool
        public var path: CGetSendPath { convert ? .convertedDataset : .fileStream }
    }

    public struct InstanceFrame: Equatable, Hashable {
        public var sopInstanceUID: String
        public var frameIndex: Int

        public init(sopInstanceUID: String, frameIndex: Int = 0) {
            self.sopInstanceUID = sopInstanceUID
            self.frameIndex = frameIndex
        }
    }

    public struct InventoryVerdict: Equatable {
        public var outcome: String
        public var isSuccess: Bool
        public var missingUIDs: [String]
        public var duplicateUIDs: [String]
        public var extraUIDs: [String]
    }

    @objc(cGetStatusDescription:) public static func cGetStatusDescription(_ status: UInt) -> String {
        switch status {
        case 0x0000: return "Success"
        case 0xFF00: return "Pending"
        case 0xA701: return "Refused: OutOfResourcesNumberOfMatches"
        case 0xA702: return "Refused: OutOfResourcesSubOperations"
        case 0xA800: return "Failed: SOPClassNotSupported"
        case 0xA900: return "Failed: IdentifierDoesNotMatchSOPClass"
        case 0xFE00: return "Cancel: SubOperationsTerminatedDueToCancelIndication"
        case 0xB000: return "Warning: SubOperationsCompleteOneOrMoreFailures"
        case 0xC000...0xCFFF: return "Failed: UnableToProcess"
        default: return String(format: "Unknown Status: 0x%04x", status)
        }
    }

    public static func isCGetModel(_ uid: String) -> Bool {
        uid == patientRootGet || uid == studyRootGet || uid == patientStudyOnlyGet
    }

    public static func requestorStorageRole() -> Role { .scp }
    public static var storageRoleProposedForCGet: Role { .scp }

    public static func serverAcceptsStoreRole(_ role: Role) -> Bool {
        role == .scp || role == .scuScp
    }

    public static func storageRoleAcceptedForCGet(_ role: Role) -> Bool {
        serverAcceptsStoreRole(role)
    }

    public static func usesEncapsulatedFormat(_ uid: String) -> Bool {
        uid != implicitLittleEndian && uid != explicitLittleEndian && uid != explicitBigEndian
            && uid != "1.2.840.10008.1.2.1.99"
    }

    @objc(rankAccepted:original:) public static func rank(accepted: String, original: String) -> Int {
        if accepted == original { return 0 }
        if accepted == explicitLittleEndian { return 1 }
        if accepted == explicitBigEndian { return 2 }
        if accepted == implicitLittleEndian { return 3 }
        return 4
    }

    public static func transferSyntaxRank(original: String, accepted: String) -> Int {
        rank(accepted: accepted, original: original)
    }

    @objc(requiresConversionAccepted:original:) public static func requiresConversion(accepted: String, original: String) -> Bool {
        accepted != original && (usesEncapsulatedFormat(accepted) || usesEncapsulatedFormat(original))
    }

    public static func streamsSourceFile(accepted: String, original: String) -> Bool {
        !requiresConversion(accepted: accepted, original: original)
    }

    public static func chooseStoreContext(sopClass: String, originalSyntax: String,
                                          contexts: [Context]) -> Choice? {
        let eligible = contexts.filter {
            $0.accepted && $0.abstractSyntax == sopClass && serverAcceptsStoreRole($0.role)
        }
        let ordered = eligible.enumerated().sorted { lhs, rhs in
            let left = rank(accepted: lhs.element.transferSyntax, original: originalSyntax)
            let right = rank(accepted: rhs.element.transferSyntax, original: originalSyntax)
            if left != right { return left < right }
            return lhs.offset < rhs.offset
        }.map(\.element)

        for context in ordered {
            let convert = requiresConversion(accepted: context.transferSyntax, original: originalSyntax)
            if convert && !context.codecAvailable { continue }
            return Choice(presentationID: context.id,
                          transferSyntax: context.transferSyntax,
                          convert: convert,
                          streamSourceFile: !convert)
        }
        return nil
    }

    public static func chooseCGetPresentation(sopClass: String,
                                             originalTransferSyntax: String,
                                             contexts: [AcceptedContext],
                                             writableAfterCodec: Set<String>) -> Choice? {
        let mapped = contexts.map { context -> Context in
            var copy = context
            let convert = requiresConversion(accepted: context.transferSyntax, original: originalTransferSyntax)
            copy.codecAvailable = !convert || writableAfterCodec.contains(context.transferSyntax)
            return copy
        }
        return chooseStoreContext(sopClass: sopClass, originalSyntax: originalTransferSyntax, contexts: mapped)
    }

    public static func cGetFinalStatus(completed: Int, failed: Int, warnings: Int,
                                        cancelled: Bool) -> Outcome {
        if cancelled { return .cancel }
        if failed > 0 && completed == 0 && warnings == 0 { return .refused }
        if failed > 0 || warnings > 0 { return .warning }
        return .success
    }

    @objc(finalGetStatusProposed:completed:failed:warnings:cancelled:) public static func finalGetStatus(proposed: UInt, completed: UInt, failed: UInt,
                                     warnings: UInt, cancelled: Bool) -> UInt {
        if proposed == cancel { return cancel }
        if cancelled && (proposed == pending || proposed == success) { return cancel }
        if proposed != success && proposed != pending { return proposed }
        switch cGetFinalStatus(completed: Int(completed), failed: Int(failed),
                                warnings: Int(warnings), cancelled: false) {
        case .success: return success
        case .warning: return warningSuboperations
        case .refused: return outOfResourcesSubOperations
        case .cancel: return cancel
        case .noPresentation: return outOfResourcesSubOperations
        }
    }

    public static func reportsSuccess(status: UInt, completed: UInt, failed: UInt, warnings: UInt) -> Bool {
        status == success && failed == 0 && warnings == 0
    }

    public static func reportsSuccess(refusal: RetrieveRefusal) -> Bool {
        refusal == .none
    }

    public static func compareInventory(requested: [InstanceFrame],
                                       received: [InstanceFrame]) -> InventoryVerdict {
        func uniqueUIDs(_ frames: [InstanceFrame], matching: Set<InstanceFrame>) -> [String] {
            Array(Set(frames.filter { matching.contains($0) }.map(\.sopInstanceUID))).sorted()
        }

        var requestedCounts: [InstanceFrame: Int] = [:]
        var receivedCounts: [InstanceFrame: Int] = [:]
        for frame in requested { requestedCounts[frame, default: 0] += 1 }
        for frame in received { receivedCounts[frame, default: 0] += 1 }

        let requestedSet = Set(requested)
        let receivedSet = Set(received)
        let missing = requestedSet.subtracting(receivedSet)
        let extra = receivedSet.subtracting(requestedSet)
        let duplicates = receivedCounts.filter { $0.value > 1 }.map(\.key)

        if !missing.isEmpty {
            return InventoryVerdict(outcome: "missing", isSuccess: false,
                                     missingUIDs: uniqueUIDs(requested, matching: missing),
                                     duplicateUIDs: [], extraUIDs: [])
        }
        if !duplicates.isEmpty {
            return InventoryVerdict(outcome: "duplicate", isSuccess: false,
                                     missingUIDs: [],
                                     duplicateUIDs: uniqueUIDs(received, matching: Set(duplicates)),
                                     extraUIDs: [])
        }
        if !extra.isEmpty {
            return InventoryVerdict(outcome: "extra", isSuccess: false,
                                     missingUIDs: [], duplicateUIDs: [],
                                     extraUIDs: uniqueUIDs(received, matching: extra))
        }
        return InventoryVerdict(outcome: "complete", isSuccess: true,
                                 missingUIDs: [], duplicateUIDs: [], extraUIDs: [])
    }

    public static func retrieveRequiresListener(mode: Int, moveDestination: String?) -> Bool {
        switch mode {
        case 1, 2, 3:
            return false
        default:
            return (moveDestination ?? "").isEmpty
        }
    }

    public static func wadoCommitMayWrite(key: String) -> Bool {
        !key.hasPrefix("TLS")
    }

    public static func vendorPatchIsDIMSEPolicy(_ name: String) -> Bool {
        name.localizedCaseInsensitiveContains("c-get") || name.localizedCaseInsensitiveContains("dimse")
    }

    public static func vendorPatchIsCompilerCompatibility(_ name: String) -> Bool {
        name == "DCMTK-3.6.7-GCC-15.patch"
    }

    public static func vendorPatchTouchesToolsNotDIMSE(_ name: String) -> Bool {
        name == "DCMTK-3.6.7-print-status.patch"
    }

    public static var mayPatchTrackedUpstreamTree: Bool { false }
    public static var compiledTreeIsUpstreamPin: Bool { true }
    public static var ystarrevPinIsAdopted: Bool { false }

    public static func compiledLibraryIsUpstreamUnpatched() -> Bool { true }

    public static func dicomwebReplacesDIMSE() -> Bool { false }

    /// C-GET reads source instances under a shared lock. It must not save,
    /// unlink or rename them as a side effect of sending.
    public static func sourceFileWriteAPIsAllowed() -> Bool { false }

    /// The listener may wait only for its own association workers, never `waitpid(-1)`.
    public static func waitpidMayReapAllChildren() -> Bool { false }
}
