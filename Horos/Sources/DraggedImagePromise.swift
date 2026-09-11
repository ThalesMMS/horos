import AppKit
import ObjectiveC

/// File promise and bitmap a viewer drag advertises to Finder and browsers.
///
/// The destination must receive a complete JPEG, or no path at all. The Carbon
/// `PasteboardCopyPasteLocation` path could name a file that was never written;
/// `NSFilePromiseProvider` hands AppKit the URL and this type writes the JPEG
/// there only after encode succeeds. TIFF travels on the same item so a browser
/// that never asks for the promise still gets a bitmap.
@objc(HorosDraggedImagePromise)
public final class DraggedImagePromise: NSObject, NSFilePromiseProviderDelegate, NSPasteboardWriting {
    @objc public static let promisedContentType = "public.jpeg"
    @objc public static let promisedFileURLType = "com.apple.pasteboard.promised-file-url"
    @objc public static let promisedFileContentType = "com.apple.pasteboard.promised-file-content-type"

    @objc public static var advertisedTypeIdentifiers: [String] {
        [
            NSPasteboard.PasteboardType.tiff.rawValue,
            promisedFileURLType,
            promisedFileContentType,
            promisedContentType,
        ]
    }

    @objc public let studyName: String?
    @objc public let seriesName: String?
    fileprivate let tiffData: Data

    private static var providerRetainKey: UInt8 = 0

    @objc(initWithTIFFData:study:series:)
    public init(tiffData: Data, study: String?, series: String?) {
        self.tiffData = tiffData
        self.studyName = study
        self.seriesName = series
        super.init()
    }

    @objc public var suggestedFileName: String {
        DraggedImageFile.name(study: studyName, series: seriesName) + ".jpg"
    }

    /// The writer Finder and browsers actually receive. The provider holds this
    /// object so the weak delegate survives until the drop finishes.
    @objc public func filePromiseProviderForDragging() -> NSFilePromiseProvider {
        let provider = DraggedImageFilePromiseProvider(tiffData: tiffData, delegate: self)
        objc_setAssociatedObject(provider, &DraggedImagePromise.providerRetainKey, self, .OBJC_ASSOCIATION_RETAIN_NONATOMIC)
        return provider
    }

    public func writableTypes(for pasteboard: NSPasteboard) -> [NSPasteboard.PasteboardType] {
        var types: [NSPasteboard.PasteboardType] = [
            NSPasteboard.PasteboardType(rawValue: Self.promisedFileURLType),
            NSPasteboard.PasteboardType(rawValue: Self.promisedFileContentType),
        ]
        if !tiffData.isEmpty {
            types.insert(.tiff, at: 0)
        }
        return types
    }

    public func pasteboardPropertyList(forType type: NSPasteboard.PasteboardType) -> Any? {
        if type == .tiff {
            return tiffData
        }
        if type.rawValue == Self.promisedFileContentType {
            return Self.promisedContentType
        }
        return nil
    }

    @objc public func jpegData() -> Data? {
        guard !tiffData.isEmpty, let rep = NSBitmapImageRep(data: tiffData) else { return nil }
        return rep.representation(using: .jpeg, properties: [.compressionFactor: 0.9])
    }

    @objc(writeJPEGToURL:error:)
    public func writeJPEG(to url: URL) throws {
        guard let data = jpegData(), !data.isEmpty else {
            throw NSError(domain: "HorosDraggedImagePromise", code: 1, userInfo: [
                NSLocalizedDescriptionKey: "The dragged image could not be encoded as JPEG.",
            ])
        }
        try data.write(to: url, options: .atomic)
    }

    public func filePromiseProvider(_ filePromiseProvider: NSFilePromiseProvider,
                                    fileNameForType fileType: String) -> String {
        suggestedFileName
    }

    public func filePromiseProvider(_ filePromiseProvider: NSFilePromiseProvider,
                                    writePromiseTo url: URL,
                                    completionHandler: @escaping (Error?) -> Void) {
        do {
            try writeJPEG(to: url)
            completionHandler(nil)
        } catch {
            completionHandler(error)
        }
    }
}

/// `NSFilePromiseProvider` plus the TIFF bitmap on the same pasteboard item.
private final class DraggedImageFilePromiseProvider: NSFilePromiseProvider {
    private let tiffData: Data

    init(tiffData: Data, delegate: NSFilePromiseProviderDelegate) {
        self.tiffData = tiffData
        super.init(fileType: DraggedImagePromise.promisedContentType, delegate: delegate)
    }

    @available(*, unavailable)
    required init?(coder: NSCoder) {
        fatalError("init(coder:) is not used for a viewer image drag")
    }

    override func writableTypes(for pasteboard: NSPasteboard) -> [NSPasteboard.PasteboardType] {
        var types = super.writableTypes(for: pasteboard)
        if !tiffData.isEmpty {
            types.insert(.tiff, at: 0)
        }
        return types
    }

    override func pasteboardPropertyList(forType type: NSPasteboard.PasteboardType) -> Any? {
        if type == .tiff {
            return tiffData
        }
        return super.pasteboardPropertyList(forType: type)
    }
}
