#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ $# -gt 0 ]]; then
    echo "Uso: $0"
    echo "Compila e assina localmente build/Release/Horos.app para copiar para Applications."
    [[ $# -eq 1 && "$1" == --help ]] && exit 0
    exit 2
fi

OUTPUT_DIR="$ROOT_DIR/build/Release"
OUTPUT_APP="$OUTPUT_DIR/Horos.app"
BUILD_LOG="$ROOT_DIR/build/logs/build-release.log"
SIGNING_LOG="$ROOT_DIR/build/logs/release-signing.log"
mkdir -p "$OUTPUT_DIR" "$ROOT_DIR/build/logs"
cd "$ROOT_DIR"

echo "Compilando Horos Release. Log: $BUILD_LOG"
if ! xcodebuild -project Horos.xcodeproj -scheme Horos -configuration Release \
    -derivedDataPath build SYMROOT="$ROOT_DIR/build/Build/Products" CODE_SIGNING_ALLOWED=NO > "$BUILD_LOG" 2>&1; then
    tail -n 60 "$BUILD_LOG" >&2
    exit 1
fi

# Finish and verify the new bundle before replacing the previous output.
STAGING_DIR="$(mktemp -d "$OUTPUT_DIR/.staging.XXXXXX")"
trap 'rm -rf "$STAGING_DIR"' EXIT
STAGED_APP="$STAGING_DIR/Horos.app"
ENTITLEMENTS="$STAGING_DIR/entitlements.plist"
/usr/bin/ditto "$ROOT_DIR/build/Build/Products/Release/Horos.app" "$STAGED_APP"

# Local ad-hoc code loads the embedded frameworks and this Mac's Homebrew libs.
# Keep that exception out of the distribution entitlements and omit debugger access.
python3 - "$ROOT_DIR/Horos/Horos.entitlements" "$ENTITLEMENTS" <<'PYTHON'
import plistlib, sys
with open(sys.argv[1], 'rb') as source:
    entitlements = plistlib.load(source)
entitlements['com.apple.security.cs.disable-library-validation'] = True
entitlements.pop('com.apple.security.get-task-allow', None)
entitlements.pop('com.apple.security.cs.allow-dyld-environment-variables', None)
with open(sys.argv[2], 'wb') as destination:
    plistlib.dump(entitlements, destination)
PYTHON

echo "Assinando e verificando o aplicativo. Log: $SIGNING_LOG"
# --deep does not sign bare helper executables in Resources, including Decompress.
/usr/bin/find "$STAGED_APP/Contents/Resources" -type f -perm -u+x -exec /bin/sh -c '
    entitlements=$1; shift
    for file do
        case "$(/usr/bin/file -b "$file")" in
            *Mach-O*) /usr/bin/codesign --force --sign - --options runtime --entitlements "$entitlements" "$file" || exit 1 ;;
        esac
    done
' _ "$ENTITLEMENTS" {} + > "$SIGNING_LOG" 2>&1
/usr/bin/codesign --force --deep --sign - "$STAGED_APP" >> "$SIGNING_LOG" 2>&1
/usr/bin/codesign --force --sign - --options runtime --entitlements "$ENTITLEMENTS" "$STAGED_APP" >> "$SIGNING_LOG" 2>&1
/usr/bin/codesign --verify --deep --strict "$STAGED_APP" >> "$SIGNING_LOG" 2>&1

BACKUP_APP=""
if [[ -e "$OUTPUT_APP" || -L "$OUTPUT_APP" ]]; then
    BACKUP_APP="$OUTPUT_DIR/Horos.previous-$(date +%Y%m%d-%H%M%S)-$$.app"
    mv "$OUTPUT_APP" "$BACKUP_APP"
fi
if ! mv "$STAGED_APP" "$OUTPUT_APP"; then
    [[ -z "$BACKUP_APP" ]] || mv "$BACKUP_APP" "$OUTPUT_APP"
    exit 1
fi
[[ -z "$BACKUP_APP" ]] || echo "Versão anterior preservada em: $BACKUP_APP"
echo "Release pronto para copiar para Applications:"
echo "$OUTPUT_APP"
