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

import Darwin
import Foundation

/// Previous working copy, plugin-less recovery, and bundled Horos Cloud deploy.
///
/// A published update used to delete the previous plugin as soon as the swap
/// succeeded. A candidate that passed preflight and then broke startup left
/// nothing usable. Horos Cloud had a second path: unzip into the live plugins
/// folder, and treat a disabled copy as missing, which put the plugin back.
@objc(HorosPluginUpdateRecovery)
public final class PluginUpdateRecovery: NSObject {
    @objc public static func previousPath(forDestination destination: String) -> String {
        let parent = (destination as NSString).deletingLastPathComponent
        let name = (destination as NSString).lastPathComponent
        return ((parent as NSString).appendingPathComponent(".horos-plugin-previous") as NSString)
            .appendingPathComponent(name)
    }

    @objc public static func shouldEnterPluginLessMode(markerExists: Bool) -> Bool {
        markerExists
    }

    @objc public static func shouldOfferDatabaseRebuild(loadingFileExists: Bool,
                                                        pluginMarkerExists: Bool) -> Bool {
        loadingFileExists && !pluginMarkerExists
    }

    @objc public static func shouldDeployBundledCloud(alreadyDeployed: Bool,
                                                      activeContainsCloud: Bool,
                                                      inactiveContainsCloud: Bool) -> Bool {
        !alreadyDeployed && !activeContainsCloud && !inactiveContainsCloud
    }

    @objc public static func isCloudPluginName(_ name: String) -> Bool {
        (name as NSString).deletingPathExtension.caseInsensitiveCompare("HorosCloud") == .orderedSame
    }

    @objc public static func explanation(pluginNamed name: String,
                                         canRestore: Bool,
                                         canDisable: Bool) -> String {
        let opening = String(format: NSLocalizedString(
            "The previous run stopped while loading the plugin %@.", comment: ""), name)
        var parts = [opening]
        if canRestore {
            parts.append(NSLocalizedString(
                "Restoring puts the previous working copy back; nothing else is touched.",
                comment: ""))
        }
        if canDisable {
            parts.append(NSLocalizedString(
                "Disabling it moves it out of the plugins folder; nothing else is touched, and "
                + "Plugin Manager can switch it back on.", comment: ""))
        } else if !canRestore {
            parts.append(NSLocalizedString(
                "It is not in one of the plugins folders, so Horos cannot disable it for you; "
                + "move it aside yourself if it keeps happening.", comment: ""))
        }
        return parts.joined(separator: " ")
    }

    @objc public static func adoptLeftoverStaging(inDirectory directory: String) -> String? {
        let manager = FileManager.default
        guard let entries = try? manager.contentsOfDirectory(atPath: directory) else { return nil }
        var adopted: String?
        for entry in entries where entry.hasPrefix(".horos-plugin-update-") {
            let staging = (directory as NSString).appendingPathComponent(entry)
            let inner = (try? manager.contentsOfDirectory(atPath: staging)) ?? []
            for name in inner {
                let candidate = (staging as NSString).appendingPathComponent(name)
                let live = (directory as NSString).appendingPathComponent(name)
                guard manager.fileExists(atPath: live) else { continue }
                let previous = previousPath(forDestination: live)
                let parent = (previous as NSString).deletingLastPathComponent
                try? manager.createDirectory(atPath: parent, withIntermediateDirectories: true)
                if manager.fileExists(atPath: previous) {
                    try? manager.removeItem(atPath: previous)
                }
                if (try? manager.moveItem(atPath: candidate, toPath: previous)) != nil {
                    adopted = previous
                }
            }
            try? manager.removeItem(atPath: staging)
        }
        return adopted
    }

    @objc public static func restorePrevious(forDestination destination: String) -> Bool {
        let previous = previousPath(forDestination: destination)
        let manager = FileManager.default
        guard manager.fileExists(atPath: previous), manager.fileExists(atPath: destination) else {
            return false
        }
        let swapped = destination.withCString { dest in
            previous.withCString { prev in
                renamex_np(prev, dest, UInt32(RENAME_SWAP)) == 0
            }
        }
        if swapped {
            try? manager.removeItem(atPath: previous)
            discardPrevious(forDestination: destination)
        }
        return swapped
    }

    @objc public static func discardPrevious(forDestination destination: String) {
        let previous = previousPath(forDestination: destination)
        let parent = (previous as NSString).deletingLastPathComponent
        try? FileManager.default.removeItem(atPath: previous)
        if let leftover = try? FileManager.default.contentsOfDirectory(atPath: parent), leftover.isEmpty {
            try? FileManager.default.removeItem(atPath: parent)
        }
    }

    @objc public static func prepareBundledCloud(fromArchive archive: String,
                                                 into pluginsDirectory: String,
                                                 alreadyDeployed: Bool,
                                                 activeContainsCloud: Bool,
                                                 inactiveContainsCloud: Bool,
                                                 error: NSErrorPointer) -> String? {
        guard shouldDeployBundledCloud(alreadyDeployed: alreadyDeployed,
                                       activeContainsCloud: activeContainsCloud,
                                       inactiveContainsCloud: inactiveContainsCloud) else {
            return nil
        }
        guard FileManager.default.fileExists(atPath: archive) else {
            error?.pointee = NSError(domain: NSPOSIXErrorDomain, code: Int(ENOENT), userInfo: nil)
            return nil
        }
        let extract = ((pluginsDirectory as NSString).deletingLastPathComponent as NSString)
            .appendingPathComponent(".horos-cloud-extract-\(UUID().uuidString)")
        do {
            try FileManager.default.createDirectory(atPath: extract, withIntermediateDirectories: true)
        } catch let failure as NSError {
            error?.pointee = failure
            return nil
        }
        let unzip = Process()
        unzip.executableURL = URL(fileURLWithPath: "/usr/bin/unzip")
        unzip.arguments = ["-o", archive, "-d", extract]
        do {
            try unzip.run()
            unzip.waitUntilExit()
        } catch let failure as NSError {
            try? FileManager.default.removeItem(atPath: extract)
            error?.pointee = failure
            return nil
        }
        guard unzip.terminationStatus == 0 else {
            try? FileManager.default.removeItem(atPath: extract)
            error?.pointee = NSError(domain: NSPOSIXErrorDomain, code: Int(unzip.terminationStatus),
                                     userInfo: nil)
            return nil
        }
        guard let found = locateCloudPlugin(in: extract) else {
            try? FileManager.default.removeItem(atPath: extract)
            return nil
        }
        return found
    }

    private static func locateCloudPlugin(in directory: String) -> String? {
        let manager = FileManager.default
        guard let enumerator = manager.enumerator(atPath: directory) else { return nil }
        var match: String?
        while let relative = enumerator.nextObject() as? String {
            let name = (relative as NSString).lastPathComponent
            guard isCloudPluginName(name) else { continue }
            let full = (directory as NSString).appendingPathComponent(relative)
            var isDir: ObjCBool = false
            guard manager.fileExists(atPath: full, isDirectory: &isDir), isDir.boolValue else { continue }
            if match != nil { return nil }
            match = full
            enumerator.skipDescendants()
        }
        return match
    }
}
