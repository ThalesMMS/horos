# Stable update channel

The application checks `https://raw.githubusercontent.com/ThalesMMS/horos/horos/updates/stable.plist` over HTTPS. `Horos` is the decimal CFBundleVersion of the latest published stable build. It is a string for compatibility with the existing plist contract. The remaining fields document the exact release and its architecture; the client compares only the build number and sends the user to the fork's release list. It does not install software or assert hardware/OS compatibility.

The initial entry is the existing `v4.0.0-macos26.1` release: version 4.0.0, build 20220801, arm64. Its release page records Developer ID signing, notarization and the DMG digest. This entry does not publish the current development checkout as a binary release.

For each future stable release:

1. Assign a strictly increasing positive decimal CFBundleVersion. Inspect the final packaged application's Info.plist: project-file defaults can be overwritten by build packaging. Do not reuse 20220801 for newer releases.
2. Build and validate the intended architectures and minimum macOS version, then complete signing/notarization and upload the final artifacts to a published, non-prerelease GitHub release in ThalesMMS/horos.
3. Confirm the release URL, tag, version, actual bundle build and architectures. Update all corresponding fields in stable.plist only after the release assets are available.
4. Commit/push the feed, fetch its HTTPS URL, parse it as a plist, and use Check for Updates in the application. Verify both an older installed build and the published build. A newer development build must not be offered an older binary as an upgrade.

Only maintainers should change the feed. Keep release numbers separate from Git history: an equal numeric build is not proof that a development checkout contains exactly the released changes. Users review release notes and choose the appropriate artifact; no download or installation is automatic. API credentials and DICOM data are not needed for checks.
