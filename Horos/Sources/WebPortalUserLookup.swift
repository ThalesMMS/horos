import CoreData
import Foundation

/// Finding a Web Portal user by the name someone typed.
///
/// Both the sign-in path and the administration page used
/// `name LIKE[cd] %@`. `LIKE` reads `*` and `?` as wildcards, so a name
/// carrying one matched other people's accounts; and the two paths then
/// disagreed about which of several matches to take — the administration page
/// kept the first and sign-in kept the last. An account edited in one place
/// could therefore be a different account from the one being signed in to.
@objc(HorosWebPortalUserLookup)
public final class WebPortalUserLookup: NSObject {
    /// Equality, not pattern matching, and still insensitive to case and
    /// diacritics so that existing sign-ins keep working.
    @objc(predicateForName:)
    public static func predicate(forName name: String) -> NSPredicate {
        NSPredicate(format: "name ==[cd] %@", name)
    }

    /// The account `name` means, resolved the same way everywhere:
    /// an exact match first, then a single match that differs only in case or
    /// diacritics. Several such matches resolve to none — picking one of them
    /// is what let an administrator edit one account while someone signed in to
    /// another.
    @objc(userAmong:forName:)
    public static func user(among matches: [NSManagedObject], forName name: String) -> NSManagedObject? {
        let named = matches.filter { $0.value(forKey: "name") is String }
        if let exact = named.first(where: { $0.value(forKey: "name") as? String == name }) {
            return exact
        }
        return named.count == 1 ? named.first : nil
    }
}
