import Foundation

/// One temporal volume: in-plane size, slice count and the backing buffer length.
@objc(HorosFourDTimeGeometry)
public final class FourDTimeGeometry: NSObject {
    @objc public let width: Int
    @objc public let height: Int
    @objc public let sliceCount: Int
    @objc public let bufferLength: Int

    @objc public var expectedBufferLength: Int {
        let voxels = sliceCount.multipliedReportingOverflow(by: width)
        guard !voxels.overflow else { return Int.max }
        let plane = voxels.partialValue.multipliedReportingOverflow(by: height)
        guard !plane.overflow else { return Int.max }
        let bytes = plane.partialValue.multipliedReportingOverflow(by: MemoryLayout<Float>.size)
        return bytes.overflow ? Int.max : bytes.partialValue
    }

    @objc(initWithWidth:height:sliceCount:bufferLength:)
    public init(width: Int, height: Int, sliceCount: Int, bufferLength: Int) {
        self.width = width
        self.height = height
        self.sliceCount = sliceCount
        self.bufferLength = bufferLength
        super.init()
    }
}

/// Bounds 4D play/pause and names geometry that reconstruction must not index.
@objc(HorosFourDSeriesGuard)
public final class FourDSeriesGuard: NSObject {
    @objc public static let timeCapacity = 500

    /// Always a valid subscript into `0 ..< count`, or 0 when there is no time.
    @objc(wrappedIndex:count:)
    public static func wrappedIndex(_ current: Int, count: Int) -> Int {
        guard count > 0 else { return 0 }
        if current >= 0 && current < count { return current }
        if current == Int.min { return 0 }
        let remainder = current % count
        return remainder >= 0 ? remainder : remainder + count
    }

    @objc(nextIndex:count:)
    public static func nextIndex(_ current: Int, count: Int) -> Int {
        guard count > 0 else { return 0 }
        if current == Int.max { return 0 }
        return wrappedIndex(current + 1, count: count)
    }

    /// Whether the 4D play control applies at all (#374, A224).
    ///
    /// One time point is a static 3D series: there is nothing to play through,
    /// and the control is switched off. More than one and it must be live.
    @objc(playControlAppliesWithTimeCount:)
    public static func playControlApplies(timeCount: Int) -> Bool {
        timeCount > 1
    }

    /// Whether what the operator can see matches what is happening.
    ///
    /// A movie still running behind a control that has been switched off is the
    /// state A224 refuses: the images keep changing and the button that would
    /// stop them cannot be pressed. A control that is off while nothing plays is
    /// fine, and so is one that is on either way.
    @objc(playControlIsCoherentWithEnabled:playing:)
    public static func playControlIsCoherent(enabled: Bool, playing: Bool) -> Bool {
        enabled || !playing
    }

    /// One time for pixList, fileList and volumeData. Surface Rendering used to
    /// pair the current pix with `fileList[0]`.
    @objc(alignedTimeIndexRequested:count:)
    public static func alignedTimeIndex(requested: Int, count: Int) -> Int {
        wrappedIndex(requested, count: count)
    }

    /// Static overlay (one time) stays at 0. Matching 4D counts share one wrap.
    @objc(fusionOverlayIndexForHostTime:hostCount:overlayCount:)
    public static func fusionOverlayIndex(hostTime: Int, hostCount: Int, overlayCount: Int) -> Int {
        if overlayCount <= 1 { return 0 }
        return wrappedIndex(hostTime, count: overlayCount)
    }

    /// Overlay with no times, or with N times where N is neither 1 nor the host
    /// count, cannot share the host 4D index.
    @objc(fusionRefusalHostTimes:overlayTimes:)
    public static func fusionRefusal(hostTimes: Int, overlayTimes: Int) -> String? {
        if overlayTimes <= 0 {
            return emptyReason(at: 0)
        }
        if overlayTimes == 1 || overlayTimes == hostTimes {
            return nil
        }
        let format = NSLocalizedString("The fused series has %d times, not %d.",
                                        comment: "alert; overlay 4D time count versus the host")
        return String(format: format, overlayTimes, max(0, hostTimes))
    }

    @objc(canStoreTimeAt:capacity:)
    public static func canStoreTime(at index: Int, capacity: Int) -> Bool {
        return capacity > 0 && index >= 0 && index < capacity
    }

    @objc(capacityReasonAt:capacity:)
    public static func capacityReason(at index: Int, capacity: Int) -> String? {
        guard !canStoreTime(at: index, capacity: capacity) else { return nil }
        let format = NSLocalizedString("4D Player is limited to a maximum number of %d series.",
                                        comment: "alert when a 4D series would overflow the time slots")
        return String(format: format, max(0, capacity))
    }

    @objc(geometryFromPixList:volume:)
    public static func geometry(fromPixList pixList: NSArray?, volume: NSData?) -> FourDTimeGeometry? {
        guard let pixList, pixList.count > 0 else { return nil }
        let first = dimensions(pixList[0])
        return FourDTimeGeometry(width: first.width, height: first.height,
                                  sliceCount: pixList.count, bufferLength: volume?.length ?? 0)
    }

    @objc(reasonForInconsistentSlices:atTime:)
    public static func reasonForInconsistentSlices(_ pixList: NSArray?, atTime time: Int) -> String? {
        guard let pixList, pixList.count > 0 else {
            return emptyReason(at: time)
        }
        let first = dimensions(pixList[0])
        guard first.width > 0, first.height > 0 else { return emptyReason(at: time) }
        for item in pixList {
            let size = dimensions(item)
            if size.width != first.width || size.height != first.height {
                return sizeReason(at: time, width: size.width, height: size.height,
                                   expectedWidth: first.width, expectedHeight: first.height)
            }
        }
        return nil
    }

    @objc(reconstructionRefusalComparing:to:atTime:)
    public static func reconstructionRefusal(comparing candidate: FourDTimeGeometry?,
                                           to reference: FourDTimeGeometry?,
                                           at time: Int) -> String? {
        guard let candidate, candidate.width > 0, candidate.height > 0, candidate.sliceCount > 0 else {
            return emptyReason(at: time)
        }
        guard let reference, reference.width > 0, reference.height > 0, reference.sliceCount > 0 else {
            return emptyReason(at: 0)
        }
        if candidate.sliceCount != reference.sliceCount {
            let format = NSLocalizedString("Time %d has %d slices, not %d.",
                                          comment: "alert; the first number is the 1-based time")
            return String(format: format, time + 1, candidate.sliceCount, reference.sliceCount)
        }
        if candidate.width != reference.width || candidate.height != reference.height {
            return sizeReason(at: time, width: candidate.width, height: candidate.height,
                               expectedWidth: reference.width, expectedHeight: reference.height)
        }
        if candidate.bufferLength < candidate.expectedBufferLength {
            let format = NSLocalizedString("Time %d volume is %d bytes, not %d.",
                                          comment: "alert; the first number is the 1-based time")
            return String(format: format, time + 1, candidate.bufferLength, candidate.expectedBufferLength)
        }
        return nil
    }

    private static func dimensions(_ pix: Any) -> (width: Int, height: Int) {
        guard let object = pix as? NSObject else { return (0, 0) }
        let width = (object.value(forKey: "pwidth") as? NSNumber)?.intValue ?? 0
        let height = (object.value(forKey: "pheight") as? NSNumber)?.intValue ?? 0
        return (width, height)
    }

    private static func emptyReason(at time: Int) -> String {
        let format = NSLocalizedString("Time %d has no frames.",
                                       comment: "alert; the number is the 1-based time")
        return String(format: format, time + 1)
    }

    private static func sizeReason(at time: Int, width: Int, height: Int,
                                     expectedWidth: Int, expectedHeight: Int) -> String {
        let format = NSLocalizedString("Time %d is %d by %d, not %d by %d.",
                                        comment: "alert; the first number is the 1-based time")
        return String(format: format, time + 1, width, height, expectedWidth, expectedHeight)
    }
}
