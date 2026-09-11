#!/usr/bin/env python3
"""The 3D interaction baseline is one protocol, not a stopwatch.

#210 has to hand #375/#385 the same volume, camera, quality and events, with
render time kept apart from load, preset generation and input. A single elapsed
time cannot say which of those spent the frame. The protocol lives in
`HorosVRInteractionBenchmark`: p50/p95 of rotate/pan/clip, first frame on its
own, empty meaning not measured. The CT phantom already used by the 3D preset
panel is the volume; this test does not start a second suite.
"""
from pathlib import Path
import json
import re
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
failures = []
helper = root / 'Horos/Sources/VRInteractionBenchmark.swift'
view = (root / 'Horos/Sources/VRView.mm').read_bytes().decode('latin1')
project = (root / 'Horos.xcodeproj/project.pbxproj').read_bytes().decode('latin1')
phantom = (root / 'tools/generate-ct-phantom-fixture.py').read_text()

if not helper.is_file():
    failures.append('Horos/Sources/VRInteractionBenchmark.swift is missing')
if 'VRInteractionBenchmark.swift' not in project:
    failures.append('project.pbxproj does not compile VRInteractionBenchmark.swift')
if 'Horos-Swift.h' not in view:
    failures.append('VRView.mm does not import Horos-Swift.h')
if 'HorosVRInteractionBenchmark' not in view:
    failures.append('VRView.mm never records 3D interaction samples')
if 'beginSample:@"rotate"' not in view:
    failures.append('VRView.mm does not time rotation')
if 'beginSample:@"pan"' not in view:
    failures.append('VRView.mm does not time panning')
if 'beginSample:@"clip"' not in view:
    failures.append('VRView.mm does not time clipping')
if '[HorosVRInteractionBenchmark endSample]' not in view:
    failures.append('VRView.mm never closes an interaction sample')

# #29 / #258: backing conversion stays on the drag path. This issue must not
# put window points back into VTK.
if 'HorosVRInteractionGeometry backingPoint:' not in view:
    failures.append('mouseDragged no longer converts window points through VRInteractionGeometry')

# The catalog volume is the #34 phantom, not a second generator.
if '--slices' not in phantom or 'default=200' not in phantom:
    failures.append('the catalog CT phantom is no longer 200 slices by default')
if '--size' not in phantom or 'default=256' not in phantom:
    failures.append('the catalog CT phantom is no longer 256 wide by default')
if "default='CT-PHANTOM-34'" not in phantom:
    failures.append('the catalog CT phantom no longer uses patient CT-PHANTOM-34')

DRIVER = r'''
import Foundation

func emit(_ key: String, _ value: String) { print("\(key)\t\(value)") }

func close(_ value: Double, _ expected: Double) -> Bool { abs(value - expected) < 1e-9 }

emit("protocol", VRInteractionBenchmark.protocolID)
emit("generator", VRInteractionBenchmark.datasetGenerator)
emit("slices", String(VRInteractionBenchmark.datasetSlices))
emit("size", String(VRInteractionBenchmark.datasetSize))
emit("spacing", String(VRInteractionBenchmark.datasetSpacingMM))
emit("patient", VRInteractionBenchmark.datasetPatientID)
emit("viewport", "\(VRInteractionBenchmark.viewportWidth)x\(VRInteractionBenchmark.viewportHeight)")
emit("projection", VRInteractionBenchmark.cameraProjection)
emit("quality", VRInteractionBenchmark.qualityName)
emit("clip", String(VRInteractionBenchmark.clipThicknessMM))

emit("kindRotate", VRInteractionBenchmark.kind(for: "rotate"))
emit("kindPan", VRInteractionBenchmark.kind(for: "pan"))
emit("kindClip", VRInteractionBenchmark.kind(for: "clip"))
emit("kindFirst", VRInteractionBenchmark.kind(for: "firstFrame"))
emit("kindLoad", VRInteractionBenchmark.kind(for: "load"))
emit("kindPreset", VRInteractionBenchmark.kind(for: "preset"))
emit("kindInput", VRInteractionBenchmark.kind(for: "input"))

let empty = VRInteractionBenchmark.percentile([], p: 50)
emit("emptyPercentile", empty == nil ? "nil" : "\(empty!)")

let series: [NSNumber] = [10, 20, 30, 40, 50]
emit("p50", String(format: "%.4f", VRInteractionBenchmark.percentile(series, p: 50)!.doubleValue))
emit("p95", String(format: "%.4f", VRInteractionBenchmark.percentile(series, p: 95)!.doubleValue))
emit("p0", String(format: "%.4f", VRInteractionBenchmark.percentile(series, p: 0)!.doubleValue))
emit("p100", String(format: "%.4f", VRInteractionBenchmark.percentile(series, p: 100)!.doubleValue))

let idle = VRInteractionBenchmark.startSession(
    revision: "deadbeef", os: "26.6.2", architecture: "arm64",
    gpu: "Apple M4", scale: 1.0)
emit("emptySummary", idle.summary)
let idleJSON = try! JSONSerialization.jsonObject(with: idle.reportJSON.data(using: .utf8)!) as! [String: Any]
let idleRotate = idleJSON["interactions"] as! [String: Any]
let idleRotateStats = idleRotate["rotate"] as! [String: Any]
emit("emptyP50IsNull", idleRotateStats["p50"] is NSNull ? "yes" : "no")
emit("emptyStacks", idleJSON["stacks"] as? String ?? "")
emit("emptyOptimization", idleJSON["optimization"] as? String ?? "")
VRInteractionBenchmark.stopSession()

let session = VRInteractionBenchmark.startSession(
    revision: "deadbeef", os: "26.6.2", architecture: "arm64",
    gpu: "Apple M4", scale: 1.0)
session.beginPhase("load")
Thread.sleep(forTimeInterval: 0.02)
session.endPhase("load")
session.beginPhase("preset")
Thread.sleep(forTimeInterval: 0.01)
session.endPhase("preset")
session.beginPhase("input")
session.endPhase("input")

session.recordSample("firstFrame", milliseconds: 80, cpuPercent: -1, gpuPercent: -1, memoryBytes: 1_000_000)
session.recordSample("rotate", milliseconds: 10, cpuPercent: 20, gpuPercent: -1, memoryBytes: 1_100_000)
session.recordSample("rotate", milliseconds: 12, cpuPercent: 22, gpuPercent: -1, memoryBytes: 1_100_000)
session.recordSample("rotate", milliseconds: 11, cpuPercent: 21, gpuPercent: -1, memoryBytes: 1_100_000)
session.recordSample("pan", milliseconds: 8, cpuPercent: -1, gpuPercent: -1, memoryBytes: 1_100_000)
session.recordSample("pan", milliseconds: 9, cpuPercent: -1, gpuPercent: -1, memoryBytes: 1_100_000)
session.recordSample("clip", milliseconds: 14, cpuPercent: -1, gpuPercent: -1, memoryBytes: 1_200_000)
session.recordStacks("not captured")

emit("summary", session.summary)
let report = try! JSONSerialization.jsonObject(with: session.reportJSON.data(using: .utf8)!) as! [String: Any]
emit("reportProtocol", report["protocol"] as? String ?? "")
emit("reportRevision", report["revision"] as? String ?? "")
emit("reportOS", report["os"] as? String ?? "")
emit("reportArch", report["architecture"] as? String ?? "")
emit("reportGPU", report["gpu"] as? String ?? "")
emit("reportScale", String(report["scale"] as? Double ?? -1))
let dataset = report["dataset"] as! [String: Any]
emit("reportPatient", dataset["patientID"] as? String ?? "")
emit("reportSlices", String(dataset["slices"] as? Int ?? -1))
let configuration = report["configuration"] as! [String: Any]
emit("reportProjection", configuration["projection"] as? String ?? "")
emit("reportQuality", configuration["quality"] as? String ?? "")
emit("firstFrame", String(report["firstFrameMs"] as? Double ?? -1))
let phases = report["phases"] as! [String: Any]
emit("hasLoad", phases["load"] != nil ? "yes" : "no")
emit("hasPreset", phases["preset"] != nil ? "yes" : "no")
emit("hasInput", phases["input"] != nil ? "yes" : "no")
let rotate = (report["interactions"] as! [String: Any])["rotate"] as! [String: Any]
emit("rotateN", String(rotate["n"] as? Int ?? -1))
emit("rotateP50", String(format: "%.4f", rotate["p50"] as? Double ?? -1))
let pan = (report["interactions"] as! [String: Any])["pan"] as! [String: Any]
emit("panN", String(pan["n"] as? Int ?? -1))
emit("cpuRecorded", report["cpuPercent"] is NSNull ? "no" : "yes")
emit("gpuAbsent", report["gpuPercent"] is NSNull ? "yes" : "no")
emit("memoryPositive", (report["memoryBytes"] as? Int ?? 0) > 0 ? "yes" : "no")

VRInteractionBenchmark.beginSample("rotate")
Thread.sleep(forTimeInterval: 0.015)
VRInteractionBenchmark.endSample()
let after = (try! JSONSerialization.jsonObject(with: session.reportJSON.data(using: .utf8)!) as! [String: Any]
    )["interactions"] as! [String: Any]
let afterRotate = after["rotate"] as! [String: Any]
emit("liveRotateN", String(afterRotate["n"] as? Int ?? -1))
VRInteractionBenchmark.stopSession()
emit("currentCleared", VRInteractionBenchmark.current == nil ? "yes" : "no")
'''

results = {}
if helper.is_file():
    swiftc = subprocess.run(['xcrun', '--sdk', 'macosx', '-f', 'swiftc'], capture_output=True, text=True)
    if swiftc.returncode != 0:
        failures.append('no swiftc here: %s' % (swiftc.stderr or '').strip())
    else:
        with tempfile.TemporaryDirectory(prefix='horos-vr-benchmark-') as directory:
            (Path(directory) / 'main.swift').write_text(DRIVER)
            binary = Path(directory) / 'benchmark'
            built = subprocess.run(
                ['xcrun', '--sdk', 'macosx', 'swiftc', '-o', str(binary),
                 str(helper), str(Path(directory) / 'main.swift')],
                capture_output=True, text=True)
            if built.returncode != 0:
                failures.append('the 3D benchmark does not compile:\n%s' % built.stderr[-1500:])
            else:
                run = subprocess.run([str(binary)], capture_output=True, text=True, timeout=60)
                if run.returncode != 0:
                    failures.append('the driver failed: %s' % (run.stderr or run.stdout)[-800:])
                for line in run.stdout.splitlines():
                    key, _, value = line.partition('\t')
                    results[key] = value

if results:
    if results.get('protocol') != 'horos-vr-interaction-210':
        failures.append('the protocol id drifted: %r' % results.get('protocol'))
    if results.get('generator') != 'tools/generate-ct-phantom-fixture.py':
        failures.append('the dataset is no longer the catalog CT phantom: %r' % results.get('generator'))
    if results.get('slices') != '200' or results.get('size') != '256':
        failures.append('the fixed volume is no longer 200 x 256: %s x %s'
                        % (results.get('slices'), results.get('size')))
    if results.get('patient') != 'CT-PHANTOM-34':
        failures.append('the catalog patient id drifted: %r' % results.get('patient'))
    if results.get('viewport') != '1024x768':
        failures.append('the viewport is no longer 1024x768: %r' % results.get('viewport'))
    if results.get('projection') != 'parallel':
        failures.append('the camera projection drifted: %r' % results.get('projection'))
    if results.get('quality') != 'shipped-LOD':
        failures.append('quality is no longer the shipped LOD: %r' % results.get('quality'))
    if results.get('clip') != '40.0':
        failures.append('the clip slab is no longer 40 mm: %r' % results.get('clip'))

    for name, expected in (
        ('kindRotate', 'interaction'), ('kindPan', 'interaction'),
        ('kindClip', 'interaction'), ('kindFirst', 'interaction'),
        ('kindLoad', 'setup'), ('kindPreset', 'setup'), ('kindInput', 'setup'),
    ):
        if results.get(name) != expected:
            failures.append('%s is %r, not %s' % (name, results.get(name), expected))

    if results.get('emptyPercentile') != 'nil':
        failures.append('an empty series is reported as a percentile: %r' % results.get('emptyPercentile'))
    if results.get('p50') != '30.0000':
        failures.append('p50 of 10..50 is not 30: %r' % results.get('p50'))
    if results.get('p95') != '48.0000':
        failures.append('p95 of 10..50 is not 48: %r' % results.get('p95'))
    if results.get('p0') != '10.0000' or results.get('p100') != '50.0000':
        failures.append('the percentile ends drifted: %s %s' % (results.get('p0'), results.get('p100')))

    if 'not measured' not in (results.get('emptySummary') or ''):
        failures.append('a session with no samples does not say so: %r' % results.get('emptySummary'))
    if results.get('emptyP50IsNull') != 'yes':
        failures.append('missing rotate samples are published as a number')
    if results.get('emptyStacks') != 'not captured':
        failures.append('missing stacks are not named: %r' % results.get('emptyStacks'))
    if results.get('emptyOptimization') != 'none':
        failures.append('the report implies an optimization that was not measured: %r'
                        % results.get('emptyOptimization'))

    if results.get('reportProtocol') != 'horos-vr-interaction-210':
        failures.append('the JSON dropped the protocol id')
    for key, expected in (
        ('reportRevision', 'deadbeef'), ('reportOS', '26.6.2'),
        ('reportArch', 'arm64'), ('reportGPU', 'Apple M4'),
        ('reportPatient', 'CT-PHANTOM-34'), ('reportSlices', '200'),
        ('reportProjection', 'parallel'), ('reportQuality', 'shipped-LOD'),
    ):
        if results.get(key) != expected:
            failures.append('%s is %r' % (key, results.get(key)))
    if results.get('reportScale') != '1.0':
        failures.append('scale is missing from the report: %r' % results.get('reportScale'))
    if results.get('firstFrame') != '80.0':
        failures.append('first frame mixed with later interaction samples: %r' % results.get('firstFrame'))
    if results.get('hasLoad') != 'yes' or results.get('hasPreset') != 'yes' or results.get('hasInput') != 'yes':
        failures.append('setup phases are missing from the report: load=%s preset=%s input=%s'
                        % (results.get('hasLoad'), results.get('hasPreset'), results.get('hasInput')))
    if results.get('rotateN') != '3':
        failures.append('rotate samples were mixed with setup phases: %r' % results.get('rotateN'))
    if results.get('rotateP50') != '11.0000':
        failures.append('rotate p50 is not the middle sample: %r' % results.get('rotateP50'))
    if results.get('panN') != '2':
        failures.append('pan samples were lost: %r' % results.get('panN'))
    if results.get('cpuRecorded') != 'yes':
        failures.append('injected CPU is missing from the report')
    if results.get('gpuAbsent') != 'yes':
        failures.append('a missing GPU sample is published as a number')
    if results.get('memoryPositive') != 'yes':
        failures.append('memory is not recorded')
    if 'first frame 80.0 ms' not in (results.get('summary') or ''):
        failures.append('the summary hides the first frame: %r' % results.get('summary'))
    if results.get('liveRotateN') != '4':
        failures.append('beginSample/endSample did not add a rotate sample: %r' % results.get('liveRotateN'))
    if results.get('currentCleared') != 'yes':
        failures.append('stopSession left a current session')

for failure in failures:
    print('FAIL: %s' % failure)
if failures:
    sys.exit(1)
print('ok: 3D interaction baseline keeps rotate/pan/clip, first frame and setup phases apart')
