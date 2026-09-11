import AppKit
import Foundation

/// Pages → PDF without touching the report that was asked for.
///
/// Horos issue 560 / workbench #129: Pages 10 on RC4 no longer produced a
/// DICOM PDF, from the menu or from marking the study Validated. The script
/// addressed Pages by its localized name and sent it an `open` of a path.
/// Pages is sandboxed; that `open` is answered and no document appears, so
/// exporting the front document has nothing to write. The original .pages
/// was the one thing that had to survive that failure, and it did only by
/// accident — the script never copied it, so a destination that resolved
/// onto the report would have replaced it.
///
/// The file is opened the way a person opens one, through LaunchServices,
/// which is what grants Pages the file. Export runs against a working copy
/// whose name we chose, so the report on the study is never the destination
/// and is never saved or closed. A PDF that did not actually appear is
/// discarded; the caller must not import it.
@objc(HorosPagesPDFConversion)
public final class PagesPDFConversion: NSObject {

    @objc(isUsablePDFAtPath:)
    public static func isUsablePDF(at path: String) -> Bool {
        guard FileManager.default.fileExists(atPath: path),
              let handle = FileHandle(forReadingAtPath: path) else { return false }
        defer {
            if #available(macOS 10.15, *) {
                try? handle.close()
            } else {
                handle.closeFile()
            }
        }
        let header = handle.readData(ofLength: 5)
        guard header.count == 5, String(data: header, encoding: .ascii) == "%PDF-" else {
            return false
        }
        let size = (try? FileManager.default.attributesOfItem(atPath: path)[.size] as? NSNumber)?.intValue ?? 0
        return size > 32
    }

    /// Tags that make an encapsulated PDF belong to the study even when no
    /// source DICOM file was found to copy from.
    @objc(associationAttributesWithStudyInstanceUID:patientName:patientID:accessionNumber:studyDescription:)
    public static func associationAttributes(studyInstanceUID: String?,
                                             patientName: String?,
                                             patientID: String?,
                                             accessionNumber: String?,
                                             studyDescription: String?) -> [String: String] {
        var attributes: [String: String] = [:]
        func put(_ name: String, _ value: String?) {
            guard let value, !value.isEmpty else { return }
            attributes[name] = value
        }
        put("StudyInstanceUID", studyInstanceUID)
        put("PatientsName", patientName)
        put("PatientID", patientID)
        put("AccessionNumber", accessionNumber)
        put("StudyDescription", studyDescription)
        return attributes
    }

    /// Writes `pdfPath` from `reportPath`. false leaves `reportPath` as it was
    /// and does not leave a PDF that anyone should import.
    @objc(convertReportAtPath:toPDFAtPath:error:)
    public static func convertReport(at reportPath: String,
                                     toPDFAt pdfPath: String,
                                     error outError: NSErrorPointer) -> Bool {
        let report = URL(fileURLWithPath: reportPath).resolvingSymlinksInPath()
        let destination = URL(fileURLWithPath: pdfPath).resolvingSymlinksInPath()
        var isDirectory: ObjCBool = false
        guard FileManager.default.fileExists(atPath: report.path, isDirectory: &isDirectory) else {
            return fail(1, "The Pages report is missing. Nothing was converted.", outError)
        }
        if destination.path == report.path || isInside(destination, parent: report) {
            return fail(2, "The PDF cannot replace the Pages report. The original report has been left unchanged.", outError)
        }
        guard let application = PagesApplication.url() else {
            return fail(3, "Pages is not installed or could not be located. The original report has been left unchanged.", outError)
        }
        guard let identifier = Bundle(url: application)?.bundleIdentifier,
              ["com.apple.iWork.Pages", "com.apple.Pages"].contains(identifier) else {
            return fail(3, "Pages is not installed or could not be located. The original report has been left unchanged.", outError)
        }

        let work = FileManager.default.temporaryDirectory
            .appendingPathComponent("horos-pages-pdf-\(UUID().uuidString)", isDirectory: true)
        do {
            try FileManager.default.createDirectory(at: work, withIntermediateDirectories: true)
        } catch {
            return fail(4, "The Pages report could not be copied for export. The original report has been left unchanged.", outError)
        }
        defer { try? FileManager.default.removeItem(at: work) }

        let copy = work.appendingPathComponent("horos-\(UUID().uuidString).pages")
        do {
            try FileManager.default.copyItem(at: report, to: copy)
        } catch {
            return fail(4, "The Pages report could not be copied for export. The original report has been left unchanged.", outError)
        }

        let configuration = NSWorkspace.OpenConfiguration()
        configuration.activates = false
        // No waiting on the completion handler: it is delivered on the main
        // queue, and report conversion runs on the main thread, so waiting
        // here is a deadlock. The script waits for the document by name.
        NSWorkspace.shared.open([copy], withApplicationAt: application,
                                configuration: configuration, completionHandler: nil)

        var exported: URL?
        for candidate in exportDestinations(application: application, work: work) {
            if run(exportScript, [copy.lastPathComponent, candidate.path,
                                  usesModernExport() ? "1" : "0", identifier]) != nil,
               isUsablePDF(at: candidate.path) {
                exported = candidate
                break
            }
            if FileManager.default.fileExists(atPath: candidate.path) {
                try? FileManager.default.removeItem(at: candidate)
            }
        }
        guard let exported else {
            return fail(5, "Pages could not export the report as PDF. Check that Horos is allowed to control Pages in System Settings > Privacy & Security > Automation. The original report has been left unchanged.", outError)
        }

        do {
            if FileManager.default.fileExists(atPath: destination.path) {
                try FileManager.default.removeItem(at: destination)
            }
            try FileManager.default.createDirectory(at: destination.deletingLastPathComponent(),
                                                    withIntermediateDirectories: true)
            try FileManager.default.copyItem(at: exported, to: destination)
        } catch {
            try? FileManager.default.removeItem(at: destination)
            return fail(6, "The PDF was exported but could not be stored. The original report has been left unchanged.", outError)
        }
        if exported.path != destination.path {
            try? FileManager.default.removeItem(at: exported)
        }
        guard isUsablePDF(at: destination.path) else {
            try? FileManager.default.removeItem(at: destination)
            return fail(5, "Pages could not export the report as PDF. The original report has been left unchanged.", outError)
        }
        return true
    }

    // MARK: talking to Pages

    private static let exportScript = """
    on run argv
      set nm to item 1 of argv
      set dest to item 2 of argv
      set modern to item 3 of argv
      set bundleId to item 4 of argv
      with timeout of 600 seconds
      tell application id bundleId
        set d to missing value
        repeat with attempt from 1 to 60
          repeat with candidate in documents
            if (name of candidate) is nm then
              set d to contents of candidate
              exit repeat
            end if
          end repeat
          if d is not missing value then exit repeat
          delay 0.5
        end repeat
        if d is missing value then error "Pages did not open " & nm
        if modern is "1" then
          export d to (POSIX file dest) as PDF
        else
          save d as "SLDocumentTypePDF" in (POSIX file dest)
        end if
        close d saving no
      end tell
      end timeout
      return "done"
    end run
    """

    private static func usesModernExport() -> Bool {
        guard let version = PagesApplication.information()?["CFBundleShortVersionString"] as? String,
              let major = version.split(separator: ".").first,
              let number = Int(major) else { return true }
        return number < 1 || number >= 5
    }

    private static func exportDestinations(application: URL, work: URL) -> [URL] {
        var destinations = [work.appendingPathComponent("export.pdf")]
        if let identifier = Bundle(url: application)?.bundleIdentifier {
            let container = FileManager.default.homeDirectoryForCurrentUser
                .appendingPathComponent("Library/Containers/\(identifier)/Data/tmp", isDirectory: true)
            if (try? FileManager.default.createDirectory(at: container, withIntermediateDirectories: true)) != nil
                || FileManager.default.fileExists(atPath: container.path) {
                destinations.append(container.appendingPathComponent("horos-pages-pdf-\(UUID().uuidString).pdf"))
            }
        }
        return destinations
    }

    private static func isInside(_ child: URL, parent: URL) -> Bool {
        let childPath = child.path
        let parentPath = parent.path
        let prefix = parentPath.hasSuffix("/") ? parentPath : parentPath + "/"
        return childPath.hasPrefix(prefix)
    }

    private static func run(_ source: String, _ arguments: [String]) -> String? {
        guard let script = NSAppleScript(source: source) else {
            NSLog("---- the script that exports a Pages report would not compile")
            return nil
        }
        let list = NSAppleEventDescriptor.list()
        for (index, value) in arguments.enumerated() {
            list.insert(NSAppleEventDescriptor(string: value), at: index + 1)
        }
        let event = NSAppleEventDescriptor(eventClass: AEEventClass(kCoreEventClass),
                                           eventID: AEEventID(kAEOpenApplication),
                                           targetDescriptor: nil,
                                           returnID: AEReturnID(kAutoGenerateReturnID),
                                           transactionID: AETransactionID(kAnyTransactionID))
        event.setParam(list, forKeyword: AEKeyword(keyDirectObject))
        var error: NSDictionary?
        let result = script.executeAppleEvent(event, error: &error)
        if let error {
            NSLog("---- the Pages report could not be exported: %@", error)
            return nil
        }
        return result.stringValue ?? "done"
    }

    @discardableResult
    private static func fail(_ code: Int, _ message: String, _ error: NSErrorPointer) -> Bool {
        NSLog("---- Pages PDF conversion failed: %@", message)
        if let error {
            error.pointee = NSError(domain: "HorosPagesPDFConversion", code: code,
                                    userInfo: [NSLocalizedDescriptionKey: message])
        }
        return false
    }
}
