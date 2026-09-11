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

/// Says, in the log, when AppKit's own layout debugging is switched on for this
/// process.
///
/// `NSConstraintBasedLayoutVisualizeMutuallyExclusiveConstraints` makes AppKit
/// draw a purple window of its own over whichever window it is complaining
/// about, carrying "Why am I seeing this purple window", "Exercise Ambiguity"
/// and a list of constraints. It is a preference, so once written it survives
/// restarts, and AppKit's own explanation of the window lists every preference
/// domain on the machine that carries the key - which reads like one
/// application drawing into another when it is nothing of the sort.
///
/// A report of a strange window is easy to answer when the log already says
/// this. Measured on macOS 26.6.2 (Darwin 25.6.0): of the layout defaults tried,
/// only these two are honoured, and only the first one draws anything.
@objc(HorosLayoutDebuggingDefaults)
public final class LayoutDebuggingDefaults: NSObject {
    /// The one that draws a window over ours.
    @objc public static let visualizerKey = "NSConstraintBasedLayoutVisualizeMutuallyExclusiveConstraints"
    /// The one that only writes to the log. AppKit has it on unless it is turned off.
    @objc public static let logKey = "NSConstraintBasedLayoutLogUnsatisfiable"
    @objc public static var keys: [String] { [visualizerKey, logKey] }

    /// `defaults write` puts a string there, an argument puts "YES", and code
    /// puts a boolean: all three mean the same thing.
    static func isOn(_ value: Any?) -> Bool {
        switch value {
        case let flag as Bool: return flag
        case let number as NSNumber: return number.boolValue
        case let text as String: return (text as NSString).boolValue
        default: return false
        }
    }

    static func isOff(_ value: Any?) -> Bool {
        value != nil && !isOn(value)
    }

    /// One line for the log, or nothing at all when neither key has been touched.
    ///
    /// `settings` is what this process is running with. `persistedIn` names the
    /// preference domain that also carries the visualizer key, or is nil when no
    /// file does, because that decides what somebody can do about it: a key in a
    /// preference file is deleted, and one this run asked for goes away when the
    /// run does.
    static func report(settings: [String: Any], persistedIn: String?) -> String? {
        var sentences: [String] = []
        if isOn(settings[visualizerKey]) {
            sentences.append("AppKit's constraint debugger is on: the purple window it draws over "
                             + "one of ours belongs to AppKit, not to Horos or to a plugin, and "
                             + "AppKit's own explanation of it lists every preference domain on "
                             + "this Mac that carries \(visualizerKey), not the applications "
                             + "reading it.")
            sentences.append(persistedIn.map {
                "It is written in the preference file; remove it with: "
                + "defaults delete \($0) \(visualizerKey)"
            } ?? ("This run asked for it - a debug build does, and so does passing "
                  + "-\(visualizerKey) YES - and nothing was written to the preference file."))
        }
        if isOff(settings[logKey]) {
            sentences.append("Unsatisfiable constraints will not be logged: "
                             + "\(logKey) has been turned off.")
        }
        return sentences.isEmpty ? nil : sentences.joined(separator: " ")
    }

    /// Switch AppKit's visualizer on for this run without leaving anything in
    /// the preference file, and take back whatever an older build left there.
    ///
    /// Writing the key was how a debug build used to turn the visualizer on. A
    /// run that ended any way other than its own quit left the key on in the
    /// person's preference file, where it applied to every later run of any
    /// build - and AppKit lists every domain carrying the key when asked why the
    /// purple window is there, which reads as two applications interfering.
    /// The registration domain is consulted the same way and is never written
    /// down; an argument still overrides it, which is how AppKit documents
    /// switching this on by hand.
    @objc public static func adoptForThisProcessOnly(_ visualizer: Bool) {
        let defaults = UserDefaults.standard
        let domain = Bundle.main.bundleIdentifier ?? ""
        if defaults.persistentDomain(forName: domain)?[visualizerKey] != nil {
            defaults.removeObject(forKey: visualizerKey)
        }
        if visualizer { defaults.register(defaults: [visualizerKey: true]) }
    }

    /// The same, for the defaults this process is actually running with, which
    /// includes anything given on the command line.
    @objc public static func reportForCurrentProcess() -> String? {
        let defaults = UserDefaults.standard
        var settings: [String: Any] = [:]
        for key in keys where defaults.object(forKey: key) != nil {
            settings[key] = defaults.object(forKey: key)
        }
        // Our own domain is the one an older build wrote, and the global domain
        // is the other place a person can set it; neither is the argument or the
        // registration domain, which leave no file behind.
        let files = [Bundle.main.bundleIdentifier ?? "«domain»", UserDefaults.globalDomain]
        let persistedIn = files.first { defaults.persistentDomain(forName: $0)?[visualizerKey] != nil }
        return report(settings: settings,
                      persistedIn: persistedIn == UserDefaults.globalDomain ? "-g" : persistedIn)
    }
}
