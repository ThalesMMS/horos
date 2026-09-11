import CoreMedia
import CoreVideo
import Foundation
import VideoToolbox

/// Frames out of the video an instance carries whole.
///
/// Transfer syntaxes 1.2.840.10008.1.2.4.100 and up put the entire stream in the
/// Pixel Data element - one fragment for the lot, not one fragment per frame -
/// so the framework's "decode this fragment" path hands the same compressed
/// bytes back for every frame index, and the colour conversion after it reads a
/// compressed stream as though it were pixels. This takes the stream once, finds
/// its parameter sets and access units, and decodes a frame at a time through
/// VideoToolbox: the decoder macOS already has, in hardware where there is
/// hardware.
@objc(HorosH264StreamDecoder)
public final class H264StreamDecoder: NSObject {

    // MARK: which objects carry a stream

    /// Every transfer syntax whose Pixel Data is one video rather than a frame.
    /// Asking the fragment decoder for a frame of one of these gives compressed
    /// bytes where pixels are expected, so a caller that cannot decode the
    /// stream is better off saying so than showing the result.
    private static let videoSyntaxes: Set<String> = [
        "1.2.840.10008.1.2.4.100",   // MPEG2 Main Profile / Main Level
        "1.2.840.10008.1.2.4.101",   // MPEG2 Main Profile / High Level
        "1.2.840.10008.1.2.4.102",   // MPEG-4 AVC/H.264 High Profile / Level 4.1
        "1.2.840.10008.1.2.4.103",   // MPEG-4 AVC/H.264 BD-compatible HP / 4.1
        "1.2.840.10008.1.2.4.104",   // MPEG-4 AVC/H.264 HP / 4.2 for 2D video
        "1.2.840.10008.1.2.4.105",   // MPEG-4 AVC/H.264 HP / 4.2 for 3D video
        "1.2.840.10008.1.2.4.106",   // MPEG-4 AVC/H.264 Stereo HP / Level 4.2
        "1.2.840.10008.1.2.4.107",   // HEVC/H.265 Main Profile / Level 5.1
        "1.2.840.10008.1.2.4.108",   // HEVC/H.265 Main 10 Profile / Level 5.1
    ]

    /// The ones this decodes: H.264, one view. MPEG-2 is a different codec,
    /// HEVC a different parameter-set layout, and the stereo syntax carries two
    /// views per picture, which is not what a single frame of Pixel Data means.
    private static let decodedSyntaxes: Set<String> = [
        "1.2.840.10008.1.2.4.102",
        "1.2.840.10008.1.2.4.103",
        "1.2.840.10008.1.2.4.104",
        "1.2.840.10008.1.2.4.105",
    ]

    @objc(isVideoTransferSyntax:)
    public static func isVideo(transferSyntax: String?) -> Bool {
        guard let uid = normalised(transferSyntax) else { return false }
        return videoSyntaxes.contains(uid)
    }

    @objc(handlesTransferSyntax:)
    public static func handles(transferSyntax: String?) -> Bool {
        guard let uid = normalised(transferSyntax) else { return false }
        return decodedSyntaxes.contains(uid)
    }

    /// UIDs read off the wire keep their padding, and a trailing NUL compares
    /// unequal to the same UID written in a literal.
    private static func normalised(_ uid: String?) -> String? {
        guard let uid else { return nil }
        let trimmed = uid.trimmingCharacters(in: CharacterSet(charactersIn: " \0\r\n\t"))
        return trimmed.isEmpty ? nil : trimmed
    }

    // MARK: one decoder per file

    private static let cacheGate = NSLock()
    private static var cache: [(key: String, decoder: H264StreamDecoder)] = []
    /// Two, so that scrolling between two series does not re-parse either
    /// stream, and a third does not keep the first two alive.
    private static let cacheLimit = 2

    /// The decoder for a file, built from `streamProvider` the first time it is
    /// asked for. Frames of a multi-frame object are loaded by one DCMPix each,
    /// and a decoder built per frame would have no reference frames to decode a
    /// predicted picture from.
    @objc(cachedDecoderForKey:streamProvider:)
    public static func cachedDecoder(forKey key: String,
                                     streamProvider: () -> Data?) -> H264StreamDecoder? {
        cacheGate.lock()
        if let position = cache.firstIndex(where: { $0.key == key }) {
            let entry = cache.remove(at: position)
            cache.append(entry)
            cacheGate.unlock()
            return entry.decoder
        }
        cacheGate.unlock()

        guard let stream = streamProvider(),
              let decoder = H264StreamDecoder(annexBStream: stream) else { return nil }

        cacheGate.lock()
        defer { cacheGate.unlock() }
        if let position = cache.firstIndex(where: { $0.key == key }) { return cache[position].decoder }
        cache.append((key, decoder))
        while cache.count > cacheLimit { cache.removeFirst() }
        return decoder
    }

    @objc public static func purgeCache() {
        cacheGate.lock()
        cache.removeAll()
        cacheGate.unlock()
    }

    // MARK: the stream

    private let stream: Data
    private var units: [[Range<Int>]] = []      // the NALs of each access unit
    private var format: CMVideoFormatDescription?
    private var order: H264PictureOrder.Order!

    @objc public private(set) var width: Int = 0
    @objc public private(set) var height: Int = 0
    @objc public var frameCount: Int { units.count }
    /// false when the shown order had to be taken as the coded order because
    /// the stream did not say; see `H264PictureOrder.Order.fromTheStream`.
    @objc public var displayOrderIsFromTheStream: Bool { order?.fromTheStream ?? false }

    /// nil when the bytes are not an H.264 elementary stream this can start
    /// from: no parameter sets, none usable, or no coded picture in them.
    @objc(initWithAnnexBStream:)
    public init?(annexBStream: Data) {
        stream = annexBStream
        super.init()
        guard build(), !units.isEmpty else { return nil }
        order = H264PictureOrder.order(of: units, in: annexBStream)
    }

    deinit {
        if let session { VTDecompressionSessionInvalidate(session) }
    }

    /// The byte ranges of every NAL unit, Annex-B start codes removed.
    private func nalRanges() -> [Range<Int>] {
        var ranges: [Range<Int>] = []
        stream.withUnsafeBytes { (raw: UnsafeRawBufferPointer) in
            let bytes = raw.bindMemory(to: UInt8.self)
            var starts: [(payload: Int, code: Int)] = []
            var index = 0
            while index + 3 <= bytes.count {
                if bytes[index] == 0, bytes[index + 1] == 0 {
                    if bytes[index + 2] == 1 {
                        starts.append((index + 3, 3)); index += 3; continue
                    }
                    if index + 4 <= bytes.count, bytes[index + 2] == 0, bytes[index + 3] == 1 {
                        starts.append((index + 4, 4)); index += 4; continue
                    }
                }
                index += 1
            }
            for (position, start) in starts.enumerated() {
                let end = position + 1 < starts.count
                    ? starts[position + 1].payload - starts[position + 1].code
                    : bytes.count
                if start.payload < end { ranges.append(start.payload..<end) }
            }
        }
        return ranges
    }

    private func kind(of range: Range<Int>) -> UInt8 { stream[range.lowerBound] & 0x1f }

    /// first_mb_in_slice is the first Exp-Golomb value of the slice header, and
    /// zero means this slice opens a picture: a picture split into several
    /// slices stays one picture.
    private func startsAPicture(_ range: Range<Int>) -> Bool {
        guard range.count > 1 else { return false }
        return stream[range.lowerBound + 1] & 0x80 != 0      // ue(0) is one 1 bit
    }

    /// Parameter sets make the format description; the slices make the frames.
    private func build() -> Bool {
        var sps: Data?, pps: Data?
        var current: [Range<Int>] = []
        var pendingNonSlice: [Range<Int>] = []   // non-slice NALs of the next picture
        var sawSlice = false

        for range in nalRanges() {
            let type = kind(of: range)
            if type == 7, sps == nil { sps = stream.subdata(in: range) }
            if type == 8, pps == nil { pps = stream.subdata(in: range) }

            guard type == 1 || type == 5 else {
                if sawSlice { pendingNonSlice.append(range) } else { current.append(range) }
                continue
            }
            if sawSlice, startsAPicture(range) {
                units.append(current)
                current = []
                sawSlice = false
            }
            if !sawSlice {
                current.append(contentsOf: pendingNonSlice)
                pendingNonSlice = []
            }
            current.append(range)
            sawSlice = true
        }
        if sawSlice { units.append(current) }

        guard let sps, let pps else { return false }
        var description: CMVideoFormatDescription?
        let status = sps.withUnsafeBytes { (first: UnsafeRawBufferPointer) in
            pps.withUnsafeBytes { (second: UnsafeRawBufferPointer) -> OSStatus in
                let pointers = [first.baseAddress!.assumingMemoryBound(to: UInt8.self),
                                second.baseAddress!.assumingMemoryBound(to: UInt8.self)]
                let sizes = [sps.count, pps.count]
                return pointers.withUnsafeBufferPointer { pointerBuffer in
                    sizes.withUnsafeBufferPointer { sizeBuffer in
                        CMVideoFormatDescriptionCreateFromH264ParameterSets(
                            allocator: kCFAllocatorDefault, parameterSetCount: 2,
                            parameterSetPointers: pointerBuffer.baseAddress!,
                            parameterSetSizes: sizeBuffer.baseAddress!,
                            nalUnitHeaderLength: 4, formatDescriptionOut: &description)
                    }
                }
            }
        }
        guard status == noErr, let description else { return false }
        format = description
        let dimensions = CMVideoFormatDescriptionGetDimensions(description)
        width = Int(dimensions.width)
        height = Int(dimensions.height)
        return width > 0 && height > 0
    }

    // MARK: decoding

    private let gate = NSLock()
    private var session: VTDecompressionSession?
    private var group = -1                       // the group the live session is in
    private var submitted = 0                    // next access unit to hand over
    private var held: [Int: Data] = [:]          // decode position -> picture
    private var recent: [Int: Data] = [:]        // the frame last asked for

    /// A frame as 8-bit RGB, three bytes per pixel, rows top to bottom, counted
    /// in the order the frames are shown.
    ///
    /// The decoder is entered at the group of pictures the frame belongs to and
    /// fed access units in coded order until the one wanted comes back, which is
    /// one decode per frame while a series is played through and a group's worth
    /// when someone drags the slider.
    @objc(rgbFrameAtIndex:)
    public func rgbFrame(at index: Int) -> Data? {
        gate.lock()
        defer { gate.unlock() }
        guard index >= 0, index < units.count else { return nil }
        if let ready = recent[index] { return ready }

        let wanted = order.displayToDecode[index]
        let which = order.groupOfDisplay[index]
        if session == nil || group != which || (submitted > wanted && held[wanted] == nil) {
            restart(at: which)
        }
        guard session != nil else { return nil }

        while held[wanted] == nil, submitted < units.count {
            let unit = submitted
            submitted += 1
            if !hand(over: unit) { break }
        }
        if held[wanted] == nil, submitted >= units.count { drain() }

        guard let frame = held[wanted] else { return nil }
        // What is still held is what the decoder gave back out of order; a frame
        // already shown is not asked for again while playing, and going back
        // re-enters the group.
        for position in held.keys where order.decodeToDisplay[position] < index { held[position] = nil }
        recent = [index: frame]
        return frame
    }

    private func restart(at which: Int) {
        if let session {
            VTDecompressionSessionInvalidate(session)
            self.session = nil
        }
        held = [:]
        submitted = order.groups[which].firstDecode
        group = which
        session = makeSession()
    }

    private func makeSession() -> VTDecompressionSession? {
        guard let format else { return nil }
        let attributes: [String: Any] = [
            kCVPixelBufferPixelFormatTypeKey as String: kCVPixelFormatType_32BGRA,
            kCVPixelBufferWidthKey as String: width,
            kCVPixelBufferHeightKey as String: height,
            kCVPixelBufferIOSurfacePropertiesKey as String: [:] as [String: Any],
        ]
        var created: VTDecompressionSession?
        let status = VTDecompressionSessionCreate(
            allocator: kCFAllocatorDefault, formatDescription: format,
            decoderSpecification: nil, imageBufferAttributes: attributes as CFDictionary,
            outputCallback: nil, decompressionSessionOut: &created)
        return status == noErr ? created : nil
    }

    /// Decoding is synchronous, so the pictures arrive on this thread while the
    /// lock is held and nothing else can be looking at `held`. Which picture
    /// came back is read off the timestamp it was handed over with rather than
    /// assumed from the order.
    private func hand(over unit: Int) -> Bool {
        guard let session, let format else { return false }

        var sample = Data()
        for nal in units[unit] {
            var length = UInt32(nal.count).bigEndian
            withUnsafeBytes(of: &length) { sample.append(contentsOf: $0) }
            sample.append(stream.subdata(in: nal))
        }

        var block: CMBlockBuffer?
        let bytes = UnsafeMutableRawPointer.allocate(byteCount: sample.count, alignment: 1)
        sample.copyBytes(to: bytes.assumingMemoryBound(to: UInt8.self), count: sample.count)
        var status = CMBlockBufferCreateWithMemoryBlock(
            allocator: kCFAllocatorDefault, memoryBlock: bytes, blockLength: sample.count,
            blockAllocator: kCFAllocatorDefault, customBlockSource: nil,
            offsetToData: 0, dataLength: sample.count, flags: 0, blockBufferOut: &block)
        guard status == noErr, let block else {
            bytes.deallocate()
            return false
        }

        var timing = CMSampleTimingInfo(
            duration: CMTime(value: 1, timescale: H264StreamDecoder.clock),
            presentationTimeStamp: CMTime(value: Int64(unit), timescale: H264StreamDecoder.clock),
            decodeTimeStamp: .invalid)
        var sizes = [sample.count]
        var buffer: CMSampleBuffer?
        status = CMSampleBufferCreateReady(
            allocator: kCFAllocatorDefault, dataBuffer: block, formatDescription: format,
            sampleCount: 1, sampleTimingEntryCount: 1, sampleTimingArray: &timing,
            sampleSizeEntryCount: 1, sampleSizeArray: &sizes, sampleBufferOut: &buffer)
        guard status == noErr, let buffer else { return false }

        status = VTDecompressionSessionDecodeFrame(
            session, sampleBuffer: buffer, flags: [], infoFlagsOut: nil) { [self] status, _, image, time, _ in
                guard status == noErr, let image,
                      let rgb = H264StreamDecoder.rgb(from: image) else { return }
                held[Int(time.value)] = rgb
            }
        return status == noErr
    }

    /// Timestamps stand for the coded position, not for time: nothing here plays
    /// the stream, and the viewer takes the frame rate from the object's own
    /// Cine Rate or Frame Time.
    private static let clock: CMTimeScale = 600

    /// The pictures the decoder is still holding, once there are no more access
    /// units to give it.
    private func drain() {
        guard let session else { return }
        VTDecompressionSessionFinishDelayedFrames(session)
        VTDecompressionSessionWaitForAsynchronousFrames(session)
    }

    private static func rgb(from image: CVImageBuffer) -> Data? {
        CVPixelBufferLockBaseAddress(image, .readOnly)
        defer { CVPixelBufferUnlockBaseAddress(image, .readOnly) }
        guard let base = CVPixelBufferGetBaseAddress(image) else { return nil }
        let width = CVPixelBufferGetWidth(image)
        let height = CVPixelBufferGetHeight(image)
        let stride = CVPixelBufferGetBytesPerRow(image)
        var out = Data(count: width * height * 3)
        out.withUnsafeMutableBytes { (destination: UnsafeMutableRawBufferPointer) in
            let target = destination.bindMemory(to: UInt8.self)
            let source = base.assumingMemoryBound(to: UInt8.self)
            var at = 0
            for row in 0..<height {
                let line = source + row * stride
                for column in 0..<width {
                    target[at] = line[column * 4 + 2]        // 32BGRA
                    target[at + 1] = line[column * 4 + 1]
                    target[at + 2] = line[column * 4]
                    at += 3
                }
            }
        }
        return out
    }
}
