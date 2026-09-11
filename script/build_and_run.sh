#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODE="${1:-run}"
case "$MODE" in run|--debug|--logs|--telemetry|--verify|--diagnostics) ;; *) echo "usage: $0 [--debug|--logs|--telemetry|--verify|--diagnostics]" >&2; exit 2;; esac
cd "$ROOT_DIR"
DEV_APP="$ROOT_DIR/build/Development/HorosDevelopment.app"
DEV_ID="org.horosproject.horos.local-development"
# A disposable internal-volume directory can avoid removable-volume consent
# during isolated tests when the checkout itself lives on an external disk.
TEST_ROOT="${HOROS_DEV_TEST_ROOT:-$ROOT_DIR/local-validation/runtime-private}"
# This launch-only option must not invalidate dependency build environment hashes.
unset HOROS_DEV_TEST_ROOT
mkdir -p "$ROOT_DIR/build/logs" "$ROOT_DIR/build/Development" "$TEST_ROOT"
# Quit only this development bundle, preserving any installed Horos/OsiriX session.
python3 - "$DEV_APP/Contents/MacOS/Horos" <<'PYTHON'
import os,signal,subprocess,sys,time
# ps reports the executable as it was invoked, so an instance started with a
# relative path does not equal the absolute one and used to survive this quit -
# leaving two development instances on screen, whose panels overlap. Match the
# tail instead: it still cannot name the installed Horos.app.
suffix='/'.join(sys.argv[1].split('/')[-4:])
def isDevelopment(command): return command==sys.argv[1] or command==suffix or command.endswith('/'+suffix)
for line in subprocess.check_output(['/bin/ps','-axo','pid=,comm='],text=True).splitlines():
    parts=line.strip().split(None,1)
    if len(parts)==2 and isDevelopment(parts[1]):
        pid=int(parts[0]);os.kill(pid,signal.SIGTERM)
        for _ in range(50):
            try: os.kill(pid,0)
            except ProcessLookupError: break
            time.sleep(0.1)
        else: raise SystemExit('Development process did not stop; build not started.')
PYTHON
xcodebuild -project Horos.xcodeproj -scheme Horos -configuration Debug -derivedDataPath build CODE_SIGNING_ALLOWED=NO > "$ROOT_DIR/build/logs/build-and-run.log" 2>&1
rm -rf "$DEV_APP"
/usr/bin/ditto "$ROOT_DIR/build/Build/Products/Debug/Horos.app" "$DEV_APP"
/usr/libexec/PlistBuddy -c "Set :CFBundleIdentifier $DEV_ID" "$DEV_APP/Contents/Info.plist"
/usr/libexec/PlistBuddy -c 'Set :CFBundleName Horos Development' "$DEV_APP/Contents/Info.plist"
# Finder loads the Quick Look extensions from this bundle. Their identifiers
# must stay prefixed with the development identifier after the rewrite above.
if [ -d "$DEV_APP/Contents/PlugIns" ]; then
    for plist in "$DEV_APP/Contents/PlugIns"/*/Contents/Info.plist; do
        [ -f "$plist" ] || continue
        old="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleIdentifier' "$plist" 2>/dev/null || true)"
        case "$old" in
            org.horosproject.horos.*)
                /usr/libexec/PlistBuddy -c "Set :CFBundleIdentifier ${DEV_ID}.${old#org.horosproject.horos.}" "$plist"
                ;;
        esac
    done
fi
# Exercise the app's hardened-runtime permissions after signing nested code.
# Ad-hoc development also loads Homebrew libraries with different signing identities.
# Keep this local exception out of the distribution entitlements.
DEV_ENTITLEMENTS="$ROOT_DIR/build/Development/entitlements.plist"
python3 - "$ROOT_DIR/Horos/Horos.entitlements" "$DEV_ENTITLEMENTS" "$MODE" <<'PYTHON'
import plistlib,sys
with open(sys.argv[1], 'rb') as source:
    entitlements = plistlib.load(source)
entitlements['com.apple.security.cs.disable-library-validation'] = True
# Hardened runtime otherwise rejects LLDB even when LLDB launches the app.
# Enable task access only for the explicitly requested local debugging mode.
if sys.argv[3] == '--debug':
    entitlements['com.apple.security.get-task-allow'] = True
# Hardened runtime otherwise strips DYLD_INSERT_LIBRARIES, so the runtime
# checkers cannot be injected. Only the explicit diagnostics mode allows it.
if sys.argv[3] == '--diagnostics':
    entitlements['com.apple.security.cs.allow-dyld-environment-variables'] = True
with open(sys.argv[2], 'wb') as destination:
    plistlib.dump(entitlements, destination)
PYTHON
# Local ad-hoc signing accommodates the development bundle identifier change.
# --deep signs nested bundles and frameworks; a bare executable copied into
# Resources is data to it, so those are signed first, inside out.
#
# The helpers in Resources are separate processes, and the hardened runtime
# implies library validation: signed without these entitlements they refuse to
# load the ad-hoc frameworks beside them and exit before running. Decompress is
# one of them, so every archive and every transcoding silently did nothing and
# the file was left in the decompression folder. Sign them with the same
# exception as the application.
[ -d "$DEV_APP/Contents/Resources" ] || { echo "Development bundle has no Resources: $DEV_APP" >&2; exit 1; }
/usr/bin/find "$DEV_APP/Contents/Resources" -type f -perm -u+x -exec /bin/sh -c '
    entitlements=$1; shift
    for file do
        case "$(/usr/bin/file -b "$file")" in
            *Mach-O*) /usr/bin/codesign --force --sign - --options runtime --entitlements "$entitlements" "$file" || exit 1 ;;
        esac
    done
' _ "$DEV_ENTITLEMENTS" {} + > "$ROOT_DIR/build/logs/development-signing.log" 2>&1
/usr/bin/codesign --force --deep --sign - "$DEV_APP" >> "$ROOT_DIR/build/logs/development-signing.log" 2>&1
/usr/bin/codesign --force --sign - --options runtime --entitlements "$DEV_ENTITLEMENTS" "$DEV_APP" >> "$ROOT_DIR/build/logs/development-signing.log" 2>&1
# The Web Portal keeps its accounts outside the DICOM database, so an isolated
# run still read and wrote the installed application's accounts until this path
# was passed too.
ARGS=(-DATABASELOCATION 1 -DATABASELOCATIONURL "$TEST_ROOT" -DEFAULT_DATABASELOCATION 1 -DEFAULT_DATABASELOCATIONURL "$TEST_ROOT" -WebPortalDatabasePath "$TEST_ROOT/WebUsers.sql" -AUTOCLEANINGSPACE NO -AUTOCLEANINGDATE NO -AUTOROUTINGACTIVATED NO -STORESCP NO -USESTORESCP NO -checkForUpdatesPlugins NO -SUEnableAutomaticChecks NO)
# Do not inherit a shell TMPDIR that may point at a removable volume. Keep
# development runtime files in the user's macOS temporary directory, without
# changing the build environment or the user's global configuration.
DEV_TMPDIR="$(/usr/bin/getconf DARWIN_USER_TEMP_DIR)"
if [[ ! -d "$DEV_TMPDIR" || ! -w "$DEV_TMPDIR" ]]; then
  echo "macOS temporary directory is unavailable: $DEV_TMPDIR" >&2
  exit 1
fi
if [[ "$MODE" == --debug ]]; then
  export TMPDIR="$DEV_TMPDIR"
  exec /usr/bin/lldb -- "$DEV_APP/Contents/MacOS/Horos" "${ARGS[@]}"
fi
if [[ "$MODE" == --diagnostics ]]; then
  # Run in the foreground with Xcode's Main Thread Checker inserted, so AppKit
  # calls made off the main thread are reported as they happen. The report goes
  # to stderr; redirect it to keep a transcript.
  CHECKER="$(xcode-select -p)/usr/lib/libMainThreadChecker.dylib"
  if [[ ! -f "$CHECKER" ]]; then
    echo "Main Thread Checker is not available at $CHECKER" >&2
    exit 1
  fi
  export TMPDIR="$DEV_TMPDIR"
  export DYLD_INSERT_LIBRARIES="$CHECKER"
  export MTC_RESET_INSERT_LIBRARIES=0
  exec "$DEV_APP/Contents/MacOS/Horos" "${ARGS[@]}"
fi
/usr/bin/open -n "$DEV_APP" --env "TMPDIR=$DEV_TMPDIR" --args "${ARGS[@]}"
case "$MODE" in
 --verify)
  sleep 3
  python3 - "$DEV_APP/Contents/MacOS/Horos" <<'PYTHON'
import subprocess,sys
suffix='/'.join(sys.argv[1].split('/')[-4:])
matches=[]
for line in subprocess.check_output(['/bin/ps','-axo','pid=,comm='],text=True).splitlines():
    parts=line.strip().split(None,1)
    if len(parts)==2 and (parts[1]==sys.argv[1] or parts[1]==suffix or parts[1].endswith('/'+suffix)):
        matches.append(parts[0])
for pid in matches: print('Development process:',pid)
raise SystemExit(0 if matches else 1)
PYTHON
  ;;
 --logs|--telemetry)
  exec /usr/bin/log stream --info --style compact --predicate 'process == "Horos"'
  ;;
esac
