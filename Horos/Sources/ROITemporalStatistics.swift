import Foundation

/// Mean / min / max of finite samples from a reconstructed MPR plane at one 4D time.
@objc(HorosROIIntensityStats)
public final class ROIIntensityStats: NSObject {
    @objc public let mean: Double
    @objc public let minimum: Double
    @objc public let maximum: Double
    @objc public let sampleCount: Int
    @objc public let timeIndex: Int
    @objc public let geometryIdentity: String

    @objc public init(mean: Double, minimum: Double, maximum: Double,
                      sampleCount: Int, timeIndex: Int, geometryIdentity: String) {
        self.mean = mean
        self.minimum = minimum
        self.maximum = maximum
        self.sampleCount = sampleCount
        self.timeIndex = timeIndex
        self.geometryIdentity = geometryIdentity
    }
}

/// Cached intensity values are valid only for the time and geometry that produced them.
@objc(HorosROITemporalValueCache)
public final class ROITemporalValueCache: NSObject {
    private var stored: ROIIntensityStats?

    @objc public func store(_ stats: ROIIntensityStats) {
        stored = stats
    }

    @objc(storedValuesMatchingTimeIndex:geometryIdentity:)
    public func storedValues(matchingTimeIndex timeIndex: Int, geometryIdentity: String) -> ROIIntensityStats? {
        guard let stored,
              stored.timeIndex == timeIndex,
              stored.geometryIdentity == geometryIdentity else { return nil }
        return stored
    }
}

/// Identity of an MPR ROI across 4D time steps. Time changes do not rewrite the region.
@objc(HorosROITemporalBinding)
public final class ROITemporalBinding: NSObject {
    @objc public let identity: String
    @objc public let geometryFingerprint: String
    @objc public let timeIndex: Int

    @objc public init(identity: String, geometryFingerprint: String, timeIndex: Int) {
        self.identity = identity
        self.geometryFingerprint = geometryFingerprint
        self.timeIndex = timeIndex
    }

    @objc(switchingTimeTo:)
    public func switchingTime(to newTime: Int) -> ROITemporalBinding {
        ROITemporalBinding(identity: identity, geometryFingerprint: geometryFingerprint, timeIndex: newTime)
    }

    /// A different sampled region is applied only when the caller asked to propagate.
    @objc(applyingGeometry:atTime:explicitPropagation:)
    public func applyingGeometry(_ fingerprint: String, atTime newTime: Int, explicitPropagation: Bool) -> ROITemporalBinding? {
        if fingerprint == geometryFingerprint {
            return ROITemporalBinding(identity: identity, geometryFingerprint: fingerprint, timeIndex: newTime)
        }
        guard explicitPropagation else { return nil }
        return ROITemporalBinding(identity: identity, geometryFingerprint: fingerprint, timeIndex: newTime)
    }

    @objc public var propertyList: [String: Any] {
        ["identity": identity, "geometryFingerprint": geometryFingerprint, "timeIndex": timeIndex]
    }

    @objc(restoredFrom:)
    public static func restored(from propertyList: [String: Any]) -> ROITemporalBinding? {
        guard let identity = propertyList["identity"] as? String, !identity.isEmpty,
              let fingerprint = propertyList["geometryFingerprint"] as? String, !fingerprint.isEmpty,
              let time = propertyList["timeIndex"] as? Int else { return nil }
        return ROITemporalBinding(identity: identity, geometryFingerprint: fingerprint, timeIndex: time)
    }
}

/// Independent 4D MPR ROI sampling: reconstruct an oblique plane, then mean/min/max.
/// Cached values from another time are never reused, even when the geometry is unchanged.
@objc(HorosROITemporalStatistics)
public final class ROITemporalStatistics: NSObject {
    /// Cached mean/min/max remain valid only for the same time and sampled region.
    @objc(cachedValuesRemainValidWithPreviousTimeIndex:currentTimeIndex:geometryUnchanged:)
    public static func cachedValuesRemainValid(previousTimeIndex: Int, currentTimeIndex: Int, geometryUnchanged: Bool) -> Bool {
        geometryUnchanged && previousTimeIndex == currentTimeIndex
    }

    /// A new reconstructed buffer (including a 4D time step) cannot keep previous intensities.
    @objc public static func mustRefreshCachedValuesAfterReconstructedBufferChange() -> Bool {
        true
    }

    @objc(geometryFingerprintMinX:minY:maxX:maxY:originX:originY:originZ:rowX:rowY:rowZ:colX:colY:colZ:)
    public static func geometryFingerprint(minX: Int, minY: Int, maxX: Int, maxY: Int,
                                           originX: Double, originY: Double, originZ: Double,
                                           rowX: Double, rowY: Double, rowZ: Double,
                                           colX: Double, colY: Double, colZ: Double) -> String {
        "\(minX),\(minY),\(maxX),\(maxY)|\(originX),\(originY),\(originZ)|\(rowX),\(rowY),\(rowZ)|\(colX),\(colY),\(colZ)"
    }

    /// Nearest-neighbour sample of a volume onto a plane. Coordinates are voxel indices.
    /// Out-of-bounds pixels are NaN and are ignored by `sampleRectangle`.
    @objc(reconstructNearestFromVolume:width:height:depth:planeWidth:planeHeight:originX:originY:originZ:rowX:rowY:rowZ:colX:colY:colZ:into:)
    public static func reconstructNearest(volume: UnsafePointer<Float>,
                                          width: Int, height: Int, depth: Int,
                                          planeWidth: Int, planeHeight: Int,
                                          originX: Double, originY: Double, originZ: Double,
                                          rowX: Double, rowY: Double, rowZ: Double,
                                          colX: Double, colY: Double, colZ: Double,
                                          into output: UnsafeMutablePointer<Float>) {
        guard width > 0, height > 0, depth > 0, planeWidth > 0, planeHeight > 0 else { return }
        for j in 0..<planeHeight {
            for i in 0..<planeWidth {
                let x = originX + Double(i) * rowX + Double(j) * colX
                let y = originY + Double(i) * rowY + Double(j) * colY
                let z = originZ + Double(i) * rowZ + Double(j) * colZ
                let xi = Int(x.rounded())
                let yi = Int(y.rounded())
                let zi = Int(z.rounded())
                let index = i + j * planeWidth
                if xi >= 0, xi < width, yi >= 0, yi < height, zi >= 0, zi < depth {
                    output[index] = volume[xi + width * (yi + height * zi)]
                } else {
                    output[index] = .nan
                }
            }
        }
    }

    /// Inclusive rectangle in reconstructed pixels. Non-finite samples are ignored.
    @objc(sampleRectangleMinX:minY:maxX:maxY:inBuffer:width:height:timeIndex:geometryIdentity:)
    public static func sampleRectangle(minX: Int, minY: Int, maxX: Int, maxY: Int,
                                       in buffer: UnsafePointer<Float>,
                                       width: Int, height: Int,
                                       timeIndex: Int,
                                       geometryIdentity: String) -> ROIIntensityStats? {
        guard width > 0, height > 0, maxX >= minX, maxY >= minY else { return nil }
        var total = 0.0
        var minimum = Double.infinity
        var maximum = -Double.infinity
        var count = 0
        let x0 = max(minX, 0)
        let y0 = max(minY, 0)
        let x1 = min(maxX, width - 1)
        let y1 = min(maxY, height - 1)
        guard x1 >= x0, y1 >= y0 else { return nil }
        for y in y0...y1 {
            for x in x0...x1 {
                let value = Double(buffer[x + y * width])
                guard value.isFinite else { continue }
                total += value
                if value < minimum { minimum = value }
                if value > maximum { maximum = value }
                count += 1
            }
        }
        guard count > 0 else { return nil }
        return ROIIntensityStats(mean: total / Double(count),
                                 minimum: minimum,
                                 maximum: maximum,
                                 sampleCount: count,
                                 timeIndex: timeIndex,
                                 geometryIdentity: geometryIdentity)
    }
}
