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

`--opacity-table` measures instead what a frame change costs the backend in use
(#657): `update()` and one render of a PET-sized scalar frame, without an
opacity table and with the menu's logarithmic one, interleaved, at the host's
software enlargements. The table adds a compute pass to `update()`.

`--filter` measures the same with and without the menu's *Sharpen 5x5*
convolution filter (#661), which adds its own compute pass to `update()`.

`--host-bytes` measures the same from the float samples (A) and from the host's
own 8-bit presentation (B), which subtraction and the DICOM shutter hand over
(#662): no compute pass, one byte per pixel to upload.

`--fusion` measures a frame change of a CT-sized image alone (A), of the same
image with a PET-sized series fused over it (B), with the logarithmic opacity
table a PET opens with, at the host's software enlargements, and of the fusion
factor moving (C): only the fused alpha column changes, so the image's textures
are kept (#658).

`--colour` measures a frame change of a colour image drawn as the previous
colour path drew it, its ARGB samples windowed after interpolation (A), as the
host's windowed bytes under its table (B), and the same bytes enlarged in
software as the host enlarges them (C) (#660).
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
parser.add_argument('--opacity-table', action='store_true', help='measure the frame-change cost with and without an opacity table (#657)')
parser.add_argument('--filter', action='store_true', help='measure the frame-change cost with and without a 5x5 convolution filter (#661)')
parser.add_argument('--host-bytes', action='store_true', help='measure the frame-change cost from float samples and from the host\'s bytes (#662)')
parser.add_argument('--fusion', action='store_true', help='measure the frame-change cost with and without a fused series, and of the fusion factor (#658)')
parser.add_argument('--colour', action='store_true', help='measure the frame-change cost of a colour image, from its samples and from the host\'s tabled bytes, and enlarged (#660)')
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
        if CommandLine.arguments.contains("colour") {
            // #660: update() and one render of a colour image, a new frame on
            // every sample: its ARGB samples windowed after interpolation (A),
            // the host's bytes under its table (B), and those enlarged (C).
            var identity = [UInt8]()
            for index in 0..<256 { identity += [UInt8(index), UInt8(index), UInt8(index), 255] }
            var tables = [UInt8](repeating: 255, count: 1024)
            for index in 0..<256 {
                tables[256 + index] = UInt8(Float(index) * 0.8); tables[512 + index] = UInt8(index); tables[768 + index] = UInt8(255 - index)
            }
            let descriptor = MTLTextureDescriptor.texture2DDescriptor(
                pixelFormat: .bgra8Unorm, width: 800, height: 800, mipmapped: false)
            descriptor.storageMode = .shared
            descriptor.usage = .renderTarget
            guard let target = device.makeTexture(descriptor: descriptor) else {
                print("FAIL: could not allocate a render target"); exit(1)
            }
            var workloads: [String: Any] = [:]
            for (width, scale) in [(256, 3), (512, 2)] {
                let bytes = Data((0..<(width * width * 4)).map { UInt8(truncatingIfNeeded: $0 * 7919) })
                func frame(_ kind: String, serial: Int) throws -> PlanarFrame {
                    let snapshot: NSMutableDictionary = [
                        "width": width, "height": width, "pixels": bytes, "clut": Data(identity), "isColor": true,
                        "frameIdentity": "\(kind)-\(serial)",
                        "screenToPixel": [0.0, 0.0, Double(width), 0.0, 0.0, Double(width)],
                        "viewSize": [800.0, 800.0], "level": 127.5, "widthWindow": 255.0,
                        "softwareScale": kind == "enlarged" ? scale : 1]
                    if kind != "samples" { snapshot["hostBytes"] = bytes; snapshot["colourTable"] = Data(tables) }
                    return try PlanarFrame(snapshot)
                }
                let renderer = try PlanarMetalRenderer(device: device)
                var samples: [String: [Sample]] = ["samples": [], "bytes": [], "enlarged": []]
                for iteration in 0..<(iterations + warmup) {
                    let order = [["samples", "bytes", "enlarged"], ["bytes", "enlarged", "samples"], ["enlarged", "samples", "bytes"]][iteration % 3]
                    for kind in order {
                        let next = try frame(kind, serial: iteration)
                        try autoreleasepool {
                            let start = ProcessInfo.processInfo.systemUptime
                            try renderer.update(next)
                            let updated = ProcessInfo.processInfo.systemUptime
                            guard let command = renderer.queue.makeCommandBuffer() else { throw PlanarMetalRenderer.failure() }
                            try renderer.encode(into: target, command: command)
                            command.commit()
                            command.waitUntilCompleted()
                            let done = ProcessInfo.processInfo.systemUptime
                            let sample = Sample(cpu: (updated - start) * 1000, wall: (done - start) * 1000,
                                                gpu: max(0, command.gpuEndTime - command.gpuStartTime) * 1000)
                            if iteration >= warmup { samples[kind]!.append(sample) }
                        }
                    }
                }
                var entry: [String: Any] = [:]
                for (kind, values) in samples {
                    entry[kind] = ["update_ms": statistics(values.map { $0.cpu }), "wall_ms": statistics(values.map { $0.wall }),
                                   "gpu_ms": statistics(values.map { $0.gpu })]
                }
                let a = statistics(samples["samples"]!.map { $0.wall })["median"]!
                entry["bytes_minus_samples_ms"] = statistics(samples["bytes"]!.map { $0.wall })["median"]! - a
                entry["enlarged_minus_samples_ms"] = statistics(samples["enlarged"]!.map { $0.wall })["median"]! - a
                workloads["colour-\(width)-x\(scale)"] = entry
            }
            report["colour"] = workloads
            print(String(data: try JSONSerialization.data(withJSONObject: report, options: [.prettyPrinted, .sortedKeys]),
                         encoding: .utf8)!)
            return
        }
        if CommandLine.arguments.contains("fusion") {
            // #658: update() and one render of an image alone (A), of the image
            // with a fused series (B), both new on every sample as while
            // scrolling, and of the fusion factor moving (C), which changes the
            // fused alpha column only. A, B and C rotate their order.
            let curve = (0..<4096).map { Float(log10(1 + Double($0) / 4095 * 9)) }
            let table = curve.withUnsafeBytes { Data($0) }
            var clut = [UInt8]()
            for index in 0..<256 { clut += [UInt8(index), UInt8(255 - index), UInt8((index * 3) % 256), 255] }
            func fusedCLUT(_ factor: Int) -> Data {
                var entries = [UInt8]()
                for index in 0..<256 { entries += [UInt8(index), UInt8((index * 5) % 256), UInt8(255 - index), UInt8((index * factor) % 256)] }
                return Data(entries)
            }
            let descriptor = MTLTextureDescriptor.texture2DDescriptor(
                pixelFormat: .bgra8Unorm, width: 800, height: 800, mipmapped: false)
            descriptor.storageMode = .shared
            descriptor.usage = .renderTarget
            guard let target = device.makeTexture(descriptor: descriptor) else {
                print("FAIL: could not allocate a render target"); exit(1)
            }
            var workloads: [String: Any] = [:]
            for (width, scale, fusedWidth, fusedScale) in [(512, 1, 168, 3), (512, 2, 168, 3), (256, 1, 128, 3)] {
                let pixels = (0..<(width * width)).map { Float(($0 * 7919) % 3000) - 1000 }.withUnsafeBytes { Data($0) }
                let fusedPixels = (0..<(fusedWidth * fusedWidth)).map { Float(($0 * 7919) % 20000) }.withUnsafeBytes { Data($0) }
                func frame(fused: Bool, serial: Int, factor: Int) throws -> PlanarFrame {
                    // A and B never share an image identity: each prepares its image.
                    let snapshot: NSMutableDictionary = [
                        "width": width, "height": width, "pixels": pixels, "clut": Data(clut),
                        "frameIdentity": "image-\(fused)-\(serial)",
                        "screenToPixel": [0.0, 0.0, Double(width), 0.0, 0.0, Double(width)],
                        "viewSize": [800.0, 800.0], "level": 40.0, "widthWindow": 400.0, "softwareScale": scale]
                    if fused {
                        snapshot["fusion"] = [
                            "width": fusedWidth, "height": fusedWidth, "pixels": fusedPixels, "clut": fusedCLUT(factor),
                            "frameIdentity": "fused-\(serial)",
                            "screenToPixel": [-10.0, -10.0, Double(fusedWidth) + 10, -10.0, -10.0, Double(fusedWidth) + 10],
                            "viewSize": [800.0, 800.0], "level": 3000.0, "widthWindow": 8000.0, "softwareScale": fusedScale,
                            "transferFunction": table, "transferLevel": 3000.0, "transferWidth": 8000.0] as NSDictionary
                    }
                    return try PlanarFrame(snapshot)
                }
                let renderer = try PlanarMetalRenderer(device: device)
                var samples: [String: [Sample]] = ["alone": [], "fused": [], "factor": []]
                var factorFrame = try frame(fused: true, serial: -1, factor: 1)
                try renderer.update(factorFrame)
                for iteration in 0..<(iterations + warmup) {
                    let order = [["alone", "fused", "factor"], ["fused", "factor", "alone"], ["factor", "alone", "fused"]][iteration % 3]
                    for kind in order {
                        let next: PlanarFrame
                        switch kind {
                        case "alone": next = try frame(fused: false, serial: iteration, factor: 1)
                        case "fused": next = try frame(fused: true, serial: iteration, factor: 1)
                        default:
                            // The same image and fused series as last time, another alpha column.
                            try renderer.update(factorFrame)
                            factorFrame = try frame(fused: true, serial: -1, factor: 2 + iteration % 200)
                            next = factorFrame
                        }
                        try autoreleasepool {
                            let start = ProcessInfo.processInfo.systemUptime
                            try renderer.update(next)
                            let updated = ProcessInfo.processInfo.systemUptime
                            guard let command = renderer.queue.makeCommandBuffer() else { throw PlanarMetalRenderer.failure() }
                            try renderer.encode(into: target, command: command)
                            command.commit()
                            command.waitUntilCompleted()
                            let done = ProcessInfo.processInfo.systemUptime
                            let sample = Sample(cpu: (updated - start) * 1000, wall: (done - start) * 1000,
                                                gpu: max(0, command.gpuEndTime - command.gpuStartTime) * 1000)
                            if iteration >= warmup { samples[kind]!.append(sample) }
                        }
                    }
                }
                var entry: [String: Any] = [:]
                for (kind, values) in samples {
                    entry[kind] = ["update_ms": statistics(values.map { $0.cpu }), "wall_ms": statistics(values.map { $0.wall }),
                                   "gpu_ms": statistics(values.map { $0.gpu })]
                }
                let alone = statistics(samples["alone"]!.map { $0.wall })["median"]!
                entry["fused_minus_alone_ms"] = statistics(samples["fused"]!.map { $0.wall })["median"]! - alone
                entry["factor_minus_alone_ms"] = statistics(samples["factor"]!.map { $0.wall })["median"]! - alone
                workloads["image-\(width)-x\(scale)-fused-\(fusedWidth)-x\(fusedScale)"] = entry
            }
            report["fusion"] = workloads
            print(String(data: try JSONSerialization.data(withJSONObject: report, options: [.prettyPrinted, .sortedKeys]),
                         encoding: .utf8)!)
            return
        }
        if CommandLine.arguments.contains("table") || CommandLine.arguments.contains("filter") || CommandLine.arguments.contains("bytes") {
            // #657: update() and one render, the cost the host pays when a
            // frame changes, without (A) and with (B) an opacity table - or,
            // for #661, the menu's Sharpen 5x5 filter. A and B alternate in
            // both orders; each sample is a new frame identity, so update()
            // always prepares, as it does while scrolling.
            let filtering = CommandLine.arguments.contains("filter")
            let presenting = CommandLine.arguments.contains("bytes")
            var sharpen: [Float] = [-1, -1, -1, -1, -1, -1, 2, 2, 2, -1, -1, 2, 8, 2, -1, -1, 2, 2, 2, -1, -1, -1, -1, -1, -1]
            let curve = (0..<4096).map { Float(log10(1 + Double($0) / 4095 * 9)) }
            let table = curve.withUnsafeBytes { Data($0) }
            var clut = [UInt8]()
            for index in 0..<256 { clut += [UInt8(index), UInt8(255 - index), UInt8((index * 3) % 256), 255] }
            let descriptor = MTLTextureDescriptor.texture2DDescriptor(
                pixelFormat: .bgra8Unorm, width: 800, height: 800, mipmapped: false)
            descriptor.storageMode = .shared
            descriptor.usage = .renderTarget
            guard let target = device.makeTexture(descriptor: descriptor) else {
                print("FAIL: could not allocate a render target"); exit(1)
            }
            var workloads: [String: Any] = [:]
            for (width, scale) in [(168, 1), (168, 3), (256, 1), (256, 3), (512, 1), (512, 2)] {
                let values = (0..<(width * width)).map { Float(($0 * 7919) % 20000) }
                let pixels = values.withUnsafeBytes { Data($0) }
                let presented = Data((0..<(width * width)).map { UInt8(truncatingIfNeeded: $0 * 7919) })
                func frame(_ withTable: Bool, _ serial: Int) throws -> PlanarFrame {
                    let snapshot: NSMutableDictionary = [
                        "width": width, "height": width, "pixels": pixels, "clut": Data(clut),
                        "frameIdentity": "table-\(withTable)-\(serial)",
                        "screenToPixel": [0.0, 0.0, Double(width), 0.0, 0.0, Double(width)],
                        "viewSize": [800.0, 800.0], "level": 3000.0, "widthWindow": 8000.0,
                        "softwareScale": scale]
                    if withTable && presenting {
                        snapshot["hostBytes"] = presented
                    } else if withTable && filtering {
                        snapshot["convolutionSize"] = 5
                        snapshot["convolutionKernel"] = Data(bytes: &sharpen, count: 25 * 4)
                        snapshot["convolutionNormalization"] = 8.0
                    } else if withTable {
                        snapshot["transferFunction"] = table
                        snapshot["transferLevel"] = 3000.0; snapshot["transferWidth"] = 8000.0
                    }
                    return try PlanarFrame(snapshot)
                }
                let renderer = try PlanarMetalRenderer(device: device)
                var without: [Sample] = [], with: [Sample] = []
                for iteration in 0..<(iterations + warmup) {
                    for withTable in (iteration % 2 == 0 ? [false, true] : [true, false]) {
                        let next = try frame(withTable, iteration)
                        try autoreleasepool {
                            let start = ProcessInfo.processInfo.systemUptime
                            try renderer.update(next)
                            let updated = ProcessInfo.processInfo.systemUptime
                            guard let command = renderer.queue.makeCommandBuffer() else { throw PlanarMetalRenderer.failure() }
                            try renderer.encode(into: target, command: command)
                            command.commit()
                            command.waitUntilCompleted()
                            let done = ProcessInfo.processInfo.systemUptime
                            let sample = Sample(cpu: (updated - start) * 1000, wall: (done - start) * 1000,
                                                gpu: max(0, command.gpuEndTime - command.gpuStartTime) * 1000)
                            if iteration >= warmup { if withTable { with.append(sample) } else { without.append(sample) } }
                        }
                    }
                }
                let a = statistics(without.map { $0.wall }), b = statistics(with.map { $0.wall })
                let extra = presenting ? "host_bytes" : filtering ? "filter" : "table"
                workloads["pet-\(width)-x\(scale)"] = [
                    "without_\(extra)": ["update_ms": statistics(without.map { $0.cpu }), "wall_ms": a,
                                         "gpu_ms": statistics(without.map { $0.gpu })],
                    "with_\(extra)": ["update_ms": statistics(with.map { $0.cpu }), "wall_ms": b,
                                      "gpu_ms": statistics(with.map { $0.gpu })],
                    "median_difference_ms": b["median"]! - a["median"]!]
            }
            report[presenting ? "hostBytes" : filtering ? "convolutionFilter" : "opacityTable"] = workloads
            print(String(data: try JSONSerialization.data(withJSONObject: report, options: [.prettyPrinted, .sortedKeys]),
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
           'PlanarMetalRenderer.swift', 'PlanarMetal4Renderer.swift', 'MetalPerformanceTrace.swift',
           'MPRMetalReslicer.swift', 'MetalComputePipelineCache.swift', 'Metal4ComputeSubmitter.swift']
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
    if arguments.opacity_table or arguments.filter or arguments.host_bytes or arguments.fusion or arguments.colour:
        mode = 'colour' if arguments.colour else 'fusion' if arguments.fusion else 'bytes' if arguments.host_bytes else 'filter' if arguments.filter else 'table'
        run = subprocess.run([str(work / 'bench'), mode],
                             capture_output=True, text=True, timeout=900)
        if run.returncode == 2:
            print(run.stdout.strip())
            raise SystemExit(2)
        if run.returncode != 0:
            print((run.stdout + run.stderr).strip() or '(no output)')
            raise SystemExit('the benchmark failed with code %d' % run.returncode)
        output = json.dumps(json.loads(run.stdout), indent=2, sort_keys=True)
        print(output)
        if arguments.json:
            arguments.json.parent.mkdir(parents=True, exist_ok=True)
            arguments.json.write_text(output + '\n')
        raise SystemExit(0)
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
