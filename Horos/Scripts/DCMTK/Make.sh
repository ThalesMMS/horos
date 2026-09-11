#!/bin/sh

set -e; set -o xtrace

cmake_dir="$TARGET_TEMP_DIR/CMake"
install_dir="$TARGET_TEMP_DIR/Install"
copy_dir="$BUILT_PRODUCTS_DIR/DCMTK"

[ -d "${copy_dir}" ] && [ ! -f "${copy_dir}/.incomplete" ] && exit 0

mkdir -p "$install_dir"
mkdir -p "${copy_dir}"
touch "${copy_dir}/.incomplete"

args=()
export MAKEFLAGS="-j $(sysctl -n hw.ncpu)"

echo "${cmake_dir}"
cd "$cmake_dir"
make "${args[@]}" install

# CMake preserves source timestamps when installing headers. A new pin can
# contain older files; make Xcode invalidate objects and prefix headers then.
find "$install_dir/include" -type f -exec touch {} +

# Keep the stock JPEG-LS codec ABI private to its adapter. The host also uses
# CharLS 2 through GDCM; those layouts must never share a symbol binding.
python3 "$PROJECT_DIR/tools/isolate-dcmtk-jpegls.py" "$install_dir/lib" \
    --architecture "$ARCHS" --deployment "$MACOSX_DEPLOYMENT_TARGET"

# Copy subset of applications to build directory
#
cp "${install_dir}/bin/dcmdump" "${copy_dir}"
cp "${install_dir}/bin/dcmpsprt" "${copy_dir}"
cp "${install_dir}/bin/dcmprscu" "${copy_dir}"
cp "${install_dir}/bin/dsr2html" "${copy_dir}"
cp "${install_dir}/bin/echoscu" "${copy_dir}"
# A built-in dictionary is used by the library; the external dictionary is
# also bundled for the application's existing dictionary consumers.
cp "$PROJECT_DIR/$TARGET_NAME/dcmdata/data/dicom.dic" "${copy_dir}"

rm -f "$copy_dir/.incomplete"

exit 0
