import AppKit
import QuickLookThumbnailing

/// Finder icon thumbnail. The process is this extension, not Horos.
@objc(ThumbnailProvider)
final class ThumbnailProvider: QLThumbnailProvider {
    override func provideThumbnail(for request: QLFileThumbnailRequest,
                                   _ handler: @escaping (QLThumbnailReply?, Error?) -> Void) {
        switch FinderPreview.load(request.fileURL) {
        case .image(let image):
            let size = request.maximumSize
            handler(QLThumbnailReply(contextSize: size, currentContextDrawing: {
                image.draw(in: NSRect(origin: .zero, size: size),
                           from: NSRect(origin: .zero, size: image.size),
                           operation: .copy, fraction: 1)
                return true
            }), nil)
        case .failure(let reason):
            handler(nil, NSError(domain: "org.horosproject.horos.FinderPreview",
                                 code: 1,
                                 userInfo: [NSLocalizedDescriptionKey: reason.sentence]))
        }
    }
}
