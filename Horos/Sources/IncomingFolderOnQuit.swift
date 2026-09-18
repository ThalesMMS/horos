import Foundation

/// What quitting does to the INCOMING folder when `DoNotEmptyIncomingDir` is off (#629).
///
/// The cleanup used to list INCOMING.noindex and then delete, and trash, each
/// name *inside TEMP.noindex*: the paths were composed from the wrong folder. The
/// only thing that ever emptied INCOMING was the fallback after those loops,
/// which sent the whole folder to the Trash. That accident is the right
/// behaviour: whatever is still in INCOMING when the app quits was received and
/// never imported, and the Trash keeps it recoverable where a delete would not.
/// So that is now the rule, stated once, with no stray calls on TEMP.noindex.
@objc(HorosIncomingFolderOnQuit)
public final class IncomingFolderOnQuit: NSObject {

    /// Entries that make the folder worth sending to the Trash. Finder's
    /// `.DS_Store` alone does not: it holds nothing that was received.
    @objc(pendingEntriesInFolder:)
    public class func pendingEntries(inFolder path: String) -> [String] {
        let names = (try? FileManager.default.contentsOfDirectory(atPath: path)) ?? []
        return names.filter { $0 != ".DS_Store" }.sorted()
    }

    /// Sends the folder to the Trash of its volume when it still holds anything.
    ///
    /// Returns without doing anything when there is nothing pending. On success
    /// `resultingPath` is where the system put the folder (nil when nothing was
    /// sent); on failure the folder is left where it was and the error says why.
    /// The caller recreates the empty folder afterwards.
    @objc(sendToTrashIfPending:resultingPath:error:)
    public class func sendToTrashIfPending(_ path: String,
                                           resultingPath: AutoreleasingUnsafeMutablePointer<NSString?>?) throws {
        resultingPath?.pointee = nil
        guard !path.isEmpty, !pendingEntries(inFolder: path).isEmpty else { return }
        var resulting: NSURL?
        try FileManager.default.trashItem(at: URL(fileURLWithPath: path, isDirectory: true), resultingItemURL: &resulting)
        resultingPath?.pointee = resulting?.path as NSString?
    }
}
