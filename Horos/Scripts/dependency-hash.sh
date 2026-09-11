#!/bin/sh
#
# Decides whether a bundled dependency has to be configured again.
#
# Every dependency used to hash `env|sort` — the whole build environment — plus
# `git describe --dirty`. Both are far wider than what a dependency compiles
# from: editing one Objective-C file flips `--dirty` and rebuilds ITK, VTK, GDCM,
# DCMTK, OpenSSL, OpenJPEG, Grok and CharLS from scratch, and so does moving the
# code signing team into a variable, which no dependency reads.
#
# What is hashed here is the material that actually reaches the dependency's
# configure step: the toolchain, the SDK, the architectures, the deployment
# target, the configuration, the compiler and linker flags the scripts forward,
# the source location, and the scripts and patches themselves.
#
# Sourced, then called with the files whose contents shape the build — always
# the calling script, plus any patch it applies, since a changed patch changes
# the source:
#
#     . "$(dirname "$path")/../dependency-hash.sh"
#     dependency_hash "$path" "$some_patch"
#
# It leaves two variables behind, keeping the names the scripts already use:
#
#     env   the recorded material, written to .cmakeenv and printed on a rebuild
#     hash  what is compared against .cmakehash

# Variables a dependency's configure step reads, directly or through the
# per-dependency scripts. One list for all of them, in one place.
#
# Deliberately absent:
#   PRODUCT_NAME       names the wrapped archive in Make.sh, not the build
#   DEVELOPMENT_TEAM, CODE_SIGN_*  signing never reaches a static library
#   TARGET_TEMP_DIR    holds .cmakehash itself, so a change is already a miss
#   ONLY_ACTIVE_ARCH   the scripts forward ARCHS, not the active slice
dependency_hash_variables='
ARCHS
CLANG_CXX_LANGUAGE_STANDARD
CLANG_CXX_LIBRARY
CONFIGURATION
MACOSX_DEPLOYMENT_TARGET
NATIVE_ARCH_ACTUAL
OTHER_CFLAGS
OTHER_CPLUSPLUSFLAGS
OTHER_LDFLAGS
PROJECT_DIR
SDK_NAME
TARGET_NAME
'

# The compiler itself. `xcrun --find` carries the selected Xcode in its path, and
# the first line of --version carries the compiler release, so switching Xcode or
# updating it in place both move. The rest of --version names the host OS, which
# would rebuild every dependency on a macOS point update, so it is left out.
dependency_hash_toolchain() {
    _clang="$(xcrun --find clang 2>/dev/null)" || _clang="$(command -v clang 2>/dev/null)"
    if [ -n "$_clang" ]; then
        printf 'CLANG=%s\n' "$_clang"
        printf 'CLANG_VERSION=%s\n' "$("$_clang" --version 2>/dev/null | head -1)"
    else
        printf 'CLANG=\nCLANG_VERSION=\n'
    fi
}

dependency_hash_environment() {
    dependency_hash_toolchain
    for _name in $dependency_hash_variables; do
        eval "_value=\${$_name-}"
        printf '%s=%s\n' "$_name" "$_value"
    done
}

# Sets `env` and `hash` from the environment above and the files passed in.
#
# `md5` lives in /sbin. Without it every digest below is the empty string and
# `hash` becomes the same constant for every environment, so the stored
# .cmakehash always matches and nothing is ever reconfigured - which is the
# failure this file exists to prevent, made silent. Say so and stop instead.
# Changing to another digest would move every hash and rebuild all eight
# dependencies, so this stays md5 and insists on having it.
dependency_hash() {
    if ! command -v md5 >/dev/null 2>&1; then
        printf 'dependency-hash.sh: md5 is not on PATH (%s); refusing to hash nothing\n' \
            "$PATH" >&2
        exit 1
    fi
    env="$(dependency_hash_environment)"
    hash="$(md5 -qs "$env")"
    for _file in "$@"; do
        hash="$hash-$(md5 -q "$_file")"
    done
}
