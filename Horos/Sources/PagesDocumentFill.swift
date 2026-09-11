import AppKit
import Foundation

/// Filling in a Pages document that has no `index.xml`.
///
/// A template saved by Pages 5 or later is IWA - compressed protocol buffers -
/// so the text substitution that works on a Pages '09 package has nothing to
/// edit, and a modern template could only be refused. Pages itself can be asked,
/// which is what the Word report already does with its mail merge.
///
/// A paragraph at a time, and not a range of characters: `set characters i thru
/// j of body text to "x"` assigns the *whole* string to *each* character of the
/// range - measured, it turned one placeholder into twenty copies of the value -
/// because that is what assigning to a plural element means in AppleScript.
@objc(HorosPagesDocumentFill)
public final class PagesDocumentFill: NSObject {

    /// Opens the document, replaces what `substitute` changes, saves and closes
    /// it. false when Pages could not be driven, and then nothing was written.
    ///
    /// Pages saves documents by itself, so the file handed here has to be a copy
    /// that may be thrown away: measured, an edit made through AppleScript was on
    /// disk before anything asked for it to be saved.
    @objc(fillDocumentAtPath:substitute:)
    public static func fill(documentAt path: String,
                            substitute: (String) -> String) -> Bool {
        guard let (identifier, body) = open(path) else {
            NSLog("---- Pages did not open the report at %@", path)
            return false
        }

        // Last paragraph first: a replacement that is not one line changes the
        // numbering of everything after it.
        var edits: [String] = [identifier]
        let paragraphs = body.components(separatedBy: "\n")
        for (index, paragraph) in paragraphs.enumerated().reversed() {
            let filled = substitute(paragraph)
            if filled != paragraph {
                edits.append(String(index + 1))
                edits.append(filled + "\n")
            }
        }
        if edits.count == 1 {
            // Nothing to fill in, and the copy stands as the template does.
            return run(Self.closeScript, [identifier]) != nil
        }
        return run(Self.writeScript, edits) != nil
    }

    // MARK: talking to Pages

    /// Pages is sandboxed, and asking it over AppleScript to open a path of our
    /// choosing did nothing at all - measured: the event was answered, and no
    /// document appeared. The file is opened the way a person opens one, through
    /// LaunchServices, which is what grants Pages the file; the script then only
    /// has to find the document that appeared, by the name of the file, and
    /// `open` does not answer with it.
    private static let openScript = """
    on run argv
      set nm to item 1 of argv
      with timeout of 600 seconds
      tell application id "com.apple.Pages"
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
        return ((id of d) as string) & linefeed & (body text of d as string)
      end tell
      end timeout
    end run
    """

    private static let writeScript = """
    on run argv
      set docId to item 1 of argv
      with timeout of 600 seconds
      tell application id "com.apple.Pages"
        set d to document id docId
        repeat with k from 2 to (count of argv) by 2
          set i to (item k of argv) as integer
          set paragraph i of body text of d to (item (k + 1) of argv)
        end repeat
        save d
        close d saving no
      end tell
      end timeout
      return "done"
    end run
    """

    private static let closeScript = """
    on run argv
      with timeout of 600 seconds
      tell application id "com.apple.Pages"
        close (document id (item 1 of argv)) saving no
      end tell
      end timeout
      return "done"
    end run
    """

    private static func open(_ path: String) -> (String, String)? {
        let name = (path as NSString).lastPathComponent
        guard let application = PagesApplication.url() else { return nil }
        // No waiting on the completion handler: it is delivered on the main
        // queue, and this runs on the main thread, so waiting for it here is a
        // deadlock - measured, the report generation stopped dead at this line.
        // The script below waits for the document to appear instead, which is
        // the thing actually being waited for.
        let configuration = NSWorkspace.OpenConfiguration()
        configuration.activates = false
        NSWorkspace.shared.open([URL(fileURLWithPath: path)], withApplicationAt: application,
                                configuration: configuration, completionHandler: nil)
        guard let answer = run(openScript, [name]) else { return nil }
        guard let newline = answer.firstIndex(of: "\n") else { return nil }
        let identifier = String(answer[answer.startIndex..<newline])
        let body = String(answer[answer.index(after: newline)...])
        return identifier.isEmpty ? nil : (identifier, body)
    }

    /// `on run argv` is reached by sending the script an open-application event
    /// whose direct object is the argument list; that is how AppleScript passes
    /// argv, and it is the only way to hand a script a value from here.
    private static func run(_ source: String, _ arguments: [String]) -> String? {
        guard let script = NSAppleScript(source: source) else {
            NSLog("---- the script that fills in a Pages document would not compile")
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
            NSLog("---- the Pages document could not be filled in: %@", error)
            return nil
        }
        return result.stringValue ?? "done"
    }
}
