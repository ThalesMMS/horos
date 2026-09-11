import AppKit
import CoreData

/// Keeping the selected study, series and image across a refresh of the list.
///
/// The browser used to remember the selected rows as the objects themselves and
/// then ask the outline for `rowForItem:`. That works only while the objects
/// survive the refresh. Refreshing a remote index replaces them, so the lookup
/// answered -1, which as an index is `NSUIntegerMax`; the selection was lost and
/// whatever came first took its place. Remembering what a row *is* - the DICOM
/// identifiers, which do survive - finds the same rows again.
@objc(HorosOutlineSelectionRestore)
public final class OutlineSelectionRestore: NSObject {
    @objc(identifierForItem:)
    public static func identifier(for item: Any?) -> String? {
        guard let item = item as? NSObject else { return nil }
        func text(_ key: String) -> String? {
            guard let value = item.value(forKey: key) as? String, !value.isEmpty else { return nil }
            return value
        }
        if item.responds(to: NSSelectorFromString("seriesInstanceUID")), let uid = text("seriesInstanceUID") {
            // Two series of one study can share a description but not an identifier.
            return "series:\(uid)"
        }
        if item.responds(to: NSSelectorFromString("studyInstanceUID")), let uid = text("studyInstanceUID") {
            return "study:\(uid)"
        }
        // Anything else - an object with no DICOM identifier - can still be
        // matched within one session by its own identity.
        if let managed = item as? NSManagedObject {
            return "object:\(managed.objectID.uriRepresentation().absoluteString)"
        }
        return nil
    }

    @objc(identifiersForItems:)
    public static func identifiers(for items: [Any]) -> [String] {
        items.compactMap { identifier(for: $0) }
    }

    /// Select one item, if the outline still holds it. `row(forItem:)` answers -1
    /// for an item it does not hold, and -1 as an index is `NSUIntegerMax`, which
    /// is not a selection anyone asked for.
    @objc(selectItem:inOutline:extending:)
    public static func select(_ item: Any?, in outline: NSOutlineView, extending: Bool) {
        let row = outline.row(forItem: item)
        guard row >= 0 else { return }
        outline.selectRowIndexes(IndexSet(integer: row), byExtendingSelection: extending)
    }

    /// The rows, among `items`, that carry those identifiers - in the order the
    /// identifiers were given, and never a row that is not there.
    @objc(rowsMatching:inItems:)
    public static func rows(matching identifiers: [String], in items: [Any]) -> IndexSet {
        guard !identifiers.isEmpty else { return IndexSet() }
        let wanted = Set(identifiers)
        var rows = IndexSet()
        for (row, item) in items.enumerated() {
            if let found = identifier(for: item), wanted.contains(found) { rows.insert(row) }
        }
        return rows
    }
}
