#!/usr/bin/env python3
"""#377/A247: a known phantom, measured against its closed form.

A247 asks that a known phantom give a closed surface and a **coherent volume** in
the supported algorithms. `tests/test-roi-volume-geometry.py` already covers the
geometry with synthetic slices; what was missing was a phantom whose volume is
known in closed form, so that "coherent" could be a number rather than a word.

Two phantoms, and the tolerance is fixed here before anything is measured:

* a **cylinder**, whose sampled areas are all equal, so the only error left is
  the integration convention. The shipped result must equal
  `area × (n − 1) × spacing` **exactly** — see the note at the end about why that
  is `n − 1` and not `n`.
* a **sphere** of radius 50 mm, sampled at 4, 2 and 1 mm. The error against
  `4/3 π r³` must **shrink** as the sampling gets finer, and must be under **2 %**
  at 1 mm.

The closed surface the criterion also asks for is a VTK mesh and is not covered
here.
"""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
source = root / 'Horos/Sources/ROIVolumeGeometry.swift'
assert source.is_file(), 'FAIL: ROIVolumeGeometry.swift is missing'

DRIVER = r'''
import Foundation
import simd

func axialSlice(areaMm2: Double, z: Double) -> ROIVolumeSlice {
    ROIVolumeSlice(areaCm2: areaMm2 / 100,
                   originX: 0, originY: 0, originZ: z,
                   normalX: 0, normalY: 0, normalZ: 1,
                   componentCount: 1, maskPixelCount: 0, pixelAreaMm2: 0,
                   spacingBetweenSlicesMm: 0)
}

func measure(_ slices: [ROIVolumeSlice]) -> Double {
    guard let result = ROIVolumeGeometry.volume(from: slices, seriesOrigins: nil,
                                                interpolateMissing: false, meshPointCount: 0)
    else { preconditionFailure("no result for \(slices.count) slices") }
    return result.volumeCm3
}

@main struct Check {
    static func main() {
        // --- cylinder: the integration convention, with no discretisation error
        let radius = 30.0, spacing = 2.0, count = 21
        let area = Double.pi * radius * radius
        var cylinder: [ROIVolumeSlice] = []
        for index in 0..<count {
            cylinder.append(axialSlice(areaMm2: area, z: Double(index) * spacing))
        }
        let measuredCylinder = measure(cylinder)
        // mm^2 * mm = mm^3, and 1000 mm^3 = 1 cm^3
        let betweenOutermost = area * Double(count - 1) * spacing / 1000
        precondition(abs(measuredCylinder - betweenOutermost) < 1e-9,
                     "cylinder: \(measuredCylinder) vs \(betweenOutermost)")
        // ...and it is NOT the slab convention, which would add one spacing.
        let slabConvention = area * Double(count) * spacing / 1000
        precondition(abs(measuredCylinder - slabConvention) > 1e-3)

        // --- sphere: convergence to the closed form
        let sphereRadius = 50.0
        let analytic = 4.0 / 3.0 * Double.pi * pow(sphereRadius, 3) / 1000
        var errors: [Double] = []
        for step in [4.0, 2.0, 1.0] {
            var slices: [ROIVolumeSlice] = []
            var z = -sphereRadius + step / 2
            while z < sphereRadius {
                let squared = sphereRadius * sphereRadius - z * z
                if squared > 0 {
                    slices.append(axialSlice(areaMm2: Double.pi * squared, z: z))
                }
                z += step
            }
            let measured = measure(slices)
            let error = abs(measured - analytic) / analytic
            errors.append(error)
            print(String(format: "sphere at %.0f mm: %.4f cm3 against %.4f cm3, %.3f%% low",
                         step, measured, analytic, error * 100))
        }
        // Finer sampling must not be worse, and 1 mm must be within 2%.
        precondition(errors[1] < errors[0], "2 mm should beat 4 mm: \(errors)")
        precondition(errors[2] < errors[1], "1 mm should beat 2 mm: \(errors)")
        precondition(errors[2] < 0.02, "1 mm sampling is \(errors[2] * 100)% off")
        // The error is one-sided: the trapezoid between plane centres leaves the
        // two caps out, so a phantom is always measured a little small.
        for step in [4.0, 2.0, 1.0] {
            var slices: [ROIVolumeSlice] = []
            var z = -sphereRadius + step / 2
            while z < sphereRadius {
                let squared = sphereRadius * sphereRadius - z * z
                if squared > 0 { slices.append(axialSlice(areaMm2: Double.pi * squared, z: z)) }
                z += step
            }
            precondition(measure(slices) < analytic, "the measurement must be an under-estimate")
        }

        // --- a single plane is not a volume, and says so rather than guessing
        precondition(ROIVolumeGeometry.volume(from: [axialSlice(areaMm2: area, z: 0)],
                                              seriesOrigins: nil, interpolateMissing: false,
                                              meshPointCount: 0) == nil)
        print(String(format: "cylinder exact to 1e-9; sphere within %.3f%% at 1 mm", errors[2] * 100))
    }
}
'''

with tempfile.TemporaryDirectory(prefix='horos-roi-phantom-') as folder:
    path = Path(folder)
    (path / 'Check.swift').write_text(DRIVER)
    # ROIVolumeGeometry names types from its neighbours, so they come too.
    build = subprocess.run(['xcrun', 'swiftc', '-parse-as-library',
                            str(root / 'Horos/Sources/VRMeasurementGeometry.swift'),
                            str(root / 'Horos/Sources/ROILineGeometry.swift'),
                            str(root / 'Horos/Sources/ROIIntersliceGeometry.swift'),
                            str(source),
                            str(path / 'Check.swift'), '-o', str(path / 'check')],
                           capture_output=True, text=True)
    if build.returncode:
        print('FAIL: the geometry does not compile')
        print(build.stderr.strip()[-1500:])
        raise SystemExit(1)
    run = subprocess.run([str(path / 'check')], capture_output=True, text=True)
    print(run.stdout.strip())
    if run.returncode:
        print('FAIL: the phantom does not match its closed form')
        print(run.stderr.strip()[-1500:])
        raise SystemExit(1)

print('PASS: a known phantom is measured coherently, and the convention is pinned')
