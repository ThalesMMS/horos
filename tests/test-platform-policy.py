#!/usr/bin/env python3
"""Product macOS 26 policy, SDK vs encoded target, and update eligibility (#369)."""
import subprocess
import tempfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
source = root / 'Horos/Sources/HorosPlatformPolicy.swift'
assert source.is_file(), 'FAIL: HorosPlatformPolicy.swift is missing'

driver = r'''
import Foundation

@main struct Check {
    static func main() {
        precondition(HorosPlatformPolicy.productMinimumMajor == 26)
        precondition(HorosPlatformPolicy.productMinimumMinor == 0)
        precondition(HorosPlatformPolicy.productMinimumDisplay() == "26.0")

        let v260 = HorosPlatformPolicy.parseVersion("26.0")!
        let v265 = HorosPlatformPolicy.parseVersion("26.5")!
        let v2662 = HorosPlatformPolicy.parseVersion("26.6.2")!
        let v27 = HorosPlatformPolicy.parseVersion("27.0")!
        let v155 = HorosPlatformPolicy.parseVersion("15.5")!
        let v11 = HorosPlatformPolicy.parseVersion("11.0")!
        precondition(v265.major == 26 && v265.minor == 5)
        precondition(v2662.patch == 2)
        precondition(v265 < v27)
        precondition(v11 < v155 && v155 < v260 && v260 < v265)

        // The SDK on this host can express the product minimum; an older one
        // cannot, which is the case the policy exists to keep separate.
        precondition(!HorosPlatformPolicy.sdkCanEncodeProductMinimum(v155))
        precondition(!HorosPlatformPolicy.sdkCanEncodeProductMinimum(sdk: "15.5"))
        precondition(HorosPlatformPolicy.sdkCanEncodeProductMinimum(v265))
        precondition(HorosPlatformPolicy.sdkCanEncodeProductMinimum(sdk: "26.5"))
        precondition(HorosPlatformPolicy.sdkCanEncodeProductMinimum(v27))

        precondition(HorosPlatformPolicy.encodedTargetIsLegal(encoded: v260, sdk: v265))
        precondition(HorosPlatformPolicy.encodedTargetIsLegal(encoded: v11, sdk: v265))
        precondition(!HorosPlatformPolicy.encodedTargetIsLegal(encoded: v27, sdk: v265))
        precondition(HorosPlatformPolicy.encodedTargetIsLegal(encoded: v27, sdk: v27))

        // A 26.0 package reaches a 26.6.2 Mac and must never reach a 15.5 one.
        precondition(HorosPlatformPolicy.shouldOfferInstallableUpdate(runtime: v2662, packageMinimum: v260))
        precondition(HorosPlatformPolicy.shouldOfferInstallableUpdate(runtime: "26.6.2", packageMinimum: "26.0"))
        precondition(!HorosPlatformPolicy.shouldOfferInstallableUpdate(runtime: v155, packageMinimum: v260))
        precondition(!HorosPlatformPolicy.shouldOfferInstallableUpdate(runtime: "15.5", packageMinimum: "26.0"))
        precondition(!HorosPlatformPolicy.shouldOfferInstallableUpdate(runtime: v2662, packageMinimum: v27))
        precondition(HorosPlatformPolicy.shouldOfferInstallableUpdate(runtime: v2662, packageMinimum: v11))

        let blocked = HorosPlatformPolicy.incompatibilityMessage(runtime: v155)!
        precondition(blocked.contains("macOS 26.0"))
        precondition(blocked.contains("15.5"))
        precondition(HorosPlatformPolicy.incompatibilityMessage(runtime: v260) == nil)
        precondition(HorosPlatformPolicy.incompatibilityMessage(runtime: v2662) == nil)

        // The Swift runtime has been in macOS since 10.14.4, so a product that
        // starts at 26.0 never needs a copy inside the bundle. An orphan there
        // is an artefact of an earlier deployment target (#555).
        precondition(!HorosPlatformPolicy.bundleMayEmbedSwiftRuntime(productMinimum: v260))
        precondition(!HorosPlatformPolicy.bundleMayEmbedSwiftRuntime(productMinimum: "26.0"))
        precondition(!HorosPlatformPolicy.bundleMayEmbedSwiftRuntime(productMinimum: v155))
        precondition(HorosPlatformPolicy.bundleMayEmbedSwiftRuntime(
            productMinimum: HorosPlatformPolicy.parseVersion("10.13")!))
        precondition(!HorosPlatformPolicy.bundleMayEmbedSwiftRuntime(
            productMinimum: HorosPlatformPolicy.swiftRuntimeInOSSince))
        precondition(HorosPlatformPolicy.embeddedFileIsSwiftRuntime("libswift_Concurrency.dylib"))
        precondition(HorosPlatformPolicy.embeddedFileIsSwiftRuntime("libswiftCore.dylib"))
        precondition(!HorosPlatformPolicy.embeddedFileIsSwiftRuntime("libswift_Concurrency.dylib.bak"))
        precondition(!HorosPlatformPolicy.embeddedFileIsSwiftRuntime("Horos"))
        precondition(!HorosPlatformPolicy.embeddedFileIsSwiftRuntime("libgdcmMSFF.dylib"))

        precondition(HorosPlatformPolicy.trackedSigningTeamIsAllowed(""))
        precondition(HorosPlatformPolicy.trackedSigningTeamIsAllowed("$(HOROS_DEVELOPMENT_TEAM)"))
        precondition(!HorosPlatformPolicy.trackedSigningTeamIsAllowed("TPT6TVH8UY"))
        precondition(HorosPlatformPolicy.ystarrevSigningTeamThatMustNotBeCopied == "TPT6TVH8UY")

        print("PASS: product minimum 26.0 is encodable by this SDK, an older SDK cannot encode it, a 26.0 package never reaches an older Mac, and the bundle needs no Swift runtime of its own")
    }
}
'''

with tempfile.TemporaryDirectory(prefix='horos-platform-policy-') as folder:
    path = Path(folder)
    (path / 'check.swift').write_text(driver)
    subprocess.run(['xcrun', 'swiftc', '-parse-as-library', str(source),
                    str(path / 'check.swift'), '-o', str(path / 'check')], check=True)
    subprocess.run([str(path / 'check')], check=True)
