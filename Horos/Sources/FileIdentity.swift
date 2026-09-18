import CryptoKit
import Foundation

/// A NIfTI or Analyze file carries no study, series or instance identifiers: the database names them
/// after the file. Named after the file alone, `subject1/brain.nii` and `subject2/brain.nii` were one
/// study, one series and one image, and imported in place they became a single series showing one of
/// the two volumes (#641). The key tells such files apart by where they are, and a file that stays where
/// it is keeps it: imported again, or read again after a relaunch.
@objc(HorosFileIdentity)
public final class FileIdentity: NSObject {
    /// Sixteen hexadecimal digits of the SHA-256 of the file's standardized path.
    @objc(keyForPath:)
    public static func key(forPath path: String) -> String {
        let standardized = (path as NSString).standardizingPath
        return SHA256.hash(data: Data(standardized.utf8)).prefix(8).map { String(format: "%02x", $0) }.joined()
    }
}
