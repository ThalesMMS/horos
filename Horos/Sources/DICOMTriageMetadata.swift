import Foundation

/// Metadata needed by the two incoming-image gates. Both gates must interpret
/// the negotiated transfer syntax in the same way, before thumbnail loading.
struct DICOMTriageMetadata {
    private struct Value {
        let vr: String
        let bytes: Data
        let littleEndian: Bool
    }
    private var values: [UInt32: Value] = [:]
    var pixelDataBytes = 0
    var hasPixelData = false
    var encapsulated = false

    func contains(group: UInt16, element: UInt16) -> Bool {
        values[UInt32(group) << 16 | UInt32(element)] != nil
    }
    func string(group: UInt16, element: UInt16) -> String? {
        guard let value = values[UInt32(group) << 16 | UInt32(element)] else { return nil }
        let text = String(decoding: value.bytes, as: UTF8.self)
            .trimmingCharacters(in: CharacterSet(charactersIn: "\0 "))
        return text.isEmpty ? nil : text
    }
    func int(group: UInt16, element: UInt16) -> Int? {
        guard let value = values[UInt32(group) << 16 | UInt32(element)] else { return nil }
        if ["US", "SS"].contains(value.vr), value.bytes.count >= 2 {
            let number = UInt16(Self.number(value.bytes, 0, 2, value.littleEndian))
            return value.vr == "SS" ? Int(Int16(bitPattern: number)) : Int(number)
        }
        if ["UL", "SL"].contains(value.vr), value.bytes.count >= 4 {
            let number = UInt32(Self.number(value.bytes, 0, 4, value.littleEndian))
            return value.vr == "SL" ? Int(Int32(bitPattern: number)) : Int(number)
        }
        return string(group: group, element: element)?.split(separator: "\\").first.flatMap { Int($0) }
    }
    func double(group: UInt16, element: UInt16) -> Double? {
        guard let value = values[UInt32(group) << 16 | UInt32(element)] else { return nil }
        if value.vr == "FD", value.bytes.count >= 8 {
            return Double(bitPattern: Self.number(value.bytes, 0, 8, value.littleEndian))
        }
        return string(group: group, element: element).flatMap(Double.init)
    }
    var pixelSpacing: (x: Double, y: Double) {
        let parts = string(group: 0x0028, element: 0x0030)?.split(separator: "\\")
            .compactMap { Double($0.trimmingCharacters(in: .whitespaces)) } ?? []
        return parts.count >= 2 ? (parts[1], parts[0]) : (parts.first ?? 0, parts.first ?? 0)
    }

    static func parse(_ data: Data) -> Self? {
        guard data.count >= 132, data[128..<132].elementsEqual("DICM".utf8) else { return nil }
        var result = Self(), offset = 132
        guard result.read(data, &offset, end: data.count, implicit: false,
                          littleEndian: true, depth: 0, meta: true) else { return nil }
        let syntax = result.string(group: 2, element: 0x10)
        // Deflated datasets must first go through the application's decoder.
        guard syntax != "1.2.840.10008.1.2.1.99" else { return nil }
        guard result.read(data, &offset, end: data.count,
                          implicit: syntax == "1.2.840.10008.1.2",
                          littleEndian: syntax != "1.2.840.10008.1.2.2", depth: 0) else { return nil }
        return result
    }

    private static func number(_ data: Data, _ offset: Int, _ count: Int, _ little: Bool) -> UInt64 {
        var value: UInt64 = 0
        for i in 0..<count {
            value |= UInt64(data[offset + i]) << ((little ? i : count - 1 - i) * 8)
        }
        return value
    }

    private mutating func read(_ data: Data, _ offset: inout Int, end: Int,
                               implicit: Bool, littleEndian: Bool, depth: Int,
                               meta: Bool = false) -> Bool {
        guard depth <= 16 else { return false }
        while end - offset >= 8 {
            let group = UInt16(Self.number(data, offset, 2, littleEndian))
            let element = UInt16(Self.number(data, offset + 2, 2, littleEndian))
            if meta && group != 2 { return true }
            if group == 0xFFFE { return true }
            let key = UInt32(group) << 16 | UInt32(element)
            let vr = implicit ? Self.implicitVR(key) : String(decoding: data[(offset + 4)..<(offset + 6)], as: UTF8.self)
            let longVR = ["OB", "OD", "OF", "OL", "OV", "OW", "SQ", "SV", "UC", "UN", "UR", "UT", "UV"].contains(vr)
            let header = implicit || !longVR ? 8 : 12
            guard end - offset >= header else { return false }
            let length = Int(Self.number(data, offset + (implicit ? 4 : longVR ? 8 : 6),
                                         implicit || longVR ? 4 : 2, littleEndian))
            offset += header
            let undefined = length == 0xFFFFFFFF
            if key == 0x7FE00010 && depth == 0 {
                hasPixelData = true
                encapsulated = undefined
                pixelDataBytes = undefined ? 0 : min(length, end - offset)
                // The gate needs metadata only, never copies or decodes pixels.
                return true
            }
            if vr == "SQ" || undefined {
                if depth == 0 { values[key] = Value(vr: "SQ", bytes: Data(), littleEndian: littleEndian) }
                let sequenceEnd = undefined ? end : offset + min(length, end - offset)
                guard undefined || length <= end - offset else { return false }
                guard readItems(data, &offset, end: sequenceEnd, implicit: implicit,
                                littleEndian: littleEndian, depth: depth + 1, undefined: undefined) else { return false }
            } else {
                guard length <= end - offset else { return false }
                // Image identity/dimensions belong to the root. An embedded icon
                // must not supply missing Rows/Columns. Geometry and ultrasound
                // calibration may be inside functional groups or region items.
                let nestedGeometry = key == 0x00280030 || (group == 0x0018 && element >= 0x6012 && element <= 0x602E)
                if depth == 0 || (nestedGeometry && values[key] == nil) {
                    values[key] = Value(vr: vr, bytes: data.subdata(in: offset..<(offset + length)), littleEndian: littleEndian)
                }
                offset += length
            }
        }
        return offset == end
    }

    private mutating func readItems(_ data: Data, _ offset: inout Int, end: Int,
                                    implicit: Bool, littleEndian: Bool, depth: Int,
                                    undefined: Bool) -> Bool {
        guard depth <= 16 else { return false }
        while end - offset >= 8 {
            let tag = UInt32(Self.number(data, offset, 2, littleEndian)) << 16
                | UInt32(Self.number(data, offset + 2, 2, littleEndian))
            let length = Int(Self.number(data, offset + 4, 4, littleEndian))
            offset += 8
            if tag == 0xFFFEE0DD { return undefined && length == 0 }
            guard tag == 0xFFFEE000 else { return false }
            let itemUndefined = length == 0xFFFFFFFF
            guard itemUndefined || length <= end - offset else { return false }
            let itemEnd = itemUndefined ? end : offset + length
            guard read(data, &offset, end: itemEnd, implicit: implicit,
                       littleEndian: littleEndian, depth: depth) else { return false }
            if itemUndefined {
                guard end - offset >= 8,
                      Self.number(data, offset, 2, littleEndian) == 0xFFFE,
                      Self.number(data, offset + 2, 2, littleEndian) == 0xE00D,
                      Self.number(data, offset + 4, 4, littleEndian) == 0 else { return false }
                offset += 8
            } else if offset != itemEnd { return false }
        }
        return !undefined && offset == end
    }

    private static func implicitVR(_ key: UInt32) -> String {
        switch key {
        case 0x00280002, 0x00280010, 0x00280011, 0x00280100...0x00280103,
             0x00186012, 0x00186014, 0x00186024, 0x00186026,
             0x00281101...0x00281103: return "US"
        case 0x00186016, 0x00186018, 0x0018601A, 0x0018601C, 0x0018601E: return "UL"
        case 0x0018602C, 0x0018602E: return "FD"
        case 0x00186011, 0x52009229, 0x52009230, 0x00289110, 0x00289132,
             0x00209111, 0x00209113, 0x00209116, 0x0040A730, 0x00880200: return "SQ"
        default: return "UN"
        }
    }
}
