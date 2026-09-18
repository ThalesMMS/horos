#!/usr/bin/env python3
"""Metal operations say where their time went, and only when asked (#619).

Builds the MPR reslicer, the volume renderer and MetalPerformanceTrace.swift as
the app has them, and drives them on a synthetic volume twice:

- without -HorosMetalPerformanceTrace: pipelines, uploads, reslices and renders
  leave no sample, and the entry points cost nanoseconds;
- with -HorosMetalPerformanceTrace YES: every operation leaves one sample with
  its name; a reslice and a render carry every phase - CPU preparation, commit
  to GPU start, GPU, wait, GPU end to observed, readback - each a non-negative
  number, the wait covering the GPU time, the phases adding up to no more than
  the total; pipelines and uploads say what they are; a Metal 4 feedback without
  timestamps gives null GPU phases, not zero; the buffer keeps the last 4096
  samples and counts the ones it dropped; a snapshot holds names and numbers
  only.

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

@main
struct Check {
    static func main() throws {
        guard let device = MTLCreateSystemDefaultDevice() else { exit(2) }
        let traced = CommandLine.arguments.contains("-HorosMetalPerformanceTrace")
        var result: [String: Any] = ["enabled": MetalPerformanceTrace.enabled]

        let (w, h, d) = (48, 40, 32)
        var voxels = Data(count: w * h * d * 4)
        voxels.withUnsafeMutableBytes { raw in
            let floats = raw.bindMemory(to: Float.self)
            for k in 0..<d { for j in 0..<h { for i in 0..<w { floats[(k * h + j) * w + i] = Float((i + j + k) % 17) * 10 } } }
        }
        let volume = try ResliceVolume(width: w, height: h, depth: d, voxels: voxels, voxelToWorld: matrix_identity_float4x4)
        let reslicer = try MPRMetalReslicer(device: device)
        try reslicer.upload(volume)
        let plane = try ReslicePlane(origin: SIMD3(0, 0, 15), rowStep: SIMD3(1, 0, 0), columnStep: SIMD3(0, 1, 0),
                                     width: 256, height: 192, thickness: 4, sampleStep: 1, projection: .maximum, background: 0)
        for _ in 0..<20 { _ = try reslicer.reslice(plane) }

        let renderer = try VolumeMetalRenderer(device: device)
        try renderer.upload(volume)
        var colour = Data(count: 1024)
        colour.withUnsafeMutableBytes { raw in for i in 0..<256 { raw[i * 4] = UInt8(i); raw[i * 4 + 3] = 255 } }
        let transfer = try VolumeTransferFunction(level: 80, width: 160, colour: colour, opacity: (0..<256).map { Float($0) / 255 })
        let camera = try VolumeCamera(position: SIMD3(24, 20, -100), focalPoint: SIMD3(24, 20, 16), viewUp: SIMD3(0, 1, 0),
                                      parallel: true, parallelScale: 30, viewAngle: 30, clippingRange: nil)
        let request = try VolumeRenderRequest(camera: camera, transfer: transfer, mode: .composite, shading: VolumeShading(enabled: true),
                                              crop: nil, width: 192, height: 160, sampleStep: 1)
        for _ in 0..<10 { _ = try renderer.render(request) }

        // A frame the original renderer drew, with its fixed reason (#664).
        MetalPerformanceTrace.recordRefusal("vr.refusal", reason: "The crop uses the original renderer.")

        // A Metal 4 feedback that carried no timestamps.
        let start = MetalPerformanceTrace.now()
        MetalPerformanceTrace.record("check.metal4.untimed", startedAt: start, committedAt: MetalPerformanceTrace.now(),
                                     observedAt: MetalPerformanceTrace.now(), gpuStartTime: 0, gpuEndTime: 0, failed: false)

        if traced {
            let before = (MetalPerformanceTrace.snapshot()["samples"] as! [[String: Any]]).count
            for _ in 0..<(MetalPerformanceTrace.capacity + 100) {
                MetalPerformanceTrace.record("check.host", startedAt: MetalPerformanceTrace.now())
            }
            result["before_fill"] = before
        }
        let snapshot = MetalPerformanceTrace.snapshot()
        let samples = snapshot["samples"] as! [[String: Any]]
        result["dropped"] = snapshot["dropped"]
        result["count"] = samples.count
        // The operation samples, before the buffer was filled with host checks.
        result["samples"] = traced ? [] : samples
        if traced {
            // Refill from a clean buffer, so the samples of the operations are kept.
            MetalPerformanceTrace.reset()
            // Since #622 an engine compiles only what no engine compiled before: after the cache is emptied the
            // first MPR engine compiles and the second finds its pipelines.
            MetalComputePipelineCache.removeAll()
            _ = try MPRMetalReslicer(device: device)
            _ = try MPRMetalReslicer(device: device)
            try reslicer.upload(volume)
            for _ in 0..<20 { _ = try reslicer.reslice(plane) }
            _ = try VolumeMetalRenderer(device: device)
            try renderer.upload(volume)
            for _ in 0..<10 { _ = try renderer.render(request) }
            MetalPerformanceTrace.record("check.metal4.untimed", startedAt: MetalPerformanceTrace.now(),
                                         committedAt: MetalPerformanceTrace.now(), observedAt: MetalPerformanceTrace.now(),
                                         gpuStartTime: 0, gpuEndTime: 0, failed: false)
            MetalPerformanceTrace.recordRefusal("vr.refusal", reason: "The crop uses the original renderer.")
            result["samples"] = MetalPerformanceTrace.snapshot()["samples"]
        }

        // The entry points' cost when the trace is off.
        if !traced {
            let n = 2_000_000
            let t0 = DispatchTime.now().uptimeNanoseconds
            for _ in 0..<n {
                let s = MetalPerformanceTrace.now()
                MetalPerformanceTrace.record("off", startedAt: s, extra: ["unused": 1])
            }
            result["off_ns_per_call"] = Double(DispatchTime.now().uptimeNanoseconds - t0) / Double(n)
        }
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
    failures = []
    with tempfile.TemporaryDirectory(prefix="horos-metal-trace-") as directory:
        work = Path(directory)
        (work / "Check.swift").write_text(DRIVER)
        subprocess.run(["xcrun", "swiftc", "-O", "-parse-as-library", "-suppress-warnings",
                        *[str(root / "Horos/Sources" / name) for name in sources], str(work / "Check.swift"),
                        "-o", str(work / "check")], check=True)
        runs = {}
        for label, arguments in (("off", []), ("on", ["-HorosMetalPerformanceTrace", "YES"])):
            run = subprocess.run([str(work / "check"), *arguments], capture_output=True, timeout=300)
            if run.returncode == 2:
                print("skipped: no Metal device")
                return 2
            if run.returncode:
                sys.stderr.write(run.stderr.decode(errors="replace"))
                return 1
            runs[label] = json.loads(run.stdout)

    off, on = runs["off"], runs["on"]
    if off["enabled"] or off["count"] != 0:
        failures.append(f"off: enabled {off['enabled']}, {off['count']} samples kept")
    if off["off_ns_per_call"] > 20:
        failures.append(f"off: an entry point costs {off['off_ns_per_call']:.1f} ns")
    if not on["enabled"]:
        failures.append("on: the default did not enable the trace")
    if on["count"] != 4096 or on["dropped"] != on["before_fill"] + 100:
        failures.append(f"on: the buffer holds {on['count']} and dropped {on['dropped']} "
                        f"(expected 4096 and {on['before_fill'] + 100})")

    samples = on["samples"]
    by_operation = {}
    for sample in samples:
        by_operation.setdefault(sample["operation"], []).append(sample)
        allowed = {"operation", "status", "cold", "bytes", "width", "height", "samples", "cpu_prepare_ms", "submit_to_gpu_ms",
                   "gpu_ms", "wait_ms", "gpu_to_observed_ms", "readback_ms", "total_ms"}
        # A refusal carries the host's fixed fallback text, and nothing else is added (#664).
        if sample["operation"].endswith(".refusal"):
            allowed = allowed | {"reason"}
        if set(sample) - allowed:
            failures.append(f"a sample carries {sorted(set(sample) - allowed)}")
    expected = {"mpr.pipeline": 2, "mpr.upload": 1, "mpr.reslice": 20, "vr.pipeline": 1, "vr.upload": 1, "vr.render": 10,
                "check.metal4.untimed": 1, "vr.refusal": 1}
    for operation, count in expected.items():
        if len(by_operation.get(operation, [])) != count:
            failures.append(f"{len(by_operation.get(operation, []))} {operation} samples, expected {count}")
    if [r.get("reason") for r in by_operation.get("vr.refusal", [])] != ["The crop uses the original renderer."]:
        failures.append(f"the refusal did not keep its reason: {by_operation.get('vr.refusal')}")
    phases = ("cpu_prepare_ms", "submit_to_gpu_ms", "gpu_ms", "wait_ms", "gpu_to_observed_ms", "readback_ms", "total_ms")
    for operation in ("mpr.reslice", "vr.render", "vr.upload"):
        for sample in by_operation.get(operation, []):
            values = {phase: sample.get(phase) for phase in phases}
            if any(not isinstance(v, (int, float)) or v < 0 for v in values.values()) or sample["status"] != "completed":
                failures.append(f"{operation}: a phase is missing or negative: {values}")
                break
            if values["wait_ms"] + 0.05 < values["gpu_ms"]:
                failures.append(f"{operation}: the wait ({values['wait_ms']:.3f}) is shorter than the GPU time ({values['gpu_ms']:.3f})")
                break
            if values["cpu_prepare_ms"] + values["wait_ms"] + values["readback_ms"] > values["total_ms"] + 0.05:
                failures.append(f"{operation}: the phases add up to more than the total: {values}")
                break
    for operation in ("mpr.pipeline", "vr.pipeline", "mpr.upload"):
        for sample in by_operation.get(operation, []):
            if sample.get("gpu_ms") is not None or not isinstance(sample.get("total_ms"), (int, float)):
                failures.append(f"{operation}: a host operation reports {sample}")
    for operation, compiled in (("mpr.pipeline", [True, False]), ("vr.pipeline", [True])):
        if [s.get("cold") for s in by_operation.get(operation, [])] != compiled:
            failures.append(f"{operation} says cold {[s.get('cold') for s in by_operation.get(operation, [])]}, "
                            f"expected {compiled}: compiled, then found compiled")
    for sample in by_operation.get("check.metal4.untimed", []):
        if sample.get("gpu_ms") is not None or sample.get("submit_to_gpu_ms") is not None or sample.get("wait_ms") is not None:
            failures.append(f"a feedback without timestamps reports GPU phases: {sample}")

    reslices = by_operation.get("mpr.reslice", [])
    if reslices:
        gpu = sorted(s["gpu_ms"] for s in reslices)
        print(f"mpr.reslice: median gpu {gpu[len(gpu) // 2]:.3f} ms, "
              f"median total {sorted(s['total_ms'] for s in reslices)[len(reslices) // 2]:.3f} ms")
    print(f"trace off: {off['off_ns_per_call']:.2f} ns per entry point")
    for failure in failures:
        print("FAIL:", failure)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
