import Foundation

/// A scissor or fillROI request brought inside one volume, or refused.
///
/// `applyScissor` walks every plane of the current orientation and asks
/// `fillROI` to write that plane. The volume is one contiguous float buffer of
/// width × height × slices. A stack index past the axis, a clip that is not a
/// plane of that orientation, or a restore whose slice is missing, is how a
/// write lands past the last voxel — the MRA scissor crash was one allocation
/// past a 512×512×204 buffer. This object is the check those callers share:
/// either a plan whose every write stays inside, or a reason the geometry is
/// not one they can use. Undo stores the same voxels as 16-bit samples; its
/// byte count is refused when the multiply does not fit.
@objc(HorosVRScissorPlan)
public final class VRScissorPlan: NSObject {
    @objc public let accepted: Bool
    /// `pixList` index of the `DCMPix` whose `fImage` is the start of the write.
    /// Axial cuts address that slice; the other two orientations always start at 0.
    @objc public let pixIndex: Int
    @objc public let stackNo: Int
    @objc public let orientation: Int
    @objc public let restore: Bool
    @objc public let clipMinX: Double
    @objc public let clipMinY: Double
    @objc public let clipMaxX: Double
    @objc public let clipMaxY: Double
    /// In-plane X run length: height on a sagittal cut, width otherwise.
    @objc public let planeWidth: Int
    @objc public let planeHeight: Int
    @objc public let undoBytes: Int
    @objc public let reason: String

    @objc public init(accepted: Bool, pixIndex: Int, stackNo: Int, orientation: Int,
                      restore: Bool, clipMinX: Double, clipMinY: Double,
                      clipMaxX: Double, clipMaxY: Double,
                      planeWidth: Int, planeHeight: Int, undoBytes: Int, reason: String) {
        self.accepted = accepted
        self.pixIndex = pixIndex
        self.stackNo = stackNo
        self.orientation = orientation
        self.restore = restore
        self.clipMinX = clipMinX
        self.clipMinY = clipMinY
        self.clipMaxX = clipMaxX
        self.clipMaxY = clipMaxY
        self.planeWidth = planeWidth
        self.planeHeight = planeHeight
        self.undoBytes = undoBytes
        self.reason = reason
    }
}

@objc(HorosVRScissorBounds)
public final class VRScissorBounds: NSObject {
    /// Same numbering as `VRController applyScissor` / `DCMPix fillROI`:
    /// 0 sagittal (X stack), 1 coronal (Y stack), 2 axial (Z stack).
    @objc(planWithWidth:height:sliceCount:orientation:stackNo:restore:clipMinX:clipMinY:clipMaxX:clipMaxY:)
    public static func plan(width: Int, height: Int, sliceCount: Int,
                            orientation: Int, stackNo: Int, restore: Bool,
                            clipMinX: Double, clipMinY: Double,
                            clipMaxX: Double, clipMaxY: Double) -> VRScissorPlan {
        func refuse(_ reason: String) -> VRScissorPlan {
            VRScissorPlan(accepted: false, pixIndex: 0, stackNo: stackNo,
                          orientation: orientation, restore: false,
                          clipMinX: 0, clipMinY: 0, clipMaxX: 0, clipMaxY: 0,
                          planeWidth: 0, planeHeight: 0, undoBytes: 0, reason: reason)
        }

        guard width > 0, height > 0, sliceCount > 0 else {
            return refuse("volume has no voxels")
        }
        guard let axis = Axis(rawValue: orientation) else {
            return refuse("orientation is not a volume axis")
        }
        guard axis.stackRange(width: width, height: height, sliceCount: sliceCount).contains(stackNo) else {
            return refuse("stack is outside the volume")
        }

        var useRestore = restore
        if restore {
            if stackNo < 0 {
                return refuse("restore needs a slice")
            }
            if axis == .axial && !((0 ..< sliceCount).contains(stackNo)) {
                return refuse("restore slice is outside the volume")
            }
            if sliceCount <= 0 {
                useRestore = false
            }
        }

        let plane = axis.planeSize(width: width, height: height, sliceCount: sliceCount)
        var minX = clipMinX, minY = clipMinY, maxX = clipMaxX, maxY = clipMaxY
        if minX == 0 && maxX == 0 && minY == 0 && maxY == 0 {
            minX = 0
            minY = 0
            maxX = Double(plane.width)
            maxY = Double(plane.height)
        }
        guard minX.isFinite, minY.isFinite, maxX.isFinite, maxY.isFinite else {
            return refuse("clip is not a finite rectangle")
        }

        minX = min(max(minX, 0), Double(plane.width))
        minY = min(max(minY, 0), Double(plane.height))
        maxX = min(max(maxX, 0), Double(plane.width))
        maxY = min(max(maxY, 0), Double(plane.height))
        if maxX < minX { swap(&maxX, &minX) }
        if maxY < minY { swap(&maxY, &minY) }
        guard maxX > minX && maxY > minY else {
            return refuse("clip does not cover any pixel")
        }

        let bytes = undoByteCount(width: width, height: height, sliceCount: sliceCount)
        guard bytes > 0 else {
            return refuse("undo buffer is larger than addressable memory")
        }

        return VRScissorPlan(
            accepted: true,
            pixIndex: axis == .axial ? stackNo : 0,
            stackNo: stackNo,
            orientation: axis.rawValue,
            restore: useRestore,
            clipMinX: minX, clipMinY: minY, clipMaxX: maxX, clipMaxY: maxY,
            planeWidth: plane.width, planeHeight: plane.height,
            undoBytes: bytes,
            reason: "")
    }

    /// 16-bit undo snapshot of the float volume. Zero when the size cannot be formed.
    @objc(undoByteCountForWidth:height:sliceCount:)
    public static func undoByteCount(width: Int, height: Int, sliceCount: Int) -> Int {
        guard width > 0, height > 0, sliceCount > 0 else { return 0 }
        let rows = width.multipliedReportingOverflow(by: height)
        guard !rows.overflow else { return 0 }
        let voxels = rows.partialValue.multipliedReportingOverflow(by: sliceCount)
        guard !voxels.overflow else { return 0 }
        let bytes = voxels.partialValue.multipliedReportingOverflow(by: MemoryLayout<UInt16>.size)
        guard !bytes.overflow, bytes.partialValue > 0 else { return 0 }
        return bytes.partialValue
    }

    /// The part of a brush texture that lies on the slice, as (column, row, width, height).
    @objc(textureInsideColumns:rows:originX:originY:width:height:)
    public static func textureInside(columns: Int, rows: Int,
                                     originX: Int, originY: Int,
                                     width: Int, height: Int) -> [NSNumber] {
        let left = max(0, min(originX, columns))
        let top = max(0, min(originY, rows))
        let right = max(left, min(originX + max(width, 0), columns))
        let bottom = max(top, min(originY + max(height, 0), rows))
        return [left, top, right - left, bottom - top].map { NSNumber(value: $0) }
    }

    /// Linear index into the contiguous volume, or nil when that sample is not inside it.
    @objc(voxelIndexWithWidth:height:sliceCount:orientation:stackNo:planeX:planeY:)
    public static func voxelIndex(width: Int, height: Int, sliceCount: Int,
                                  orientation: Int, stackNo: Int,
                                  planeX: Int, planeY: Int) -> NSNumber? {
        guard let axis = Axis(rawValue: orientation),
              width > 0, height > 0, sliceCount > 0,
              axis.stackRange(width: width, height: height, sliceCount: sliceCount).contains(stackNo)
        else { return nil }
        let plane = axis.planeSize(width: width, height: height, sliceCount: sliceCount)
        guard (0 ..< plane.width).contains(planeX), (0 ..< plane.height).contains(planeY) else { return nil }
        let slab = width * height
        let index: Int
        switch axis {
        case .sagittal:
            index = planeY * slab + planeX * width + stackNo
        case .coronal:
            index = planeY * slab + stackNo * width + planeX
        case .axial:
            index = stackNo * slab + planeY * width + planeX
        }
        let limit = slab * sliceCount
        guard (0 ..< limit).contains(index) else { return nil }
        return NSNumber(value: index)
    }

    private enum Axis: Int {
        case sagittal = 0
        case coronal = 1
        case axial = 2

        func stackRange(width: Int, height: Int, sliceCount: Int) -> Range<Int> {
            switch self {
            case .sagittal: return 0 ..< width
            case .coronal: return 0 ..< height
            case .axial: return 0 ..< sliceCount
            }
        }

        func planeSize(width: Int, height: Int, sliceCount: Int) -> (width: Int, height: Int) {
            switch self {
            case .sagittal: return (height, sliceCount)
            case .coronal: return (width, sliceCount)
            case .axial: return (width, height)
            }
        }
    }
}
