//  Copyright (c) 2026 Thales Matheus M Santos (ThalesMMS)
//
//  This file is part of a fork of Horos (https://github.com/ThalesMMS/horos).
//
//  It is free software: you can redistribute it and/or modify it under the
//  terms of the GNU Lesser General Public License as published by the Free
//  Software Foundation, version 3 of the License.
//
//  It is distributed in the hope that it will be useful, but WITHOUT ANY
//  WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR
//  A PARTICULAR PURPOSE. See the GNU Lesser General Public License for details.

import AppKit
import Security
import Darwin

struct HorosInstallContext {
    let source: URL
    let destination: URL
    let userDirectory: Bool
    let diskImage: String?
    let nested: Bool
    let authorization: Bool
}

enum HorosInstallDecision { case install, decline(suppress: Bool) }
enum HorosInstallResult: Equatable {
    case skipped, declined, authorizationCancelled, activatedExisting
    case installed(dockAdded: Bool, originalRetained: Bool)
    case failed(String)
}

enum HorosInstallError: LocalizedError {
    case cancelled, operation(String)
    var errorDescription: String? {
        switch self {
        case .cancelled: return "Authorization was cancelled."
        case .operation(let reason): return reason
        }
    }
}

/// The consent and lifecycle policy uses the same boundary in production and
/// in tests. Test implementations never launch an application or write the Dock.
@MainActor protocol HorosInstallOperations {
    func consent(_ context: HorosInstallContext) -> HorosInstallDecision
    func isRunning(_ destination: URL) -> Bool
    func activate(_ destination: URL) throws
    func stage(_ context: HorosInstallContext, at staging: URL) throws
    func validate(_ context: HorosInstallContext, at staging: URL) throws
    func commit(_ context: HorosInstallContext, staging: URL) throws
    func discard(_ staging: URL)
    func relaunch(_ destination: URL, diskImage: String?) throws
    func addToDock(_ destination: URL) -> Bool
    func trash(_ source: URL) -> Bool
}

@MainActor @objc(HorosApplicationInstaller)
final class HorosApplicationInstaller: NSObject {
    static let suppressKey = "moveToApplicationsFolderAlertSuppress"
    private static var inProgress = false

    static func preferredDirectory(user: URL?, local: URL, manager: FileManager = .default) -> URL {
        if let user, let contents = try? manager.contentsOfDirectory(at: user, includingPropertiesForKeys: nil),
           contents.contains(where: { $0.pathExtension == "app" }) {
            return user.resolvingSymlinksInPath()
        }
        return local.resolvingSymlinksInPath()
    }

    static func isInstalled(_ source: URL, directories: [URL]) -> Bool {
        let path = source.standardizedFileURL.path
        return directories.contains { path.hasPrefix($0.standardizedFileURL.path + "/") }
            || source.deletingLastPathComponent().pathComponents.contains("Applications")
    }

    static func run(_ context: HorosInstallContext, defaults: UserDefaults,
                    operations: any HorosInstallOperations) -> HorosInstallResult {
        if defaults.bool(forKey: suppressKey) { return .skipped }
        switch operations.consent(context) {
        case .decline(let suppress):
            if suppress { defaults.set(true, forKey: suppressKey) }
            return .declined
        case .install: break
        }
        let staging = context.destination.deletingLastPathComponent()
            .appendingPathComponent(".horos-install-\(UUID().uuidString).app")
        defer { operations.discard(staging) }
        do {
            // Check before either installation path, including authorization.
            if operations.isRunning(context.destination) {
                try operations.activate(context.destination)
                return .activatedExisting
            }
            try operations.stage(context, at: staging)
            try operations.validate(context, at: staging)
            // A destination may have started while copying or authenticating.
            if operations.isRunning(context.destination) {
                try operations.activate(context.destination)
                return .activatedExisting
            }
            try operations.commit(context, staging: staging)
            // A failed launch keeps the source and never modifies the Dock.
            try operations.relaunch(context.destination, diskImage: context.nested ? nil : context.diskImage)
            let dock = operations.addToDock(context.destination)
            let retained = context.nested || context.diskImage != nil || !operations.trash(context.source)
            return .installed(dockAdded: dock, originalRetained: retained)
        } catch HorosInstallError.cancelled {
            return .authorizationCancelled
        } catch {
            return .failed(error.localizedDescription)
        }
    }

    @objc static func moveToApplicationsFolderIfNecessary() {
        #if !MACAPPSTORE
        guard !inProgress, !UserDefaults.standard.bool(forKey: suppressKey) else { return }
        let source = Bundle.main.bundleURL.standardizedFileURL
        let manager = FileManager.default
        let directories = manager.urls(for: .applicationDirectory, in: .allDomainsMask)
        let nested = source.deletingLastPathComponent().pathComponents.contains { $0.hasSuffix(".app") }
        if isInstalled(source, directories: directories) && !nested { return }
        guard let local = manager.urls(for: .applicationDirectory, in: .localDomainMask).first else { return }
        let user = manager.urls(for: .applicationDirectory, in: .userDomainMask).first
        let directory = preferredDirectory(user: user, local: local)
        let destination = directory.appendingPathComponent(source.lastPathComponent)
        let context = HorosInstallContext(source: source, destination: destination,
            userDirectory: directory == user?.resolvingSymlinksInPath(),
            diskImage: HorosNativeInstallOperations.containingDiskImage(source), nested: nested,
            authorization: !manager.isWritableFile(atPath: directory.path)
                || (manager.fileExists(atPath: destination.path) && !manager.isWritableFile(atPath: destination.path)))
        inProgress = true
        defer { inProgress = false }
        let result = run(context, defaults: .standard, operations: HorosNativeInstallOperations())
        switch result {
        case .activatedExisting, .installed:
            exit(0)
        case .failed(let reason):
            let alert = NSAlert()
            alert.messageText = NSLocalizedString("Could not move to Applications folder", comment: "")
            alert.informativeText = reason
            alert.runModal()
        default: break
        }
        #endif
    }
}

@MainActor final class HorosNativeInstallOperations: HorosInstallOperations {
    private let manager = FileManager.default

    func consent(_ context: HorosInstallContext) -> HorosInstallDecision {
        let alert = NSAlert()
        alert.messageText = NSLocalizedString(context.userDirectory
            ? "Move Isis DICOM Viewer to Applications folder in your Home folder?" : "Move Isis DICOM Viewer to Applications folder?", comment: "")
        alert.informativeText = NSLocalizedString("Isis DICOM Viewer is currently not in the Applications folder. It is recommended to run Isis DICOM Viewer from the Applications folder. I can move it now, add an icon to the dock and restart, if you agree? (recommended)", comment: "")
        if context.authorization {
            alert.informativeText += " " + NSLocalizedString("Note that this will require an administrator password.", comment: "")
        }
        alert.addButton(withTitle: NSLocalizedString("Move to Applications Folder", comment: ""))
        alert.addButton(withTitle: NSLocalizedString("Do Not Move", comment: "")).keyEquivalent = "\u{1b}"
        alert.showsSuppressionButton = true
        NSApp.activate(ignoringOtherApps: true)
        return alert.runModal() == .alertFirstButtonReturn ? .install
            : .decline(suppress: alert.suppressionButton?.state == .on)
    }

    func isRunning(_ destination: URL) -> Bool {
        NSWorkspace.shared.runningApplications.contains {
            $0.bundleURL?.resolvingSymlinksInPath() == destination.resolvingSymlinksInPath()
        }
    }

    func activate(_ destination: URL) throws {
        guard let application = NSWorkspace.shared.runningApplications.first(where: {
            $0.bundleURL?.resolvingSymlinksInPath() == destination.resolvingSymlinksInPath()
        }), application.activate(options: [.activateAllWindows]) else {
            throw HorosInstallError.operation("The installed application could not be activated.")
        }
    }

    func stage(_ context: HorosInstallContext, at staging: URL) throws {
        guard context.source.pathExtension == "app", context.destination.pathExtension == "app",
              context.source.resolvingSymlinksInPath() != context.destination.resolvingSymlinksInPath(),
              !manager.fileExists(atPath: staging.path) else {
            throw HorosInstallError.operation("Invalid application installation paths.")
        }
        // Do not follow a destination symlink into an unrelated location.
        if (try? context.destination.resourceValues(forKeys: [.isSymbolicLinkKey]).isSymbolicLink) == true {
            throw HorosInstallError.operation("The installation destination is a symbolic link.")
        }
        if context.authorization {
            try Self.authorizedShell(Self.authorizedCopyScript(source: context.source, staging: staging))
        } else {
            try manager.copyItem(at: context.source, to: staging)
            // Foundation may add quarantine flags to a copied bundle. Retain
            // the source attribute, including its original trust provenance.
            if let value = try Self.quarantine(context.source) {
                let result = value.withUnsafeBytes {
                    setxattr(staging.path, "com.apple.quarantine", $0.baseAddress, value.count, 0, 0)
                }
                guard result == 0 else { throw POSIXError(POSIXErrorCode(rawValue: errno) ?? .EIO) }
            }
        }
    }

    func validate(_ context: HorosInstallContext, at staging: URL) throws {
        guard let executable = Bundle(url: staging)?.executableURL,
              manager.isExecutableFile(atPath: executable.path) else {
            throw HorosInstallError.operation("The copied application bundle is incomplete.")
        }
        // Preserve the downloaded bundle's trust state; never strip quarantine.
        guard try Self.quarantine(context.source) == Self.quarantine(staging) else {
            throw HorosInstallError.operation("The copied application's quarantine differs from the source.")
        }
        var sourceCode: SecStaticCode?
        var stagedCode: SecStaticCode?
        guard SecStaticCodeCreateWithPath(context.source as CFURL, [], &sourceCode) == errSecSuccess,
              SecStaticCodeCreateWithPath(staging as CFURL, [], &stagedCode) == errSecSuccess,
              let sourceCode, let stagedCode else {
            throw HorosInstallError.operation("The application signature could not be inspected.")
        }
        let sourceStatus = SecStaticCodeCheckValidity(sourceCode, SecCSFlags(rawValue: kSecCSCheckAllArchitectures), nil)
        if sourceStatus == errSecCSUnsigned {
            guard SecStaticCodeCheckValidity(stagedCode, [], nil) == errSecCSUnsigned else {
                throw HorosInstallError.operation("The copied application's signing state changed.")
            }
            return
        }
        var requirement: SecRequirement?
        guard sourceStatus == errSecSuccess,
              SecCodeCopyDesignatedRequirement(sourceCode, [], &requirement) == errSecSuccess,
              SecStaticCodeCheckValidity(stagedCode, SecCSFlags(rawValue: kSecCSCheckAllArchitectures), requirement) == errSecSuccess else {
            throw HorosInstallError.operation("The copied application's signature is invalid.")
        }
    }

    func commit(_ context: HorosInstallContext, staging: URL) throws {
        if (try? context.destination.resourceValues(forKeys: [.isSymbolicLinkKey]).isSymbolicLink) == true {
            throw HorosInstallError.operation("The installation destination is a symbolic link.")
        }
        if context.authorization {
            // Keep a rollback copy rather than privileged recursive deletion.
            let backup = context.destination.deletingLastPathComponent()
                .appendingPathComponent(".horos-previous-\(UUID().uuidString).app")
            try Self.authorizedShell(Self.authorizedCommitScript(destination: context.destination,
                staging: staging, backup: backup))
            if manager.fileExists(atPath: backup.path), !trash(backup) {
                NSLog("The previous application was retained at %@", backup.path)
            }
        } else {
            if manager.fileExists(atPath: context.destination.path), !trash(context.destination) {
                throw HorosInstallError.operation("The previous application could not be moved to Trash.")
            }
            try manager.moveItem(at: staging, to: context.destination)
        }
    }

    func discard(_ staging: URL) {
        // Only the unique staging path owned by this transaction is discarded.
        if manager.fileExists(atPath: staging.path), !trash(staging) {
            NSLog("The incomplete installation was retained at %@", staging.path)
        }
    }

    func trash(_ source: URL) -> Bool {
        do { try manager.trashItem(at: source, resultingItemURL: nil); return true }
        catch { return false }
    }

    func addToDock(_ destination: URL) -> Bool { PFAddInstalledApplicationToDock(destination.path) }

    static func shellQuote(_ value: String) -> String {
        "'" + value.replacingOccurrences(of: "'", with: "'\\''") + "'"
    }

    static func appleScriptQuote(_ value: String) -> String {
        "\"" + value.replacingOccurrences(of: "\\", with: "\\\\")
            .replacingOccurrences(of: "\"", with: "\\\"")
            .replacingOccurrences(of: "\r", with: "\\r")
            .replacingOccurrences(of: "\n", with: "\\n") + "\""
    }

    static func authorizedCopyScript(source: URL, staging: URL) -> String {
        let src = shellQuote(source.path)
        let dst = shellQuote(staging.path)
        return "/usr/bin/ditto --rsrc --extattr --acl " + src + " " + dst + " || exit 1; "
            + "if quarantine=$(/usr/bin/xattr -px com.apple.quarantine " + src + " 2>/dev/null); then "
            + "/usr/bin/xattr -wx com.apple.quarantine \"$quarantine\" " + dst + " || exit 1; fi"
    }

    static func authorizedCommitScript(destination: URL, staging: URL, backup: URL) -> String {
        let dst = shellQuote(destination.path)
        let old = shellQuote(backup.path)
        let src = shellQuote(staging.path)
        return "if [ -L \(dst) ] || [ -e \(old) ]; then exit 1; fi; if [ -e \(dst) ]; then /bin/mv \(dst) \(old) || exit 1; fi; "
            + "if /bin/mv \(src) \(dst); then exit 0; else "
            + "if [ -e \(old) ]; then /bin/mv \(old) \(dst); fi; exit 1; fi"
    }

    static func authorizedShell(_ command: String) throws {
        var failure: NSDictionary?
        let script = NSAppleScript(source: "do shell script " + appleScriptQuote(command) + " with administrator privileges")
        guard script?.executeAndReturnError(&failure) != nil else {
            if failure?[NSAppleScript.errorNumber] as? Int == -128 { throw HorosInstallError.cancelled }
            throw HorosInstallError.operation(failure?[NSAppleScript.errorMessage] as? String ?? "Authorized installation failed.")
        }
    }

    static func quarantine(_ url: URL) throws -> Data? {
        let size = getxattr(url.path, "com.apple.quarantine", nil, 0, 0, 0)
        if size < 0 {
            if errno == ENOATTR { return nil }
            throw POSIXError(POSIXErrorCode(rawValue: errno) ?? .EIO)
        }
        var bytes = Data(count: size)
        let count = bytes.withUnsafeMutableBytes { getxattr(url.path, "com.apple.quarantine", $0.baseAddress, size, 0, 0) }
        guard count == size else { throw POSIXError(.EIO) }
        return bytes
    }

    static func containingDiskImage(_ source: URL) -> String? {
        var fs = statfs()
        guard statfs(source.deletingLastPathComponent().path, &fs) == 0, fs.f_flags & UInt32(MNT_ROOTFS) == 0 else { return nil }
        let device = withUnsafePointer(to: &fs.f_mntfromname) {
            $0.withMemoryRebound(to: CChar.self, capacity: Int(MNAMELEN)) { String(cString: $0) }
        }
        var error: NSError?
        guard let data = HorosRunBoundedTask("/usr/bin/hdiutil", ["info", "-plist"], 10, &error),
              let info = try? PropertyListSerialization.propertyList(from: data, format: nil) as? [String: Any],
              let images = info["images"] as? [[String: Any]] else { return nil }
        return images.contains { image in
            (image["system-entities"] as? [[String: Any]])?.contains { $0["dev-entry"] as? String == device } == true
        } ? device : nil
    }

    static func relaunchScript(_ destination: URL, pid: Int32, diskImage: String?) -> String {
        let detach = diskImage.map { "; /bin/sleep 5; /usr/bin/hdiutil detach " + shellQuote($0) } ?? ""
        return "while /bin/kill -0 \(pid) 2>/dev/null; do /bin/sleep 0.1; done; /usr/bin/open "
            + shellQuote(destination.path) + " && :" + detach
    }

    func relaunch(_ destination: URL, diskImage: String?) throws {
        let task = Process()
        task.executableURL = URL(fileURLWithPath: "/bin/sh")
        task.arguments = ["-c", Self.relaunchScript(destination, pid: getpid(), diskImage: diskImage)]
        task.standardInput = FileHandle.nullDevice
        task.standardOutput = FileHandle.nullDevice
        task.standardError = FileHandle.nullDevice
        var error: NSError?
        guard HorosLaunchTask(task, &error) else { throw error ?? CocoaError(.executableNotLoadable) }
    }
}
