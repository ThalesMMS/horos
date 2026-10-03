# Distribution builds

Both channels compile the same `Horos` target in Release for Apple Silicon. The scripts select an
xcconfig override; the viewers, DICOM processing and database implementation stay
shared. The dependency cache is shared, so distribution builds run one at a time.

```sh
./script/build_github.sh
./script/build_appstore.sh
```

The GitHub build is written to `build/Release/Isis DICOM Viewer.app`. It includes
the updater and external plugins and has no sandbox entitlement on the main app.
The Quick Look extensions remain sandboxed.

The App Store build is written to `build/AppStore/Isis DICOM Viewer.app`. It uses
`MACAPPSTORE` in both Swift and Objective-C, excludes the updater and external
plugin installation/loading, and enables App Sandbox. Its default bundle ID is
`thalesmms.isis.Isis-DICOM-Viewer`, matching the existing App Store Connect entry
and allowing the channels to coexist. It uses
its own container and does not automatically open or migrate the direct build's
database. Users can choose an existing database folder explicitly. Access to
selected database and import locations is stored as security-scoped bookmarks.

Both default builds are signed ad hoc for local validation. The local signatures
allow loading the embedded libraries without a Team ID. That exception is not in
the App Store distribution entitlements.

To archive with Xcode signing and export a package for App Store Connect:

```sh
ISIS_APPSTORE_TEAM=YOUR_TEAM_ID ./script/build_appstore.sh --export
```

This requires development/distribution certificates and provisioning profiles for
the app and its Quick Look extensions. It writes an xcarchive and export under
`build/AppStore`. It does not upload or submit the app. Store acceptance and
signed export are separate from successful local compilation.

Set `ISIS_APPSTORE_BUILD` to an unused Apple build number and
`ISIS_APPSTORE_VERSION` to the version in App Store Connect (default `1.0`).
`ISIS_APPSTORE_BUNDLE_ID` can select another registered app. The build number
defaults to `YYMM.DD.sequence`, with at most four digits in the first component
and two digits in each remaining component. App and extension versions stay in
sync. Set `ISIS_APPSTORE_ALLOW_PROVISIONING_UPDATES=1` to let the existing Xcode
account manage signing profiles during archive and export.

The GitHub channel retains the `HOROS_RELEASE_BUILD` and `HOROS_RELEASE_SEQUENCE`
build-number contract. `script/build_release.sh` remains the compatible
direct-build entry point.
