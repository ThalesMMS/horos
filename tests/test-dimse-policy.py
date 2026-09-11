#!/usr/bin/env python3
"""C-GET syntax/role policy lives in the app (#371), not in a vendor patch."""
import subprocess
import tempfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
source = root / 'Horos/Sources/HorosDIMSEPolicy.swift'
assert source.is_file(), 'FAIL: HorosDIMSEPolicy.swift is missing'

driver = r'''
import Foundation

@main struct Check {
    static let jpeg = "1.2.840.10008.1.2.4.70"
    static let lee = HorosDIMSEPolicy.explicitLittleEndian
    static let lei = HorosDIMSEPolicy.implicitLittleEndian
    static let bee = HorosDIMSEPolicy.explicitBigEndian
    static let ct = "1.2.840.10008.5.1.4.1.1.2"
    static let mr = "1.2.840.10008.5.1.4.1.1.4"

    static func main() {
        precondition(HorosDIMSEPolicy.compiledLibraryPath == "DCMTK")
        precondition(HorosDIMSEPolicy.compiledLibraryVersion == "3.7.0+")
        precondition(HorosDIMSEPolicy.bundledToolsPath == "DCMTK")
        precondition(HorosDIMSEPolicy.bundledToolsVersion == "3.7.0+")
        precondition(HorosDIMSEPolicy.implementationClassUID == "1.2.276.0.7230010.3.0.3.7.0")
        precondition(HorosDIMSEPolicy.compiledLibraryIsUpstreamUnpatched())
        precondition(!HorosDIMSEPolicy.dicomwebReplacesDIMSE())
        precondition(!HorosDIMSEPolicy.sourceFileWriteAPIsAllowed())
        precondition(!HorosDIMSEPolicy.waitpidMayReapAllChildren())

        precondition(HorosDIMSEPolicy.isCGetModel(HorosDIMSEPolicy.patientRootGet))
        precondition(HorosDIMSEPolicy.isCGetModel(HorosDIMSEPolicy.studyRootGet))
        precondition(HorosDIMSEPolicy.isCGetModel(HorosDIMSEPolicy.patientStudyOnlyGet))
        precondition(!HorosDIMSEPolicy.isCGetModel("1.2.840.10008.5.1.4.1.2.2.1"))
        precondition(HorosDIMSEPolicy.requestorStorageRole() == .scp)
        precondition(HorosDIMSEPolicy.serverAcceptsStoreRole(.scp))
        precondition(HorosDIMSEPolicy.serverAcceptsStoreRole(.scuScp))
        precondition(!HorosDIMSEPolicy.serverAcceptsStoreRole(.scu))
        precondition(!HorosDIMSEPolicy.serverAcceptsStoreRole(.none))

        precondition(HorosDIMSEPolicy.rank(accepted: jpeg, original: jpeg) == 0)
        precondition(HorosDIMSEPolicy.rank(accepted: lee, original: jpeg) == 1)
        precondition(HorosDIMSEPolicy.rank(accepted: bee, original: jpeg) == 2)
        precondition(HorosDIMSEPolicy.rank(accepted: lei, original: jpeg) == 3)
        precondition(HorosDIMSEPolicy.rank(accepted: "1.2.840.10008.1.2.4.90", original: jpeg) == 4)
        precondition(HorosDIMSEPolicy.rank(accepted: lee, original: lee) == 0)

        precondition(!HorosDIMSEPolicy.usesEncapsulatedFormat(lee))
        precondition(!HorosDIMSEPolicy.usesEncapsulatedFormat(lei))
        precondition(!HorosDIMSEPolicy.usesEncapsulatedFormat(bee))
        precondition(HorosDIMSEPolicy.usesEncapsulatedFormat(jpeg))
        precondition(HorosDIMSEPolicy.usesEncapsulatedFormat("1.2.840.10008.1.2.5"))

        precondition(!HorosDIMSEPolicy.requiresConversion(accepted: jpeg, original: jpeg))
        precondition(HorosDIMSEPolicy.requiresConversion(accepted: lee, original: jpeg))
        precondition(HorosDIMSEPolicy.requiresConversion(accepted: jpeg, original: lee))
        precondition(!HorosDIMSEPolicy.requiresConversion(accepted: lei, original: lee))
        precondition(HorosDIMSEPolicy.streamsSourceFile(accepted: jpeg, original: jpeg))
        precondition(!HorosDIMSEPolicy.streamsSourceFile(accepted: lee, original: jpeg))

        let jpegAndNative = [
            HorosDIMSEPolicy.Context(id: 1, abstractSyntax: ct, transferSyntax: lee, role: .scp, accepted: true),
            HorosDIMSEPolicy.Context(id: 3, abstractSyntax: ct, transferSyntax: jpeg, role: .scp, accepted: true),
        ]
        let pass = HorosDIMSEPolicy.chooseStoreContext(sopClass: ct, originalSyntax: jpeg, contexts: jpegAndNative)!
        precondition(pass.presentationID == 3)
        precondition(pass.transferSyntax == jpeg)
        precondition(!pass.convert)
        precondition(pass.streamSourceFile)

        let nativeOnly = [
            HorosDIMSEPolicy.Context(id: 5, abstractSyntax: ct, transferSyntax: lee, role: .scp, accepted: true, codecAvailable: true),
        ]
        let convert = HorosDIMSEPolicy.chooseStoreContext(sopClass: ct, originalSyntax: jpeg, contexts: nativeOnly)!
        precondition(convert.presentationID == 5)
        precondition(convert.convert)
        precondition(!convert.streamSourceFile)

        let noCodec = [
            HorosDIMSEPolicy.Context(id: 7, abstractSyntax: ct, transferSyntax: lee, role: .scp, accepted: true, codecAvailable: false),
        ]
        precondition(HorosDIMSEPolicy.chooseStoreContext(sopClass: ct, originalSyntax: jpeg, contexts: noCodec) == nil)

        let wrongRole = [
            HorosDIMSEPolicy.Context(id: 1, abstractSyntax: ct, transferSyntax: jpeg, role: .scu, accepted: true),
            HorosDIMSEPolicy.Context(id: 3, abstractSyntax: ct, transferSyntax: jpeg, role: .none, accepted: true),
            HorosDIMSEPolicy.Context(id: 5, abstractSyntax: mr, transferSyntax: jpeg, role: .scp, accepted: true),
            HorosDIMSEPolicy.Context(id: 7, abstractSyntax: ct, transferSyntax: jpeg, role: .scp, accepted: false),
        ]
        precondition(HorosDIMSEPolicy.chooseStoreContext(sopClass: ct, originalSyntax: jpeg, contexts: wrongRole) == nil)

        let scuScp = [
            HorosDIMSEPolicy.Context(id: 9, abstractSyntax: ct, transferSyntax: jpeg, role: .scuScp, accepted: true),
        ]
        precondition(HorosDIMSEPolicy.chooseStoreContext(sopClass: ct, originalSyntax: jpeg, contexts: scuScp)?.presentationID == 9)

        precondition(HorosDIMSEPolicy.cGetFinalStatus(completed: 4, failed: 0, warnings: 0, cancelled: false) == .success)
        precondition(HorosDIMSEPolicy.cGetFinalStatus(completed: 3, failed: 1, warnings: 0, cancelled: false) == .warning)
        precondition(HorosDIMSEPolicy.cGetFinalStatus(completed: 0, failed: 2, warnings: 0, cancelled: false) == .refused)
        precondition(HorosDIMSEPolicy.cGetFinalStatus(completed: 1, failed: 0, warnings: 1, cancelled: false) == .warning)
        precondition(HorosDIMSEPolicy.cGetFinalStatus(completed: 2, failed: 0, warnings: 0, cancelled: true) == .cancel)
        precondition(HorosDIMSEPolicy.cGetFinalStatus(completed: 0, failed: 0, warnings: 0, cancelled: false) == .success)

        precondition(HorosDIMSEPolicy.ystarrevDCMTKVersion == "3.7.0")
        precondition(!HorosDIMSEPolicy.ystarrevPinIsAdopted)
        precondition(HorosDIMSEPolicy.compiledTreeIsUpstreamPin)
        precondition(!HorosDIMSEPolicy.mayPatchTrackedUpstreamTree)
        precondition(HorosDIMSEPolicy.licenseIdentifier == "dcmtk")
        precondition(HorosDIMSEPolicy.storageRoleProposedForCGet == .scp)
        precondition(HorosDIMSEPolicy.storageRoleAcceptedForCGet(.scp))
        precondition(!HorosDIMSEPolicy.storageRoleAcceptedForCGet(.scu))
        precondition(!HorosDIMSEPolicy.storageRoleAcceptedForCGet(.defaultRole))

        precondition(!HorosDIMSEPolicy.retrieveRequiresListener(mode: 1, moveDestination: nil))
        precondition(HorosDIMSEPolicy.retrieveRequiresListener(mode: 0, moveDestination: nil))
        precondition(!HorosDIMSEPolicy.retrieveRequiresListener(mode: 0, moveDestination: "OTHERAE"))
        precondition(!HorosDIMSEPolicy.retrieveRequiresListener(mode: 2, moveDestination: nil))
        precondition(HorosDIMSEPolicy.wadoCommitMayWrite(key: "WADOPort"))
        precondition(!HorosDIMSEPolicy.wadoCommitMayWrite(key: "TLSEnabled"))
        precondition(!HorosDIMSEPolicy.wadoCommitMayWrite(key: "TLSAuthenticated"))

        let jpegCtx = HorosDIMSEPolicy.AcceptedContext(
            id: 1, abstractSyntax: ct, transferSyntax: jpeg, role: .scp, accepted: true)
        let streamed = HorosDIMSEPolicy.chooseCGetPresentation(
            sopClass: ct, originalTransferSyntax: jpeg,
            contexts: [jpegCtx], writableAfterCodec: [])!
        precondition(streamed.path == .fileStream)
        let nativeOnlyWritable = [
            HorosDIMSEPolicy.AcceptedContext(id: 5, abstractSyntax: ct, transferSyntax: lee, role: .scp, accepted: true)
        ]
        precondition(HorosDIMSEPolicy.chooseCGetPresentation(
            sopClass: ct, originalTransferSyntax: jpeg,
            contexts: nativeOnlyWritable, writableAfterCodec: []) == nil)
        let converted = HorosDIMSEPolicy.chooseCGetPresentation(
            sopClass: ct, originalTransferSyntax: jpeg,
            contexts: nativeOnlyWritable, writableAfterCodec: [lee])!
        precondition(converted.path == .convertedDataset)

        precondition(HorosDIMSEPolicy.finalGetStatus(
            proposed: HorosDIMSEPolicy.success, completed: 4, failed: 0,
            warnings: 0, cancelled: false) == HorosDIMSEPolicy.success)
        precondition(HorosDIMSEPolicy.finalGetStatus(
            proposed: HorosDIMSEPolicy.success, completed: 4, failed: 2,
            warnings: 0, cancelled: false) == HorosDIMSEPolicy.warningSuboperations)
        precondition(HorosDIMSEPolicy.finalGetStatus(
            proposed: HorosDIMSEPolicy.success, completed: 0, failed: 6,
            warnings: 0, cancelled: false) == HorosDIMSEPolicy.outOfResourcesSubOperations)
        precondition(HorosDIMSEPolicy.finalGetStatus(
            proposed: HorosDIMSEPolicy.pending, completed: 2, failed: 0,
            warnings: 0, cancelled: true) == HorosDIMSEPolicy.cancel)
        precondition(!HorosDIMSEPolicy.reportsSuccess(
            status: HorosDIMSEPolicy.warningSuboperations, completed: 4, failed: 2, warnings: 0))
        precondition(HorosDIMSEPolicy.reportsSuccess(
            status: HorosDIMSEPolicy.success, completed: 6, failed: 0, warnings: 0))
        precondition(!HorosDIMSEPolicy.reportsSuccess(refusal: .unwritableFolder))
        precondition(!HorosDIMSEPolicy.reportsSuccess(refusal: .incompatiblePresentation))
        precondition(!HorosDIMSEPolicy.reportsSuccess(refusal: .partialFailure))
        precondition(HorosDIMSEPolicy.reportsSuccess(refusal: .none))

        let uidA = HorosDIMSEPolicy.InstanceFrame(sopInstanceUID: "1.2.3", frameIndex: 0)
        let uidB = HorosDIMSEPolicy.InstanceFrame(sopInstanceUID: "1.2.4", frameIndex: 0)
        let uidA1 = HorosDIMSEPolicy.InstanceFrame(sopInstanceUID: "1.2.3", frameIndex: 1)
        let complete = HorosDIMSEPolicy.compareInventory(requested: [uidA, uidB], received: [uidB, uidA])
        precondition(complete.isSuccess && complete.outcome == "complete")
        let missing = HorosDIMSEPolicy.compareInventory(requested: [uidA, uidB], received: [uidA])
        precondition(!missing.isSuccess && missing.outcome == "missing" && missing.missingUIDs == ["1.2.4"])
        let extra = HorosDIMSEPolicy.compareInventory(requested: [uidA], received: [uidA, uidB])
        precondition(!extra.isSuccess && extra.outcome == "extra")
        let duplicate = HorosDIMSEPolicy.compareInventory(requested: [uidA], received: [uidA, uidA])
        precondition(!duplicate.isSuccess && duplicate.outcome == "duplicate")
        let frames = HorosDIMSEPolicy.compareInventory(requested: [uidA, uidA1], received: [uidA])
        precondition(!frames.isSuccess && frames.missingUIDs == ["1.2.3"])

        precondition(!HorosDIMSEPolicy.vendorPatchIsDIMSEPolicy("DCMTK-3.6.7-GCC-15.patch"))
        precondition(!HorosDIMSEPolicy.vendorPatchIsDIMSEPolicy("DCMTK-3.6.7-print-status.patch"))
        precondition(HorosDIMSEPolicy.vendorPatchIsCompilerCompatibility("DCMTK-3.6.7-GCC-15.patch"))
        precondition(HorosDIMSEPolicy.vendorPatchTouchesToolsNotDIMSE("DCMTK-3.6.7-print-status.patch"))

        print("PASS: C-GET ranks original syntax first, rejects the wrong role, and does not rewrite source files")
    }
}
'''

with tempfile.TemporaryDirectory(prefix='horos-dimse-policy-') as folder:
    path = Path(folder)
    (path / 'check.swift').write_text(driver)
    subprocess.run(['xcrun', 'swiftc', '-parse-as-library', str(source),
                    str(path / 'check.swift'), '-o', str(path / 'check')], check=True)
    subprocess.run([str(path / 'check')], check=True)
