import Foundation

/// Where each coded picture of an H.264 stream belongs in the shown sequence.
///
/// VideoToolbox hands pictures back in the order they were decoded. Measured on
/// a 30-picture x264 stream with a B pyramid, `VTDecompressionSessionDecodeFrame`
/// emitted decode positions 0,1,2,... in that order under every combination of
/// `kVTDecodeFrame_EnableTemporalProcessing` and asynchronous decompression,
/// while the pictures are meant to be shown in a different order. Frame 12 of a
/// DICOM video is the twelfth frame as shown, not the twelfth as coded, so the
/// order is read from where the stream states it: Picture Order Count, H.264
/// clause 8.2.1.
enum H264PictureOrder {

    /// Decode order beside display order, and the points a decoder may be
    /// entered at.
    struct Order {
        /// A group of pictures: an IDR and everything coded after it up to the
        /// next one. An IDR empties what the decoder is holding, so nothing
        /// coded before it can be shown after it, and a group can be decoded
        /// without decoding what came before.
        struct Group {
            var firstDecode: Int
            var firstDisplay: Int
            var count: Int
        }

        var displayToDecode: [Int]
        var decodeToDisplay: [Int]
        var groupOfDisplay: [Int]        // display position -> index into groups
        var groups: [Group]
        /// false when the stream did not say and decode order had to do: no
        /// parameter set this can read, a picture order type it does not
        /// implement, or parameter sets that change part way through. A stream
        /// without B pictures shows its frames in decode order anyway.
        var fromTheStream: Bool
    }

    static func order(of units: [[Range<Int>]], in stream: Data) -> Order {
        let opens = idrFlags(of: units, in: stream)
        let counts = pictureOrderCounts(of: units, in: stream)

        var decodeToDisplay = [Int](repeating: 0, count: units.count)
        var groups: [Order.Group] = []
        var run: [Int] = []
        var shown = 0

        func settle() {
            guard let first = run.first else { return }
            let ordered = counts.map { values in
                run.sorted { values[$0] == values[$1] ? $0 < $1 : values[$0] < values[$1] }
            } ?? run
            for (rank, decodePosition) in ordered.enumerated() {
                decodeToDisplay[decodePosition] = shown + rank
            }
            groups.append(.init(firstDecode: first, firstDisplay: shown, count: run.count))
            shown += run.count
            run = []
        }

        for position in 0..<units.count {
            if opens[position] { settle() }
            run.append(position)
        }
        settle()

        var displayToDecode = [Int](repeating: 0, count: units.count)
        for (decode, display) in decodeToDisplay.enumerated() { displayToDecode[display] = decode }
        var groupOfDisplay = [Int](repeating: 0, count: units.count)
        for (index, group) in groups.enumerated() {
            for display in group.firstDisplay..<(group.firstDisplay + group.count) {
                groupOfDisplay[display] = index
            }
        }
        return Order(displayToDecode: displayToDecode, decodeToDisplay: decodeToDisplay,
                     groupOfDisplay: groupOfDisplay, groups: groups, fromTheStream: counts != nil)
    }

    /// The access units that begin with an IDR picture.
    private static func idrFlags(of units: [[Range<Int>]], in stream: Data) -> [Bool] {
        units.map { unit in
            guard let slice = firstSlice(of: unit, in: stream) else { return false }
            return (stream[slice.lowerBound] & 0x1f) == 5
        }
    }

    private static func firstSlice(of unit: [Range<Int>], in stream: Data) -> Range<Int>? {
        unit.first {
            let type = stream[$0.lowerBound] & 0x1f
            return type == 1 || type == 5
        }
    }

    /// nil when the stream cannot be read this far.
    private static func pictureOrderCounts(of units: [[Range<Int>]], in stream: Data) -> [Int]? {
        var sequence: SequenceParameters?
        var picture: PictureParameters?
        for unit in units {
            for nal in unit {
                switch stream[nal.lowerBound] & 0x1f {
                case 7:
                    guard let parsed = SequenceParameters(nal: stream.subdata(in: nal)) else { return nil }
                    if let existing = sequence, existing != parsed { return nil }
                    sequence = parsed
                case 8:
                    guard let parsed = PictureParameters(nal: stream.subdata(in: nal)) else { return nil }
                    if let existing = picture, existing != parsed { return nil }
                    picture = parsed
                default: break
                }
            }
        }
        guard let sequence, let picture else { return nil }
        if sequence.pictureOrderType == 1, sequence.offsetsForRefFrame.isEmpty,
           !sequence.deltaAlwaysZero { return nil }

        var counts: [Int] = []
        var state = OrderState(sequence: sequence)
        for unit in units {
            guard let slice = firstSlice(of: unit, in: stream),
                  let header = SliceHeader(nal: stream.subdata(in: slice),
                                           sequence: sequence, picture: picture),
                  !header.isField,
                  let count = state.pictureOrderCount(of: header) else { return nil }
            counts.append(count)
        }
        return counts
    }

    // MARK: reading bits

    /// The bits of a raw byte sequence payload.
    private struct BitReader {
        private let bytes: [UInt8]
        private var position = 0                      // in bits
        init(_ bytes: [UInt8]) { self.bytes = bytes }
        var exhausted: Bool { position >= bytes.count * 8 }

        mutating func bit() -> UInt32 {
            guard position < bytes.count * 8 else { position += 1; return 0 }
            let value = (bytes[position >> 3] >> (7 - UInt8(position & 7))) & 1
            position += 1
            return UInt32(value)
        }
        mutating func bits(_ count: Int) -> UInt32 {
            var value: UInt32 = 0
            for _ in 0..<count { value = (value << 1) | bit() }
            return value
        }
        /// ue(v): the leading zeros say how many bits follow.
        mutating func unsigned() -> UInt32 {
            var zeros = 0
            while !exhausted, bit() == 0 {
                zeros += 1
                if zeros > 31 { return 0 }
            }
            if zeros == 0 { return 0 }
            return (1 << UInt32(zeros)) - 1 + bits(zeros)
        }
        /// se(v).
        mutating func signed() -> Int {
            let value = unsigned()
            let magnitude = Int((value + 1) / 2)
            return value % 2 == 0 ? -magnitude : magnitude
        }
    }

    /// The 0x03 a writer inserts so that payload bytes cannot look like a start
    /// code is not part of the syntax and has to come out before the bits are
    /// read.
    private static func payload(of nal: Data, upTo limit: Int) -> [UInt8] {
        var bytes: [UInt8] = []
        bytes.reserveCapacity(min(nal.count, limit))
        var zeros = 0
        for byte in nal {
            if zeros >= 2, byte == 3 { zeros = 0; continue }
            bytes.append(byte)
            zeros = byte == 0 ? zeros + 1 : 0
            if bytes.count >= limit { break }
        }
        return bytes
    }

    // MARK: parameter sets

    private struct SequenceParameters: Equatable {
        var log2MaxFrameNum = 4
        var pictureOrderType = 0
        var log2MaxPictureOrderLSB = 4
        var deltaAlwaysZero = false
        var offsetForNonReference = 0
        var offsetsForRefFrame: [Int] = []
        var framesOnly = true
        var separateColourPlane = false

        /// The profiles that carry the chroma and scaling-list block, which sits
        /// before the fields this needs and so cannot be skipped over blindly.
        private static let extendedProfiles: Set<UInt32> = [100, 110, 122, 244, 44, 83, 86,
                                                            118, 128, 138, 139, 134, 135]

        init?(nal: Data) {
            var reader = BitReader(payload(of: nal, upTo: 256))
            _ = reader.bits(8)                                  // the NAL header
            let profile = reader.bits(8)
            _ = reader.bits(8)                                  // constraint flags
            _ = reader.bits(8)                                  // level
            _ = reader.unsigned()                               // seq_parameter_set_id
            var chroma: UInt32 = 1
            if SequenceParameters.extendedProfiles.contains(profile) {
                chroma = reader.unsigned()
                if chroma == 3 { separateColourPlane = reader.bit() == 1 }
                _ = reader.unsigned()                           // bit_depth_luma_minus8
                _ = reader.unsigned()                           // bit_depth_chroma_minus8
                _ = reader.bit()                                // qpprime_y_zero_transform_bypass
                if reader.bit() == 1 {                          // seq_scaling_matrix_present
                    for list in 0..<(chroma != 3 ? 8 : 12) {
                        if reader.bit() == 1 {
                            SequenceParameters.skipScalingList(&reader, length: list < 6 ? 16 : 64)
                        }
                    }
                }
            }
            log2MaxFrameNum = Int(reader.unsigned()) + 4
            pictureOrderType = Int(reader.unsigned())
            switch pictureOrderType {
            case 0:
                log2MaxPictureOrderLSB = Int(reader.unsigned()) + 4
            case 1:
                deltaAlwaysZero = reader.bit() == 1
                offsetForNonReference = reader.signed()
                _ = reader.signed()                             // offset_for_top_to_bottom_field
                let cycle = reader.unsigned()
                guard cycle <= 255 else { return nil }
                for _ in 0..<cycle { offsetsForRefFrame.append(reader.signed()) }
            case 2:
                break
            default:
                return nil
            }
            _ = reader.unsigned()                               // max_num_ref_frames
            _ = reader.bit()                                    // gaps_in_frame_num_allowed
            _ = reader.unsigned()                               // pic_width_in_mbs_minus1
            _ = reader.unsigned()                               // pic_height_in_map_units_minus1
            framesOnly = reader.bit() == 1
            if reader.exhausted { return nil }
            if log2MaxFrameNum > 16 || log2MaxPictureOrderLSB > 16 { return nil }
        }

        private static func skipScalingList(_ reader: inout BitReader, length: Int) {
            var last = 8, next = 8
            for _ in 0..<length {
                if next != 0 {
                    next = (last + reader.signed() + 256) % 256
                }
                if next != 0 { last = next }
            }
        }
    }

    private struct PictureParameters: Equatable {
        var bottomFieldOrderPresent = false
        init?(nal: Data) {
            var reader = BitReader(payload(of: nal, upTo: 64))
            _ = reader.bits(8)                                  // the NAL header
            _ = reader.unsigned()                               // pic_parameter_set_id
            _ = reader.unsigned()                               // seq_parameter_set_id
            _ = reader.bit()                                    // entropy_coding_mode_flag
            bottomFieldOrderPresent = reader.bit() == 1
            if reader.exhausted { return nil }
        }
    }

    // MARK: slice headers

    private struct SliceHeader {
        var isIDR = false
        var isReference = false
        var isField = false
        var frameNumber = 0
        var orderLSB = 0
        var deltaOrder = 0

        init?(nal: Data, sequence: SequenceParameters, picture: PictureParameters) {
            var reader = BitReader(payload(of: nal, upTo: 64))
            let header = reader.bits(8)
            isIDR = (header & 0x1f) == 5
            isReference = ((header >> 5) & 3) != 0
            _ = reader.unsigned()                               // first_mb_in_slice
            _ = reader.unsigned()                               // slice_type
            _ = reader.unsigned()                               // pic_parameter_set_id
            if sequence.separateColourPlane { _ = reader.bits(2) }
            frameNumber = Int(reader.bits(sequence.log2MaxFrameNum))
            if !sequence.framesOnly {
                isField = reader.bit() == 1
                if isField { _ = reader.bit() }                 // bottom_field_flag
            }
            if isIDR { _ = reader.unsigned() }                  // idr_pic_id
            switch sequence.pictureOrderType {
            case 0:
                orderLSB = Int(reader.bits(sequence.log2MaxPictureOrderLSB))
                if picture.bottomFieldOrderPresent, !isField { _ = reader.signed() }
            case 1:
                if !sequence.deltaAlwaysZero {
                    deltaOrder = reader.signed()
                    if picture.bottomFieldOrderPresent, !isField { _ = reader.signed() }
                }
            default:
                break
            }
            if reader.exhausted { return nil }
        }
    }

    // MARK: the count itself

    /// H.264 clause 8.2.1, for pictures coded as frames.
    private struct OrderState {
        let sequence: SequenceParameters
        var previousOrderMSB = 0
        var previousOrderLSB = 0
        var previousFrameNumber = 0
        var previousFrameNumberOffset = 0
        var seenAPicture = false

        init(sequence: SequenceParameters) { self.sequence = sequence }

        mutating func pictureOrderCount(of header: SliceHeader) -> Int? {
            switch sequence.pictureOrderType {
            case 0: return fromLeastSignificantBits(header)
            case 1: return fromCycle(header)
            case 2: return fromFrameNumber(header)
            default: return nil
            }
        }

        private mutating func fromLeastSignificantBits(_ header: SliceHeader) -> Int {
            let modulus = 1 << sequence.log2MaxPictureOrderLSB
            var msb = 0
            if header.isIDR {
                previousOrderMSB = 0
                previousOrderLSB = 0
            } else if header.orderLSB < previousOrderLSB,
                      previousOrderLSB - header.orderLSB >= modulus / 2 {
                msb = previousOrderMSB + modulus
            } else if header.orderLSB > previousOrderLSB,
                      header.orderLSB - previousOrderLSB > modulus / 2 {
                msb = previousOrderMSB - modulus
            } else {
                msb = previousOrderMSB
            }
            // Only a reference picture moves the origin the next one counts from.
            if header.isReference {
                previousOrderMSB = msb
                previousOrderLSB = header.orderLSB
            }
            return msb + header.orderLSB
        }

        private mutating func fromCycle(_ header: SliceHeader) -> Int {
            let maximum = 1 << sequence.log2MaxFrameNum
            var offset = 0
            if header.isIDR {
                offset = 0
            } else if previousFrameNumber > header.frameNumber {
                offset = previousFrameNumberOffset + maximum
            } else {
                offset = previousFrameNumberOffset
            }
            var absolute = sequence.offsetsForRefFrame.isEmpty ? 0 : offset + header.frameNumber
            if !header.isReference, absolute > 0 { absolute -= 1 }
            var expected = 0
            if absolute > 0 {
                let perCycle = sequence.offsetsForRefFrame.reduce(0, +)
                let cycles = (absolute - 1) / sequence.offsetsForRefFrame.count
                let within = (absolute - 1) % sequence.offsetsForRefFrame.count
                expected = cycles * perCycle
                for index in 0...within { expected += sequence.offsetsForRefFrame[index] }
            }
            if !header.isReference { expected += sequence.offsetForNonReference }
            previousFrameNumber = header.frameNumber
            previousFrameNumberOffset = offset
            seenAPicture = true
            return expected + header.deltaOrder
        }

        private mutating func fromFrameNumber(_ header: SliceHeader) -> Int {
            let maximum = 1 << sequence.log2MaxFrameNum
            var offset = 0
            if header.isIDR {
                offset = 0
            } else if previousFrameNumber > header.frameNumber {
                offset = previousFrameNumberOffset + maximum
            } else {
                offset = previousFrameNumberOffset
            }
            previousFrameNumber = header.frameNumber
            previousFrameNumberOffset = offset
            seenAPicture = true
            return 2 * (offset + header.frameNumber) - (header.isReference ? 0 : 1)
        }
    }
}
