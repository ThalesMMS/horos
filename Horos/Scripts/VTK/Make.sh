#!/bin/sh

set -e; set -o xtrace

source_dir="$PROJECT_DIR/$TARGET_NAME"
cmake_dir="$TARGET_TEMP_DIR/CMake"
install_dir="$TARGET_TEMP_DIR/Install"

if [ -d "$install_dir" ] && [ -f "$install_dir/wlib/lib$PRODUCT_NAME.a" ] && [ ! -f "$install_dir/.incomplete" ]; then
    exit 0
fi

mkdir -p "$install_dir"
touch "$install_dir/.incomplete"

args=()
export MAKEFLAGS="-j $(sysctl -n hw.ncpu)"

cd "$cmake_dir"
make "${args[@]}" install

# missing tiff headers
mkdir -p "$install_dir/include/vtktiff/libtiff"
if [ -f "$cmake_dir/ThirdParty/tiff/vtktiff/libtiff/tiffconf.h" ]; then
    find "$source_dir/ThirdParty/tiff/vtktiff/libtiff" -name '*.h' -exec rsync {} "$install_dir/include/vtktiff/libtiff/" \;
    rsync "$cmake_dir/ThirdParty/tiff/vtktiff/libtiff/tiffconf.h" "$install_dir/include/vtktiff/libtiff/"
elif [ -d "/opt/homebrew/include" ]; then
    for header in tiff.h tiffconf.h tiffio.h tiffvers.h; do
        if [ -e "/opt/homebrew/include/$header" ]; then
            cp -Lf "/opt/homebrew/include/$header" "$install_dir/include/vtktiff/libtiff/"
        fi
    done
fi

if [ -f "$install_dir/include/vtk_tiff.h" ]; then
    sed -i '' 's|# include <tiffio.h>|# include <vtktiff/libtiff/tiffio.h>|' "$install_dir/include/vtk_tiff.h"
fi

# wrap the libs into one
mkdir -p "$install_dir/wlib"
ars=$(find "$install_dir/lib" -name '*.a' -type f | tr '\n' ' ')
libtool -static -o "$install_dir/wlib/lib$PRODUCT_NAME.a" $ars

rm -f "$install_dir/.incomplete"

exit 0
