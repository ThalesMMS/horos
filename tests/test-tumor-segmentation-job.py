#!/usr/bin/env python3
"""Local tumour-segmentation helper contract: job JSON, mock run, no silent resize."""
from pathlib import Path
import json
import struct
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
source = root / 'Horos/Sources/TumorSegmentationJob.swift'
helper = root / 'tools/metal3d_tumor_segmentation_mock.py'
if not source.is_file():
    print('FAIL: Horos/Sources/TumorSegmentationJob.swift is missing')
    sys.exit(1)
if not helper.is_file():
    print('FAIL: tools/metal3d_tumor_segmentation_mock.py is missing')
    sys.exit(1)

main = r'''
import Foundation

func check(_ condition: @autoclosure () -> Bool, _ message: String) {
    precondition(condition(), message)
}

check(TumorSegmentationJob.voxelCount(width: 4, height: 4, depth: 2) == 32, "4x4x2 voxels")
check(TumorSegmentationJob.inputByteCount(width: 4, height: 4, depth: 2) == 128, "float32 LE bytes")
check(TumorSegmentationJob.labelmapByteCount(width: 4, height: 4, depth: 2) == 32, "uint8 voxels")
check(TumorSegmentationJob.voxelCount(width: -1, height: 4, depth: 2) == nil, "negative size")
check(TumorSegmentationJob.allowedLabels == [0, 1, 2, 4], "BraTS-style labels")

let identity: [[Double]] = [
    [1, 0, 0, 0],
    [0, 1, 0, 0],
    [0, 0, 1, 0],
    [0, 0, 0, 1],
]
let good: [String: Any] = [
    "dimensions": [4, 4, 2],
    "expectedVoxelCount": 32,
    "spacingMM": [1.0, 1.0, 2.0],
    "referenceVoxelToPatientMatrix": identity,
    "inputVolume": "/tmp/input.float32.raw",
    "outputLabelmap": "/tmp/out.uint8.raw",
    "resultJSON": "/tmp/result.json",
    "selectedDICOMSeries": [[
        "seriesDescription": "T1c axial",
        "suggestedRole": "t1c",
        "localPaths": ["/tmp/synthetic/IM0001"],
        "localImageCount": 2,
        "channelRegistration": "dicom-patient-geometry",
    ]],
    "tumourSeeds": [[
        "volumeVoxel": [1, 1, 0],
        "diameterMM": 5.0,
    ]],
    "tumourSeedSelectionRadiusMM": 60,
]
let job = try TumorSegmentationJob.parse(good)
check(job.width == 4 && job.height == 4 && job.depth == 2, "parsed dimensions")
check(job.voxelOrder == "z,y,x", "x is fastest")
check(job.inputScalar == "float32-le", "little-endian float32")
check(job.selectedSeriesCount == 1, "explicit series")
check(job.seedCount == 1, "seeds")
check(job.registrationIsGeometric, "DICOM geometry is geometric")

var missingCount = good
missingCount.removeValue(forKey: "expectedVoxelCount")
check(TumorSegmentationJob.parseRefusal(missingCount)!.lowercased().contains("voxel"),
      "missing voxel count")

var wrongCount = good
wrongCount["expectedVoxelCount"] = 16
check(TumorSegmentationJob.parseRefusal(wrongCount)!.contains("32"), "count must match WxHxD")

var badMatrix = good
badMatrix["referenceVoxelToPatientMatrix"] = [1, 0, 0]
check(TumorSegmentationJob.parseRefusal(badMatrix)!.lowercased().contains("matrix"),
      "LPS matrix must be 4x4")

var resize = good
resize["selectedDICOMSeries"] = [[
    "seriesDescription": "T2",
    "suggestedRole": "t2",
    "localPaths": ["/tmp/synthetic/IM0001"],
    "localImageCount": 2,
    "channelRegistration": "shape-resize-fallback",
]]
let resizeJob = try TumorSegmentationJob.parse(resize)
check(!resizeJob.registrationIsGeometric, "shape resize is not geometric registration")
check(TumorSegmentationJob.importRefusal(for: resizeJob)!.lowercased().contains("resize"),
      "resize must not import as registered")

check(TumorSegmentationJob.seriesRole(fromDescription: "Ax T1 GAD") == "t1c", "post-contrast T1")
check(TumorSegmentationJob.seriesRole(fromDescription: "T2 FLAIR") == "flair", "FLAIR")
check(TumorSegmentationJob.seriesRole(fromDescription: "T2 TSE") == "t2", "T2")
check(TumorSegmentationJob.seriesRole(fromDescription: "MPRAGE") == "t1", "T1")

check(TumorSegmentationJob.kind(forHelperName: "metal3d_tumor_segmentation_mock.py") == .mock, "mock")
check(TumorSegmentationJob.kind(forHelperName: "metal3d_tumor_segmentation_candidate.py") == .candidate, "candidate")
check(TumorSegmentationJob.kind(forHelperName: "metal3d_tumor_segmentation_nnunet.py") == .nnunet, "nnunet")
check(TumorSegmentationJob.kind(forHelperName: "metal3d_tumor_segmentation_external.py") == .external, "external")

let mockResult: [String: Any] = ["backend": "mock-threshold", "status": "ok"]
check(TumorSegmentationJob.displayKind(result: mockResult, helperKind: .mock) == .mock, "mock stays mock")
check(TumorSegmentationJob.promoteToTrained(result: mockResult, helperKind: .mock) == false,
      "mock is not a trained prediction")
check(TumorSegmentationJob.promoteToTrained(result: ["backend": "heuristic-candidate"], helperKind: .candidate) == false,
      "candidate is not a trained prediction")

check(TumorSegmentationJob.nnunetModelFolder(environment: [:], config: [:]) == nil, "no folder")
check(TumorSegmentationJob.nnunetRefusal(environment: [:], config: [:])!.lowercased().contains("nnunet"),
      "missing model is an error")
check(TumorSegmentationJob.fallbackKindWhenModelMissing == nil,
      "missing nnU-Net must not become a seed sphere or heuristic")

let args = TumorSegmentationJob.launchArguments(helper: "/helpers/mock.py", job: "/tmp/job.json")
check(args == ["--job", "/tmp/job.json"], "only --job")
check(TumorSegmentationJob.timeoutSeconds == 180, "bounded helper")

let log = TumorSegmentationJob.sanitizeLog(
    "patient Jane Doe ID 123-45 ran helper --job /tmp/job.json",
    patientName: "Jane Doe",
    patientID: "123-45")
check(!log.contains("Jane"), log)
check(!log.contains("123-45"), log)
check(log.contains("--job"), "keep the argument name")

let labels = Data([0, 1, 2, 4, 0, 1, 2, 4] + [UInt8](repeating: 0, count: 24))
check(TumorSegmentationJob.labelmapRefusal(labels, expectedVoxelCount: 32) == nil, "valid labels")
let truncated = Data([0, 1, 2])
check(TumorSegmentationJob.labelmapRefusal(truncated, expectedVoxelCount: 32)!.lowercased().contains("trunc"),
      "truncated output")
let invalid = Data([0, 1, 3] + [UInt8](repeating: 0, count: 29))
check(TumorSegmentationJob.labelmapRefusal(invalid, expectedVoxelCount: 32)!.contains("3"),
      "label 3 is not a Horos label until remapped")

print("PASS: job contract names geometry, backends and refusals")
'''

with tempfile.TemporaryDirectory(prefix='horos-tumor-seg-') as tmp:
    p = Path(tmp)
    (p / 'main.swift').write_text(main)
    compiled = subprocess.run(
        ['xcrun', 'swiftc', str(source), str(p / 'main.swift'), '-o', str(p / 'test')],
        capture_output=True, text=True)
    if compiled.returncode != 0:
        print('FAIL: swiftc TumorSegmentationJob.swift')
        print(compiled.stderr or compiled.stdout)
        sys.exit(1)
    ran = subprocess.run([str(p / 'test')], capture_output=True, text=True)
    if ran.returncode != 0:
        print('FAIL: TumorSegmentationJob assertions')
        print(ran.stderr or ran.stdout)
        sys.exit(1)
    print(ran.stdout.strip())

    work = p / 'job'
    work.mkdir()
    width, height, depth = 4, 4, 2
    voxels = width * height * depth
    # z,y,x with x fastest: a bright 2x2x1 blob in the first slice.
    volume = [0.0] * voxels
    for y in range(2):
        for x in range(2):
            volume[y * width + x] = 10.0
    input_path = work / 'input.float32.raw'
    input_path.write_bytes(b''.join(struct.pack('<f', value) for value in volume))
    output_path = work / 'tumor-labelmap.uint8.raw'
    result_path = work / 'result.json'
    job_path = work / 'job.json'
    identity = [
        [1, 0, 0, 0],
        [0, 1, 0, 0],
        [0, 0, 1, 0],
        [0, 0, 0, 1],
    ]
    job_path.write_text(json.dumps({
        'dimensions': [width, height, depth],
        'expectedVoxelCount': voxels,
        'spacingMM': [1.0, 1.0, 2.0],
        'referenceVoxelToPatientMatrix': identity,
        'inputVolume': str(input_path),
        'outputLabelmap': str(output_path),
        'resultJSON': str(result_path),
    }))
    launched = subprocess.run(
        [sys.executable, str(helper), '--job', str(job_path)],
        capture_output=True, text=True, timeout=20)
    if launched.returncode != 0:
        print('FAIL: mock helper --job')
        print(launched.stderr or launched.stdout)
        sys.exit(1)
    labels = output_path.read_bytes()
    if len(labels) != voxels:
        print('FAIL: mock labelmap size %d != %d' % (len(labels), voxels))
        sys.exit(1)
    if any(label not in (0, 1, 2, 4) for label in labels):
        print('FAIL: mock wrote a label outside 0/1/2/4')
        sys.exit(1)
    if labels[0] != 1 or labels[-1] != 0:
        print('FAIL: mock threshold did not mark the bright blob in z,y,x order')
        sys.exit(1)
    result = json.loads(result_path.read_text())
    if result.get('backend') != 'mock-threshold':
        print('FAIL: mock result did not name the mock backend')
        sys.exit(1)
    if 'not diagnostic' not in result.get('message', '').lower():
        print('FAIL: mock must say it is not diagnostic')
        sys.exit(1)
    stdout = json.loads(launched.stdout)
    if stdout.get('backend') != 'mock-threshold':
        print('FAIL: helper stdout must name the mock backend')
        sys.exit(1)

print('PASS: mock helper --job writes a uint8 z/y/x labelmap')
