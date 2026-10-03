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

@objc(IsisDistributionChannel)
public final class DistributionChannel: NSObject {
    @objc public static var isAppStore: Bool {
        #if MACAPPSTORE
        true
        #else
        false
        #endif
    }

    @objc public static var supportsExternalPlugins: Bool { !isAppStore }
    @objc public static var supportsGitHubUpdates: Bool { !isAppStore }

    static func configurePreferences() {
        let defaults = UserDefaults.standard
        defaults.set(isAppStore, forKey: "MACAPPSTORE")
        #if MACAPPSTORE
        defaults.set(false, forKey: "AUTHENTICATION")
        defaults.set(false, forKey: "CheckHorosUpdates")
        defaults.set(false, forKey: "checkForUpdatesPlugins")
        #endif
    }

    @MainActor static func configureMenu(_ menu: NSMenu?) {
        #if MACAPPSTORE
        guard let menu else { return }
        for item in menu.items {
            if item.action == NSSelectorFromString("checkForUpdates:") ||
                item.submenu?.items.contains(where: { $0.target is PluginManagerController }) == true {
                menu.removeItem(item)
            } else {
                configureMenu(item.submenu)
            }
        }
        #endif
    }
}
