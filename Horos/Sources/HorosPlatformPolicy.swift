import Foundation

/// Product-level macOS policy for the ystarrev-era Horos (#369).
///
/// The product minimum is macOS 26.0. That is not the same as the value encoded
/// in `MACOSX_DEPLOYMENT_TARGET`: Apple requires the encoded target to be at
/// most the SDK used to compile. This type keeps those three numbers distinct
/// (product policy, SDK, encoded target) so an older SDK cannot ship a
/// contradictory Info.plist, and a package built for the product minimum is
/// never offered as an installable update to a Mac that cannot run it.
@objc(HorosPlatformPolicy)
public final class HorosPlatformPolicy: NSObject {
    @objc public static let productMinimumMajor = 26
    @objc public static let productMinimumMinor = 0
    @objc public static let ystarrevSigningTeamThatMustNotBeCopied = "TPT6TVH8UY"

    public struct Version: Equatable, Comparable {
        public var major: Int
        public var minor: Int
        public var patch: Int

        public init(major: Int, minor: Int = 0, patch: Int = 0) {
            self.major = major
            self.minor = minor
            self.patch = patch
        }

        public static func < (lhs: Version, rhs: Version) -> Bool {
            if lhs.major != rhs.major { return lhs.major < rhs.major }
            if lhs.minor != rhs.minor { return lhs.minor < rhs.minor }
            return lhs.patch < rhs.patch
        }

        public var display: String {
            if patch == 0 { return "\(major).\(minor)" }
            return "\(major).\(minor).\(patch)"
        }
    }

    public static let productMinimum = Version(major: productMinimumMajor, minor: productMinimumMinor)

    public static func parseVersion(_ text: String) -> Version? {
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return nil }
        let parts = trimmed.split(separator: ".", omittingEmptySubsequences: false)
        guard let major = Int(parts[0]), major >= 0 else { return nil }
        let minor = parts.count > 1 ? Int(parts[1]) ?? 0 : 0
        let patch = parts.count > 2 ? Int(parts[2]) ?? 0 : 0
        return Version(major: major, minor: minor, patch: patch)
    }

    /// The encoded deployment target may not exceed the SDK. The product
    /// minimum can be written into xcconfig/Info.plist only when the SDK is at
    /// least that version.
    public static func sdkCanEncodeProductMinimum(_ sdk: Version) -> Bool {
        sdk >= productMinimum
    }

    public static func encodedTargetIsLegal(encoded: Version, sdk: Version) -> Bool {
        encoded <= sdk
    }

    /// A package must not be presented as an installable update to a runtime
    /// below its own `LSMinimumSystemVersion`. Builds encoded with an older
    /// minimum remain offerable to any runtime that meets that older value.
    public static func shouldOfferInstallableUpdate(runtime: Version, packageMinimum: Version) -> Bool {
        runtime >= packageMinimum
    }

    public static func incompatibilityMessage(runtime: Version) -> String? {
        guard runtime < productMinimum else { return nil }
        return "This Horos build requires macOS \(productMinimum.display) or later. This Mac is running macOS \(runtime.display)."
    }

    /// Empty team is the tracked default. The ystarrev checkout's team ID must
    /// never land in a tracked xcconfig.
    public static func trackedSigningTeamIsAllowed(_ team: String) -> Bool {
        let trimmed = team.trimmingCharacters(in: .whitespacesAndNewlines)
        if trimmed.isEmpty { return true }
        if trimmed == "$(HOROS_DEVELOPMENT_TEAM)" { return true }
        return trimmed != ystarrevSigningTeamThatMustNotBeCopied
    }

    @objc(productMinimumDisplay)
    public static func productMinimumDisplay() -> String { productMinimum.display }

    @objc(shouldOfferInstallableUpdateWithRuntime:packageMinimum:)
    public static func shouldOfferInstallableUpdate(runtime: String, packageMinimum: String) -> Bool {
        guard let run = parseVersion(runtime), let pack = parseVersion(packageMinimum) else { return false }
        return shouldOfferInstallableUpdate(runtime: run, packageMinimum: pack)
    }

    @objc(incompatibilityMessageForRuntime:)
    public static func incompatibilityMessage(forRuntime runtime: String) -> String? {
        guard let version = parseVersion(runtime) else { return nil }
        return incompatibilityMessage(runtime: version)
    }

    @objc(sdkCanEncodeProductMinimumWithSDK:)
    public static func sdkCanEncodeProductMinimum(sdk: String) -> Bool {
        guard let version = parseVersion(sdk) else { return false }
        return sdkCanEncodeProductMinimum(version)
    }

    // MARK: - What the bundle may carry

    /// The Swift runtime has shipped inside macOS since 10.14.4. A copy of it in
    /// the application bundle is back-deployment support, put there for systems
    /// that do not have it — and Xcode stops copying *and signing* those the
    /// moment the deployment target rises past the release that adopted them.
    public static let swiftRuntimeInOSSince = Version(major: 10, minor: 14, patch: 4)

    /// Whether a build for `productMinimum` still needs the Swift runtime inside
    /// the bundle.
    ///
    /// At macOS 26 it never does, so any `libswift*.dylib` found in a built
    /// bundle is an orphan left by an earlier build: an incremental products
    /// directory keeps what the current build no longer produces. #555 is that,
    /// found after #369 — the orphan was also unsigned, which is enough on its
    /// own to fail notarisation.
    public static func bundleMayEmbedSwiftRuntime(productMinimum: Version) -> Bool {
        productMinimum < swiftRuntimeInOSSince
    }

    @objc(bundleMayEmbedSwiftRuntimeForProductMinimum:)
    public static func bundleMayEmbedSwiftRuntime(productMinimum: String) -> Bool {
        guard let version = parseVersion(productMinimum) else { return false }
        return bundleMayEmbedSwiftRuntime(productMinimum: version)
    }

    /// The name of a Mach-O inside the bundle is enough to tell: the Swift
    /// runtime libraries Xcode embeds are all `libswift…`, and no Horos or
    /// vendored dependency uses that prefix.
    @objc(embeddedFileIsSwiftRuntime:)
    public static func embeddedFileIsSwiftRuntime(_ name: String) -> Bool {
        name.hasPrefix("libswift") && name.hasSuffix(".dylib")
    }
}
