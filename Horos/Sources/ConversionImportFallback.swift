import Foundation

/// Recovery for inputs left behind by a failed compression/decompression batch.
/// Database allocation and indexing stay with the existing Objective-C importer.
@objc(HorosConversionImportFallback)
public final class ConversionImportFallback: NSObject {
    @objc(recoverFiles:allocateDestination:importFile:)
    public static func recover(
        files: [String],
        allocateDestination: () -> String?,
        importFile: (String) -> Int
    ) -> String {
        let manager = FileManager.default
        var verdicts: [String] = []
        for source in files {
            // Successful conversions removed their source. Archives already
            // have their own failure/retry protocol and must retain it.
            let url = URL(fileURLWithPath: source)
            guard manager.fileExists(atPath: source),
                  !["zip", "osirixzip"].contains(url.pathExtension.lowercased()) else { continue }
            let name = url.lastPathComponent
            guard let destination = allocateDestination(), destination != source else {
                verdicts.append("\(name): conversion failed; cannot allocate an import destination. Original retained at \(source).")
                continue
            }
            do {
                // Keep the source until the existing importer confirms success.
                // In particular, disk-full and unreadable inputs cannot erase it.
                try manager.copyItem(atPath: source, toPath: destination)
                let images = importFile(destination)
                if images > 0 {
                    do {
                        try manager.removeItem(atPath: source)
                        verdicts.append("\(name): indexed unchanged after conversion failed (\(images) image records).")
                    } catch {
                        verdicts.append("\(name): indexed unchanged (\(images) image records); source also retained at \(source): \(error.localizedDescription)")
                    }
                } else {
                    // The importer may quarantine or delete its working copy.
                    // The original stays outside that policy, available for repair.
                    verdicts.append("\(name): conversion failed and the original could not be indexed. Original retained at \(source); import copy was handed to the database at \(destination).")
                }
            } catch {
                verdicts.append("\(name): conversion failed; fallback copy failed: \(error.localizedDescription). Original retained at \(source).")
            }
        }
        return verdicts.joined(separator: "\n")
    }
}
