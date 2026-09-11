#!/bin/sh

# A failure here used to be invisible: the aliases would be missing or half
# built and the build would carry on to sign the application around them.
set -eu
set -x

framework_path="$TARGET_BUILD_DIR/$FRAMEWORKS_FOLDER_PATH/Horos.framework"

# codesign is given the identity Xcode resolved for this build, or ad hoc when
# there is none. EXPANDED_CODE_SIGN_IDENTITY is the identity itself; the _NAME
# beside it is the display name, which codesign cannot look up.
identity="${EXPANDED_CODE_SIGN_IDENTITY:-${CODE_SIGN_IDENTITY:--}}"
[ -n "$identity" ] || identity="-"
signing_allowed="${CODE_SIGNING_ALLOWED:-YES}"

# many plugins are hard-linked to the API framework, and its name changed over time

alts=( HorosAPI OsiriXAPI 'OsiriX Headers' HorosDCM)
for alt in "${alts[@]}"; do
    alt_framework_path="$TARGET_BUILD_DIR/$FRAMEWORKS_FOLDER_PATH/$alt.framework"
    rm -Rf "$alt_framework_path"
    cp -R "$framework_path" "$alt_framework_path"
    # cp -R brings Horos.framework's signature along, and everything below - the
    # renamed binary, the dropped headers, the rewritten identifier - happens
    # underneath it. The copy then declares a seal over content that is no longer
    # there, which is why codesign --verify --deep --strict rejected the whole
    # application with "invalid Info.plist (plist or signature have been
    # modified)" and named one of these frameworks as the subcomponent. Drop the
    # inherited seal here and sign the alias for what it actually contains, once
    # the edits are done.
    rm -Rf "$alt_framework_path/Versions/A/_CodeSignature"
    mv "$alt_framework_path/Versions/A/Horos" "$alt_framework_path/Versions/A/$alt"
    rm -f "$alt_framework_path/Horos"
    rm -f "$alt_framework_path/Headers"
    rm -Rf "$alt_framework_path/Versions/A/Headers"
    ( cd "$alt_framework_path" && ln -s "Versions/A/$alt" )
    sed -i '' "s/Horos/$alt/" "$alt_framework_path/Versions/A/Resources/Info.plist"
    sed -i '' "s/org.horosproject.api/org.horosproject.$alt/" "$alt_framework_path/Versions/A/Resources/Info.plist"
done

#exception since this is temporary
sed -i '' "s/org.horosproject.OsiriX\ Headers/org.horosproject.OsiriXHeaders/" \
    "$TARGET_BUILD_DIR/$FRAMEWORKS_FOLDER_PATH/OsiriX Headers.framework/Versions/A/Resources/Info.plist"

# Sealed last, so the identifier codesign records is the one the edits above
# left in the Info.plist rather than Horos.framework's. This phase runs before
# Xcode signs the application, which seals the frameworks by their signatures;
# nothing here needs a --force --deep pass over the finished bundle.
if [ "$signing_allowed" != "NO" ]; then
    for alt in "${alts[@]}"; do
        /usr/bin/codesign --force --sign "$identity" --options runtime \
            "$TARGET_BUILD_DIR/$FRAMEWORKS_FOLDER_PATH/$alt.framework"
    done
else
    echo "note: code signing is disabled; leaving the API aliases unsigned"
fi

exit 0
