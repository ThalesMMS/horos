import Foundation
import CoreGraphics
import simd

/// Longitudinal registration, companion overlays and guided ROI copy (#378).
///
/// Everything here is geometry in DICOM patient millimetres (LPS). The viewer
/// keeps its volumes, ROI objects, undo queue and fusion controls; this file
/// only computes transforms, judges their quality and plans where copied ROIs
/// land. Tolerances are fixed here, before any comparison, and every refusal
/// carries its reason. No transform is ever produced by a silent fallback: a
/// degenerate, insufficient or poorly overlapping registration is reported as
/// such and the caller must not draw anything as aligned.

// MARK: - Transform

/// Rigid transform from a moving series' patient frame into a fixed series'
/// patient frame. Row-major 4×4 for ObjC callers; `simd` inside.
@objc(HorosRegistrationTransform)
public final class RegistrationTransform: NSObject {
    public static let algorithmName = "Horn 1987 closed-form quaternion, rigid (rotation + translation), Swift"
    public static let algorithmVersion = "1.0 (#378, 2026-09-13)"

    public let matrix: double4x4
    @objc public let algorithm: String
    @objc public let version: String

    public init(matrix: double4x4, algorithm: String = RegistrationTransform.algorithmName,
                version: String = RegistrationTransform.algorithmVersion) {
        self.matrix = matrix; self.algorithm = algorithm; self.version = version
    }

    /// The identity: the two series share a Frame of Reference, so no transform is estimated.
    @objc public static let identity = RegistrationTransform(matrix: matrix_identity_double4x4,
                                                             algorithm: "Identity (shared Frame of Reference)",
                                                             version: RegistrationTransform.algorithmVersion)

    @objc public var isIdentity: Bool {
        var maximum = 0.0
        for c in 0..<4 { for r in 0..<4 { maximum = max(maximum, abs(matrix[c][r] - matrix_identity_double4x4[c][r])) } }
        return maximum < 1e-12
    }

    /// Row-major 16 numbers, the convention the host's VTK and ITK routes use.
    @objc public var rowMajor: [Double] {
        var out: [Double] = []
        for r in 0..<4 { for c in 0..<4 { out.append(matrix[c][r]) } }
        return out
    }

    @objc public convenience init?(rowMajor: [Double]) {
        guard rowMajor.count == 16, rowMajor.allSatisfy(\.isFinite) else { return nil }
        var m = matrix_identity_double4x4
        for r in 0..<4 { for c in 0..<4 { m[c][r] = rowMajor[r * 4 + c] } }
        self.init(matrix: m)
    }

    @objc public var inverse: RegistrationTransform {
        RegistrationTransform(matrix: matrix.inverse, algorithm: algorithm + " (inverse)", version: version)
    }

    public func apply(_ p: SIMD3<Double>) -> SIMD3<Double> {
        let h = matrix * SIMD4(p.x, p.y, p.z, 1)
        return SIMD3(h.x, h.y, h.z)
    }

    /// Rotates a direction (no translation).
    public func rotate(_ d: SIMD3<Double>) -> SIMD3<Double> {
        let h = matrix * SIMD4(d.x, d.y, d.z, 0)
        return SIMD3(h.x, h.y, h.z)
    }

    @objc public func apply(_ point: [Double]) -> [Double] {
        guard point.count == 3 else { return point }
        let q = apply(SIMD3(point[0], point[1], point[2]))
        return [q.x, q.y, q.z]
    }

    @objc public func concatenated(after other: RegistrationTransform) -> RegistrationTransform {
        RegistrationTransform(matrix: matrix * other.matrix, algorithm: algorithm, version: version)
    }
}

// MARK: - Quality

@objc(HorosRegistrationVerdict)
public enum RegistrationVerdict: Int {
    case accepted = 0
    case warning
    case rejected
}

/// The numbers a user sees next to an overlay, and the verdict they imply.
/// Thresholds are the acceptance tolerances and do not move per case.
@objc(HorosRegistrationQuality)
public final class RegistrationQuality: NSObject {
    @objc public static let acceptedRMSMM = 2.0
    @objc public static let warningRMSMM = 5.0
    @objc public static let acceptedOverlap = 0.5
    @objc public static let minimumOverlap = 0.25

    @objc public let landmarkCount: Int
    @objc public let rmsMM: Double
    @objc public let maxMM: Double
    @objc public let overlapFraction: Double
    @objc public let verdict: RegistrationVerdict
    @objc public let reasons: [String]

    public init(landmarkCount: Int, rmsMM: Double, maxMM: Double, overlapFraction: Double) {
        self.landmarkCount = landmarkCount; self.rmsMM = rmsMM; self.maxMM = maxMM; self.overlapFraction = overlapFraction
        var reasons: [String] = []
        var verdict = RegistrationVerdict.accepted
        if !rmsMM.isFinite || !maxMM.isFinite || !overlapFraction.isFinite {
            verdict = .rejected; reasons.append("Registration produced non-finite numbers.")
        }
        if rmsMM > RegistrationQuality.warningRMSMM {
            verdict = .rejected
            reasons.append(String(format: "Landmark RMS error %.2f mm exceeds %.1f mm.", rmsMM, RegistrationQuality.warningRMSMM))
        } else if rmsMM > RegistrationQuality.acceptedRMSMM {
            verdict = worse(verdict, .warning)
            reasons.append(String(format: "Landmark RMS error %.2f mm exceeds %.1f mm.", rmsMM, RegistrationQuality.acceptedRMSMM))
        }
        if overlapFraction < RegistrationQuality.minimumOverlap {
            verdict = .rejected
            reasons.append(String(format: "Only %.0f %% of the moving volume overlaps the fixed volume after registration.", overlapFraction * 100))
        } else if overlapFraction < RegistrationQuality.acceptedOverlap {
            verdict = worse(verdict, .warning)
            reasons.append(String(format: "Only %.0f %% of the moving volume overlaps the fixed volume.", overlapFraction * 100))
        }
        self.verdict = verdict
        self.reasons = reasons
    }

    @objc public var summary: String {
        let label = ["accepted", "warning", "rejected"][verdict.rawValue]
        var text = String(format: "%@: %ld landmark(s), RMS %.2f mm, max %.2f mm, overlap %.0f %%",
                          label, landmarkCount, rmsMM, maxMM, overlapFraction * 100)
        if !reasons.isEmpty { text += ". " + reasons.joined(separator: " ") }
        return text
    }
}

private func worse(_ a: RegistrationVerdict, _ b: RegistrationVerdict) -> RegistrationVerdict {
    a.rawValue >= b.rawValue ? a : b
}

/// Axis-aligned bounds of a volume in its own patient frame, used for overlap.
@objc(HorosVolumeBounds)
public final class VolumeBounds: NSObject {
    @objc public let minimum: [Double]
    @objc public let maximum: [Double]
    @objc public init?(minimum: [Double], maximum: [Double]) {
        guard minimum.count == 3, maximum.count == 3, minimum.allSatisfy(\.isFinite), maximum.allSatisfy(\.isFinite),
              zip(minimum, maximum).allSatisfy({ $0 <= $1 }) else { return nil }
        self.minimum = minimum; self.maximum = maximum
    }
    var corners: [SIMD3<Double>] {
        var out: [SIMD3<Double>] = []
        for i in 0..<8 {
            out.append(SIMD3(i & 1 == 0 ? minimum[0] : maximum[0], i & 2 == 0 ? minimum[1] : maximum[1], i & 4 == 0 ? minimum[2] : maximum[2]))
        }
        return out
    }
    var volume: Double { (maximum[0] - minimum[0]) * (maximum[1] - minimum[1]) * (maximum[2] - minimum[2]) }

    /// Fraction of `moving`'s box that lies inside `fixed` after `transform`,
    /// measured on the transformed box's axis-aligned envelope. A box is a
    /// coarse proxy; it exists to refuse a registration that carried one
    /// volume away from the other, not to grade a good one.
    public static func overlap(moving: VolumeBounds, fixed: VolumeBounds, transform: RegistrationTransform) -> Double {
        let moved = moving.corners.map { transform.apply($0) }
        let lo = SIMD3(moved.map(\.x).min()!, moved.map(\.y).min()!, moved.map(\.z).min()!)
        let hi = SIMD3(moved.map(\.x).max()!, moved.map(\.y).max()!, moved.map(\.z).max()!)
        let movedVolume = (hi.x - lo.x) * (hi.y - lo.y) * (hi.z - lo.z)
        guard movedVolume > 0 else { return 0 }
        var inter = 1.0
        for axis in 0..<3 {
            let a = max(lo[axis], fixed.minimum[axis]), b = min(hi[axis], fixed.maximum[axis])
            if b <= a { return 0 }
            inter *= b - a
        }
        return inter / movedVolume
    }
}

// MARK: - Landmark registration

@objc(HorosLandmarkRegistrationResult)
public final class LandmarkRegistrationResult: NSObject {
    @objc public let transform: RegistrationTransform?
    @objc public let quality: RegistrationQuality?
    @objc public let refusal: String?
    init(transform: RegistrationTransform?, quality: RegistrationQuality?, refusal: String?) {
        self.transform = transform; self.quality = quality; self.refusal = refusal
    }
    @objc public var isUsable: Bool { transform != nil && quality != nil && quality!.verdict != .rejected }
}

/// Named landmark pairs → rigid transform. Names pair the points, as the
/// host's 3-point route does; the same number on both sides, at least three,
/// no repeated name, not collinear. Scale is not estimated: two series of the
/// same patient share millimetres.
@objc(HorosLandmarkRegistration)
public final class LandmarkRegistration: NSObject {
    @objc public static let minimumLandmarks = 3
    @objc public static let collinearityToleranceMM = 0.1

    @objc public static func solve(fixedNames: [String], fixedPoints: [[Double]],
                                   movingNames: [String], movingPoints: [[Double]],
                                   movingBounds: VolumeBounds?, fixedBounds: VolumeBounds?) -> LandmarkRegistrationResult {
        func refuse(_ why: String) -> LandmarkRegistrationResult { LandmarkRegistrationResult(transform: nil, quality: nil, refusal: why) }
        guard fixedNames.count == fixedPoints.count, movingNames.count == movingPoints.count else {
            return refuse("Landmark names and points do not match in count.")
        }
        guard fixedPoints.count == movingPoints.count else {
            return refuse("Needs the same number of landmarks on both series (\(fixedPoints.count) fixed, \(movingPoints.count) moving).")
        }
        guard fixedPoints.count >= minimumLandmarks else {
            return refuse("Needs at least \(minimumLandmarks) named landmarks on each series; found \(fixedPoints.count).")
        }
        if Set(fixedNames).count != fixedNames.count || Set(movingNames).count != movingNames.count {
            return refuse("A landmark name is repeated; each name must appear once per series.")
        }
        guard Set(fixedNames) == Set(movingNames) else {
            let missing = Set(fixedNames).symmetricDifference(Set(movingNames)).sorted()
            return refuse("Landmark names do not pair two by two: \(missing.joined(separator: ", ")).")
        }
        guard fixedPoints.allSatisfy({ $0.count == 3 && $0.allSatisfy(\.isFinite) }),
              movingPoints.allSatisfy({ $0.count == 3 && $0.allSatisfy(\.isFinite) }) else {
            return refuse("A landmark has no finite patient coordinates.")
        }
        let order = fixedNames.indices.sorted { fixedNames[$0] < fixedNames[$1] }
        let movingIndex = Dictionary(uniqueKeysWithValues: movingNames.enumerated().map { ($1, $0) })
        let fixed = order.map { SIMD3(fixedPoints[$0][0], fixedPoints[$0][1], fixedPoints[$0][2]) }
        let moving = order.map { i -> SIMD3<Double> in let p = movingPoints[movingIndex[fixedNames[i]]!]; return SIMD3(p[0], p[1], p[2]) }
        if isCollinear(fixed) || isCollinear(moving) {
            return refuse("The landmarks are collinear; a rigid transform is not determined.")
        }
        guard let transform = horn(moving: moving, fixed: fixed) else {
            return refuse("The landmark configuration is degenerate; no rotation could be solved.")
        }
        var sum = 0.0, worst = 0.0
        for (m, f) in zip(moving, fixed) {
            let e = simd_length(transform.apply(m) - f)
            sum += e * e; worst = max(worst, e)
        }
        let rms = (sum / Double(fixed.count)).squareRoot()
        var overlap = 1.0
        if let mb = movingBounds, let fb = fixedBounds { overlap = VolumeBounds.overlap(moving: mb, fixed: fb, transform: transform) }
        let quality = RegistrationQuality(landmarkCount: fixed.count, rmsMM: rms, maxMM: worst, overlapFraction: overlap)
        return LandmarkRegistrationResult(transform: transform, quality: quality, refusal: nil)
    }

    static func isCollinear(_ points: [SIMD3<Double>]) -> Bool {
        guard points.count >= 3 else { return true }
        let a = points[0]
        var direction: SIMD3<Double>? = nil
        for p in points.dropFirst() {
            let d = p - a
            if simd_length(d) < collinearityToleranceMM { continue }
            if let u = direction {
                if simd_length(simd_cross(u, d)) / simd_length(d) > collinearityToleranceMM { return false }
            } else { direction = d / simd_length(d) }
        }
        return true
    }

    /// Horn's closed form: the rotation is the eigenvector of the largest
    /// eigenvalue of the 4×4 symmetric matrix built from the cross-covariance
    /// of the centred point sets; Jacobi rotations find it.
    static func horn(moving: [SIMD3<Double>], fixed: [SIMD3<Double>]) -> RegistrationTransform? {
        let n = Double(moving.count)
        let cm = moving.reduce(SIMD3<Double>(repeating: 0), +) / n
        let cf = fixed.reduce(SIMD3<Double>(repeating: 0), +) / n
        var s = [[Double]](repeating: [Double](repeating: 0, count: 3), count: 3)
        for (m, f) in zip(moving, fixed) {
            let a = m - cm, b = f - cf
            for i in 0..<3 { for j in 0..<3 { s[i][j] += a[i] * b[j] } }
        }
        let trace = s[0][0] + s[1][1] + s[2][2]
        var nmat = [[Double]](repeating: [Double](repeating: 0, count: 4), count: 4)
        nmat[0][0] = trace
        nmat[0][1] = s[1][2] - s[2][1]; nmat[0][2] = s[2][0] - s[0][2]; nmat[0][3] = s[0][1] - s[1][0]
        nmat[1][0] = nmat[0][1]; nmat[2][0] = nmat[0][2]; nmat[3][0] = nmat[0][3]
        nmat[1][1] = s[0][0] - s[1][1] - s[2][2]; nmat[1][2] = s[0][1] + s[1][0]; nmat[1][3] = s[2][0] + s[0][2]
        nmat[2][1] = nmat[1][2]; nmat[2][2] = -s[0][0] + s[1][1] - s[2][2]; nmat[2][3] = s[1][2] + s[2][1]
        nmat[3][1] = nmat[1][3]; nmat[3][2] = nmat[2][3]; nmat[3][3] = -s[0][0] - s[1][1] + s[2][2]
        guard let (values, vectors) = jacobiEigen(nmat) else { return nil }
        var best = 0
        for i in 1..<4 where values[i] > values[best] { best = i }
        let q = simd_normalize(simd_quatd(ix: vectors[1][best], iy: vectors[2][best], iz: vectors[3][best], r: vectors[0][best]))
        guard q.length.isFinite, q.length > 0 else { return nil }
        let r = double3x3(q)
        let t = cf - r * cm
        let m = double4x4(SIMD4(r[0].x, r[0].y, r[0].z, 0), SIMD4(r[1].x, r[1].y, r[1].z, 0),
                          SIMD4(r[2].x, r[2].y, r[2].z, 0), SIMD4(t.x, t.y, t.z, 1))
        return RegistrationTransform(matrix: m)
    }

    /// Cyclic Jacobi for a symmetric 4×4; returns eigenvalues and the matrix
    /// whose columns are the eigenvectors.
    static func jacobiEigen(_ input: [[Double]]) -> (values: [Double], vectors: [[Double]])? {
        var a = input
        var v = [[Double]](repeating: [Double](repeating: 0, count: 4), count: 4)
        for i in 0..<4 { v[i][i] = 1 }
        for _ in 0..<100 {
            var off = 0.0
            for i in 0..<4 { for j in 0..<4 where i != j { off += a[i][j] * a[i][j] } }
            if off < 1e-24 { break }
            for p in 0..<3 { for q in (p + 1)..<4 {
                if abs(a[p][q]) < 1e-300 { continue }
                let theta = (a[q][q] - a[p][p]) / (2 * a[p][q])
                let t = (theta >= 0 ? 1.0 : -1.0) / (abs(theta) + (theta * theta + 1).squareRoot())
                let c = 1 / (t * t + 1).squareRoot(), s = t * c
                for k in 0..<4 {
                    let akp = a[k][p], akq = a[k][q]
                    a[k][p] = c * akp - s * akq; a[k][q] = s * akp + c * akq
                }
                for k in 0..<4 {
                    let apk = a[p][k], aqk = a[q][k]
                    a[p][k] = c * apk - s * aqk; a[q][k] = s * apk + c * aqk
                }
                for k in 0..<4 {
                    let vkp = v[k][p], vkq = v[k][q]
                    v[k][p] = c * vkp - s * vkq; v[k][q] = s * vkp + c * vkq
                }
            } }
        }
        let values = (0..<4).map { a[$0][$0] }
        guard values.allSatisfy(\.isFinite) else { return nil }
        return (values, v)
    }
}

// MARK: - Companion overlays and the registration session

/// One companion series drawn over the base: its own transform, blend and verdict.
@objc(HorosCompanionOverlay)
public final class CompanionOverlay: NSObject {
    @objc public let seriesInstanceUID: String
    @objc public let frameOfReferenceUID: String
    @objc public private(set) var transform: RegistrationTransform
    @objc public private(set) var quality: RegistrationQuality?
    @objc public private(set) var blend: Double
    @objc public private(set) var rejected: Bool = false
    @objc public private(set) var generation: Int = 0

    init(seriesInstanceUID: String, frameOfReferenceUID: String, transform: RegistrationTransform, quality: RegistrationQuality?, blend: Double) {
        self.seriesInstanceUID = seriesInstanceUID; self.frameOfReferenceUID = frameOfReferenceUID
        self.transform = transform; self.quality = quality; self.blend = min(max(blend, 0), 1)
    }
    /// Whether panes may draw the companion as aligned.
    @objc public var isAligned: Bool { !rejected && (quality?.verdict ?? .accepted) != .rejected }
    func set(transform: RegistrationTransform, quality: RegistrationQuality?) {
        self.transform = transform; self.quality = quality; rejected = quality?.verdict == .rejected; generation += 1
    }
    func setBlend(_ value: Double) { blend = min(max(value, 0), 1); generation += 1 }
    func reject() { rejected = true; generation += 1 }
    func reset(sharedFrame: Bool) {
        transform = sharedFrame ? .identity : RegistrationTransform.identity
        quality = nil; rejected = !sharedFrame; generation += 1
    }
}

/// The base series' registration state: companions keyed by Series Instance
/// UID, each with an independent transform. `generation` changes on every
/// edit so every pane can tell whether it is drawing the current state.
@objc(HorosRegistrationSession)
public final class RegistrationSession: NSObject {
    @objc public let baseSeriesInstanceUID: String
    @objc public let baseFrameOfReferenceUID: String
    @objc public private(set) var companions: [CompanionOverlay] = []
    @objc public private(set) var generation: Int = 0

    @objc public init(baseSeriesInstanceUID: String, baseFrameOfReferenceUID: String) {
        self.baseSeriesInstanceUID = baseSeriesInstanceUID; self.baseFrameOfReferenceUID = baseFrameOfReferenceUID
    }

    @objc public func companion(_ seriesInstanceUID: String) -> CompanionOverlay? {
        companions.first { $0.seriesInstanceUID == seriesInstanceUID }
    }

    /// Adds a companion. A shared Frame of Reference starts aligned with the
    /// identity; a different one starts *unaligned* until a registration is
    /// accepted — never assumed aligned.
    @objc @discardableResult
    public func addCompanion(seriesInstanceUID: String, frameOfReferenceUID: String, blend: Double) -> CompanionOverlay {
        if let existing = companion(seriesInstanceUID) { return existing }
        let shared = !baseFrameOfReferenceUID.isEmpty && frameOfReferenceUID == baseFrameOfReferenceUID
        let overlay = CompanionOverlay(seriesInstanceUID: seriesInstanceUID, frameOfReferenceUID: frameOfReferenceUID,
                                       transform: .identity, quality: nil, blend: blend)
        if !shared { overlay.reject() }
        companions.append(overlay); generation += 1
        return overlay
    }

    @objc @discardableResult
    public func setRegistration(_ seriesInstanceUID: String, result: LandmarkRegistrationResult) -> Bool {
        guard let overlay = companion(seriesInstanceUID), let transform = result.transform, let quality = result.quality else { return false }
        overlay.set(transform: transform, quality: quality); generation += 1
        return quality.verdict != .rejected
    }

    @objc public func setBlend(_ seriesInstanceUID: String, blend: Double) {
        guard let overlay = companion(seriesInstanceUID) else { return }
        overlay.setBlend(blend); generation += 1
    }

    @objc public func reject(_ seriesInstanceUID: String) {
        companion(seriesInstanceUID)?.reject(); generation += 1
    }

    @objc public func reset(_ seriesInstanceUID: String) {
        guard let overlay = companion(seriesInstanceUID) else { return }
        overlay.reset(sharedFrame: !baseFrameOfReferenceUID.isEmpty && overlay.frameOfReferenceUID == baseFrameOfReferenceUID)
        generation += 1
    }

    @objc public func removeCompanion(_ seriesInstanceUID: String) {
        companions.removeAll { $0.seriesInstanceUID == seriesInstanceUID }; generation += 1
    }
}

// MARK: - Two-patient comparison

/// An explicit choice of two studies to compare, persisted by their Study
/// Instance UIDs. Names never identify anything here: two patients with the
/// same name are two patients, and a study is recognised only by its UID.
@objc(HorosPatientComparisonSelection)
public final class PatientComparisonSelection: NSObject {
    @objc public static let defaultsKey = "HorosPatientComparisonSelections"
    @objc public let firstPatientID: String
    @objc public let firstStudyInstanceUID: String
    @objc public let secondPatientID: String
    @objc public let secondStudyInstanceUID: String
    @objc public let confirmedAt: Date

    @objc public init?(firstPatientID: String, firstStudyInstanceUID: String,
                       secondPatientID: String, secondStudyInstanceUID: String, confirmedAt: Date = Date()) {
        guard !firstStudyInstanceUID.isEmpty, !secondStudyInstanceUID.isEmpty, firstStudyInstanceUID != secondStudyInstanceUID else { return nil }
        self.firstPatientID = firstPatientID; self.firstStudyInstanceUID = firstStudyInstanceUID
        self.secondPatientID = secondPatientID; self.secondStudyInstanceUID = secondStudyInstanceUID; self.confirmedAt = confirmedAt
    }

    /// Both study UIDs, in either order; patient IDs must also match so a
    /// re-used UID with another ID is not silently accepted.
    @objc public func matches(studyA: String, patientA: String, studyB: String, patientB: String) -> Bool {
        (studyA == firstStudyInstanceUID && patientA == firstPatientID && studyB == secondStudyInstanceUID && patientB == secondPatientID) ||
        (studyB == firstStudyInstanceUID && patientB == firstPatientID && studyA == secondStudyInstanceUID && patientA == secondPatientID)
    }

    @objc public var description_: String {
        "\(firstPatientID) [\(firstStudyInstanceUID)] vs \(secondPatientID) [\(secondStudyInstanceUID)]"
    }

    var record: [String: Any] {
        ["firstPatientID": firstPatientID, "firstStudyInstanceUID": firstStudyInstanceUID,
         "secondPatientID": secondPatientID, "secondStudyInstanceUID": secondStudyInstanceUID,
         "confirmedAt": confirmedAt.timeIntervalSince1970]
    }

    static func from(record: [String: Any]) -> PatientComparisonSelection? {
        guard let a = record["firstPatientID"] as? String, let sa = record["firstStudyInstanceUID"] as? String,
              let b = record["secondPatientID"] as? String, let sb = record["secondStudyInstanceUID"] as? String else { return nil }
        let when = (record["confirmedAt"] as? Double).map { Date(timeIntervalSince1970: $0) } ?? Date()
        return PatientComparisonSelection(firstPatientID: a, firstStudyInstanceUID: sa, secondPatientID: b, secondStudyInstanceUID: sb, confirmedAt: when)
    }

    @objc public static func stored(in defaults: UserDefaults) -> [PatientComparisonSelection] {
        (defaults.array(forKey: defaultsKey) as? [[String: Any]] ?? []).compactMap(from(record:))
    }

    @objc public func store(in defaults: UserDefaults) {
        var all = PatientComparisonSelection.stored(in: defaults).filter {
            !$0.matches(studyA: firstStudyInstanceUID, patientA: firstPatientID, studyB: secondStudyInstanceUID, patientB: secondPatientID)
        }
        all.append(self)
        defaults.set(all.map(\.record), forKey: PatientComparisonSelection.defaultsKey)
    }

    @objc public static func find(in defaults: UserDefaults, studyA: String, patientA: String,
                                  studyB: String, patientB: String) -> PatientComparisonSelection? {
        stored(in: defaults).first { $0.matches(studyA: studyA, patientA: patientA, studyB: studyB, patientB: patientB) }
    }

    /// Whether two viewers need an explicit comparison confirmation: any pair
    /// of different patient IDs, and also the same ID under different names,
    /// which cannot be told apart from two patients.
    @objc public static func requiresExplicitChoice(patientA: String, nameA: String, patientB: String, nameB: String) -> Bool {
        patientA != patientB || nameA != nameB
    }
}

// MARK: - Guided ROI copy

@objc(HorosGuidedCopyStatus)
public enum GuidedCopyStatus: Int {
    case placed = 0
    case noSlice
    case ambiguous
    case unsupportedGeometry
    case invalidSource
}

/// Where one source ROI lands on the target series, in patient and target pixels.
@objc(HorosGuidedCopyPlacement)
public final class GuidedCopyPlacement: NSObject {
    @objc public var sourceImageIndex: Int = -1
    @objc public var sourceTemporalIndex: Int = 0
    @objc public var sourceROIIndex: Int = -1
    @objc public var name: String = ""
    @objc public var typeCode: Int = 0
    @objc public var patientPoints: [[Double]] = []
    @objc public var targetImageIndex: Int = -1
    @objc public var targetTemporalIndex: Int = 0
    @objc public var points: [[Double]] = []
    @objc public var rect: NSRect = NSRect(x: 0, y: 0, width: 0, height: 0)
    @objc public var throughPlaneMM: Double = 0
    @objc public var status: GuidedCopyStatus = .invalidSource
    @objc public var reason: String = ""
    @objc public var provenance: String = ""
}

@objc(HorosGuidedCopyPlan)
public final class GuidedCopyPlan: NSObject {
    @objc public let placements: [GuidedCopyPlacement]
    @objc public let transform: RegistrationTransform
    @objc public let offsetMM: [Double]
    init(placements: [GuidedCopyPlacement], transform: RegistrationTransform, offsetMM: [Double]) {
        self.placements = placements; self.transform = transform; self.offsetMM = offsetMM
    }
    @objc public var placed: [GuidedCopyPlacement] { placements.filter { $0.status == .placed } }
    @objc public var refused: [GuidedCopyPlacement] { placements.filter { $0.status != .placed } }
    @objc public var summary: String {
        var lines: [String] = []
        for p in placements {
            if p.status == .placed {
                lines.append(String(format: "%@ (source slice %ld) → target slice %ld, %.2f mm through-plane",
                                    p.name, p.sourceImageIndex + 1, p.targetImageIndex + 1, p.throughPlaneMM))
            } else {
                lines.append("\(p.name) (source slice \(p.sourceImageIndex + 1)): \(p.reason)")
            }
        }
        return lines.joined(separator: "\n")
    }
}

/// Plans the copy of every ROI of `source` onto `target` through `transform`
/// (source patient frame → target patient frame) plus a manual offset in
/// target millimetres. Each ROI goes to the target image whose plane is
/// nearest to its transformed points; nothing lands on "the current slice",
/// and a ROI whose plane is farther than the tolerance from every target
/// image is refused by name. Brush, rectangle and oval ROIs keep their pixel
/// geometry, so they are copied only onto an aligned target with the same
/// pixel spacing; polygons, pencils, lines and points are reprojected.
@objc(HorosGuidedROICopy)
public final class GuidedROICopy: NSObject {
    @objc public static let spacingTolerance = 0.001
    @objc public static let orientationDotTolerance = 0.9

    /// Half the target slice spacing, at least 0.5 mm; when a series has one
    /// image, 0.5 mm.
    @objc public static func planeTolerance(for target: ROIInterchangeSeries) -> Double {
        let positions = target.images.compactMap { image -> Double? in
            guard image.imagePosition.count == 3, let n = normal(of: image) else { return nil }
            return simd_dot(SIMD3(image.imagePosition[0], image.imagePosition[1], image.imagePosition[2]), n)
        }.sorted()
        var spacing = 0.0
        for (a, b) in zip(positions, positions.dropFirst()) where b - a > 1e-6 { spacing = spacing == 0 ? b - a : min(spacing, b - a) }
        return max(0.5, spacing / 2)
    }

    @objc public static func plan(source: ROIInterchangeSeries, target: ROIInterchangeSeries,
                                  transform: RegistrationTransform, offsetMM: [Double]) -> GuidedCopyPlan {
        let offset = offsetMM.count == 3 && offsetMM.allSatisfy(\.isFinite) ? SIMD3(offsetMM[0], offsetMM[1], offsetMM[2]) : SIMD3<Double>(repeating: 0)
        let tolerance = planeTolerance(for: target)
        var placements: [GuidedCopyPlacement] = []
        let targetSlices = target.images.map { slicePoint(for: $0) }
        for image in source.images {
            for (roiIndex, roi) in image.rois.enumerated() {
                let placement = GuidedCopyPlacement()
                placement.sourceImageIndex = image.index; placement.sourceTemporalIndex = image.temporalIndex
                placement.sourceROIIndex = roiIndex; placement.name = roi.name; placement.typeCode = roi.typeCode
                placement.provenance = provenance(source: source, image: image, roi: roi, transform: transform, offset: offset)
                placements.append(placement)
                guard let sourceSlice = slicePoint(for: image) else {
                    placement.status = .invalidSource; placement.reason = "The source image has no position or orientation."; continue
                }
                let pixels: [SIMD2<Double>]
                if rectBased(roi.typeCode) {
                    guard roi.hasRect else { placement.status = .invalidSource; placement.reason = "The ROI has no rectangle."; continue }
                    pixels = [SIMD2(Double(roi.rect.origin.x) + Double(roi.rect.size.width) / 2, Double(roi.rect.origin.y) + Double(roi.rect.size.height) / 2)]
                } else if roi.typeCode == ROIInterchangeType.brush.rawValue {
                    guard roi.brushWidth > 0, roi.brushHeight > 0 else { placement.status = .invalidSource; placement.reason = "The brush has no mask."; continue }
                    pixels = [SIMD2(Double(roi.brushOriginX) + Double(roi.brushWidth) / 2, Double(roi.brushOriginY) + Double(roi.brushHeight) / 2)]
                } else {
                    guard !roi.points.isEmpty else { placement.status = .invalidSource; placement.reason = "The ROI has no points."; continue }
                    pixels = roi.points.map { SIMD2(Double($0.pointValue.x), Double($0.pointValue.y)) }
                }
                let patient = pixels.map { pixel -> SIMD3<Double> in
                    let p = ROIIntersliceGeometry.patientPoint(from: ROISlicePoint(
                        pixelX: pixel.x, pixelY: pixel.y, originX: sourceSlice.originX, originY: sourceSlice.originY, originZ: sourceSlice.originZ,
                        rowX: sourceSlice.rowX, rowY: sourceSlice.rowY, rowZ: sourceSlice.rowZ, colX: sourceSlice.colX, colY: sourceSlice.colY, colZ: sourceSlice.colZ,
                        normalX: sourceSlice.normalX, normalY: sourceSlice.normalY, normalZ: sourceSlice.normalZ,
                        spacingX: sourceSlice.spacingX, spacingY: sourceSlice.spacingY, pixelCenter: false))
                    return transform.apply(SIMD3(p.x, p.y, p.z)) + offset
                }
                placement.patientPoints = patient.map { [$0.x, $0.y, $0.z] }
                // Nearest target plane by the centroid, then every point must lie within tolerance.
                let centroid = patient.reduce(SIMD3<Double>(repeating: 0), +) / Double(patient.count)
                var candidates: [(index: Int, through: Double)] = []
                for (index, slice) in targetSlices.enumerated() {
                    guard let slice = slice, target.images[index].temporalIndex == image.temporalIndex,
                          let projection = ROIIntersliceGeometry.projection(of: ROIPatientPoint(x: centroid.x, y: centroid.y, z: centroid.z), onto: slice) else { continue }
                    if abs(projection.throughPlane) <= tolerance { candidates.append((index, abs(projection.throughPlane))) }
                }
                candidates.sort { $0.through < $1.through }
                guard let best = candidates.first else {
                    placement.status = .noSlice
                    placement.reason = String(format: "No target image within %.2f mm of the ROI's plane after registration.", tolerance); continue
                }
                if candidates.count > 1, candidates[1].through - best.through < 1e-6 {
                    placement.status = .ambiguous; placement.reason = "Two target images are equally near the ROI's plane; not applied by order."; continue
                }
                let targetImage = target.images[best.index]
                let targetSlice = targetSlices[best.index]!
                let aligned = orientationsAlign(image, targetImage)
                let sameSpacing = abs(image.pixelSpacingX - targetImage.pixelSpacingX) <= spacingTolerance * max(1, image.pixelSpacingX) &&
                                  abs(image.pixelSpacingY - targetImage.pixelSpacingY) <= spacingTolerance * max(1, image.pixelSpacingY)
                let rigidPixelGeometry = rectBased(roi.typeCode) || roi.typeCode == ROIInterchangeType.brush.rawValue
                if rigidPixelGeometry && !(aligned && sameSpacing && transform.isRigidInPlane(sourceSlice: sourceSlice, targetSlice: targetSlice)) {
                    placement.status = .unsupportedGeometry
                    placement.reason = "\(roi.name) keeps pixel geometry (brush/rectangle/oval/point); the target image is not aligned with the same pixel spacing, so it is not resampled."
                    continue
                }
                var projected: [[Double]] = []
                var worst = 0.0
                for p in patient {
                    guard let projection = ROIIntersliceGeometry.projection(of: ROIPatientPoint(x: p.x, y: p.y, z: p.z), onto: targetSlice) else { break }
                    projected.append([projection.pixelX, projection.pixelY]); worst = max(worst, abs(projection.throughPlane))
                }
                guard projected.count == patient.count else { placement.status = .invalidSource; placement.reason = "Could not project the ROI onto the target image."; continue }
                if worst > tolerance {
                    placement.status = .noSlice
                    placement.reason = String(format: "The ROI spans %.2f mm through the target plane; it does not lie on one target image.", worst); continue
                }
                placement.targetImageIndex = best.index; placement.targetTemporalIndex = targetImage.temporalIndex
                placement.throughPlaneMM = worst
                if rigidPixelGeometry {
                    let shift = SIMD2(projected[0][0] - pixels[0].x, projected[0][1] - pixels[0].y)
                    if rectBased(roi.typeCode) {
                        placement.rect = NSRect(x: Double(roi.rect.origin.x) + shift.x, y: Double(roi.rect.origin.y) + shift.y,
                                                width: Double(roi.rect.size.width), height: Double(roi.rect.size.height))
                    } else {
                        let brushX = Double(roi.brushOriginX) + shift.x
                        let brushY = Double(roi.brushOriginY) + shift.y
                        placement.rect = NSRect(x: brushX, y: brushY, width: Double(roi.brushWidth), height: Double(roi.brushHeight))
                    }
                    placement.points = projected
                } else {
                    placement.points = projected
                }
                placement.status = .placed
                placement.reason = "Placed by patient position."
            }
        }
        return GuidedCopyPlan(placements: placements, transform: transform, offsetMM: [offset.x, offset.y, offset.z])
    }

    static func rectBased(_ typeCode: Int) -> Bool {
        typeCode == ROIInterchangeType.rectangle.rawValue || typeCode == ROIInterchangeType.oval.rawValue || typeCode == ROIInterchangeType.point2D.rawValue
    }

    static func provenance(source: ROIInterchangeSeries, image: ROIInterchangeImage, roi: ROIInterchangeROI,
                           transform: RegistrationTransform, offset: SIMD3<Double>) -> String {
        String(format: "Copied from series %@ image %@ (frame %ld) via %@ %@; offset %.2f/%.2f/%.2f mm",
               source.seriesInstanceUID ?? "?", image.sopInstanceUID ?? "?", image.frame, transform.algorithm, transform.version,
               offset.x, offset.y, offset.z)
    }

    static func normal(of image: ROIInterchangeImage) -> SIMD3<Double>? {
        guard image.imageOrientation.count == 6 else { return nil }
        let iop = image.imageOrientation
        let n = simd_cross(SIMD3(iop[0], iop[1], iop[2]), SIMD3(iop[3], iop[4], iop[5]))
        let length = simd_length(n)
        guard length > 0, length.isFinite else { return nil }
        return n / length
    }

    static func orientationsAlign(_ a: ROIInterchangeImage, _ b: ROIInterchangeImage) -> Bool {
        guard a.imageOrientation.count == 6, b.imageOrientation.count == 6 else { return false }
        let ra = SIMD3(a.imageOrientation[0], a.imageOrientation[1], a.imageOrientation[2]), rb = SIMD3(b.imageOrientation[0], b.imageOrientation[1], b.imageOrientation[2])
        let ca = SIMD3(a.imageOrientation[3], a.imageOrientation[4], a.imageOrientation[5]), cb = SIMD3(b.imageOrientation[3], b.imageOrientation[4], b.imageOrientation[5])
        return simd_dot(ra, rb) > orientationDotTolerance && simd_dot(ca, cb) > orientationDotTolerance
    }

    static func slicePoint(for image: ROIInterchangeImage) -> ROISlicePoint? {
        guard image.imagePosition.count == 3, image.imageOrientation.count == 6, image.pixelSpacingX > 0, image.pixelSpacingY > 0,
              let n = normal(of: image) else { return nil }
        let iop = image.imageOrientation
        return ROISlicePoint(pixelX: 0, pixelY: 0, originX: image.imagePosition[0], originY: image.imagePosition[1], originZ: image.imagePosition[2],
                             rowX: iop[0], rowY: iop[1], rowZ: iop[2], colX: iop[3], colY: iop[4], colZ: iop[5],
                             normalX: n.x, normalY: n.y, normalZ: n.z, spacingX: image.pixelSpacingX, spacingY: image.pixelSpacingY, pixelCenter: false)
    }
}

extension RegistrationTransform {
    /// True when the transform maps the source row/column axes onto the target
    /// row/column axes (no in-plane rotation), so pixel geometry can move as a
    /// whole. A pure translation between aligned images qualifies.
    func isRigidInPlane(sourceSlice: ROISlicePoint, targetSlice: ROISlicePoint) -> Bool {
        let row = rotate(SIMD3(sourceSlice.rowX, sourceSlice.rowY, sourceSlice.rowZ))
        let col = rotate(SIMD3(sourceSlice.colX, sourceSlice.colY, sourceSlice.colZ))
        return simd_dot(row, SIMD3(targetSlice.rowX, targetSlice.rowY, targetSlice.rowZ)) > 0.9999 &&
               simd_dot(col, SIMD3(targetSlice.colX, targetSlice.colY, targetSlice.colZ)) > 0.9999
    }
}
