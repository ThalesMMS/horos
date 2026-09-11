import Foundation

/// Where a cropped image sits, once it is no longer the whole image.
///
/// Cutting a rectangle out of an image and leaving Image Position (Patient)
/// alone puts the crop where the original was - so every measurement, every
/// reformat and every fusion against it is out by the offset of the corner. The
/// position of the new first pixel is the old position plus the two in-plane
/// directions, each travelled by the number of pixels dropped times the spacing
/// along it.
///
/// DICOM's names for those are worth stating, because getting them the wrong way
/// round is the usual mistake and the result still looks plausible:
/// Image Orientation (Patient) is the direction of increasing **column** index
/// first and of increasing **row** index second, while Pixel Spacing is the
/// distance between **rows** first and between **columns** second.
@objc(HorosCroppedImageGeometry)
public final class CroppedImageGeometry: NSObject {
    /// The Image Position (Patient) of a crop whose first pixel is the original's
    /// pixel at (`column`, `row`). Returns nil when the geometry it was given is
    /// not one it can use.
    @objc(positionForPosition:orientation:spacing:column:row:)
    public static func position(position: [NSNumber], orientation: [NSNumber],
                                spacing: [NSNumber], column: Int, row: Int) -> [NSNumber]? {
        guard position.count == 3, orientation.count == 6, spacing.count == 2 else { return nil }
        let origin = position.map { $0.doubleValue }
        let along = orientation.map { $0.doubleValue }
        let betweenRows = spacing[0].doubleValue          // vertical, along the row direction
        let betweenColumns = spacing[1].doubleValue       // horizontal, along the column direction
        guard betweenRows.isFinite, betweenColumns.isFinite,
              along.allSatisfy({ $0.isFinite }), origin.allSatisfy({ $0.isFinite })
        else { return nil }

        let columnDirection = Array(along[0 ..< 3])       // increasing column index
        let rowDirection = Array(along[3 ..< 6])          // increasing row index
        let moved = (0 ..< 3).map { axis in
            origin[axis]
                + columnDirection[axis] * Double(column) * betweenColumns
                + rowDirection[axis] * Double(row) * betweenRows
        }
        return moved.map { NSNumber(value: $0) }
    }

    /// A rectangle brought inside an image of this size, as (column, row, width,
    /// height). Empty when nothing of it is inside.
    @objc(rectangleInsideColumns:rows:column:row:width:height:)
    public static func rectangleInside(columns: Int, rows: Int,
                                       column: Int, row: Int,
                                       width: Int, height: Int) -> [NSNumber] {
        let left = max(0, min(column, columns))
        let top = max(0, min(row, rows))
        let right = max(left, min(column + max(width, 0), columns))
        let bottom = max(top, min(row + max(height, 0), rows))
        return [left, top, right - left, bottom - top].map { NSNumber(value: $0) }
    }
}
