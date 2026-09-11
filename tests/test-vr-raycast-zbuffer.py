#!/usr/bin/env python3
"""Dental3D/CBCT ray casting must not index an invalid VTK Z buffer.

Upstream Horos 2.2 crashed in vtkFixedPointRayCastImage::GetZBufferValue while
Dental3DPlugin's configurePlugin was on screen with a CBCT volume. That stack
is not a plugin ABI load failure (NSCocoaErrorDomain 3585 / dyld). A compatible
arm64 plugin still ray-casts; the Horos mapper must drop a NULL or zero-size
Z buffer before CastRays so AddressSanitizer never sees the historical -1
index.
"""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
source = root / 'Horos/Sources/VRRayCastZBuffer.swift'
header = root / 'Horos/Sources/VRRayCastZBufferGuard.h'
if not source.is_file():
    raise SystemExit('FAIL: Horos/Sources/VRRayCastZBuffer.swift is missing')
if not header.is_file():
    raise SystemExit('FAIL: Horos/Sources/VRRayCastZBufferGuard.h is missing')

swift = r'''
import Foundation

func expect(_ ok: Bool, _ message: String) {
    precondition(ok, message)
}

expect(!RayCastZBuffer.isUsable(useZBuffer: true, pointerValid: false, width: 8, height: 8),
       "NULL Z buffer is not usable")
expect(!RayCastZBuffer.isUsable(useZBuffer: true, pointerValid: true, width: 0, height: 8),
       "zero-width Z buffer is not usable")
expect(!RayCastZBuffer.isUsable(useZBuffer: true, pointerValid: true, width: 8, height: 0),
       "zero-height Z buffer is not usable")
expect(!RayCastZBuffer.isUsable(useZBuffer: true, pointerValid: true, width: -1, height: 8),
       "negative Z size is not usable")
expect(!RayCastZBuffer.isUsable(useZBuffer: false, pointerValid: true, width: 8, height: 8),
       "UseZBuffer off stays off")
expect(RayCastZBuffer.isUsable(useZBuffer: true, pointerValid: true, width: 8, height: 8),
       "captured Z buffer remains usable")

let zCrash = RayCastZBuffer.classifyFailure(
    stackSymbol: "vtkFixedPointRayCastImage::GetZBufferValue(int, int)",
    loadErrorDomain: "",
    loadErrorCode: 0)
expect(zCrash == "raycast-zbuffer", "GetZBufferValue is the ray-cast crash, got \(zCrash)")

let abi = RayCastZBuffer.classifyFailure(
    stackSymbol: "dyld bootstrap",
    loadErrorDomain: NSCocoaErrorDomain,
    loadErrorCode: NSExecutableArchitectureMismatchError)
expect(abi == "abi-plugin-load", "architecture mismatch is ABI, got \(abi)")

let missing = RayCastZBuffer.classifyFailure(
    stackSymbol: "_objc_map_images",
    loadErrorDomain: NSCocoaErrorDomain,
    loadErrorCode: 3588)
expect(abi == "abi-plugin-load" && missing == "abi-plugin-load",
       "missing-image / wrong-arch plugin load is not GetZBufferValue")

let cbct = RayCastZBuffer.diagnoseCBCT(spacingMM: 0.2, sliceIntervalMM: 0.2,
                                       sliceCount: 32, pixelWidth: 64, pixelHeight: 64)
expect(cbct == "cbct-ready", "isotropic 0.2 mm CBCT is ready, got \(cbct)")

let invalid = RayCastZBuffer.diagnoseCBCT(spacingMM: 0, sliceIntervalMM: 0.2,
                                            sliceCount: 32, pixelWidth: 64, pixelHeight: 64)
expect(invalid == "invalid", "zero spacing is not a volume")

let nan = RayCastZBuffer.diagnoseCBCT(spacingMM: .nan, sliceIntervalMM: 0.2,
                                      sliceCount: 8, pixelWidth: 8, pixelHeight: 8)
expect(nan == "invalid", "NaN spacing is preserved as invalid")

let compatible = RayCastZBuffer.classifyTrigger(
    pluginCompatible: true, pluginLoaded: true,
    cbctDiagnosis: "cbct-ready", zBufferUsable: true)
expect(compatible == "raycast-ready", "compatible Dental3D + CBCT may ray-cast, got \(compatible)")

let sanitized = RayCastZBuffer.classifyTrigger(
    pluginCompatible: true, pluginLoaded: true,
    cbctDiagnosis: "cbct-ready", zBufferUsable: false)
expect(sanitized == "raycast-sanitized",
       "compatible plugin still ray-casts after dropping a bad Z buffer, got \(sanitized)")

let intel = RayCastZBuffer.classifyTrigger(
    pluginCompatible: false, pluginLoaded: false,
    cbctDiagnosis: "cbct-ready", zBufferUsable: false)
expect(intel == "abi-plugin-load", "Intel-only Dental3D is ABI, not a Z-buffer crash")

print("PASS: ABI load is distinct from GetZBufferValue; CBCT ray-cast drops an invalid Z buffer")
'''

c = r'''
#include "VRRayCastZBufferGuard.h"
#include <stdio.h>
#include <stdlib.h>
#include <assert.h>

/* Same indexing as VTK 8.2 vtkFixedPointRayCastImage::GetZBufferValue. */
static float GetZBufferValue(int use, const float *z, int width, int height,
                             float sample, int x, int y)
{
    int xPos, yPos;
    if (!use) {
        return 1.0f;
    }
    xPos = (int)((float)x * sample);
    yPos = (int)((float)y * sample);
    xPos = (xPos >= width) ? (width - 1) : xPos;
    yPos = (yPos >= height) ? (height - 1) : yPos;
    return *(z + yPos * width + xPos);
}

int main(void) {
    float captured[16];
    int i, use;
    float value;
    for (i = 0; i < 16; i++) captured[i] = 0.25f + 0.01f * (float)i;

    use = 1;
    if (!HorosRayCastZBufferIsUsable(use, captured, 4, 4)) {
        fprintf(stderr, "FAIL: a captured 4x4 Z buffer was refused\n");
        return 1;
    }
    value = GetZBufferValue(use, captured, 4, 4, 1.0f, 1, 2);
    assert(value == captured[2 * 4 + 1]);

    /* Historical Dental3D path: Intermix on, CaptureZBuffer left size 0 / NULL. */
    use = 1;
    if (!HorosRayCastZBufferIsUsable(use, NULL, 0, 0)) {
        use = 0;
    } else {
        fprintf(stderr, "FAIL: NULL zero-size Z buffer was treated as usable\n");
        return 1;
    }
    value = GetZBufferValue(use, NULL, 0, 0, 1.0f, 0, 0);
    if (value != 1.0f) {
        fprintf(stderr, "FAIL: sanitized GetZBufferValue returned %f\n", value);
        return 1;
    }

    use = 1;
    if (!HorosRayCastZBufferIsUsable(use, captured, 0, 8)) {
        use = 0;
    }
    value = GetZBufferValue(use, captured, 0, 8, 1.0f, 3, 1);
    assert(value == 1.0f);

    puts("PASS: ASan GetZBufferValue replica survives NULL/zero-size Z after the Horos guard");
    return 0;
}
'''

with tempfile.TemporaryDirectory(prefix='horos-raycast-zbuffer-') as directory:
    path = Path(directory)
    (path / 'main.swift').write_text(swift)
    subprocess.run([
        'xcrun', 'swiftc', str(source), str(path / 'main.swift'),
        '-o', str(path / 'swift-test')
    ], check=True)
    subprocess.run([str(path / 'swift-test')], check=True)

    (path / 'zbuffer.c').write_text(c)
    subprocess.run([
        'xcrun', 'clang', '-fsanitize=address', '-g',
        '-I', str(root / 'Horos/Sources'),
        str(path / 'zbuffer.c'), '-o', str(path / 'asan-test')
    ], check=True)
    env = dict(**{k: v for k, v in __import__('os').environ.items()})
    env['ASAN_OPTIONS'] = 'halt_on_error=1:detect_leaks=0'
    subprocess.run([str(path / 'asan-test')], check=True, env=env)
