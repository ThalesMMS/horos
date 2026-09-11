import Foundation

/// The VOI LUT an object carries instead of a window.
///
/// PS 3.3 C.11.2: when an object has a VOI LUT Sequence, that table is how its
/// values are meant to be shown, and Window Center and Width are the
/// alternative, not the other way round. Horos read neither: the table was
/// parsed only on a code path that no longer runs, and the preference that
/// turns it on switched itself off - and rewrote itself in the defaults - the
/// first time an image was loaded. An object whose only windowing instruction
/// is its table was therefore shown with a window Horos computed for itself.
@objc(HorosVOILookupTable)
public final class VOILookupTable: NSObject {

    /// The first stored value the table maps; below it everything takes the
    /// first entry.
    @objc public private(set) var firstMapped: Int = 0
    @objc public private(set) var entries: Int = 0
    /// Bits per entry, as the descriptor states it: 8 through 16.
    @objc public private(set) var depth: Int = 0
    /// The entries, one 32-bit value each in host order, ready to be copied
    /// into the buffer `-[DCMPix setVOILUT:number:depth:table:image:isSigned:]`
    /// takes.
    @objc public private(set) var table = Data()

    @objc public private(set) var smallest: Int = 0
    @objc public private(set) var largest: Int = 0

    /// nil when the sequence item is not a table this can use: a descriptor
    /// that is not three values, a count that does not match the data, a depth
    /// outside 8 to 16.
    ///
    /// `descriptor` is LUT Descriptor (0028,3002) and `data` LUT Data
    /// (0028,3006), which a parser hands back either as bytes or as numbers
    /// depending on the value representation the file declared. `signed` is the
    /// object's Pixel Representation, which is what says whether the first
    /// mapped value is negative.
    @objc(initWithDescriptor:data:pixelRepresentationIsSigned:)
    public init?(descriptor: [NSNumber]?, data: Any?, signed: Bool) {
        super.init()
        guard let descriptor, descriptor.count >= 3 else { return nil }

        // Zero means 65536: the count is stored in sixteen bits and the largest
        // table there is does not fit in them.
        entries = descriptor[0].intValue == 0 ? 65536 : descriptor[0].intValue
        depth = descriptor[2].intValue
        guard entries > 1, entries <= 65536, depth >= 8, depth <= 16 else { return nil }

        let first = descriptor[1].intValue
        firstMapped = (signed && first > 32767) ? first - 65536 : first

        guard let values = VOILookupTable.values(from: data, entries: entries, depth: depth)
        else { return nil }

        smallest = values.min().map(Int.init) ?? 0
        largest = values.max().map(Int.init) ?? 0
        table = values.withUnsafeBufferPointer { Data(buffer: $0) }
        return
    }

    private static func values(from data: Any?, entries: Int, depth: Int) -> [UInt32]? {
        if let numbers = data as? [NSNumber] {
            guard numbers.count >= entries else { return nil }
            return numbers.prefix(entries).map { UInt32(truncatingIfNeeded: $0.intValue) }
        }
        guard let bytes = data as? Data else { return nil }

        // Eight-bit entries are one byte each when the writer used OB, and one
        // sixteen-bit word each when it used OW - the length settles it, which
        // is the only thing that can.
        if bytes.count >= entries * 2 {
            return (0..<entries).map { index in
                let low = UInt32(bytes[bytes.startIndex + index * 2])
                let high = UInt32(bytes[bytes.startIndex + index * 2 + 1])
                return low | (high << 8)                    // little endian
            }
        }
        if depth <= 8, bytes.count >= entries {
            return (0..<entries).map { UInt32(bytes[bytes.startIndex + $0]) }
        }
        return nil
    }

    /// The window that shows the whole of what the table produces, which is what
    /// a table is for: the object's own Window Center and Width describe its
    /// input, and mean nothing once the values are its output.
    @objc public var windowCenter: Double { (Double(largest) + Double(smallest)) / 2.0 }
    @objc public var windowWidth: Double { max(Double(largest) - Double(smallest) + 1.0, 1.0) }
}
