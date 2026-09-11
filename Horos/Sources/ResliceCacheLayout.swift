import Foundation

/// Where a voxel sits in the orthogonal reslice cache (#374, A225).
///
/// The Y reslice keeps one **transposed** copy of every source image, so that a
/// column of the source — which is a row of the resliced image — is contiguous
/// and can be copied with one `memcpy`. The filling operation writes it that
/// way: for each of the `width` columns it lays down `height` consecutive
/// values.
///
/// That layout was then written out again at each of the two places that read it
/// back, and one of them multiplied by the wrong side:
///
///     srcP = Ycache + y*newTotal*newX + i * w;         // height: right
///     srcP = Ycache + y*newTotal*newX + i * newTotal;  // width: wrong
///
/// On a square image the two are the same and nothing shows. On any other, the
/// second walks the cache at the wrong stride — which is a hatched slice, the
/// symptom A225 describes — and for a column near the end it reads past the
/// slice, and past the buffer entirely on the last one.
///
/// The layout is stated once here so the three sites cannot disagree again.
@objc(HorosResliceCacheLayout)
public final class ResliceCacheLayout: NSObject {
    /// Floats in the whole cache: one transposed image per slice.
    @objc(elementCountForWidth:height:slices:)
    public static func elementCount(width: Int, height: Int, slices: Int) -> Int {
        guard width > 0, height > 0, slices > 0 else { return 0 }
        return width * height * slices
    }

    /// First element of a slice's transposed image.
    @objc(sliceBaseForSlice:width:height:)
    public static func sliceBase(slice: Int, width: Int, height: Int) -> Int {
        slice * width * height
    }

    /// A column of the source is `height` values long and they are contiguous,
    /// so columns are `height` apart — never `width`.
    @objc(columnOffsetForColumn:height:)
    public static func columnOffset(column: Int, height: Int) -> Int {
        column * height
    }

    /// One voxel, for a test to walk the whole cache.
    @objc(offsetForSlice:column:row:width:height:)
    public static func offset(slice: Int, column: Int, row: Int,
                              width: Int, height: Int) -> Int {
        sliceBase(slice: slice, width: width, height: height)
            + columnOffset(column: column, height: height) + row
    }

    /// Whether a column's `height` values all lie inside the cache. The stride
    /// that was wrong made this false for columns near the end of a wide image.
    @objc(columnFitsForSlice:column:width:height:slices:)
    public static func columnFits(slice: Int, column: Int,
                                  width: Int, height: Int, slices: Int) -> Bool {
        guard slice >= 0, column >= 0, column < width else { return false }
        let start = offset(slice: slice, column: column, row: 0, width: width, height: height)
        return start >= 0 && start + height <= elementCount(width: width, height: height, slices: slices)
    }
}
