// #373/A111 harness. Compile with the production PlanarMetalRenderer and
// VolumeAllocation sources; no alternate shader, loader or application window.
import Foundation
import Metal
import CryptoKit

@main struct Measure {
    static func now() -> Double { ProcessInfo.processInfo.systemUptime }
    static func main() throws {
        let directory = URL(fileURLWithPath:CommandLine.arguments[1])
        let input = try JSONSerialization.jsonObject(with:Data(contentsOf:directory.appendingPathComponent("input.json"))) as! [String:Any]
        guard let device = MTLCreateSystemDefaultDevice() else { print("skipped: Metal unavailable"); exit(2) }
        let width = input["width"] as! Int, height = input["height"] as! Int
        let outputWidth = input["output_width"] as! Int, outputHeight = input["output_height"] as! Int
        let table = try Data(contentsOf:directory.appendingPathComponent("clut.rgba"))
        let entries = input["frames"] as! [[String:String]]
        let pixels = try entries.map { try Data(contentsOf:directory.appendingPathComponent($0["pixels"]!)) }
        let expected = try entries.map { try Data(contentsOf:directory.appendingPathComponent($0["expected"]!)) }
        let originalHashes = pixels.map { SHA256.hash(data:$0) }
        var allowed = Set<UInt32>()
        for index in 0..<256 {
            allowed.insert(UInt32(table[index*4+2]) | UInt32(table[index*4+1])<<8 | UInt32(table[index*4])<<16 | 255<<24)
        }
        let initialization = now()
        let renderer = try PlanarMetalRenderer(device:device)
        let pipelineMilliseconds = (now()-initialization)*1000
        var samples = [[String:Any]](), checked = 0, maximumError = 0
        for pass in 0...3 {
            for index in entries.indices {
                try autoreleasepool {
                    let start = now()
                    let copy = pixels[index].withUnsafeBytes { Data(bytes:$0.baseAddress!,count:$0.count) }
                    let frame = try PlanarFrame([
                        "width":width,"height":height,"pixels":copy,"clut":table,
                        "frameIdentity":entries[index]["id"]!,"level":input["level"]!,"widthWindow":input["width_window"]!,
                        "screenToPixel":[0.0,0.0,Double(width),0.0,0.0,Double(height)],
                        "viewSize":[Double(width),Double(height)],"isColor":false,"nearest":false])
                    let snapshotEnd = now()
                    try renderer.update(frame)
                    let uploadEnd = now()
                    // Same target format/allocation and encode path as renderTexture.
                    // Explicit command ownership exposes Metal's hardware timestamps.
                    let descriptor = MTLTextureDescriptor.texture2DDescriptor(pixelFormat:.bgra8Unorm,
                        width:outputWidth,height:outputHeight,mipmapped:false)
                    descriptor.storageMode = .shared; descriptor.usage = .renderTarget
                    guard let target = device.makeTexture(descriptor:descriptor),
                          let command = renderer.queue.makeCommandBuffer() else { fatalError("Metal allocation") }
                    try renderer.encode(into:target,command:command)
                    let submit = now()
                    command.commit(); command.waitUntilCompleted()
                    let completed = now()
                    guard command.status == .completed else { throw command.error ?? PlanarMetalRenderer.failure() }
                    let gpuTime = command.gpuEndTime-command.gpuStartTime
                    var sample:[String:Any] = ["pass":pass,"frame":index,"id":entries[index]["id"]!,
                        "snapshot_ms":(snapshotEnd-start)*1000,"upload_ms":(uploadEnd-snapshotEnd)*1000,
                        "allocate_encode_ms":(submit-uploadEnd)*1000,"submit_wait_ms":(completed-submit)*1000,
                        "frame_wall_ms":(completed-start)*1000,"metal_allocated_bytes":device.currentAllocatedSize]
                    sample["gpu_ms"] = command.gpuStartTime > 0 && gpuTime >= 0 ? gpuTime*1000 : NSNull()
                    samples.append(sample)
                    // Readback and reference checking are outside every timing.
                    var actual = Data(count:outputWidth*outputHeight*4)
                    actual.withUnsafeMutableBytes {
                        target.getBytes($0.baseAddress!,bytesPerRow:outputWidth*4,
                            from:MTLRegionMake2D(0,0,outputWidth,outputHeight),mipmapLevel:0)
                    }
                    guard expected[index].count == actual.count else { fatalError("reference size") }
                    var maxError = 0, forbidden = 0
                    actual.withUnsafeBytes { (a:UnsafeRawBufferPointer) in
                        expected[index].withUnsafeBytes { (e:UnsafeRawBufferPointer) in
                            for byte in 0..<a.count { maxError = max(maxError,abs(Int(a[byte])-Int(e[byte]))) }
                        }
                        for pixel in stride(from:0,to:a.count,by:4) {
                            let color = UInt32(a[pixel]) | UInt32(a[pixel+1])<<8 | UInt32(a[pixel+2])<<16 | UInt32(a[pixel+3])<<24
                            if !allowed.contains(color) { forbidden += 1 }
                        }
                    }
                    guard maxError <= 1 && forbidden == 0 else {
                        fatalError("FAIL: pass=\(pass) frame=\(index) error=\(maxError) forbidden=\(forbidden)")
                    }
                    maximumError = max(maximumError,maxError); checked += outputWidth*outputHeight
                }
            }
        }
        guard pixels.map({SHA256.hash(data:$0)}) == originalHashes else { fatalError("source pixels changed") }
        renderer.clear()
        let result:[String:Any] = ["device":device.name,"os":ProcessInfo.processInfo.operatingSystemVersionString,
            "pipeline_initialization_ms":pipelineMilliseconds,"pixels_checked":checked,
            "maximum_channel_error":maximumError,"unexpected_clut_colors":0,
            "source_pixels_unchanged":true,"samples":samples]
        let output = try JSONSerialization.data(withJSONObject:result,options:[.prettyPrinted,.sortedKeys])
        try output.write(to:directory.appendingPathComponent("gpu-results.json"),options:.atomic)
        print("PASS: \(checked) low-contrast GPU pixels, max error \(maximumError), zero colors outside CLUT; first pass + 3 repeated sequences")
    }
}
