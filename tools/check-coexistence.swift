#!/usr/bin/env swift
// Answer the three questions a "two DICOM viewers on one Mac" report raises,
// without guessing from a screenshot.
//
//     swift tools/check-coexistence.swift [--port 11112,8080,3333] [--scheme horos,osirix]
//
// 1. Which applications can open `horos://` and `osirix://`, and which one
//    LaunchServices picks. Horos claims both schemes on purpose, so a link
//    written for either viewer opens whichever application the system chose -
//    that decides what opens a study, and nothing about how a window looks.
// 2. Whether the ports Horos listens on are already held, and by what. Horos and
//    OsiriX default to the same three (DICOM 11112, XML-RPC 8080, Web Portal
//    3333), so the second one started cannot bind them.
// 3. Which preference domains on this Mac carry an AppKit layout-debugging
//    default. `NSConstraintBasedLayoutVisualizeMutuallyExclusiveConstraints`
//    makes AppKit draw a purple window of its own over the application's, and
//    AppKit's own explanation of that window lists every domain that carries the
//    key - which reads like two applications interfering when it is one
//    preference written twice.
//
// Exit 0 when nothing is contended and no layout debugging is on, 1 otherwise.
// It reads; it changes nothing.
import AppKit

var schemes = ["horos", "osirix"]
var ports = [11112, 8080, 3333]
var arguments = Array(CommandLine.arguments.dropFirst())
while let flag = arguments.first {
    arguments.removeFirst()
    switch flag {
    case "--scheme": schemes = (arguments.first ?? "").split(separator: ",").map(String.init)
                     if !arguments.isEmpty { arguments.removeFirst() }
    case "--port": ports = (arguments.first ?? "").split(separator: ",").compactMap { Int($0) }
                   if !arguments.isEmpty { arguments.removeFirst() }
    default: FileHandle.standardError.write(Data("unknown argument \(flag)\n".utf8)); exit(2)
    }
}

var findings: [String] = []

// padding(toLength:) cuts anything longer than the column, which would quietly
// shorten a scheme somebody passed in; widen the column instead.
func column(_ text: String, _ width: Int) -> String {
    text.padding(toLength: max(width, text.count), withPad: " ", startingAt: 0)
}

// --- 1. who opens the links -------------------------------------------------
print("URL schemes")
for scheme in schemes {
    guard let url = URL(string: "\(scheme)://example") else { continue }
    let candidates = NSWorkspace.shared.urlsForApplications(toOpen: url)
    let chosen = NSWorkspace.shared.urlForApplication(toOpen: url)
    if candidates.isEmpty {
        print("  \(column(scheme, 10)) no application claims it")
        continue
    }
    print("  \(column(scheme, 10)) "
          + "\(candidates.count) application(s) claim it")
    for application in candidates {
        let identifier = Bundle(url: application)?.bundleIdentifier ?? "?"
        print("    \(application == chosen ? "->" : "  ") \(identifier)  \(application.path)")
    }
    let identifiers = Set(candidates.compactMap { Bundle(url: $0)?.bundleIdentifier })
    // Several copies of Horos itself is the ordinary case on a machine that
    // builds it; another vendor's viewer in the list is what a report means.
    let others = identifiers.filter { !$0.hasPrefix("org.horosproject.") }
    if !others.isEmpty {
        findings.append("\(scheme):// is also claimed by \(others.sorted().joined(separator: ", "))")
    }
}

// --- 2. the ports -----------------------------------------------------------
print("\nPorts")
func holder(of port: Int) -> String? {
    let task = Process()
    task.executableURL = URL(fileURLWithPath: "/usr/sbin/lsof")
    task.arguments = ["-nP", "-iTCP:\(port)", "-sTCP:LISTEN"]
    let pipe = Pipe()
    task.standardOutput = pipe
    task.standardError = FileHandle.nullDevice
    do { try task.run() } catch { return nil }
    let data = pipe.fileHandleForReading.readDataToEndOfFile()
    task.waitUntilExit()
    let lines = String(decoding: data, as: UTF8.self)
        .split(separator: "\n").dropFirst()          // the header
        .map { $0.split(separator: " ", omittingEmptySubsequences: true) }
        .filter { $0.count > 1 }
        .map { "\($0[0]) (pid \($0[1]))" }
    return lines.isEmpty ? nil : Set(lines).sorted().joined(separator: ", ")
}
let named = [11112: "DICOM listener", 8080: "XML-RPC", 3333: "Web Portal"]
for port in ports {
    let name = named[port] ?? "port"
    if let who = holder(of: port) {
        print("  \(column(String(port), 7))\(column(name, 16)) held by \(who)")
        findings.append("port \(port) (\(name)) is already held by \(who)")
    } else {
        print("  \(column(String(port), 7))\(column(name, 16)) free")
    }
}

// --- 3. the purple window ---------------------------------------------------
print("\nAppKit layout debugging")
let layoutKeys = ["NSConstraintBasedLayoutVisualizeMutuallyExclusiveConstraints",
                  "NSConstraintBasedLayoutLogUnsatisfiable"]
// CFPreferencesCopyApplicationList is gone, and `defaults domains` is what a
// person would use to find the domain to delete the key from anyway.
func preferenceDomains() -> [String] {
    let task = Process()
    task.executableURL = URL(fileURLWithPath: "/usr/bin/defaults")
    task.arguments = ["domains"]
    let pipe = Pipe()
    task.standardOutput = pipe
    task.standardError = FileHandle.nullDevice
    do { try task.run() } catch { return [] }
    let data = pipe.fileHandleForReading.readDataToEndOfFile()
    task.waitUntilExit()
    return String(decoding: data, as: UTF8.self)
        .split(separator: ",")
        .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
        .filter { !$0.isEmpty }
}
var domains = preferenceDomains()
domains.append(kCFPreferencesAnyApplication as String)       // the global domain
var anySet = false
for key in layoutKeys {
    let carriers = domains.filter {
        CFPreferencesCopyValue(key as CFString, $0 as CFString,
                               kCFPreferencesCurrentUser, kCFPreferencesAnyHost) != nil
    }.sorted()
    for domain in carriers {
        let value = CFPreferencesCopyValue(key as CFString, domain as CFString,
                                           kCFPreferencesCurrentUser, kCFPreferencesAnyHost)!
        print("  \(key) = \(value) in \(domain)")
        anySet = true
        if key == layoutKeys[0], (value as? NSNumber)?.boolValue == true
            || (value as? NSString)?.boolValue == true {
            findings.append("\(domain) draws AppKit's purple constraint window "
                            + "(defaults delete \(domain) \(key))")
        }
    }
}
if !anySet { print("  no domain carries one of these keys") }

print("")
if findings.isEmpty {
    print("ok: nothing here explains a second viewer opening links, holding a port, or a purple window")
    exit(0)
}
for finding in findings { print("found: \(finding)") }
exit(1)
