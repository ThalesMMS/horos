#!/bin/sh

export PATH="$PATH:/opt/local/bin:/opt/local/sbin:/opt/homebrew/bin/"

path="$( cd "$(dirname "${BASH_SOURCE[0]}")" && pwd )/$(basename "${BASH_SOURCE[0]}")"
print_status_patch="$(dirname "$path")/DCMTK-3.6.7-print-status.patch"
revision_file="$(dirname "$path")/UPSTREAM_REVISION"
cd "$TARGET_NAME"; pwd

# One narrow hash for every dependency; see Horos/Scripts/dependency-hash.sh.
. "$(dirname "$path")/../dependency-hash.sh"
dependency_hash "$path" "$revision_file" "$print_status_patch" "$(dirname "$path")/Make.sh" "$PROJECT_DIR/tools/isolate-dcmtk-jpegls.py"

set -e; set -o xtrace

source_dir="$PROJECT_DIR/$TARGET_NAME"
expected_revision="$(cat "$revision_file")"
if [ "$(git -C "$source_dir" rev-parse HEAD)" != "$expected_revision" ] || \
   [ -n "$(git -C "$source_dir" status --porcelain --untracked-files=normal)" ]; then
    echo "error: DCMTK must be the clean upstream revision $expected_revision. Local changes were preserved." >&2
    exit 1
fi
compat_source_dir="$TARGET_TEMP_DIR/PatchedSource"
cmake_dir="$TARGET_TEMP_DIR/CMake"
install_dir="$TARGET_TEMP_DIR/Install"

mkdir -p "$cmake_dir"; cd "$cmake_dir"
if [ -e "$cmake_dir/Makefile" -a -f "$cmake_dir/.buildhash" ] && [ "$(cat "$cmake_dir/.buildhash")" == "$hash" ]; then
    exit 0
fi

# A reconfigured source/patch must also refresh the copied executables.
# Otherwise Make.sh can mistake the previous tools for a completed new build.
mkdir -p "$BUILT_PRODUCTS_DIR/DCMTK"
touch "$BUILT_PRODUCTS_DIR/DCMTK/.incomplete"

if [ -e ".cmakeenv" ]; then
    echo "Rebuilding.."
    cat '.cmakeenv'
    echo "$env"
fi

command -v cmake >/dev/null 2>&1 || { echo >&2 "error: building $TARGET_NAME requires CMake. Please install CMake. Aborting."; exit 1; }
command -v pkg-config >/dev/null 2>&1 || { echo >&2 "error: building $TARGET_NAME requires pkg-config. Please install pkg-config. Aborting."; exit 1; }

mv "$cmake_dir" "$cmake_dir.tmp"
[ -d "$install_dir" ] && mv "$install_dir" "$install_dir.tmp"
rm -Rf "$cmake_dir.tmp" "$install_dir.tmp" "$compat_source_dir"
mkdir -p "$cmake_dir";

# Only the print command-line application's exit status is adapted. All
# libraries are built from stock upstream sources, including DIMSE and TLS.
ditto "$source_dir" "$compat_source_dir"
/usr/bin/patch --silent -d "$compat_source_dir" -p0 < "$print_status_patch"
source_dir="$compat_source_dir"

args=( "$source_dir" )
cfs=( $OTHER_CFLAGS )
cxxfs=( $OTHER_CPLUSPLUSFLAGS -DDCMTK_MAX_SEQUENCE_NESTING=16 )

args+=(-Wno-dev)
args+=(-DCMAKE_POLICY_VERSION_MINIMUM=3.5)
args+=(-DCMAKE_OSX_DEPLOYMENT_TARGET="$MACOSX_DEPLOYMENT_TARGET")
args+=(-DCMAKE_OSX_ARCHITECTURES="$ARCHS")
args+=(-DDCMTK_ENABLE_MANPAGES=OFF)
args+=(-DBUILD_SHARED_LIBS=OFF)
args+=(-DCMAKE_BUILD_TYPE="$CONFIGURATION")
args+=(-DCMAKE_CXX_STANDARD=11)
args+=(-DDCMTK_ENABLE_CXX11=ON)
args+=(-DDCMTK_DEFAULT_DICT=builtin)

args+=(-DCMAKE_INSTALL_PREFIX="$install_dir")

args+=(-DCMAKE_IGNORE_PATH="/opt/local/include;/opt/local/lib;/opt/homebrew/include;/opt/homebrew/lib")

export PKG_CONFIG_PATH="$CONFIGURATION_TEMP_DIR/OpenJPEG.build/Install/lib/pkgconfig"

#cxxfs+=( -I/usr/local/opt/openssl/include )

if [ "$CONFIGURATION" = 'Debug' ]; then
    cxxfs+=( -g )
else
    cxxfs+=( -O2 )
fi

if [ ${#cfs[@]} -ne 0 ]; then
    cfss="${cfs[@]}"
    args+=( -DCMAKE_C_FLAGS="$cfss" )
fi
if [ ${#cxxfs[@]} -ne 0 ]; then
    cxxfss="${cxxfs[@]}"
    args+=( -DCMAKE_CXX_FLAGS="$cxxfss" )
fi

args+=(-DDCMTK_WITH_OPENSSL=ON)
args+=(-DOPENSSL_ROOT_DIR="$CONFIGURATION_TEMP_DIR/OpenSSL.build/Install")
args+=(-DOPENSSL_USE_STATIC_LIBS=ON)
args+=(-DOPENSSL_CRYPTO_LIBRARY="$CONFIGURATION_TEMP_DIR/OpenSSL.build/Install/lib/libcrypto.a")
args+=(-DOPENSSL_INCLUDE_DIR="$CONFIGURATION_TEMP_DIR/OpenSSL.build/Install/include")
args+=(-DOPENSSL_SSL_LIBRARY="$CONFIGURATION_TEMP_DIR/OpenSSL.build/Install/lib/libssl.a")

cd "$cmake_dir"
cmake "${args[@]}"

echo "$hash" > "$cmake_dir/.buildhash"
echo "$env" > "$cmake_dir/.cmakeenv"

exit 0
