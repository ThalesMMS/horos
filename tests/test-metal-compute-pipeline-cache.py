#!/usr/bin/env python3
"""MPR and VR engines share compute pipelines compiled once per device and configuration (#622).

Builds Horos/Sources/MetalComputePipelineCache.swift with the MPR and VR engines and a driver that counts the
cache's compilations, attempts and hits:

  * two MPR engines: one compilation, one hit, the same pipeline object, the same pixels;
  * VR's four option combinations (hardware filtering, as the device resolves it, and empty-space skipping):
    one compilation each, pipelines apart; four more engines only hit, each drawing what the engine that
    compiled drew, and what an engine compiling afresh after the cache is emptied draws;
  * a source that does not compile, and a function the source lacks: each request fails and the next one
    compiles again, so a failure is never served from the cache;
  * eight MPR engines made at once on eight threads after the cache is emptied: one compilation, seven hits,
    one pipeline;
  * an engine and its volume are freed while their pipelines stay cached.

Exit 2 (skipped) without swiftc or a Metal device.
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]

DRIVER = r'''
import Foundation
import Metal
import simd

func counts() -> [Int] { [MetalComputePipelineCache.compilations, MetalComputePipelineCache.attempts, MetalComputePipelineCache.hits] }
func delta(_ before: [Int]) -> [Int] { zip(counts(), before).map { $0 - $1 } }

@main
struct Check {
    static func main() throws {
        guard let device = MTLCreateSystemDefaultDevice() else { exit(2) }
        var result: [String: Any] = ["floatFiltering": device.supports32BitFloatFiltering]
        let (w, h, d) = (24, 20, 16)
        var voxels = Data(count: w * h * d * 4)
        voxels.withUnsafeMutableBytes { raw in
            let floats = raw.bindMemory(to: Float.self)
            for k in 0..<d { for j in 0..<h { for i in 0..<w { floats[(k * h + j) * w + i] = Float((i * 7 + j * 3 + k * 11) % 23) * 10 } } }
        }
        let volume = try ResliceVolume(width: w, height: h, depth: d, voxels: voxels, voxelToWorld: matrix_identity_float4x4)
        let plane = try ReslicePlane(origin: SIMD3(0.5, 0.25, 7.5), rowStep: SIMD3(0.9, 0.1, 0), columnStep: SIMD3(0, 1, 0.2),
                                     width: 23, height: 19, thickness: 3, sampleStep: 0.5, projection: .mean, background: -1)

        // Two MPR engines.
        var before = counts()
        let first = try MPRMetalReslicer(device: device), second = try MPRMetalReslicer(device: device)
        result["mprTwo"] = delta(before)
        result["mprSamePipeline"] = first.pipeline === second.pipeline
        try first.upload(volume); try second.upload(volume)
        result["mprSamePixels"] = try first.reslice(plane) == second.reslice(plane)

        // VR's four combinations, compiled once each, then served.
        let camera = try VolumeCamera(position: SIMD3(11.5, 9.5, -40), focalPoint: SIMD3(11.5, 9.5, 7.5), viewUp: SIMD3(0.2, 1, 0),
                                      parallel: true, parallelScale: 14, viewAngle: 30, clippingRange: nil)
        var colour = Data(count: 1024)
        colour.withUnsafeMutableBytes { raw in for i in 0..<256 { raw[i * 4] = UInt8(i); raw[i * 4 + 1] = UInt8(255 - i); raw[i * 4 + 3] = 255 } }
        let transfer = try VolumeTransferFunction(level: 110, width: 220, colour: colour,
                                                  opacity: VolumeTransferFunction.opacityTable(points: [SIMD2(0, 0), SIMD2(90, 0), SIMD2(256, 0.7)]))
        func picture(_ renderer: VolumeMetalRenderer, _ mode: VolumeRenderingMode) throws -> Data {
            let request = try VolumeRenderRequest(camera: camera, transfer: transfer, mode: mode, shading: VolumeShading(enabled: true),
                                                  crop: nil, width: 29, height: 23, sampleStep: 0.5)
            let rendered = try renderer.render(request)
            return rendered.bgra + rendered.scalar
        }
        let combinations = [(true, true), (true, false), (false, true), (false, false)]
        before = counts()
        var compiledEngines = [VolumeMetalRenderer]()
        for (filtering, skipping) in combinations {
            compiledEngines.append(try VolumeMetalRenderer(device: device, hardwareFiltering: filtering, emptySpaceSkipping: skipping))
        }
        result["vrFirstFour"] = delta(before)
        before = counts()
        var servedEngines = [VolumeMetalRenderer]()
        for (filtering, skipping) in combinations {
            servedEngines.append(try VolumeMetalRenderer(device: device, hardwareFiltering: filtering, emptySpaceSkipping: skipping))
        }
        result["vrSecondFour"] = delta(before)
        result["vrPipelinesShared"] = zip(compiledEngines, servedEngines).map { $0.pipeline === $1.pipeline }
        result["vrDistinctPipelines"] = Set(compiledEngines.map { ObjectIdentifier($0.pipeline) }).count
        var samePictures = true
        for (compiled, served) in zip(compiledEngines, servedEngines) {
            try compiled.upload(volume); try served.upload(volume)
            for mode in [VolumeRenderingMode.composite, .maximum] where try picture(compiled, mode) != picture(served, mode) { samePictures = false }
        }
        MetalComputePipelineCache.removeAll()
        before = counts()
        for (index, (filtering, skipping)) in combinations.enumerated() {
            let recompiled = try VolumeMetalRenderer(device: device, hardwareFiltering: filtering, emptySpaceSkipping: skipping)
            try recompiled.upload(volume)
            for mode in [VolumeRenderingMode.composite, .maximum] where try picture(recompiled, mode) != picture(compiledEngines[index], mode) { samePictures = false }
        }
        result["vrRecompiled"] = delta(before)
        result["vrSamePictures"] = samePictures

        // Failures are not cached.
        func attempt(_ configuration: MetalComputePipelineCache.Configuration) -> String {
            do { _ = try MetalComputePipelineCache.pipelines(device: device, configuration: configuration); return "compiled" }
            catch { return "\(error)" }
        }
        let broken = MetalComputePipelineCache.Configuration(source: "kernel void broken(uint i [[thread_position_in_grid]]) { undeclared(); }",
                                                             functions: ["broken"])
        let absent = MetalComputePipelineCache.Configuration(source: "kernel void present(uint i [[thread_position_in_grid]]) {}",
                                                             functions: ["absent"])
        before = counts()
        result["brokenFirst"] = attempt(broken)
        result["brokenAgain"] = attempt(broken)
        result["absentFirst"] = attempt(absent)
        result["absentAgain"] = attempt(absent)
        result["failures"] = delta(before)

        // Eight engines at once.
        MetalComputePipelineCache.removeAll()
        before = counts()
        let lock = NSLock()
        var concurrent = [MPRMetalReslicer?](repeating: nil, count: 8)
        DispatchQueue.concurrentPerform(iterations: 8) { index in
            let engine = try? MPRMetalReslicer(device: device)
            lock.withLock { concurrent[index] = engine }
        }
        result["concurrent"] = delta(before)
        result["concurrentPipelines"] = Set(concurrent.compactMap { $0.map { ObjectIdentifier($0.pipeline) } }).count
        result["concurrentEngines"] = concurrent.compactMap { $0 }.count

        // The cache holds no engine and no volume.
        weak var freedEngine: MPRMetalReslicer?
        weak var freedVolume: NSData?
        try autoreleasepool {
            let engine = try MPRMetalReslicer(device: device)
            let bytes = NSData(data: voxels)
            try engine.upload(try ResliceVolume(width: w, height: h, depth: d, voxels: bytes as Data, voxelToWorld: matrix_identity_float4x4))
            _ = try engine.reslice(plane)
            freedEngine = engine
            freedVolume = bytes
        }
        result["engineFreed"] = freedEngine == nil
        result["volumeFreed"] = freedVolume == nil

        FileHandle.standardOutput.write(try JSONSerialization.data(withJSONObject: result))
    }
}
'''


def main():
    if subprocess.run(["xcrun", "--find", "swiftc"], capture_output=True).returncode != 0:
        print("skipped: needs swiftc")
        return 2
    sources = ["VolumeAllocation.swift", "VolumeSession.swift", "MPRMetalReslicer.swift", "VolumeMetalRenderer.swift",
               "MetalPerformanceTrace.swift", "MetalComputePipelineCache.swift",
               "Metal4ComputeSubmitter.swift"]
    with tempfile.TemporaryDirectory(prefix="horos-pipeline-cache-") as directory:
        work = Path(directory)
        (work / "Check.swift").write_text(DRIVER)
        subprocess.run(["xcrun", "swiftc", "-O", "-parse-as-library", "-suppress-warnings",
                        *[str(root / "Horos/Sources" / name) for name in sources], str(work / "Check.swift"),
                        "-o", str(work / "check")], check=True)
        run = subprocess.run([str(work / "check")], capture_output=True, timeout=300)
        if run.returncode == 2:
            print("skipped: no Metal device")
            return 2
        if run.returncode != 0:
            sys.stderr.write(run.stderr.decode(errors="replace"))
            raise SystemExit(f"driver failed with {run.returncode}")
        r = json.loads(run.stdout)

    failures = []

    def check(condition, message):
        if not condition:
            failures.append(message)

    # counts are [compilations, attempts, hits]
    check(r["mprTwo"] == [1, 1, 1], f"two MPR engines: {r['mprTwo']} compilations/attempts/hits, expected [1, 1, 1]")
    check(r["mprSamePipeline"], "the second MPR engine did not get the first one's pipeline")
    check(r["mprSamePixels"], "two MPR engines sharing a pipeline resliced different pixels")
    kinds = 4 if r["floatFiltering"] else 2
    check(r["vrFirstFour"] == [kinds, kinds, 4 - kinds],
          f"VR's four combinations: {r['vrFirstFour']}, expected [{kinds}, {kinds}, {4 - kinds}]")
    check(r["vrSecondFour"] == [0, 0, 4], f"four more VR engines: {r['vrSecondFour']}, expected only hits")
    check(all(r["vrPipelinesShared"]), f"a served VR engine did not get its combination's pipeline: {r['vrPipelinesShared']}")
    check(r["vrDistinctPipelines"] == kinds, f"{r['vrDistinctPipelines']} distinct VR pipelines for {kinds} configurations")
    check(r["vrRecompiled"] == [kinds, kinds, 4 - kinds], f"VR after emptying the cache: {r['vrRecompiled']}")
    check(r["vrSamePictures"], "a VR engine drew differently with a served or a recompiled pipeline")
    check("compiled" not in (r["brokenFirst"], r["brokenAgain"], r["absentFirst"], r["absentAgain"]),
          "a source that does not compile, or a missing function, was accepted")
    check("absent is missing" in r["absentFirst"] and "absent is missing" in r["absentAgain"],
          f"a missing function was not named: {r['absentFirst'][:120]}")
    check(r["failures"] == [0, 4, 0], f"failed requests: {r['failures']}, expected four attempts and nothing cached")
    check(r["concurrent"] == [1, 1, 7] and r["concurrentPipelines"] == 1 and r["concurrentEngines"] == 8,
          f"eight engines at once: {r['concurrent']}, {r['concurrentPipelines']} pipelines, {r['concurrentEngines']} engines")
    check(r["engineFreed"] and r["volumeFreed"], "the cache kept an engine or a volume alive")

    for failure in failures:
        print("FAIL:", failure)
    if failures:
        return 1
    print(f"metal compute pipeline cache: shared by equal engines, apart by configuration ({kinds} VR kinds), "
          "failures retried, one compilation for eight engines at once, nothing retained")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
