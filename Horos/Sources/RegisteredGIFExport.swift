import Foundation
import AppKit
import ImageIO
import UniformTypeIdentifiers

/// Animated GIF of a registered comparison, for #384 package B.
///
/// The comparison a reader actually makes between two registered series is a
/// blink: the same anatomy, the same frame, alternating between the two studies
/// so that what moved is the only thing that moves. This turns the captures the
/// viewer already produces into that animation and puts it on the clipboard.
///
/// It renders nothing itself and owns no pixels: the caller hands it the images
/// the viewer drew, in the order the plan asked for. It also writes no file —
/// the GIF goes to the pasteboard as data, so there is no temporary to leave
/// behind or to leave invalid.
///
/// It does not replace the fused DICOM export (#142), the movie/codec export
/// (#147), the flythrough (#222) or the drag file promises (#270); those keep
/// their own acceptance.
@objc(HorosRegisteredGIFFrame)
@objcMembers public final class RegisteredGIFFrame: NSObject {
    /// `""` for the base series, otherwise the companion's Series Instance UID.
    public let companionSeriesInstanceUID: String
    /// Fraction of the companion in the blend, 0 (base only) to 1 (companion only).
    public let blend: Double
    public let delaySeconds: Double

    public init(companionSeriesInstanceUID: String, blend: Double, delaySeconds: Double) {
        self.companionSeriesInstanceUID = companionSeriesInstanceUID
        self.blend = blend
        self.delaySeconds = delaySeconds
    }

    public var isBaseOnly: Bool { blend <= 0 }

    public var label: String {
        if isBaseOnly { return "base" }
        if blend >= 1 { return companionSeriesInstanceUID }
        return String(format: "%@ %.0f%%", companionSeriesInstanceUID, blend * 100)
    }
}

@objc(HorosRegisteredGIFPlan)
@objcMembers public final class RegisteredGIFPlan: NSObject {
    /// The session this plan belongs to. A plan made for one comparison must
    /// not be filled with another comparison's captures.
    public let sessionKey: String
    /// What the comparison was when the plan was made: which companion, aligned
    /// or not, under which transform. Moving the blend is what the capture
    /// itself does and does not count; re-registering or rejecting does.
    public let registrationKey: String
    public let companionSeriesInstanceUID: String
    public let frames: [RegisteredGIFFrame]
    /// 0 means forever, which is what a blink comparison wants.
    public let loops: Int
    public let refusal: String

    init(sessionKey: String, registrationKey: String, companionSeriesInstanceUID: String,
         frames: [RegisteredGIFFrame], loops: Int, refusal: String) {
        self.sessionKey = sessionKey
        self.registrationKey = registrationKey
        self.companionSeriesInstanceUID = companionSeriesInstanceUID
        self.frames = frames
        self.loops = loops
        self.refusal = refusal
    }

    public var isUsable: Bool { refusal.isEmpty && !frames.isEmpty }
    public var frameCount: Int { frames.count }
    public var totalDurationSeconds: Double { frames.reduce(0) { $0 + $1.delaySeconds } }
    public var blendValues: [Double] { frames.map(\.blend) }
    public var labels: [String] { frames.map(\.label) }
}

@objc(HorosRegisteredGIFResult)
@objcMembers public final class RegisteredGIFResult: NSObject {
    public let data: Data?
    public let refusal: String
    public let width: Int
    public let height: Int
    public let frameCount: Int

    init(data: Data?, refusal: String, width: Int = 0, height: Int = 0, frameCount: Int = 0) {
        self.data = data
        self.refusal = refusal
        self.width = width
        self.height = height
        self.frameCount = frameCount
    }

    public var isUsable: Bool { data != nil && refusal.isEmpty }
}

@objc(HorosRegisteredGIF)
public final class RegisteredGIF: NSObject {
    @objc public static let minimumDelaySeconds = 0.02
    @objc public static let maximumDelaySeconds = 10.0
    @objc public static let defaultDelaySeconds = 0.5
    @objc public static let maximumFrames = 240
    @objc public static let maximumPixels = 4096
    @objc public static let pasteboardTypeIdentifier = "com.compuserve.gif"

    // The exports this one does not stand in for.
    @objc public static func replacesFusedDICOMExport() -> Bool { false }
    @objc public static func replacesMovieExport() -> Bool { false }
    @objc public static func replacesFlythrough() -> Bool { false }
    @objc public static func replacesDragFilePromises() -> Bool { false }
    /// The GIF reaches the clipboard as data. Nothing is spooled.
    @objc public static func writesTemporaryFiles() -> Bool { false }

    /// A refusal, as a result the caller can return.
    @objc(refusedResultWithReason:)
    public static func refusedResult(_ reason: String) -> RegisteredGIFResult {
        RegisteredGIFResult(data: nil, refusal: reason)
    }

    @objc(sessionKeyForSession:)
    public static func sessionKey(_ session: RegistrationSession) -> String {
        session.baseSeriesInstanceUID + "|" + session.baseFrameOfReferenceUID
    }

    /// The two ends of a blink comparison.
    @objc public static func blinkStops() -> [Double] { [0, 1] }

    /// Which companion, aligned or not, under which transform.
    @objc(registrationKeyForSession:companion:)
    public static func registrationKey(_ session: RegistrationSession, companion uid: String) -> String {
        guard let overlay = session.companion(uid) else { return sessionKey(session) + "|absent" }
        let matrix = overlay.transform.rowMajor.map { String(format: "%.6f", $0) }.joined(separator: ",")
        return [sessionKey(session), uid, overlay.isAligned ? "aligned" : "unaligned", matrix].joined(separator: "|")
    }

    /// A ramp that goes to the companion and back, so the loop has no jump.
    @objc(rampStopsWithSteps:)
    public static func rampStops(steps: Int) -> [Double] {
        guard steps >= 2 else { return blinkStops() }
        let up = (0..<steps).map { Double($0) / Double(steps - 1) }
        return up + up.dropFirst().dropLast().reversed()
    }

    // MARK: - The plan

    @objc(planForSession:companion:blendStops:delaySeconds:)
    public static func plan(session: RegistrationSession, companion uid: String,
                            blendStops: [Double], delaySeconds: Double) -> RegisteredGIFPlan {
        let key = sessionKey(session)
        func refuse(_ why: String) -> RegisteredGIFPlan {
            RegisteredGIFPlan(sessionKey: key, registrationKey: registrationKey(session, companion: uid),
                              companionSeriesInstanceUID: uid, frames: [], loops: 0, refusal: why)
        }
        guard let companion = session.companion(uid) else {
            return refuse("This viewer has no registered companion series to compare with.")
        }
        guard companion.isAligned else {
            return refuse("The companion series is not registered to this one; a blink of unregistered "
                          + "series would show movement that is not the patient's.")
        }
        guard !blendStops.isEmpty else { return refuse("The comparison has no frames.") }
        guard blendStops.count <= maximumFrames else {
            return refuse("A comparison of \(blendStops.count) frames is longer than the \(maximumFrames) allowed.")
        }
        guard blendStops.allSatisfy({ $0.isFinite && $0 >= 0 && $0 <= 1 }) else {
            return refuse("A blend must be between 0 and 1.")
        }
        guard delaySeconds.isFinite, delaySeconds >= minimumDelaySeconds, delaySeconds <= maximumDelaySeconds else {
            return refuse(String(format: "A frame must last between %.2f s and %.0f s.",
                                 minimumDelaySeconds, maximumDelaySeconds))
        }
        let frames = blendStops.map {
            RegisteredGIFFrame(companionSeriesInstanceUID: uid, blend: $0, delaySeconds: delaySeconds)
        }
        return RegisteredGIFPlan(sessionKey: key, registrationKey: registrationKey(session, companion: uid),
                                 companionSeriesInstanceUID: uid, frames: frames, loops: 0, refusal: "")
    }

    /// A plan filled by another comparison, or by one that was re-registered
    /// under it, is not this comparison any more. The blend is not part of the
    /// identity: moving it is what the capture does.
    @objc(refusalForApplyingPlan:toSession:)
    public static func refusalForApplying(_ plan: RegisteredGIFPlan, to session: RegistrationSession) -> String {
        if plan.sessionKey != sessionKey(session) {
            return "These captures belong to another comparison."
        }
        if plan.registrationKey != registrationKey(session, companion: plan.companionSeriesInstanceUID) {
            return "The registration changed while the comparison was being captured; nothing was copied."
        }
        return ""
    }

    // MARK: - The captures

    /// What the images must be before they can be one animation.
    @objc(refusalForImages:plan:)
    public static func refusalForImages(_ images: [NSImage], plan: RegisteredGIFPlan) -> String {
        if !plan.refusal.isEmpty { return plan.refusal }
        guard images.count == plan.frameCount else {
            return "The comparison captured \(images.count) of \(plan.frameCount) frames; nothing was copied."
        }
        var size: (Int, Int)?
        for image in images {
            guard let bitmap = cgImage(image) else { return "A frame of the comparison could not be captured." }
            let current = (bitmap.width, bitmap.height)
            if current.0 <= 0 || current.1 <= 0 { return "A frame of the comparison is empty." }
            if current.0 > maximumPixels || current.1 > maximumPixels {
                return "A frame of \(current.0)×\(current.1) is larger than the \(maximumPixels) pixels allowed."
            }
            if let first = size, first != current {
                return "The frames do not share one size (\(first.0)×\(first.1) and \(current.0)×\(current.1)); "
                     + "a comparison must not change size between frames."
            }
            size = current
        }
        return ""
    }

    // MARK: - The animation

    @objc(dataForPlan:images:)
    public static func data(for plan: RegisteredGIFPlan, images: [NSImage]) -> RegisteredGIFResult {
        let refusal = refusalForImages(images, plan: plan)
        if !refusal.isEmpty { return RegisteredGIFResult(data: nil, refusal: refusal) }
        let bitmaps = images.compactMap { cgImage($0) }
        guard bitmaps.count == images.count else {
            return RegisteredGIFResult(data: nil, refusal: "A frame of the comparison could not be captured.")
        }
        let output = NSMutableData()
        guard let destination = CGImageDestinationCreateWithData(output, UTType.gif.identifier as CFString,
                                                                 bitmaps.count, nil) else {
            return RegisteredGIFResult(data: nil, refusal: "The animation could not be written.")
        }
        CGImageDestinationSetProperties(destination, [
            kCGImagePropertyGIFDictionary: [kCGImagePropertyGIFLoopCount: plan.loops],
        ] as CFDictionary)
        for (index, bitmap) in bitmaps.enumerated() {
            let delay = plan.frames[index].delaySeconds
            CGImageDestinationAddImage(destination, bitmap, [
                kCGImagePropertyGIFDictionary: [
                    kCGImagePropertyGIFDelayTime: delay,
                    kCGImagePropertyGIFUnclampedDelayTime: delay,
                ],
            ] as CFDictionary)
        }
        guard CGImageDestinationFinalize(destination) else {
            return RegisteredGIFResult(data: nil, refusal: "The animation could not be written.")
        }
        return RegisteredGIFResult(data: output as Data, refusal: "",
                                   width: bitmaps[0].width, height: bitmaps[0].height,
                                   frameCount: bitmaps.count)
    }

    // MARK: - Reading one back

    @objc(frameCountInData:)
    public static func frameCount(in data: Data) -> Int {
        guard let source = CGImageSourceCreateWithData(data as CFData, nil) else { return 0 }
        return CGImageSourceGetCount(source)
    }

    @objc(frameDelaysInData:)
    public static func frameDelays(in data: Data) -> [Double] {
        guard let source = CGImageSourceCreateWithData(data as CFData, nil) else { return [] }
        return (0..<CGImageSourceGetCount(source)).map { index in
            guard let properties = CGImageSourceCopyPropertiesAtIndex(source, index, nil) as? [CFString: Any],
                  let gif = properties[kCGImagePropertyGIFDictionary] as? [CFString: Any] else { return 0 }
            let unclamped = gif[kCGImagePropertyGIFUnclampedDelayTime] as? Double ?? 0
            return unclamped > 0 ? unclamped : (gif[kCGImagePropertyGIFDelayTime] as? Double ?? 0)
        }
    }

    @objc(loopCountInData:)
    public static func loopCount(in data: Data) -> Int {
        guard let source = CGImageSourceCreateWithData(data as CFData, nil),
              let properties = CGImageSourceCopyProperties(source, nil) as? [CFString: Any],
              let gif = properties[kCGImagePropertyGIFDictionary] as? [CFString: Any] else { return -1 }
        return gif[kCGImagePropertyGIFLoopCount] as? Int ?? -1
    }

    @objc(frameBitmapInData:atIndex:)
    public static func frameBitmap(in data: Data, at index: Int) -> NSBitmapImageRep? {
        guard let source = CGImageSourceCreateWithData(data as CFData, nil),
              index >= 0, index < CGImageSourceGetCount(source),
              let image = CGImageSourceCreateImageAtIndex(source, index, nil) else { return nil }
        return NSBitmapImageRep(cgImage: image)
    }

    // MARK: - The clipboard

    /// The animation goes to the clipboard as data. No file is written, so
    /// nothing can be left behind half-written or already deleted.
    @objc(copyData:toPasteboard:)
    @discardableResult
    public static func copy(_ data: Data, to pasteboard: NSPasteboard) -> Bool {
        guard !data.isEmpty, frameCount(in: data) > 0 else { return false }
        pasteboard.clearContents()
        return pasteboard.setData(data, forType: NSPasteboard.PasteboardType(pasteboardTypeIdentifier))
    }

    @objc(dataOnPasteboard:)
    public static func data(on pasteboard: NSPasteboard) -> Data? {
        pasteboard.data(forType: NSPasteboard.PasteboardType(pasteboardTypeIdentifier))
    }

    // MARK: - Helpers

    /// The capture, colour-managed into sRGB.
    ///
    /// A view captured with `lockFocus` comes back in the display's colour
    /// space; a GIF declares sRGB. Handing the encoder the untouched pixels
    /// would keep the numbers and change the colours — a window level that
    /// reads darker on the clipboard than in the viewer. Converting first is
    /// what makes the animation the same picture as the static view.
    @objc(sRGBImageForImage:)
    public static func cgImage(_ image: NSImage) -> CGImage? {
        var rect = NSRect(x: 0, y: 0, width: image.size.width, height: image.size.height)
        guard rect.width > 0, rect.height > 0,
              let captured = image.cgImage(forProposedRect: &rect, context: nil, hints: nil),
              captured.width > 0, captured.height > 0,
              let space = CGColorSpace(name: CGColorSpace.sRGB),
              let context = CGContext(data: nil, width: captured.width, height: captured.height,
                                      bitsPerComponent: 8, bytesPerRow: 0, space: space,
                                      bitmapInfo: CGImageAlphaInfo.noneSkipLast.rawValue)
        else { return nil }
        context.draw(captured, in: CGRect(x: 0, y: 0, width: captured.width, height: captured.height))
        return context.makeImage()
    }
}
