#!/usr/bin/env python3
"""The selected study and series survive a refresh that replaces the objects.

The browser remembered the selected rows as the objects themselves and asked the
outline for `rowForItem:` afterwards. Refreshing a remote index replaces those
objects, so the lookup answered -1 - NSUIntegerMax as an index - and the
selection was lost, which is the report of the list jumping back to the first
patient on every refresh.
"""
from pathlib import Path
import subprocess, tempfile

root = Path(__file__).resolve().parents[1]
browser = (root / 'Horos/Sources/BrowserController.m').read_bytes().decode('latin1')
assert 'indexSetWithIndex: [databaseOutline rowForItem:' not in browser, \
    'a row that the outline does not hold can reach selectRowIndexes: again as -1'
assert browser.count('HorosOutlineSelectionRestore selectItem:') >= 8, \
    'the guarded selection is no longer used everywhere it was'
assert 'HorosOutlineSelectionRestore rowsMatching:' in browser, \
    'the browser no longer restores the selection by identifier'

source = r'''
import CoreData
import Foundation

// Managed objects with the attributes the outline holds, in a throwaway store.
let model = NSManagedObjectModel()
func entity(_ name: String, _ attributes: [String]) -> NSEntityDescription {
    let description = NSEntityDescription()
    description.name = name
    description.managedObjectClassName = NSStringFromClass(NSManagedObject.self)
    description.properties = attributes.map {
        let attribute = NSAttributeDescription()
        attribute.name = $0
        attribute.attributeType = .stringAttributeType
        return attribute
    }
    return description
}
model.entities = [entity("Study", ["studyInstanceUID", "name"]),
                  entity("Series", ["seriesInstanceUID", "studyInstanceUID", "name"]),
                  entity("Album", ["name"])]
let coordinator = NSPersistentStoreCoordinator(managedObjectModel: model)
try! coordinator.addPersistentStore(ofType: NSInMemoryStoreType, configurationName: nil, at: nil, options: nil)
let context = NSManagedObjectContext(concurrencyType: .mainQueueConcurrencyType)
context.persistentStoreCoordinator = coordinator

func make(_ name: String, _ values: [String: String]) -> NSManagedObject {
    let object = NSEntityDescription.insertNewObject(forEntityName: name, into: context)
    for (key, value) in values { object.setValue(value, forKey: key) }
    return object
}

// The list before a refresh, and the same list rebuilt as new objects after one.
func build() -> [NSManagedObject] {
    [make("Study", ["studyInstanceUID": "1.2.3", "name": "Alpha"]),
     make("Study", ["studyInstanceUID": "1.2.4", "name": "Bravo"]),
     make("Series", ["seriesInstanceUID": "1.2.4.1", "studyInstanceUID": "1.2.4", "name": "axial"]),
     make("Series", ["seriesInstanceUID": "1.2.4.2", "studyInstanceUID": "1.2.4", "name": "coronal"]),
     make("Study", ["studyInstanceUID": "1.2.5", "name": "Charlie"])]
}
let before = build()
let after = build()

// The second study and its second series were selected; after the refresh the
// same two rows have to come back, and by identifier, not by pointer.
let selected = [before[1], before[3]]
let identifiers = OutlineSelectionRestore.identifiers(for: selected)
precondition(identifiers == ["study:1.2.4", "series:1.2.4.2"], "\(identifiers)")
let rows = OutlineSelectionRestore.rows(matching: identifiers, in: after)
precondition(rows == IndexSet([1, 3]), "\(rows)")
// None of the new objects is the old one, which is the case that used to fail.
precondition(!after.contains(where: { $0 === before[1] }))

// A row that really is gone is simply not selected, and nothing else moves.
let shorter = [after[0], after[4]]
precondition(OutlineSelectionRestore.rows(matching: identifiers, in: shorter).isEmpty)
// A study and a series never answer for each other, even with the same text.
let ambiguous = OutlineSelectionRestore.rows(matching: ["study:1.2.4.2"], in: after)
precondition(ambiguous.isEmpty, "a series identifier matched a study")
// An album row, which has neither identifier, is skipped rather than crashing.
let album = make("Album", ["name": "Today"])
precondition(OutlineSelectionRestore.identifier(for: album) != nil)
precondition(OutlineSelectionRestore.identifiers(for: [album, NSNull()]).count == 1)
precondition(OutlineSelectionRestore.rows(matching: [], in: after).isEmpty)

// Selecting one item: an outline that does not hold it must keep its selection.
import AppKit
final class Outline: NSOutlineView {
    var held: [Any] = []
    override func row(forItem item: Any?) -> Int {
        guard let item = item as? NSObject else { return -1 }
        return held.firstIndex(where: { ($0 as? NSObject) === item }) ?? -1
    }
    var selected = IndexSet()
    override func selectRowIndexes(_ indexes: IndexSet, byExtendingSelection extend: Bool) {
        selected = extend ? selected.union(indexes) : indexes
    }
}
let outline = Outline()
outline.held = after
OutlineSelectionRestore.select(after[2], in: outline, extending: false)
precondition(outline.selected == IndexSet(integer: 2))
OutlineSelectionRestore.select(before[0], in: outline, extending: false)
precondition(outline.selected == IndexSet(integer: 2), "an absent item changed the selection")
OutlineSelectionRestore.select(nil, in: outline, extending: false)
precondition(outline.selected == IndexSet(integer: 2), "nil changed the selection")
print("PASS: the selection is found again after the objects are replaced, a row that is gone is not selected, and study and series identifiers do not cross, and an absent item leaves the selection alone")
'''
with tempfile.TemporaryDirectory(prefix='horos-outline-selection-') as tmp:
    p = Path(tmp)
    (p / 'main.swift').write_text(source)
    subprocess.run(['xcrun', 'swiftc', str(root / 'Horos/Sources/OutlineSelectionRestore.swift'),
                    str(p / 'main.swift'), '-o', str(p / 'test')], check=True)
    subprocess.run([str(p / 'test')], check=True)
