import Foundation

/// Recovery for inputs left behind by a failed compression/decompression batch.
/// Database allocation and indexing stay with the existing Objective-C importer.
@objc(HorosConversionImportFallback)
public final class ConversionImportFallback: NSObject {
    /// `importFiles` indexes every copy in one call and answers how many image
    /// records each path produced. One file per call used to be one commit per
    /// file, with its notifications and browser refresh (#694).
    @objc(recoverFiles:allocateDestination:importFiles:)
    public static func recover(
        files: [String],
        allocateDestination: () -> String?,
        importFiles: ([String]) -> [String: Int]
    ) -> String {
        let manager = FileManager.default
        var verdicts: [String] = []
        var copies: [(source: String, destination: String, name: String)] = []
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
                copies.append((source, destination, name))
            } catch {
                verdicts.append("\(name): conversion failed; fallback copy failed: \(error.localizedDescription). Original retained at \(source).")
            }
        }
        guard !copies.isEmpty else { return verdicts.joined(separator: "\n") }
        var indexed: [String: Int] = [:]
        for (path, count) in importFiles(copies.map { $0.destination }) {
            indexed[normalized(path), default: 0] += count
        }
        for copy in copies {
            let images = indexed[normalized(copy.destination)] ?? 0
            if images > 0 {
                do {
                    try manager.removeItem(atPath: copy.source)
                    verdicts.append("\(copy.name): indexed unchanged after conversion failed (\(images) image records).")
                } catch {
                    verdicts.append("\(copy.name): indexed unchanged (\(images) image records); source also retained at \(copy.source): \(error.localizedDescription)")
                }
            } else {
                // The importer may quarantine or delete its working copy.
                // The original stays outside that policy, available for repair.
                verdicts.append("\(copy.name): conversion failed and the original could not be indexed. Original retained at \(copy.source); import copy was handed to the database at \(copy.destination).")
            }
        }
        return verdicts.joined(separator: "\n")
    }

    private static func normalized(_ path: String) -> String {
        URL(fileURLWithPath: path).standardizedFileURL.resolvingSymlinksInPath().path
    }
}
