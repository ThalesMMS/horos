#!/usr/bin/env python3
"""Generated T2 phantom keeps known TEs and recovers compartment T2 values."""
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    import pydicom
except ImportError as error:
    print('need pydicom to read the generated phantom:', error, file=sys.stderr)
    sys.exit(2)

root = Path(__file__).resolve().parents[1]
source = root / 'Horos/Sources/T2FitMap.swift'

with tempfile.TemporaryDirectory(prefix='horos-t2-phantom-') as folder:
    dest = Path(folder) / 'phantom'
    subprocess.run([sys.executable, str(root / 'tools/generate-t2-phantom-fixture.py'),
                    str(dest), '--size', '16'], check=True)
    files = sorted(dest.glob('echo-*.dcm'))
    if len(files) != 4:
        print('FAIL: expected four echo images, got', len(files), file=sys.stderr)
        sys.exit(1)
    tes, frames = [], []
    for path in files:
        dataset = pydicom.dcmread(path)
        tes.append(float(dataset.EchoTime))
        count = int(dataset.Rows) * int(dataset.Columns)
        frames.append(struct.unpack('<%dH' % count, dataset.PixelData))
        assert dataset.Modality == 'MR'
        assert dataset.PatientID == 'T2-156'
        width = int(dataset.Columns)
        height = int(dataset.Rows)
    if tes != [10.0, 20.0, 40.0, 80.0]:
        print('FAIL: unexpected echo times', tes, file=sys.stderr)
        sys.exit(1)
    literal = []
    for frame in frames:
        values = ', '.join('%.4f' % float(value) for value in frame)
        literal.append('[%s]' % values)
    code = '''
import Foundation
let tes: [Double] = %s
let frames: [[Float]] = [
%s
]
let map = T2FitMap.fitSeries(signals: frames, echoTimesMilliseconds: tes, width: %d, height: %d)
precondition(map.code == 0, map.reason)
let truths: [Double] = [40, 80, 120, 200]
for y in 0..<%d {
    for x in 0..<%d {
        let expected = truths[(y < %d ? 0 : 2) + (x < %d ? 0 : 1)]
        let got = Double(map.t2Milliseconds[y * %d + x])
        precondition(abs(got - expected) < 1.5, "\\(got) != \\(expected)")
    }
}
print("PASS: generated T2 phantom recovers 40/80/120/200 ms compartments")
''' % (tes, ',\n'.join(literal), width, height, height, width, height // 2, width // 2, width)
    with tempfile.TemporaryDirectory(prefix='horos-t2-phantom-fit-') as compiled:
        path = Path(compiled)
        (path / 'main.swift').write_text(code)
        subprocess.run(['xcrun', 'swiftc', str(source), str(path / 'main.swift'),
                        '-o', str(path / 'test')], check=True)
        subprocess.run([str(path / 'test')], check=True)
