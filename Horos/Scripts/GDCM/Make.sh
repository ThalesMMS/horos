#!/bin/sh

set -e; set -o xtrace

cmake_dir="$TARGET_TEMP_DIR/CMake"
install_dir="$TARGET_TEMP_DIR/Install"

# Skip the build only while nothing in the source tree is newer than the library
# the application actually links. Exiting on the mere existence of the install
# directory meant a change to GDCM never reached the application: the individual
# libraries could be rebuilt by hand and the merged one, which is what is linked,
# was left as it was. Four rebuilds of the application in a row picked up nothing.
wrapped="$install_dir/wlib/lib$PRODUCT_NAME.a"
if [ -d "$install_dir" ] && [ ! -f "$install_dir/.incomplete" ] && [ -f "$wrapped" ]; then
    changed=$(find "$SRCROOT/GDCM" -type f \( -name '*.h' -o -name '*.txx' -o -name '*.cxx' \
        -o -name '*.c' -o -name '*.hxx' -o -name 'CMakeLists.txt' \) -newer "$wrapped" -print -quit)
    [ -z "$changed" ] && exit 0
    echo "GDCM source is newer than $wrapped ($changed); rebuilding"
fi

mkdir -p "$install_dir"
touch "$install_dir/.incomplete"

args=()
export MAKEFLAGS="-j $(sysctl -n hw.ncpu)"
export CC=clang
export CXX=clang

cd "$cmake_dir"
make "${args[@]}" install

# wrap the libs into one
mkdir -p "$install_dir/wlib"
ars=$(find "$install_dir/lib" -name '*.a' -type f)
libtool -static -o "$install_dir/wlib/lib$PRODUCT_NAME.a" $ars

rm -f "$install_dir/.incomplete"

exit 0
