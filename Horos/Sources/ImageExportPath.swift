import Foundation

/// Builds numbered image filenames while preserving dots in the chosen base name.
@objc(HorosImageExportPath)
public final class ImageExportPath: NSObject {
    @objc(pathForSelection:index:extension:)
    public static func path(selection: String, index: Int, fileExtension: String) -> String {
        var base = (selection as NSString).deletingPathExtension
        // The save panel proposes "Series.0001.jpg" for a multi-image export.
        if (base as NSString).pathExtension == "0001" {
            base = (base as NSString).deletingPathExtension
        }
        return (base as NSString).appendingPathExtension(String(format: "%04ld.%@", index, fileExtension))!
    }
}
