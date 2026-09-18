import Foundation

/// Waiting for the threads a retrieve has started (#634).
///
/// The IMAGE-level retrieve of `-[DCMTKQueryNode move:retrieveMode:]` hands its
/// associations to threads and waited for them by asking whether any was
/// `isExecuting`. A thread that has just been started has not begun executing:
/// measured right after `+performBlockInBackground:` returned, 300 threads out of
/// 300 still answered NO. The first look therefore found nothing running, the
/// wait ended after one pause, and the move went on - deciding whether the
/// IMAGE level had failed, closing the inventory and releasing its association
/// slot - while the images were still arriving, and a cancellation from then on
/// no longer reached them.
///
/// `isFinished` has no such gap: it is NO from creation until the thread's work
/// has returned.
@objc(HorosRetrieveThreadGroup)
public final class RetrieveThreadGroup: NSObject {

    /// Returns once every thread has finished. While any is still unfinished, a
    /// cancellation of `owner` is passed on to all of them, as often as it is seen.
    @objc(waitForThreads:propagatingCancellationOf:pollInterval:)
    public static func wait(for threads: [Thread], propagatingCancellationOf owner: Thread?,
                            pollInterval: TimeInterval) {
        while threads.contains(where: { !$0.isFinished }) {
            if owner?.isCancelled == true {
                threads.forEach { $0.cancel() }
            }
            Thread.sleep(forTimeInterval: pollInterval)
        }
    }

    /// The same, pausing 50 ms between looks, as the loops it replaces did.
    @objc(waitForThreads:propagatingCancellationOf:)
    public static func wait(for threads: [Thread], propagatingCancellationOf owner: Thread?) {
        wait(for: threads, propagatingCancellationOf: owner, pollInterval: 0.05)
    }

    /// Whether any of the threads was cancelled - by itself, which is how a failed
    /// IMAGE-level association reports, or by the owner.
    @objc(anyCancelled:)
    public static func anyCancelled(_ threads: [Thread]) -> Bool {
        threads.contains { $0.isCancelled }
    }
}
