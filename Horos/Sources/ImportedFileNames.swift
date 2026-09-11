import Foundation

/// The name a file arrived with, for the moment between copying it into the
/// database and reading it.
///
/// A file that is not DICOM has no identity of its own: `-[DicomFile
/// getImageFile]` makes one out of the file's **name**, and a trailing number is
/// what turns `scan001.jpg`, `scan002.jpg`, … into one series. The database
/// copies the file to a numbered name of its own first - `2173.tif` - so what
/// the reader saw was that number: every raster file, whatever it was called,
/// came out with the same empty stem and they all fell into a single series.
///
/// The database leaves the original name here on its way past, and the reader
/// takes it. Nothing else uses it, and an entry that is never taken is dropped
/// once the table grows past what an import can hold.
@objc(HorosImportedFileNames)
public final class ImportedFileNames: NSObject {
    private static let gate = NSLock()
    private static var names: [String: String] = [:]
    private static var order: [String] = []
    /// An import hands over its files in one batch, so the table only has to
    /// hold a batch; well past that, the oldest entries were never claimed.
    private static let limit = 20_000

    @objc(rememberName:forPath:)
    public static func remember(_ name: String?, forPath path: String?) {
        guard let name, !name.isEmpty, let path, !path.isEmpty else { return }
        gate.lock()
        defer { gate.unlock() }
        if names.updateValue(name, forKey: path) == nil { order.append(path) }
        while order.count > limit {
            names.removeValue(forKey: order.removeFirst())
        }
    }

    /// The name, and it is forgotten: a stored file is read once on the way in.
    @objc(nameForPath:)
    public static func name(forPath path: String?) -> String? {
        guard let path else { return nil }
        gate.lock()
        defer { gate.unlock() }
        guard let name = names.removeValue(forKey: path) else { return nil }
        if let position = order.firstIndex(of: path) { order.remove(at: position) }
        return name
    }

    @objc public static func forgetAll() {
        gate.lock()
        names.removeAll()
        order.removeAll()
        gate.unlock()
    }

    @objc public static var count: Int {
        gate.lock()
        defer { gate.unlock() }
        return names.count
    }
}
