// Synthetic metadata-only Core Data fixture for database sorting, not image viewing.
// Usage: swift tools/generate-date-sort-database.swift MODEL.mom NEW-Database.sql
import Foundation
import CoreData

guard CommandLine.arguments.count == 3 else { fatalError("Expected model and new database paths") }
let target = URL(fileURLWithPath: CommandLine.arguments[2])
guard !FileManager.default.fileExists(atPath: target.path) else { fatalError("Destination must not exist") }
let model = NSManagedObjectModel(contentsOf: URL(fileURLWithPath: CommandLine.arguments[1]))!
let hashes = model.entityVersionHashesByName
for entity in model.entities { entity.managedObjectClassName = "NSManagedObject" }
precondition(hashes == model.entityVersionHashesByName, "Fixture must preserve model compatibility")
let coordinator = NSPersistentStoreCoordinator(managedObjectModel: model)
try coordinator.addPersistentStore(ofType: NSSQLiteStoreType, configurationName: nil, at: target,
                                  options: [NSSQLitePragmasOption: ["journal_mode": "DELETE"]])
let context = NSManagedObjectContext(concurrencyType: .mainQueueConcurrencyType)
context.persistentStoreCoordinator = coordinator
context.undoManager = nil
let date = Date(timeIntervalSinceReferenceDate: 800_000_000)
for i in 0..<20_000 {
    let study = NSEntityDescription.insertNewObject(forEntityName: "Study", into: context)
    let identifier = String(format: "LOCAL-SORT-%05d", i)
    for (key, value) in ["name": identifier, "patientID": identifier, "patientUID": identifier,
                         "studyInstanceUID": "1.2.826.0.1.3680043.10.543.62.\(i+1)",
                         "studyName": "Synthetic date sorting", "modality": "MR"] {
        study.setValue(value, forKey: key)
    }
    study.setValue(false, forKey: "expanded")
    study.setValue(10, forKey: "numberOfImages")
    study.setValue(true, forKey: "hasDICOM")
    // Five thousand missing dates; fifteen thousand repeated across three days.
    let acquisition: Date? = i % 4 == 0 ? nil : date.addingTimeInterval(Double(i % 4) * 86400)
    study.setValue(acquisition, forKey: "date")
    study.setValue(date, forKey: "dateAdded")
    let series = NSEntityDescription.insertNewObject(forEntityName: "Series", into: context)
    series.setValue(study, forKey: "study")
    series.setValue("Synthetic metadata only", forKey: "name")
    series.setValue("MR", forKey: "modality")
    series.setValue("1.2.826.0.1.3680043.10.543.62.\(i+1).1", forKey: "seriesDICOMUID")
    series.setValue(1, forKey: "id")
    series.setValue(10, forKey: "numberOfImages")
    series.setValue(acquisition, forKey: "date")
    for j in 0..<10 {
        let image = NSEntityDescription.insertNewObject(forEntityName: "Image", into: context)
        image.setValue(series, forKey: "series")
        image.setValue(j+1, forKey: "instanceNumber")
        image.setValue(acquisition, forKey: "date")
        image.setValue("MR", forKey: "storedModality")
        image.setValue(1, forKey: "storedNumberOfFrames")
        image.setValue("dcm", forKey: "storedExtension")
    }
    if i % 200 == 199 { try context.save(); context.reset() }
}
try context.save()
for entity in ["Study", "Series", "Image"] {
    print("\(entity)=\(try context.count(for: NSFetchRequest(entityName: entity)))")
}
