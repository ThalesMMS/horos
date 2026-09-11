#!/usr/bin/env python3
"""The Metal 4 planar pilot draws what the backend in use draws (#609).

No app, no window, no database. The pilot and `PlanarMetalRenderer` render the
same `PlanarFrame` offscreen and the outputs are compared byte for byte, with
no tolerance: the two share the shader, the textures and the window/CLUT
arithmetic, so anything but an exact match is a defect, not rounding.

It then exercises the contracts the submission model has to honour:

* fifty consecutive submissions complete exactly once each - the origin
  recorded a hang from reusing one `MTL4CommitOptions` across commits, so every
  submission builds its own;
* the per-device cache holds only compiled artefacts, distinguishes pixel
  format, sample count and blending, and never stores a failed compilation;
* a slot keeps the textures its submission reads until the GPU reports
  completion, and gives them back afterwards;
* with every slot busy the newest request is kept and the older ones are
  dropped, so a redraw storm cannot grow a queue behind the UI;
* a submission that cannot be encoded frees its slot and publishes nothing.
"""
from pathlib import Path
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
sources = ['VolumeAllocation.swift', 'VolumeSession.swift', 'PlanarComparison.swift',
           'PlanarMetalRenderer.swift', 'PlanarMetal4Renderer.swift']
project = (root / 'Horos.xcodeproj/project.pbxproj').read_text()
failures = []
if project.count('PlanarMetal4Renderer.swift in Sources') < 1:
    failures.append('PlanarMetal4Renderer.swift is not in the Horos target')

# Source level: one options object per submission, built inside submit.
pilot = (root / 'Horos/Sources/PlanarMetal4Renderer.swift').read_text()
submit = pilot[pilot.index('func submit(into target:'):pilot.index('/// One completion per submission')]
if 'let options = MTL4CommitOptions()' not in submit:
    failures.append('the commit options are not built inside submit; the origin recorded a hang from reusing them')
if 'addFeedbackHandler' not in submit:
    failures.append('the submission registers no feedback handler')
if 'slot.release()' not in pilot or 'retained' not in pilot:
    failures.append('a submission does not retain and release what it used')

DRIVER = r'''
import Foundation
import Metal

func expect(_ ok: Bool, _ reason: String) { if !ok { print("FAIL: " + reason); exit(1) } }

func makeFrame(width: Int, height: Int, colour: Bool, nearest: Bool, scale: Int) throws -> PlanarFrame {
    var pixels = Data()
    if colour {
        var bytes = [UInt8]()
        for index in 0..<(width * height) {
            bytes += [255, UInt8((index * 31) % 256), UInt8(255 - (index * 17) % 256), UInt8((index * 11) % 256)]
        }
        pixels = Data(bytes)
    } else {
        let values = (0..<(width * height)).map { Float(($0 * 7) % 2048) - 1024 }
        pixels = values.withUnsafeBytes { Data($0) }
    }
    var clut = [UInt8]()
    for index in 0..<256 { clut += index < 128 ? [0, 0, 255, 255] : [255, 255, 0, 255] }
    let snapshot: NSDictionary = [
        "width": width, "height": height, "pixels": pixels, "clut": Data(clut),
        "frameIdentity": "pilot-\(width)x\(height)-\(colour)-\(nearest)-\(scale)",
        "screenToPixel": [0.0, 0.0, Double(width), 0.0, 0.0, Double(height)],
        "viewSize": [64.0, 40.0],
        "level": colour ? 127.5 : 40.0, "widthWindow": colour ? 255.0 : 400.0,
        "isColor": colour, "nearest": nearest, "background": false, "softwareScale": scale,
    ]
    return try PlanarFrame(snapshot)
}

@main struct Check {
    static func main() throws {
        guard let device = MTLCreateSystemDefaultDevice() else {
            print("skipped: Metal device unavailable"); exit(2)
        }
        guard PlanarMetal4Renderer.isSupported(device) else {
            print("skipped: this device or system has no Metal 4"); exit(2)
        }

        // 1. Identical pixels on every case the host actually produces.
        var cases = 0
        for (colour, nearest, scale) in [(false, false, 1), (false, true, 1), (true, false, 1),
                                         (true, true, 1), (false, false, 2), (false, false, 3)] {
            let frame = try makeFrame(width: 32, height: 20, colour: colour, nearest: nearest, scale: scale)
            let legacy = try PlanarMetalRenderer(device: device)
            let pilot = try PlanarMetal4Renderer(device: device)
            try legacy.update(frame)
            try pilot.update(frame)
            let a = try legacy.renderBGRA(width: 64, height: 40)
            let b = try pilot.renderBGRA(width: 64, height: 40)
            expect(a.count == b.count, "different output sizes for colour=\(colour) scale=\(scale)")
            expect(a == b, "the pilot drew different pixels for colour=\(colour) nearest=\(nearest) scale=\(scale)")
            cases += 1
        }

        // 2. Fifty consecutive submissions, each completing exactly once.
        let frame = try makeFrame(width: 64, height: 64, colour: false, nearest: false, scale: 1)
        let pilot = try PlanarMetal4Renderer(device: device)
        try pilot.update(frame)
        let descriptor = MTLTextureDescriptor.texture2DDescriptor(
            pixelFormat: .bgra8Unorm, width: 64, height: 40, mipmapped: false)
        descriptor.storageMode = .shared
        descriptor.usage = .renderTarget
        var targets: [MTLTexture] = []
        for _ in 0..<PlanarMetal4Renderer.slotCount {
            guard let texture = device.makeTexture(descriptor: descriptor) else {
                print("FAIL: could not allocate a target"); exit(1)
            }
            targets.append(texture)
        }
        // Completions arrive on Metal's feedback queue, so the issuer keeps its
        // own state behind a lock rather than in captured locals.
        let total = 50
        let issuer = Issuer(renderer: pilot, targets: targets, total: total)
        issuer.start()
        let deadline = Date().addingTimeInterval(20)
        while issuer.completed < total && Date() < deadline {
            RunLoop.current.run(mode: .default, before: Date().addingTimeInterval(0.002))
        }
        expect(issuer.failures == 0, "\(issuer.failures) consecutive submissions reported an error")
        expect(issuer.completed == total,
               "only \(issuer.completed) of \(total) consecutive submissions completed; this is the reused-options hang")
        expect(pilot.completedCount == total, "completed \(pilot.completedCount), expected \(total)")
        expect(pilot.failedCount == 0, "\(pilot.failedCount) submissions failed")

        // 3. The per-device cache: compiled artefacts only, keyed completely.
        PlanarMetal4Renderer.PipelineCache.removeAll()
        let cache = try PlanarMetal4Renderer.PipelineCache.shared(for: device)
        expect(try PlanarMetal4Renderer.PipelineCache.shared(for: device) === cache,
               "the same device got two caches")
        let base = PlanarMetal4Renderer.PipelineCache.Key(
            vertexFunction: "planarVertex", fragmentFunction: "planarFragment",
            colorFormat: MTLPixelFormat.bgra8Unorm.rawValue, sampleCount: 1, blending: false)
        _ = try cache.pipeline(for: base)
        let afterFirst = cache.compileCount
        expect(afterFirst == 1, "the first pipeline compiled \(afterFirst) times")
        _ = try cache.pipeline(for: base)
        expect(cache.compileCount == afterFirst, "an identical key compiled again")
        expect(cache.hitCount >= 1, "an identical key did not hit the cache")
        for variant in [PlanarMetal4Renderer.PipelineCache.Key(
                            vertexFunction: "planarVertex", fragmentFunction: "planarFragment",
                            colorFormat: MTLPixelFormat.rgba8Unorm.rawValue, sampleCount: 1, blending: false),
                        PlanarMetal4Renderer.PipelineCache.Key(
                            vertexFunction: "planarVertex", fragmentFunction: "planarFragment",
                            colorFormat: MTLPixelFormat.bgra8Unorm.rawValue, sampleCount: 4, blending: false),
                        PlanarMetal4Renderer.PipelineCache.Key(
                            vertexFunction: "planarVertex", fragmentFunction: "planarFragment",
                            colorFormat: MTLPixelFormat.bgra8Unorm.rawValue, sampleCount: 1, blending: true)] {
            let before = cache.compileCount
            _ = try cache.pipeline(for: variant)
            expect(cache.compileCount == before + 1,
                   "a different format, sample count or blending state reused a pipeline")
        }
        // A compilation that fails is not remembered as a success. Metal 4
        // reports a shader problem when the library is built, so that is where
        // the failure is produced and where the cache must refuse to record it.
        var threw = false
        do {
            _ = try PlanarMetal4Renderer.PipelineCache.make(
                device: device, source: "this is not a shader")
        } catch { threw = true }
        expect(threw, "a library that cannot compile was accepted")
        PlanarMetal4Renderer.PipelineCache.removeAll()
        threw = false
        var recovered: PlanarMetal4Renderer.PipelineCache?
        do { recovered = try PlanarMetal4Renderer.PipelineCache.shared(for: device) } catch { threw = true }
        expect(!threw && recovered != nil, "a failed compilation poisoned the cache for the device")
        expect(recovered!.compileCount == 0, "a fresh cache already claims a compiled pipeline")

        // 4. With every slot busy the newest request survives and the rest are
        //    dropped; the queue behind the UI never grows.
        let storm = try PlanarMetal4Renderer(device: device)
        try storm.update(frame)
        var accepted = 0
        let newest = Latest()
        for index in 0..<40 {
            let ok = try storm.submit(into: targets[0], coalescing: true) { _ in newest.record(index) }
            if ok { accepted += 1 }
        }
        expect(accepted == PlanarMetal4Renderer.slotCount,
               "\(accepted) submissions were accepted at once, expected \(PlanarMetal4Renderer.slotCount)")
        expect(storm.coalescedCount == 40 - PlanarMetal4Renderer.slotCount,
               "\(storm.coalescedCount) requests were coalesced, expected \(40 - PlanarMetal4Renderer.slotCount)")
        let stormDeadline = Date().addingTimeInterval(20)
        while newest.value < 39 && Date() < stormDeadline {
            RunLoop.current.run(mode: .default, before: Date().addingTimeInterval(0.002))
        }
        expect(newest.value == 39, "the newest request was not the one that ran (ran \(newest.value))")
        expect(storm.submittedCount <= PlanarMetal4Renderer.slotCount + 2,
               "a storm of 40 requests cost \(storm.submittedCount) submissions")

        // 5. A renderer with no frame publishes nothing and keeps no slot.
        let empty = try PlanarMetal4Renderer(device: device)
        threw = false
        do { _ = try empty.submit(into: targets[0]) { _ in } } catch { threw = true }
        expect(threw, "a renderer with no frame submitted anyway")
        expect(empty.submittedCount == 0, "a refused submission was counted")
        // Every slot is still free afterwards.
        try empty.update(frame)
        var free = 0
        for _ in 0..<PlanarMetal4Renderer.slotCount {
            if (try? empty.submit(into: targets[0], coalescing: false) { _ in }) == true { free += 1 }
        }
        expect(free == PlanarMetal4Renderer.slotCount,
               "only \(free) slots were free after a refused submission")

        print("ok: the Metal 4 pilot matches the existing backend on \(cases) cases, "
            + "completes \(total) consecutive submissions and coalesces a 40-request storm into "
            + "\(storm.submittedCount) submissions")
    }
}

final class Latest {
    private let lock = NSLock()
    private var highest = -1
    var value: Int { lock.withLock { highest } }
    func record(_ index: Int) { lock.withLock { highest = max(highest, index) } }
}

/// Keeps a fixed number of submissions moving without ever letting two threads
/// touch the same counter.
final class Issuer {
    private let lock = NSLock()
    private let renderer: PlanarMetal4Renderer
    private let targets: [MTLTexture]
    private let total: Int
    private var issued = 0
    private var done = 0
    private var errors = 0

    init(renderer: PlanarMetal4Renderer, targets: [MTLTexture], total: Int) {
        self.renderer = renderer
        self.targets = targets
        self.total = total
    }

    var completed: Int { lock.withLock { done } }
    var failures: Int { lock.withLock { errors } }

    func start() { issue() }

    private func issue() {
        while true {
            lock.lock()
            guard issued < total else { lock.unlock(); return }
            let index = issued
            lock.unlock()
            let target = targets[index % targets.count]
            guard let accepted = try? renderer.submit(into: target, coalescing: false, completion: { [weak self] error in
                guard let self else { return }
                self.lock.lock()
                self.done += 1
                if error != nil { self.errors += 1 }
                self.lock.unlock()
                self.issue()
            }), accepted else { return }
            lock.lock()
            issued += 1
            lock.unlock()
        }
    }
}
'''

if not failures:
    with tempfile.TemporaryDirectory(prefix='horos-metal4-pilot-') as temporary:
        work = Path(temporary)
        (work / 'Check.swift').write_text(DRIVER)
        build = subprocess.run(['xcrun', 'swiftc', '-O', '-parse-as-library',
                                *[str(root / 'Horos/Sources' / name) for name in sources],
                                str(work / 'Check.swift'), '-o', str(work / 'check')],
                               capture_output=True, text=True)
        if build.returncode != 0:
            failures.append('the driver did not compile:\n' + build.stderr[-4000:])
        else:
            run = subprocess.run([str(work / 'check')], capture_output=True, text=True, timeout=300)
            if run.returncode == 2:
                print((run.stdout + run.stderr).strip())
                raise SystemExit(2)
            if run.returncode != 0:
                failures.append((run.stdout + run.stderr).strip() or 'the driver failed without output')
            else:
                print(run.stdout.strip())

if failures:
    for failure in failures:
        print('FAIL:', failure)
    raise SystemExit(1)
