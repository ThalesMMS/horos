#!/usr/bin/env python3
"""#552: the shipped default refuses incompatible frames with identical geometry.

Generate the existing --parallel-pair phantom, then pass its real DICOM identity
to the production Swift admission policy. A/B and A/C differ only in the frame,
so refusing C cannot be explained by orientation or a different study.
"""
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile

try:
    import pydicom
except ImportError:
    print('needs pydicom to generate/read the --parallel-pair fixture', file=sys.stderr)
    raise SystemExit(2)

ROOT = Path(__file__).resolve().parents[1]
registered = re.findall(r'\[defaultValues setObject:@"([01])" forKey:@"UseFrameofReferenceUID"\]',
                        (ROOT / 'Horos/Sources/DefaultsOsiriX.m').read_text())
assert len(registered) == 1, 'one canonical registered preference is required'

DRIVER = r'''
import AppKit
@main struct Probe {
    static func main() throws {
        let records = try JSONSerialization.jsonObject(with: Data(contentsOf: URL(fileURLWithPath: CommandLine.arguments[1]))) as! [[String: String]]
        let name = "org.horosproject.tests.frame-default." + UUID().uuidString
        let defaults = UserDefaults(suiteName: name)!
        defer { defaults.removePersistentDomain(forName: name) }
        let key = ViewerReferenceLines.frameOfReferencePreferenceKey
        defaults.register(defaults: [key: CommandLine.arguments[2] == "1"])
        precondition(defaults.persistentDomain(forName: name)?[key] == nil)
        func admitted(_ target: Int) -> Bool {
            let world = ViewerReferenceLines.sameThreeDWorld(
                destinationFrame: records[target]["frame"], sourceFrame: records[0]["frame"],
                destinationStudy: records[target]["study"], sourceStudy: records[0]["study"],
                useFrameOfReference: defaults.bool(forKey: key))
            return ViewerReferenceLines.admitSynchronization(sameWorld: world, registered: false,
                                                            sameStudyOnly: true, manualSync: false)
        }
        precondition(admitted(1), "same-frame positive control must follow")
        precondition(!admitted(2), "different frame must be refused by the shipped default")
        let reason = ViewerReferenceLines.absenceReason(
            destinationFrame: records[2]["frame"], sourceFrame: records[0]["frame"],
            destinationStudy: records[2]["study"], sourceStudy: records[0]["study"],
            useFrameOfReference: defaults.bool(forKey: key), sameStudyOnly: true, registered: false)
        precondition(reason?.contains("Different frame of reference") == true)
        // Registering a new default must preserve an explicit legacy preference.
        defaults.set(false, forKey: key)
        defaults.register(defaults: [key: true])
        precondition(!defaults.bool(forKey: key) && admitted(2))
        print("PASS: registered default admits A/B and refuses A/C; explicit override preserved")
    }
}
'''

with tempfile.TemporaryDirectory(prefix='horos-frame-default-') as folder:
    work = Path(folder)
    fixture = work / 'fixture'
    subprocess.run([sys.executable, str(ROOT / 'tools/generate-cross-reference-fixture.py'),
                    str(fixture), '--parallel-pair'], check=True)
    groups = [[pydicom.dcmread(fixture / f'{series:02d}-{index:02d}.dcm') for index in range(16)]
              for series in (5, 6, 7)]
    for index in range(16):
        a, b, c = [group[index] for group in groups]
        for key in ('StudyInstanceUID', 'ImageOrientationPatient', 'ImagePositionPatient',
                    'PixelSpacing', 'SliceThickness', 'Rows', 'Columns', 'PixelData'):
            assert getattr(a, key) == getattr(b, key) == getattr(c, key), (index, key)
        assert a.FrameOfReferenceUID == b.FrameOfReferenceUID != c.FrameOfReferenceUID
    (work / 'identity.json').write_text(json.dumps([
        {'study': str(group[0].StudyInstanceUID), 'frame': str(group[0].FrameOfReferenceUID)}
        for group in groups]))
    (work / 'main.swift').write_text(DRIVER)
    subprocess.run(['xcrun', 'swiftc', '-parse-as-library',
                    str(ROOT / 'Horos/Sources/ViewerReferenceLines.swift'), str(work / 'main.swift'),
                    '-o', str(work / 'probe')], check=True)
    subprocess.run([str(work / 'probe'), str(work / 'identity.json'), registered[0]], check=True)
print('PASS: 48 synthetic DICOM images, identical geometry/pixels, only FrameOfReferenceUID differs')
