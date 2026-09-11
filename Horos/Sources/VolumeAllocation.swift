import Foundation

/// How much memory a volume needs, and how to say so (#375, A214).
///
/// A214 asks that limit dimensions either render or produce an **explicit
/// diagnosis or fallback** — never a silent black film, and never a forced
/// reduction. The allocation guards that stand in front of the 3D engine, the
/// reslicing and the resampling used to fail with a dialogue titled "32-bit"
/// telling the operator to *upgrade to OsiriX 64-bit or OsiriX MD*. On this
/// arm64-only, 64-bit-only product (#369, #370) that is false, unactionable, and
/// names a different application — and it says nothing about what was actually
/// too large.
///
/// This computes the size that was refused and phrases it, so the diagnosis can
/// name the matrix instead.
@objc(HorosVolumeAllocation)
public final class VolumeAllocation: NSObject {
    /// Bytes for `width × height × slices × bytesPerVoxel`, saturating rather
    /// than wrapping: a wrapped product would ask for a small buffer, get it,
    /// and fail later as a black frame — which is the outcome A214 refuses.
    @objc(byteCountForWidth:height:slices:bytesPerVoxel:)
    public static func byteCount(width: Int, height: Int, slices: Int, bytesPerVoxel: Int) -> Int {
        let terms = [width, height, slices, bytesPerVoxel]
        guard terms.allSatisfy({ $0 > 0 }) else { return 0 }
        var total = 1
        for term in terms {
            let product = total.multipliedReportingOverflow(by: term)
            if product.overflow { return Int.max }
            total = product.partialValue
        }
        return total
    }

    /// A size an operator can act on: "1.4 GB", not 1503238553.
    @objc(describeByteCount:)
    public static func describe(byteCount: Int) -> String {
        guard byteCount > 0 else { return "0 bytes" }
        if byteCount == Int.max { return "more memory than this machine can address" }
        let units = ["bytes", "kB", "MB", "GB", "TB"]
        var value = Double(byteCount)
        var unit = 0
        while value >= 1024 && unit < units.count - 1 {
            value /= 1024
            unit += 1
        }
        if unit == 0 { return "\(byteCount) bytes" }
        return String(format: value >= 100 ? "%.0f %@" : "%.1f %@", value, units[unit])
    }

    /// `width × height × slices`, for a message that names what was refused.
    @objc(describeMatrixWithWidth:height:slices:)
    public static func describeMatrix(width: Int, height: Int, slices: Int) -> String {
        "\(width) × \(height) × \(slices)"
    }
}
