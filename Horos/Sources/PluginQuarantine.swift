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

import Foundation

/// Where the "a plugin was loading when we stopped" note lives, and where a
/// plugin goes when it is switched off.
///
/// `PluginManager` writes the path of each plugin before opening its bundle and
/// removes it afterwards, so a file left behind names the plugin that was
/// loading when the application went away. The note used to be written to
/// `/tmp/PluginCrashed` while the startup check read `Plugin_Loading` in the
/// application support folder, so nothing ever read what was written and the
/// recovery could not run. `/tmp` was the wrong place for it anyway: it is
/// writable by everybody on the machine, and every Horos and OsiriX on it would
/// have shared the one file.
@objc(HorosPluginQuarantine)
public final class PluginQuarantine: NSObject {
    /// The note, inside the folder Horos already keeps its plugins in.
    ///
    /// One file per bundle identifier: a development build and an installed one
    /// load plugins from the same folders, and a shared note would have each
    /// accusing whatever the other was loading.
    @objc public static func markerPath(inDirectory directory: String,
                                        forBundle identifier: String?) -> String {
        let name = (identifier?.isEmpty == false ? identifier! : "unknown")
            .replacingOccurrences(of: "/", with: "_")
        return (directory as NSString).appendingPathComponent("Plugin_Loading.\(name)")
    }

    /// Where the plugin at `path` goes when it is disabled: the "Disabled"
    /// directory paired with whichever plugin directory it is in. Nil when it is
    /// in none of them, because moving it somewhere unrelated is worse than
    /// leaving it and saying so.
    ///
    /// `active` and `inactive` are `PluginManager`'s own lists, paired by
    /// position: user, system, application.
    @objc public static func inactivePath(forPluginAt path: String,
                                          active: [String], inactive: [String]) -> String? {
        func tidy(_ text: String) -> String {
            var value = (text as NSString).standardizingPath
            while value.count > 1 && value.hasSuffix("/") { value.removeLast() }
            return value
        }
        let file = tidy(path)
        guard file != "/" else { return nil }
        let directory = (file as NSString).deletingLastPathComponent
        let name = (file as NSString).lastPathComponent
        guard !name.isEmpty else { return nil }
        for (index, candidate) in active.enumerated() where tidy(candidate) == tidy(directory) {
            guard index < inactive.count else { return nil }
            return (tidy(inactive[index]) as NSString).appendingPathComponent(name)
        }
        return nil
    }

    /// What to tell somebody whose last run stopped inside a plugin. `name` is
    /// the plugin's, and `canDisable` says whether there is anywhere to move it.
    @objc public static func explanation(pluginNamed name: String, canDisable: Bool) -> String {
        let opening = String(format: NSLocalizedString(
            "The previous run stopped while loading the plugin %@.", comment: ""), name)
        return canDisable
            ? opening + " " + NSLocalizedString(
                "Disabling it moves it out of the plugins folder; nothing else is touched, and "
                + "Plugin Manager can switch it back on.", comment: "")
            : opening + " " + NSLocalizedString(
                "It is not in one of the plugins folders, so Horos cannot disable it for you; "
                + "move it aside yourself if it keeps happening.", comment: "")
    }
}
