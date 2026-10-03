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

import Foundation
import Synchronization

/// Retains the grants for selected database and import folders across launches.
@objc(IsisSandboxFileAccess)
public final class SandboxFileAccess: NSObject {
    private static let bookmarksKey = "SandboxFolderBookmarks"
    private struct Grant: Sendable {
        let url: URL
        let started: Bool
    }
    private static let activeURLs = Mutex<[String: Grant]>([:])

    @objc(rememberURL:)
    @discardableResult public static func remember(_ url: URL) -> Bool {
        #if MACAPPSTORE
        return activeURLs.withLock { active in
            let path = url.standardizedFileURL.path
            let started = url.startAccessingSecurityScopedResource()
            do {
                let data = try url.bookmarkData(options: .withSecurityScope,
                                               includingResourceValuesForKeys: nil, relativeTo: nil)
                var bookmarks = UserDefaults.standard.dictionary(forKey: bookmarksKey) ?? [:]
                bookmarks[path] = data
                UserDefaults.standard.set(bookmarks, forKey: bookmarksKey)
                if let previous = active[path], previous.started {
                    previous.url.stopAccessingSecurityScopedResource()
                }
                active[path] = Grant(url: url, started: started)
                return true
            } catch {
                if started { url.stopAccessingSecurityScopedResource() }
                NSLog("Unable to retain folder access: %@", error.localizedDescription)
                return false
            }
        }
        #else
        return true
        #endif
    }

    @objc public static func restore() {
        #if MACAPPSTORE
        activeURLs.withLock { active in
            var bookmarks = UserDefaults.standard.dictionary(forKey: bookmarksKey) ?? [:]
            for (path, value) in bookmarks {
                guard active[path] == nil, let data = value as? Data else { continue }
                do {
                    var stale = false
                    let url = try URL(resolvingBookmarkData: data, options: .withSecurityScope,
                                      relativeTo: nil, bookmarkDataIsStale: &stale)
                    guard url.startAccessingSecurityScopedResource() else { continue }
                    active[path] = Grant(url: url, started: true)
                    if stale {
                        bookmarks[path] = try url.bookmarkData(options: .withSecurityScope,
                                                             includingResourceValuesForKeys: nil, relativeTo: nil)
                    }
                } catch {
                    NSLog("Unable to restore folder access: %@", error.localizedDescription)
                }
            }
            UserDefaults.standard.set(bookmarks, forKey: bookmarksKey)
        }
        #endif
    }
}
