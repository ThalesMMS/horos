import Foundation

/// Names and reserves the file an image dragged out of a viewer is written into.
///
/// The destination directory belongs to whichever application accepts the drop,
/// so the name has to survive being turned into a path component there. A study
/// or series description is free text out of the DICOM data: it can hold a path
/// separator, a colon, or a leading dot, none of which can go into a file name
/// unexamined. Spaces are kept — this name is read by a person, unlike the
/// export folder names, which follow their own policy.
@objc(HorosDraggedImageFile)
public final class DraggedImageFile: NSObject {
    /// One safe path component describing what is being dragged.
    @objc(nameForStudy:series:)
    public static func name(study: String?, series: String?) -> String {
        let parts = [clean(study), clean(series)].filter { !$0.isEmpty }
        return parts.isEmpty ? "Horos" : parts.joined(separator: " - ")
    }

    /// The first unused URL for that name in `directory`, or nil when the
    /// directory already holds a thousand of them.
    @objc(urlInDirectory:name:pathExtension:)
    public static func url(in directory: URL, name: String, pathExtension: String) -> URL? {
        for index in 0...999 {
            let component = index == 0 ? name : "\(name) (\(index))"
            let candidate = directory.appendingPathComponent(component)
                                     .appendingPathExtension(pathExtension)
            if !FileManager.default.fileExists(atPath: candidate.path) { return candidate }
        }
        return nil
    }

    /// Readable, one component, and short enough for any destination.
    static func clean(_ value: String?) -> String {
        let forbidden = CharacterSet.controlCharacters
            .union(CharacterSet(charactersIn: "/\\:<>|?*\""))
        let mapped = (value ?? "").precomposedStringWithCanonicalMapping.unicodeScalars.map {
            forbidden.contains($0) ? " "
                : (CharacterSet.whitespacesAndNewlines.contains($0) ? " " : String($0))
        }.joined()
        let collapsed = mapped.split(separator: " ", omittingEmptySubsequences: true).joined(separator: " ")
        let trimmed = collapsed.trimmingCharacters(in: CharacterSet(charactersIn: " ."))
        var result = ""
        for character in trimmed {
            guard result.utf8.count + String(character).utf8.count <= 96 else { break }
            result.append(character)
        }
        return result.trimmingCharacters(in: CharacterSet(charactersIn: " ."))
    }
}
