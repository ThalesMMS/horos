#!/usr/bin/env python3
"""One name, one account, in sign-in and in administration alike.

Both paths looked a user up with `name LIKE[cd] %@`. LIKE reads `*` and `?` as
wildcards, so a name carrying one matched accounts it does not equal; and when
several matched, the administration page kept the first while sign-in kept the
last, so an administrator could be editing a different account from the one
being signed in to.
"""
from pathlib import Path
import subprocess, sys, tempfile

root = Path(__file__).resolve().parents[1]
for name in ('Horos/Sources/WebPortalDatabase.mm', 'Horos/Sources/WebPortalConnection.mm',
             'Horos/Sources/WebPortalUser.mm'):
    source = (root / name).read_bytes().decode('latin1')
    assert 'name LIKE[cd]' not in source, f'{name} still matches user names as a pattern'
    assert 'HorosWebPortalUserLookup' in source, f'{name} no longer uses the shared lookup'
connection = (root / 'Horos/Sources/WebPortalConnection.mm').read_bytes().decode('latin1')
assert 'userAmong: matches forName: username' in connection, 'sign-in no longer resolves by the shared rule'
assert 'lastObject' not in connection.split('executeFetchRequest: r error: nil')[1][:200], \
    'sign-in still takes whichever match came last'
# A name typed in another case finds the account and can never match its password,
# because the digest is taken over the name as typed. Say so where it can be read.
assert 'the name is registered as' in connection, \
    'a sign-in refused for the spelling of the name is still logged as a wrong password'
assert 'Unsuccessful login attempt with invalid password' in connection, \
    'the generic refusal message is gone'

source = r'''
import CoreData
import Foundation

// A throwaway in-memory store, so the rule is exercised on real managed objects.
let model = NSManagedObjectModel()
let entity = NSEntityDescription()
entity.name = "User"
entity.managedObjectClassName = NSStringFromClass(NSManagedObject.self)
let attribute = NSAttributeDescription()
attribute.name = "name"
attribute.attributeType = .stringAttributeType
entity.properties = [attribute]
model.entities = [entity]
let coordinator = NSPersistentStoreCoordinator(managedObjectModel: model)
try! coordinator.addPersistentStore(ofType: NSInMemoryStoreType, configurationName: nil, at: nil, options: nil)
let context = NSManagedObjectContext(concurrencyType: .mainQueueConcurrencyType)
context.persistentStoreCoordinator = coordinator

@discardableResult
func make(_ name: String) -> NSManagedObject {
    let user = NSEntityDescription.insertNewObject(forEntityName: "User", into: context)
    user.setValue(name, forKey: "name")
    return user
}
func matches(_ name: String) -> [NSManagedObject] {
    let request = NSFetchRequest<NSManagedObject>(entityName: "User")
    request.predicate = WebPortalUserLookup.predicate(forName: name)
    return try! context.fetch(request)
}
func lookup(_ name: String) -> String? {
    WebPortalUserLookup.user(among: matches(name), forName: name)?.value(forKey: "name") as? String
}

make("Alice"); make("bob"); make("Zoé")
// The ordinary cases still work, case and diacritics included.
precondition(lookup("Alice") == "Alice")
precondition(lookup("alice") == "Alice", "sign-in stays insensitive to case")
precondition(lookup("ALICE") == "Alice")
precondition(lookup("BOB") == "bob")
precondition(lookup("zoe") == "Zoé", "diacritics stay insensitive")
precondition(lookup("carol") == nil)
// The wildcards LIKE used to honour are now ordinary characters.
for pattern in ["*", "A*", "?????", "Alic?", "*b*"] {
    precondition(lookup(pattern) == nil, "\(pattern) must not match anyone")
}
make("*")
precondition(lookup("*") == "*", "a name that is literally an asterisk matches itself only")
precondition(lookup("Alice") == "Alice")
// Two accounts differing only in case resolve the same way everywhere: exactly,
// or not at all.
make("ALICE")
precondition(lookup("Alice") == "Alice", "an exact match wins over an ambiguous one")
precondition(lookup("ALICE") == "ALICE")
precondition(lookup("alice") == nil, "an ambiguous name must not pick one of them")
print("PASS: equality not pattern, case and diacritics still insensitive, ambiguity refused rather than resolved by order")
'''
with tempfile.TemporaryDirectory(prefix='horos-portal-lookup-') as tmp:
    p = Path(tmp)
    (p / 'main.swift').write_text(source)
    subprocess.run(['xcrun', 'swiftc', str(root / 'Horos/Sources/WebPortalUserLookup.swift'),
                    str(p / 'main.swift'), '-o', str(p / 'test')], check=True)
    subprocess.run([str(p / 'test')], check=True)
