#!/usr/bin/env python3
"""Inventory completeness follows imported identities, never transport/frame counts."""
import subprocess,tempfile
from pathlib import Path
root=Path(__file__).resolve().parents[1]
driver=r'''
import Foundation
import CoreData
let directory=CommandLine.arguments[1]
let rows=(1...10).map { ["uid":"1.2.\($0)","series":"1.3"] }
let m=RetrieveInventory.begin(study:"1.1",series:"",endpoint:"PACS@localhost:104",database:directory,instances:rows,confirmed:true)
assert(m.beginImportRefresh() && !m.beginImportRefresh())
NotificationCenter.default.post(name:.NSManagedObjectContextDidSave,object:nil)
assert(m.beginImportRefresh() && !m.beginImportRefresh())
NotificationCenter.default.post(name:.NSManagedObjectContextObjectsDidChange,object:nil)
assert(m.beginImportRefresh())
m.invalidateImportRefresh();assert(m.beginImportRefresh())
m.updateImportedUIDs([])
for i in 1...8 {m.record(uid:"1.2.\(i)",status:0)}
m.record(uid:"1.2.1",status:0);m.record(uid:"1.2.9",status:0xa900)
// Ten local rows, eight expected UIDs: duplicate frames/alien identities cannot fill the gaps.
m.updateImportedUIDs((1...8).map{"1.2.\($0)"}+["9.8","9.9"])
assert(m.matchesReportedCount(10) && m.matchesReportedCount(0) && !m.matchesReportedCount(11))
assert(m.importedCount==8 && m.localUniqueCount==10 && !m.isComplete && m.needsAttention)
assert(m.missingUIDs==["1.2.10","1.2.9"] && m.duplicateUIDs==["1.2.1"] && m.rejectedUIDs==["1.2.9"])
assert(m.unexpectedUIDs==["9.8","9.9"] && Set(m.missingSeries["1.3"]!)==Set(m.missingUIDs))
m.finish()
let snapshot=try JSONSerialization.jsonObject(with:Data(contentsOf:URL(fileURLWithPath:m.path))) as! [String:Any]
assert(snapshot["missingUIDs"] as! [String]==m.missingUIDs)
let retry=RetrieveInventory.begin(study:"1.1",series:"",endpoint:"PACS@localhost:104",database:directory,instances:rows,confirmed:true)
assert(retry === m) // every query window sees the current snapshot
retry.updateImportedUIDs((1...8).map{"1.2.\($0)"})
retry.record(uid:"1.2.9",status:0);retry.record(uid:"1.2.10",status:0)
assert(!retry.needsAttention && !retry.isComplete) // received, but not imported yet
retry.updateImportedUIDs((1...10).map{"1.2.\($0)"})
assert(retry.isComplete && retry.missingUIDs.isEmpty && retry.rejectedUIDs==["1.2.9"])
assert(retry.duplicateUIDs==["1.2.1"])
retry.finish()
let unknown=RetrieveInventory.begin(study:"2.1",series:"",endpoint:"PACS",database:directory,instances:rows,confirmed:false)
unknown.updateImportedUIDs((1...10).map{"1.2.\($0)"})
assert(!unknown.isComplete && unknown.needsAttention && unknown.unexpectedUIDs.isEmpty)
let concurrent=RetrieveInventory.begin(study:"3.1",series:"",endpoint:"PACS",database:directory,instances:rows,confirmed:true)
DispatchQueue.concurrentPerform(iterations:32){_ in
 NotificationCenter.default.post(name:Notification.Name("HorosDICOMStoreCompleted"),object:nil,userInfo:["uid":"1.2.1","study":"3.1","series":"1.3","status":0])
}
assert(concurrent.duplicateUIDs==["1.2.1"])
concurrent.finish();unknown.finish()
let first=RetrieveInventory.begin(study:"5.1",series:"",endpoint:"PACS",database:directory,instances:rows,confirmed:true)
let second=RetrieveInventory.begin(study:"5.1",series:"",endpoint:"PACS",database:directory,instances:rows,confirmed:true)
assert(first === second);first.record(uid:"1.2.1",status:0);first.finish()
NotificationCenter.default.post(name:Notification.Name("HorosDICOMStoreCompleted"),object:nil,userInfo:["uid":"1.2.1","study":"5.1","series":"1.3","status":0])
assert(second.duplicateUIDs==["1.2.1"]);second.finish()
weak var released: RetrieveInventory?
autoreleasepool {
 let temporary=RetrieveInventory.begin(study:"4.1",series:"",endpoint:"PACS",database:directory,instances:rows,confirmed:true)
 released=temporary;temporary.finish()
}
assert(released==nil) // old studies do not retain all their UIDs globally forever
print("ok: exact UID reconciliation, duplicate/rejection history, pending import, unknown inventory and concurrent store events")
'''
with tempfile.TemporaryDirectory(prefix='horos-inventory-') as d:
 p=Path(d);(p/'main.swift').write_text(driver)
 subprocess.run(['xcrun','swiftc',str(root/'Horos/Sources/RetrieveInventory.swift'),str(p/'main.swift'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test'),d],check=True,timeout=20)
