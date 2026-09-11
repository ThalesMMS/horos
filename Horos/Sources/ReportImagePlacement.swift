import AppKit
import Foundation

/// A figure that goes into a Pages or Word report at a size that does not
/// depend on the pixel dimensions of the source, and that stays put when the
/// document is saved and opened again.
@objc(HorosReportImagePlacement)
public final class ReportImagePlacement: NSObject {

    /// 12 cm by 9 cm at 72 pt/inch. A CT or MR frame is fitted inside this box
    /// so two insertions of the same image occupy the same space.
    @objc public static let defaultBox = CGSize(width: 340, height: 255)

    @objc(displaySizeWithPixelWidth:pixelHeight:box:)
    public static func displaySize(pixelWidth: Double, pixelHeight: Double, box: CGSize) -> CGSize {
        guard pixelWidth > 0, pixelHeight > 0, box.width > 0, box.height > 0 else { return .zero }
        let scale = min(box.width / pixelWidth, box.height / pixelHeight)
        return CGSize(width: pixelWidth * scale, height: pixelHeight * scale)
    }

    @objc(displaySizeWithPixelWidth:pixelHeight:)
    public static func displaySize(pixelWidth: Double, pixelHeight: Double) -> CGSize {
        displaySize(pixelWidth: pixelWidth, pixelHeight: pixelHeight, box: defaultBox)
    }
}

@objc(HorosReportImageKind)
public enum ReportImageKind: Int {
    case pages
    case word
    case unsupported
}

@objc(HorosReportPreparedImage)
public final class ReportPreparedImage: NSObject {
    @objc public let path: String
    @objc public let widthPoints: Double
    @objc public let heightPoints: Double

    @objc public init(path: String, widthPoints: Double, heightPoints: Double) {
        self.path = path
        self.widthPoints = widthPoints
        self.heightPoints = heightPoints
    }
}

/// Copies the selected frames next to the report and asks Pages or Word to
/// insert them as inline figures. The editor is driven on a private copy; the
/// original report is replaced only after that copy has been written.
@objc(HorosReportImageInsertion)
public final class ReportImageInsertion: NSObject {

    /// The last AppleScript or lookup failure. Native Pages/Word proof reads
    /// this number; a generic alert is not a captured error.
    @objc public static var lastError: NSDictionary?

    /// Human-readable recovery text for the last failure, including the
    /// AppleScript number when the editor timed out, refused Automation, or
    /// could not take the figure.
    @objc public static func lastErrorMessage() -> String {
        errorMessage(from: lastError)
    }

    @objc(errorMessageFromError:)
    public static func errorMessage(from error: NSDictionary?) -> String {
        let code = appleScriptErrorCode(error)
        switch code {
        case -1712:
            return NSLocalizedString("Horos did not receive a reply from Pages or Word in time (error -1712). If macOS asked for Automation permission, allow Horos to control Pages and Microsoft Word in System Settings > Privacy & Security > Automation, then retry. The original report and the source images have been preserved.", comment: "")
        case -609:
            return NSLocalizedString("Pages or Word dropped the Automation connection (error -609). Check that the editor is still running, allow Horos to control it in System Settings > Privacy & Security > Automation, then retry. The original report and the source images have been preserved.", comment: "")
        case -1743:
            return NSLocalizedString("Automation was denied. Allow Horos to control Pages and Microsoft Word in System Settings > Privacy & Security > Automation, then retry. The original report and the source images have been preserved.", comment: "")
        case -1728:
            return NSLocalizedString("Microsoft Word is not installed or could not be located (error -1728). Install Word with creation and editing enabled to insert images into a .doc or .docx report. The original report and the source images have been preserved.", comment: "")
        case -10024:
            return NSLocalizedString("Pages could not insert the image into that container (error -10024). The original report and the source images have been preserved.", comment: "")
        case -43:
            return NSLocalizedString("Pages or Word could not be found (error -43). The original report and the source images have been preserved.", comment: "")
        default:
            if code == 0 {
                return NSLocalizedString("The selected images could not be inserted. The original report and the source images have been preserved.", comment: "")
            }
            return String(format: NSLocalizedString("The selected images could not be inserted (error %ld). The original report and the source images have been preserved.", comment: ""), code)
        }
    }

    @objc(kindOfReportPath:)
    public static func kind(ofReportPath path: String) -> ReportImageKind {
        switch (path as NSString).pathExtension.lowercased() {
        case "pages": return .pages
        case "doc", "docx": return .word
        default: return .unsupported
        }
    }

    @objc(writeJPEG:toPath:)
    public static func writeJPEG(_ image: NSImage, to path: String) -> Bool {
        guard let tiff = image.tiffRepresentation,
              let rep = NSBitmapImageRep(data: tiff),
              let data = rep.representation(using: .jpeg, properties: [.compressionFactor: 0.9])
        else { return false }
        do {
            try data.write(to: URL(fileURLWithPath: path), options: .atomic)
            return true
        } catch {
            return false
        }
    }

    /// Writes a JPEG next to the report. The source path is never opened for
    /// writing, and a destination that resolves to the source is refused.
    @objc(writeCopyFrom:to:)
    public static func writeCopy(from sourcePath: String, to destinationPath: String) -> Bool {
        let source = URL(fileURLWithPath: sourcePath).resolvingSymlinksInPath()
        let destination = URL(fileURLWithPath: destinationPath).resolvingSymlinksInPath()
        guard source != destination else { return false }
        guard let image = NSImage(contentsOf: source) else { return false }
        return writeJPEG(image, to: destination.path)
    }

    @objc(prepareSources:directory:)
    public static func prepare(sources: [String], directory: String) -> [ReportPreparedImage] {
        let manager = FileManager.default
        do {
            try manager.createDirectory(atPath: directory, withIntermediateDirectories: true)
        } catch {
            return []
        }
        var prepared: [ReportPreparedImage] = []
        for (index, source) in sources.enumerated() {
            let name = String(format: "%04ld.jpg", index + 1)
            let destination = (directory as NSString).appendingPathComponent(name)
            guard writeCopy(from: source, to: destination),
                  let image = NSImage(contentsOfFile: destination) else { return [] }
            let size = ReportImagePlacement.displaySize(
                pixelWidth: Double(image.size.width),
                pixelHeight: Double(image.size.height),
                box: ReportImagePlacement.defaultBox
            )
            guard size.width > 0, size.height > 0 else { return [] }
            prepared.append(ReportPreparedImage(path: destination, widthPoints: size.width, heightPoints: size.height))
        }
        return prepared
    }

    @objc(pagesScriptWithDocumentName:images:)
    public static func pagesScript(documentName: String, images: [ReportPreparedImage]) -> String {
        var lines = [
            "tell application id \"com.apple.Pages\"",
            "  with timeout of 600 seconds",
        ]
        lines.append(contentsOf: waitForNamedDocumentLines(documentName, missing: "Pages did not open the report"))
        lines.append("    try")
        for image in images {
            lines.append("      make new image at end of body text of d with properties {file:(POSIX file \(appleString(image.path))), width:\(appleNumber(image.widthPoints)), height:\(appleNumber(image.heightPoints))}")
        }
        lines.append(contentsOf: closeNamedDocumentOnErrorLines())
        lines.append(contentsOf: [
            "  end timeout",
            "end tell",
        ])
        return lines.joined(separator: "\n")
    }

    @objc(wordScriptWithDocumentName:images:)
    public static func wordScript(documentName: String, images: [ReportPreparedImage]) -> String {
        var lines = [
            "tell application \"Microsoft Word\"",
            "  with timeout of 600 seconds",
        ]
        lines.append(contentsOf: waitForNamedDocumentLines(documentName, missing: "Word did not open the report"))
        lines.append("    try")
        for image in images {
            lines.append("      set pic to make inline picture at text object of d file name \(appleString(image.path))")
            lines.append("      set width of pic to \(appleNumber(image.widthPoints))")
            lines.append("      set height of pic to \(appleNumber(image.heightPoints))")
        }
        lines.append(contentsOf: closeNamedDocumentOnErrorLines())
        lines.append(contentsOf: [
            "  end timeout",
            "end tell",
        ])
        return lines.joined(separator: "\n")
    }

    @objc(insertWithReportPath:sources:runner:)
    public static func insert(reportPath: String, sources: [String], runner: @escaping (String, String) -> Bool) -> Bool {
        lastError = nil
        let kind = kind(ofReportPath: reportPath)
        guard kind != .unsupported, !sources.isEmpty else { return false }
        let original = URL(fileURLWithPath: reportPath)
        var isDirectory: ObjCBool = false
        guard FileManager.default.fileExists(atPath: reportPath, isDirectory: &isDirectory) else { return false }

        let work = FileManager.default.temporaryDirectory.appendingPathComponent("horos-report-images-\(UUID().uuidString)")
        defer { try? FileManager.default.removeItem(at: work) }
        do {
            try FileManager.default.createDirectory(at: work, withIntermediateDirectories: true)
            // A private name, not the original filename: Pages and Word find the
            // document by name, and the already-open report would otherwise be
            // the one the script edited.
            let preparedName = "Horos-inserted-report.\(original.pathExtension)"
            let prepared = work.appendingPathComponent(preparedName)
            try FileManager.default.copyItem(at: original, to: prepared)
            let copies = prepare(sources: sources, directory: work.appendingPathComponent("images").path)
            guard copies.count == sources.count else { return false }
            let script = kind == .pages
                ? pagesScript(documentName: preparedName, images: copies)
                : wordScript(documentName: preparedName, images: copies)
            guard runner(script, prepared.path) else { return false }
            _ = try FileManager.default.replaceItemAt(original, withItemAt: prepared)
            return true
        } catch {
            return false
        }
    }

    @objc(insertWithReportPath:sources:)
    public static func insert(reportPath: String, sources: [String]) -> Bool {
        insert(reportPath: reportPath, sources: sources) { script, prepared in
            run(script, opening: prepared, kind: kind(ofReportPath: reportPath))
        }
    }

    /// Opens the private copy the way a person would, then sends the script.
    /// Waiting on NSWorkspace's completion handler from the main thread is a
    /// deadlock; the script waits for the document by name instead.
    @objc(runScript:opening:kind:)
    public static func run(_ script: String, opening path: String, kind: ReportImageKind) -> Bool {
        lastError = nil
        guard let application = applicationURL(for: kind) else {
            rememberError(code: kind == .word ? -1728 : -43,
                          message: kind == .word ? "Microsoft Word is not installed" : "Pages is not installed")
            return false
        }
        let configuration = NSWorkspace.OpenConfiguration()
        configuration.activates = false
        NSWorkspace.shared.open([URL(fileURLWithPath: path)], withApplicationAt: application,
                                configuration: configuration, completionHandler: nil)
        guard let appleScript = NSAppleScript(source: script) else {
            NSLog("---- the script that inserts a report image would not compile")
            rememberError(code: 1, message: "The script that inserts a report image would not compile")
            return false
        }
        var error: NSDictionary?
        appleScript.executeAndReturnError(&error)
        if let error {
            lastError = error
            NSLog("---- the report image could not be inserted: %@", error)
            closeNamedDocument((path as NSString).lastPathComponent, kind: kind)
            return false
        }
        return true
    }

    private static func applicationURL(for kind: ReportImageKind) -> URL? {
        switch kind {
        case .pages:
            // Same order as HorosPagesApplication: Pages '09 still wins when both
            // are installed, because a '09 document needs that editor.
            return NSWorkspace.shared.urlForApplication(withBundleIdentifier: "com.apple.iWork.Pages")
                ?? NSWorkspace.shared.urlForApplication(withBundleIdentifier: "com.apple.Pages")
        case .word:
            return NSWorkspace.shared.urlForApplication(withBundleIdentifier: "com.microsoft.Word")
        case .unsupported:
            return nil
        }
    }

    private static func waitForNamedDocumentLines(_ name: String, missing: String) -> [String] {
        [
            "    set d to missing value",
            "    repeat with attempt from 1 to 60",
            "      repeat with candidate in documents",
            "        if (name of candidate) is \(appleString(name)) then",
            "          set d to contents of candidate",
            "          exit repeat",
            "        end if",
            "      end repeat",
            "      if d is not missing value then exit repeat",
            "      delay 0.5",
            "    end repeat",
            "    if d is missing value then error \(appleString(missing))",
        ]
    }

    private static func closeNamedDocumentOnErrorLines() -> [String] {
        [
            "      save d",
            "      close d saving no",
            "    on error errorMessage number errorNumber",
            "      try",
            "        close d saving no",
            "      end try",
            "      error errorMessage number errorNumber",
            "    end try",
        ]
    }

    /// Only the private copy, never the document the user already had open.
    private static func closeNamedDocument(_ name: String, kind: ReportImageKind) {
        let tell = kind == .pages
            ? "tell application id \"com.apple.Pages\""
            : "tell application \"Microsoft Word\""
        let source = [
            tell,
            "  with timeout of 15 seconds",
            "    try",
            "      repeat with candidate in documents",
            "        if (name of candidate) is \(appleString(name)) then",
            "          close (contents of candidate) saving no",
            "          exit repeat",
            "        end if",
            "      end repeat",
            "    end try",
            "  end timeout",
            "end tell",
        ].joined(separator: "\n")
        guard let appleScript = NSAppleScript(source: source) else { return }
        var ignored: NSDictionary?
        appleScript.executeAndReturnError(&ignored)
    }

    private static func rememberError(code: Int, message: String) {
        lastError = [
            NSAppleScript.errorNumber: NSNumber(value: code),
            NSAppleScript.errorMessage: message,
        ]
    }

    private static func appleScriptErrorCode(_ error: NSDictionary?) -> Int {
        guard let error else { return 0 }
        if let number = error[NSAppleScript.errorNumber] as? NSNumber {
            return number.intValue
        }
        if let number = error["NSAppleScriptErrorNumber"] as? Int {
            return number
        }
        return 0
    }

    private static func appleString(_ value: String) -> String {
        let escaped = value
            .replacingOccurrences(of: "\\", with: "\\\\")
            .replacingOccurrences(of: "\"", with: "\\\"")
        return "\"\(escaped)\""
    }

    private static func appleNumber(_ value: Double) -> String {
        String(format: "%g", value)
    }
}
