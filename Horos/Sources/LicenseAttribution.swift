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

/// One third-party or host notice that the distributed app must keep.
@objc(HorosLicensedComponent)
public final class LicensedComponent: NSObject {
    @objc public let identifier: String
    @objc public let name: String
    @objc public let license: String
    @objc public let sourcePath: String
    @objc public let incorporated: Bool
    @objc public let origin: String
    @objc public let distributionNote: String

    @objc public init(identifier: String,
                      name: String,
                      license: String,
                      sourcePath: String,
                      incorporated: Bool,
                      origin: String,
                      distributionNote: String) {
        self.identifier = identifier
        self.name = name
        self.license = license
        self.sourcePath = sourcePath
        self.incorporated = incorporated
        self.origin = origin
        self.distributionNote = distributionNote
    }
}

/// Provenance, credits and the notices that belong in the checkout and app bundle.
///
/// This is not legal advice. It records what is actually in this workbench and
/// which origin texts were snapshotted. It does not copy donor-fork source.
@objc(HorosLicenseAttribution)
public final class LicenseAttribution: NSObject {
    /// The donor fork this workbench adapted excerpts from. Credited by author,
    /// not by repository handle; NOTICE records which components were adapted.
    @objc public static let donorRevision = "23722fb552d96fa2d60c7f58a6d4ac2c27950f86"
    @objc public static let donorAuthor = "Yves Starreveld"
    @objc public static let snapshotDirectory =
        "docs/third-party/donor-horos-23722fb552d96fa2d60c7f58a6d4ac2c27950f86"
    @objc public static let originLicenseSHA256 =
        "d885acd3300b5464fe5e6774610b35fb2d83192f272be3325d69b89d2d666f38"
    @objc public static let originCopyingLesserSHA256 =
        "c9f740e3eddbb3a01de0d3924a9afd17782567e20c28e55d0e2436376b5c9000"
    @objc public static let catalogID = "L368"

    @objc public static let requiredRootResourceNames = ["LICENSE", "COPYING.LESSER", "NOTICE"]
    @objc public static let requiredSplashResourceNames = ["about.html", "licenses.html", "OpenSSL-LICENSE.txt"]

    @objc public static func components() -> [LicensedComponent] {
        [
            LicensedComponent(
                identifier: "horos",
                name: "Horos Project",
                license: "LGPLv3",
                sourcePath: "LICENSE",
                incorporated: true,
                origin: "host",
                distributionNote: "Offer Corresponding Source with the app. COPYING.LESSER ships in the bundle."),
            LicensedComponent(
                identifier: "osirix",
                name: "OsiriX",
                license: "LGPLv3",
                sourcePath: "LICENSE",
                incorporated: true,
                origin: "host",
                distributionNote: "Historical fork. Keep OsiriX Team credit and file headers."),
            LicensedComponent(
                identifier: "donor",
                name: "Yves Starreveld (donor fork)",
                license: "LGPLv3 with Grok AGPLv3 notice",
                sourcePath: "docs/third-party/donor-horos-23722fb552d96fa2d60c7f58a6d4ac2c27950f86/LICENSE",
                incorporated: true,
                origin: "adapted-source",
                distributionNote: "The query/retrieve server uses adapted excerpts from the recorded revision. Preserve their headers and distinguish local changes."),
            LicensedComponent(
                identifier: "dcmtk",
                name: "DCMTK",
                license: "BSD-style (OFFIS)",
                sourcePath: "DCMTK/COPYRIGHT",
                incorporated: true,
                origin: "host",
                distributionNote: "Keep copyright, conditions and disclaimer in documentation."),
            LicensedComponent(
                identifier: "itk",
                name: "ITK",
                license: "Apache-2.0",
                sourcePath: "ITK/LICENSE",
                incorporated: true,
                origin: "host",
                distributionNote: "Keep NOTICE and Apache terms with binaries."),
            LicensedComponent(
                identifier: "vtk",
                name: "VTK",
                license: "BSD-3-Clause",
                sourcePath: "VTK/Copyright.txt",
                incorporated: true,
                origin: "host",
                distributionNote: "Keep copyright and disclaimer."),
            LicensedComponent(
                identifier: "gdcm",
                name: "GDCM",
                license: "BSD-3-Clause",
                sourcePath: "GDCM/Copyright.txt",
                incorporated: true,
                origin: "host",
                distributionNote: "Keep copyright and disclaimer."),
            LicensedComponent(
                identifier: "openjpeg",
                name: "OpenJPEG",
                license: "BSD-2-Clause",
                sourcePath: "OpenJPEG/LICENSE",
                incorporated: true,
                origin: "host",
                distributionNote: "Keep copyright and disclaimer."),
            LicensedComponent(
                identifier: "openssl",
                name: "OpenSSL 3.5.8",
                license: "Apache-2.0",
                sourcePath: "OpenSSL/upstream/LICENSE.txt",
                incorporated: true,
                origin: "host",
                distributionNote: "The unmodified upstream Apache license ships in Splash/OpenSSL-LICENSE.txt."),
            LicensedComponent(
                identifier: "charls",
                name: "CharLS",
                license: "BSD-3-Clause",
                sourcePath: "CharLS/License.txt",
                incorporated: true,
                origin: "host",
                distributionNote: "Keep copyright and disclaimer."),
            LicensedComponent(
                identifier: "horoscloud",
                name: "HorosCloud / Purview",
                license: "Proprietary notice in LICENSE",
                sourcePath: "LICENSE",
                incorporated: true,
                origin: "local-workbench",
                distributionNote: "Present in this workbench, absent from the donor fork's LICENSE. Do not import that removal. Do not drop the plugin to simplify licensing."),
            LicensedComponent(
                identifier: "weights",
                name: "External model weights",
                license: "not imported",
                sourcePath: "",
                incorporated: false,
                origin: "none",
                distributionNote: "No ONNX/PyTorch/HDF5 weights are shipped. Do not copy weights without their terms."),
        ]
    }

    @objc public static func incorporatedComponents() -> [LicensedComponent] {
        components().filter(\.incorporated)
    }

    @objc public static func materialQuestions() -> [String] {
        [
            "Horos is LGPLv3 and its linked libraries keep their own terms; do not treat the tree as uniformly LGPL.",
            "The Purview/HorosCloud notice is local; replacing LICENSE with the donor fork's file would delete it.",
            "The donor fork's source tree is not copied here. Credit its author without claiming exclusive authorship of Horos.",
            "This catalog is not a legal opinion and does not authorise distribution of an incompatible combination.",
        ]
    }

    @objc public static func preservesPurviewNotice(in licenseText: String) -> Bool {
        licenseText.contains("Purview") && licenseText.contains("HorosCloud")
    }

    @objc public static func creditsDonor(in text: String) -> Bool {
        text.contains(donorAuthor)
    }

    @objc public static func isBlindOriginReplacement(originLicense: String,
                                                    workbenchLicense: String) -> Bool {
        originLicense == workbenchLicense
    }

    @objc public static func treatsAllComponentsAsLGPL() -> Bool {
        let licenses = Set(incorporatedComponents().map(\.license))
        return licenses.count == 1 && licenses.contains("LGPLv3")
    }

    @objc(missingNoticesInDirectory:)
    public static func missingNotices(inDirectory directory: URL) -> [String] {
        var missing: [String] = []
        let files = FileManager.default
        for name in requiredRootResourceNames {
            let url = directory.appendingPathComponent(name)
            if !files.fileExists(atPath: url.path) {
                missing.append(name)
            }
        }
        let splash = directory.appendingPathComponent("Splash")
        for name in requiredSplashResourceNames {
            let url = splash.appendingPathComponent(name)
            if !files.fileExists(atPath: url.path) {
                missing.append("Splash/\(name)")
            }
        }
        return missing
    }

    @objc(missingNoticesIn:)
    public static func missingNotices(in bundle: Bundle) -> [String] {
        guard let root = bundle.resourceURL else {
            return requiredRootResourceNames + requiredSplashResourceNames.map { "Splash/\($0)" }
        }
        return missingNotices(inDirectory: root)
    }

    @objc public static func aboutCreditsHTML() -> String {
        let rows = components().map { component in
            let status = component.incorporated ? "in the app" : "not copied"
            return "<li><strong>\(escape(component.name))</strong> — \(escape(component.license)). \(escape(status)). \(escape(component.distributionNote))</li>"
        }.joined(separator: "\n")
        return """
        <h2>Credits and licenses</h2>
        <p>Horos is published by the Horos Project and remains based on OsiriX. Contributors to this workbench are not exclusive authors of Horos.</p>
        <p>Selected excerpts were adapted from a donor fork of Horos authored by <strong>\(donorAuthor)</strong>, snapshot \(donorRevision). License texts from that revision are versioned; reused excerpts keep their headers and are distinct from local modifications such as the Purview/HorosCloud notice.</p>
        <ul>
        \(rows)
        </ul>
        """
    }

    @objc public static func attributionSummary() -> String {
        let names = components().map(\.name).joined(separator: ", ")
        return "Horos LGPLv3; OsiriX; \(donorAuthor); \(names)"
    }

    private static func escape(_ text: String) -> String {
        text
            .replacingOccurrences(of: "&", with: "&amp;")
            .replacingOccurrences(of: "<", with: "&lt;")
            .replacingOccurrences(of: ">", with: "&gt;")
    }
}
