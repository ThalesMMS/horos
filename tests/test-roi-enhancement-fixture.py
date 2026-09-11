#!/usr/bin/env python3
"""Generated dynamic phantom keeps known times and recovers the vessel TAC."""
from pathlib import Path
import subprocess
import sys
import tempfile

try:
    import pydicom
except ImportError as error:
    print('need pydicom to read the generated phantom:', error, file=sys.stderr)
    raise SystemExit(2)

root = Path(__file__).resolve().parents[1]
source = root / 'Horos/Sources/ROIEnhancement.swift'
if not source.is_file():
    raise SystemExit('FAIL: Horos/Sources/ROIEnhancement.swift is missing')

generator = root / 'tools/generate-roi-enhancement-fixture.py'
times = [0.0, 2.0, 4.0, 6.0, 8.0, 10.0, 12.0, 14.0]
hu = [40.0, 80.0, 150.0, 220.0, 200.0, 140.0, 90.0, 60.0]

with tempfile.TemporaryDirectory(prefix='horos-roi-enhancement-phantom-') as folder:
    dest = Path(folder) / 'phantom'
    subprocess.run([sys.executable, str(generator), str(dest)], check=True)
    files = sorted(dest.glob('phase-*.dcm'))
    if len(files) != 8:
        raise SystemExit('FAIL: expected eight dynamic phases, got %d' % len(files))
    frames = []
    width = height = None
    for index, path in enumerate(files):
        dataset = pydicom.dcmread(path)
        rows, columns = int(dataset.Rows), int(dataset.Columns)
        if width is None:
            width, height = columns, rows
        pixels = [float(value) for value in dataset.pixel_array.flatten()]
        frames.append(pixels)
        acquired = str(dataset.AcquisitionTime)
        expected_seconds = times[index]
        seconds = int(acquired[0:2]) * 3600 + int(acquired[2:4]) * 60 + int(acquired[4:6])
        if seconds != 12 * 3600 + int(expected_seconds):
            raise SystemExit('FAIL: AcquisitionTime %s is not t=%s' % (acquired, expected_seconds))

    swift = r'''
import Foundation
let times: [Double] = %s
let hu: [Double] = %s
let width = %d, height = %d
let frames: [[Float]] = [
%s
]
let vessel = ROIEnhancement.Region(name: "vessel", column: width / 4, row: height / 4,
                                   width: width / 2, height: height / 2)
let phases = zip(times, frames).map {
    ROIEnhancement.Phase(timeSeconds: $0.0, pixels: $0.1, width: width, height: height)
}
let result = ROIEnhancement.curves(phases: phases, regions: [vessel])
precondition(result.code == 0, result.reason)
for (index, sample) in result.curves[0].samples.enumerated() {
    precondition(abs(sample.mean - hu[index]) < 0.51, "\(sample.mean) != \(hu[index])")
}
print("PASS: generated dynamic phantom recovers the known vessel TAC")
''' % (
        times,
        hu,
        width,
        height,
        ',\n'.join('    [' + ', '.join('%.1f' % value for value in frame) + ']' for frame in frames),
    )
    with tempfile.TemporaryDirectory(prefix='horos-roi-enhancement-fit-') as compiled:
        path = Path(compiled)
        (path / 'main.swift').write_text(swift)
        subprocess.run([
            'xcrun', 'swiftc', str(source), str(path / 'main.swift'),
            '-o', str(path / 'test')
        ], check=True)
        subprocess.run([str(path / 'test')], check=True)
