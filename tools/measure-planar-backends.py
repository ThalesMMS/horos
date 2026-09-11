#!/usr/bin/env python3
"""Measure the planar submission path on both Metal backends (#609).

No app, no window, no database: the same `PlanarFrame` the host builds is
rendered offscreen by `PlanarMetalRenderer` (the backend in use) and by
`PlanarMetal4Renderer` (the pilot), and the two outputs are compared byte for
byte before any timing is reported.

Workloads, repetitions and the decision rule are fixed here, before the
comparison, and printed with the result:

    cold pipeline compilation   first build of the render pipeline state
    warm pipeline compilation   the same build with the device cache in place
    cpu encode                  entry to commit, on the calling thread
    gpu                         the GPU's own start/end timestamps
    wall                        entry to the point the pixels may be read

    python3 tools/measure-planar-backends.py [--iterations 200] [--json out.json]
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument('--iterations', type=int, default=200)
parser.add_argument('--warmup', type=int, default=20)
parser.add_argument('--json', type=Path, default=None)
arguments = parser.parse_args()

DRIVER = r'''
import Foundation
import Metal

struct Sample { var cpu: Double; var wall: Double; var gpu: Double }

func statistics(_ values: [Double]) -> [String: Double] {
    guard !values.isEmpty else { return [:] }
    let sorted = values.sorted()
    func percentile(_ p: Double) -> Double {
        let index = min(max(Int((Double(sorted.count - 1) * p).rounded()), 0), sorted.count - 1)
        return sorted[index]
    }
    return ["mean": values.reduce(0, +) / Double(values.count),
            "median": percentile(0.5), "p95": percentile(0.95),
            "min": sorted.first!, "max": sorted.last!]
}

func makeFrame(width: Int, height: Int, colour: Bool, viewWidth: Double, viewHeight: Double) throws -> PlanarFrame {
    var pixels = Data()
    if colour {
        var bytes = [UInt8]()
        for index in 0..<(width * height) {
            bytes += [255, UInt8((index * 31) % 256), UInt8(255 - (index * 17) % 256), UInt8((index * 11) % 256)]
        }
        pixels = Data(bytes)
    } else {
        let values = (0..<(width * height)).map { Float(($0 % 4096)) - 1024 }
        pixels = values.withUnsafeBytes { Data($0) }
    }
    var clut = [UInt8]()
    for index in 0..<256 { clut += [UInt8(index), UInt8(255 - index), UInt8((index * 3) % 256), 255] }
    let snapshot: NSDictionary = [
        "width": width, "height": height, "pixels": pixels, "clut": Data(clut),
        "frameIdentity": "bench-\(width)x\(height)-\(colour)",
        "screenToPixel": [0.0, 0.0, Double(width), 0.0, 0.0, Double(height)],
        "viewSize": [viewWidth, viewHeight],
        "level": colour ? 127.5 : 40.0, "widthWindow": colour ? 255.0 : 400.0,
        "isColor": colour, "nearest": false, "background": false, "softwareScale": 1,
    ]
    return try PlanarFrame(snapshot)
}

@main struct Benchmark {
    static func main() throws {
        guard let device = MTLCreateSystemDefaultDevice() else {
            print("skipped: Metal device unavailable"); exit(2)
        }
        guard PlanarMetal4Renderer.isSupported(device) else {
            print("skipped: this device or system has no Metal 4"); exit(2)
        }

        let iterations = ITERATIONS
        let warmup = WARMUP
        var report: [String: Any] = ["device": device.name,
                                     "architecture": device.architecture.name,
                                     "iterations": iterations, "warmup": warmup]

        // Compilation is measured in its own process, one backend per run:
        // whichever compiles second finds the system shader cache already warm
        // and reports a time that is not a compilation.
        if CommandLine.arguments.contains("compile3") {
            let started = ProcessInfo.processInfo.systemUptime
            _ = try PlanarMetalRenderer(device: device)
            let cold = (ProcessInfo.processInfo.systemUptime - started) * 1000
            let again = ProcessInfo.processInfo.systemUptime
            _ = try PlanarMetalRenderer(device: device)
            let warm = (ProcessInfo.processInfo.systemUptime - again) * 1000
            print(String(data: try JSONSerialization.data(withJSONObject:
                ["backend": "metal3", "cold_ms": cold, "warm_ms": warm], options: [.sortedKeys]),
                encoding: .utf8)!)
            return
        }
        if CommandLine.arguments.contains("compile4") {
            PlanarMetal4Renderer.PipelineCache.removeAll()
            let started = ProcessInfo.processInfo.systemUptime
            let cold = try PlanarMetal4Renderer(device: device)
            let coldMilliseconds = (ProcessInfo.processInfo.systemUptime - started) * 1000
            let again = ProcessInfo.processInfo.systemUptime
            let warmRenderer = try PlanarMetal4Renderer(device: device)
            let warm = (ProcessInfo.processInfo.systemUptime - again) * 1000
            print(String(data: try JSONSerialization.data(withJSONObject:
                ["backend": "metal4", "cold_ms": coldMilliseconds, "warm_ms": warm,
                 "pipeline_compiles": cold.pipelineCompileCount,
                 "pipeline_hits": warmRenderer.pipelineHitCount], options: [.sortedKeys]),
                encoding: .utf8)!)
            return
        }

        let workloads: [(String, Int, Int, Bool, Int, Int)] = [
            ("mono-512-view-800x500", 512, 512, false, 800, 500),
            ("mono-1024-view-1600x1000", 1024, 1024, false, 1600, 1000),
            ("colour-512-view-800x500", 512, 512, true, 800, 500),
        ]

        var results: [String: Any] = [:]
        for (name, width, height, colour, viewWidth, viewHeight) in workloads {
            let frame = try makeFrame(width: width, height: height, colour: colour,
                                      viewWidth: Double(viewWidth), viewHeight: Double(viewHeight))
            let legacy = try PlanarMetalRenderer(device: device)
            let pilot = try PlanarMetal4Renderer(device: device)
            try legacy.update(frame)
            try pilot.update(frame)

            // Correctness first: the same pixels, or the timings mean nothing.
            let legacyPixels = try legacy.renderBGRA(width: viewWidth, height: viewHeight)
            let pilotPixels = try pilot.renderBGRA(width: viewWidth, height: viewHeight)
            var differing = 0
            legacyPixels.withUnsafeBytes { a in
                pilotPixels.withUnsafeBytes { b in
                    for index in 0..<min(a.count, b.count) where a[index] != b[index] { differing += 1 }
                }
            }
            guard legacyPixels.count == pilotPixels.count, differing == 0 else {
                print("FAIL: \(name): \(differing) of \(legacyPixels.count) bytes differ between backends")
                exit(1)
            }

            // The target is created once, as the host does, so allocation is
            // not counted as submission cost on either side.
            let descriptor = MTLTextureDescriptor.texture2DDescriptor(
                pixelFormat: .bgra8Unorm, width: viewWidth, height: viewHeight, mipmapped: false)
            descriptor.storageMode = .shared
            descriptor.usage = .renderTarget
            guard let legacyTarget = device.makeTexture(descriptor: descriptor),
                  let pilotTarget = device.makeTexture(descriptor: descriptor) else {
                print("FAIL: could not allocate a render target"); exit(1)
            }

            var legacySamples: [Sample] = []
            var pilotSamples: [Sample] = []
            for iteration in 0..<(iterations + warmup) {
                autoreleasepool {
                    // Metal 3, exactly as the host submits today.
                    let start = ProcessInfo.processInfo.systemUptime
                    guard let command = legacy.queue.makeCommandBuffer() else { return }
                    try? legacy.encode(into: legacyTarget, command: command)
                    command.commit()
                    let encoded = ProcessInfo.processInfo.systemUptime
                    command.waitUntilCompleted()
                    let done = ProcessInfo.processInfo.systemUptime
                    let gpu = max(0, command.gpuEndTime - command.gpuStartTime) * 1000
                    if iteration >= warmup {
                        legacySamples.append(Sample(cpu: (encoded - start) * 1000,
                                                    wall: (done - start) * 1000, gpu: gpu))
                    }
                }
                autoreleasepool {
                    let start = ProcessInfo.processInfo.systemUptime
                    try? pilot.render(into: pilotTarget)
                    let done = ProcessInfo.processInfo.systemUptime
                    if iteration >= warmup {
                        pilotSamples.append(Sample(cpu: pilot.lastEncodeMilliseconds,
                                                   wall: (done - start) * 1000,
                                                   gpu: pilot.lastGPUMilliseconds))
                    }
                }
            }
            // Pipelined throughput: what each backend can sustain when the
            // caller does not wait for one frame before submitting the next.
            // Each in-flight frame gets its own target, so no submission writes
            // a texture another one is still reading.
            var targets: [MTLTexture] = []
            for _ in 0..<PlanarMetal4Renderer.slotCount {
                guard let texture = device.makeTexture(descriptor: descriptor) else {
                    print("FAIL: could not allocate a pipeline target"); exit(1)
                }
                targets.append(texture)
            }
            let pipelinedCount = 200

            let legacyStart = ProcessInfo.processInfo.systemUptime
            let inFlight = DispatchSemaphore(value: PlanarMetal4Renderer.slotCount)
            for index in 0..<pipelinedCount {
                inFlight.wait()
                autoreleasepool {
                    guard let command = legacy.queue.makeCommandBuffer() else { inFlight.signal(); return }
                    try? legacy.encode(into: targets[index % targets.count], command: command)
                    command.addCompletedHandler { _ in inFlight.signal() }
                    command.commit()
                }
            }
            for _ in 0..<PlanarMetal4Renderer.slotCount { inFlight.wait() }
            let legacyPipelined = (ProcessInfo.processInfo.systemUptime - legacyStart) * 1000
            // Restore the count: libdispatch traps if a semaphore is released
            // below the value it was created with.
            for _ in 0..<PlanarMetal4Renderer.slotCount { inFlight.signal() }

            let pilotStart = ProcessInfo.processInfo.systemUptime
            var issued = 0
            var finished = 0
            func issue() {
                while issued < pipelinedCount {
                    let target = targets[issued % targets.count]
                    guard let ok = try? pilot.submit(into: target, coalescing: false, completion: { _ in
                        finished += 1
                        issue()
                    }), ok else { return }
                    issued += 1
                }
            }
            issue()
            let deadline = Date().addingTimeInterval(60)
            while finished < pipelinedCount && Date() < deadline {
                RunLoop.current.run(mode: .default, before: Date().addingTimeInterval(0.001))
            }
            let pilotPipelined = (ProcessInfo.processInfo.systemUptime - pilotStart) * 1000
            guard finished == pipelinedCount else {
                print("FAIL: \(name): only \(finished) of \(pipelinedCount) pipelined frames completed")
                exit(1)
            }

            results[name] = [
                "metal3": ["cpu_ms": statistics(legacySamples.map { $0.cpu }),
                           "gpu_ms": statistics(legacySamples.map { $0.gpu }),
                           "wall_ms": statistics(legacySamples.map { $0.wall })],
                "metal4": ["cpu_ms": statistics(pilotSamples.map { $0.cpu }),
                           "gpu_ms": statistics(pilotSamples.map { $0.gpu }),
                           "wall_ms": statistics(pilotSamples.map { $0.wall })],
                "identicalBytes": true,
                "metal4_submitted": pilot.submittedCount,
                "metal4_completed": pilot.completedCount,
                "metal4_failed": pilot.failedCount,
                "metal4_coalesced": pilot.coalescedCount,
                "pipelined": ["frames": pipelinedCount,
                              "metal3_total_ms": legacyPipelined,
                              "metal4_total_ms": pilotPipelined,
                              "metal3_per_frame_ms": legacyPipelined / Double(pipelinedCount),
                              "metal4_per_frame_ms": pilotPipelined / Double(pipelinedCount)],
            ]
        }
        report["workloads"] = results
        let data = try JSONSerialization.data(withJSONObject: report, options: [.prettyPrinted, .sortedKeys])
        print(String(data: data, encoding: .utf8)!)
    }
}
'''


sources = ['VolumeAllocation.swift', 'VolumeSession.swift', 'PlanarComparison.swift',
           'PlanarMetalRenderer.swift', 'PlanarMetal4Renderer.swift']
driver = DRIVER.replace('ITERATIONS', str(arguments.iterations)).replace('WARMUP', str(arguments.warmup))

import contextlib, os
_keep = os.environ.get('HOROS_BENCH_KEEP')
with (contextlib.nullcontext(_keep) if _keep else tempfile.TemporaryDirectory(prefix='horos-planar-bench-')) as temporary:
    work = Path(temporary)
    (work / 'Benchmark.swift').write_text(driver)
    build = subprocess.run(['xcrun', 'swiftc', '-O', '-parse-as-library',
                            *[str(root / 'Horos/Sources' / name) for name in sources],
                            str(work / 'Benchmark.swift'), '-o', str(work / 'bench')],
                           capture_output=True, text=True)
    if build.returncode != 0:
        print(build.stderr[-4000:])
        raise SystemExit('the benchmark did not compile')
    compilation = {}
    for order in (['compile3', 'compile4'], ['compile4', 'compile3']):
        for mode in order:
            probe = subprocess.run([str(work / 'bench'), mode], capture_output=True, text=True, timeout=300)
            if probe.returncode == 2:
                print(probe.stdout.strip())
                raise SystemExit(2)
            probe.check_returncode()
            record = json.loads(probe.stdout.strip())
            compilation.setdefault(record['backend'], []).append(
                dict(record, position=order.index(mode) + 1))
    run = subprocess.run([str(work / 'bench')], capture_output=True, text=True, timeout=900)
    output = (run.stdout + run.stderr).strip()
    if run.returncode == 2:
        print(output)
        raise SystemExit(2)
    if run.returncode != 0:
        print(output or '(no output)')
        print('stdout bytes:', len(run.stdout), 'stderr bytes:', len(run.stderr))
        raise SystemExit('the benchmark failed with code %d' % run.returncode)

report = json.loads(output)
report['compilation'] = compilation
output = json.dumps(report, indent=2, sort_keys=True)
print(output)
if arguments.json:
    arguments.json.parent.mkdir(parents=True, exist_ok=True)
    arguments.json.write_text(output + '\n')
    print('\nwrote', arguments.json, file=sys.stderr)
