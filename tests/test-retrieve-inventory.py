#!/usr/bin/env python3
"""Inventory completeness follows imported identities, never transport/frame counts.

A retrieve's inventory is judged once what it received is in the index (#646):
received files are indexed by the importer's timer after the transfer returns,
and judged at once a retrieve that brought every instance was recorded as
incomplete. Modelled here with an index that catches up in steps; the move waits
before its final refresh, and warns about received instances the index never took.
"""
import subprocess,tempfile
from pathlib import Path
root=Path(__file__).resolve().parents[1]
node=(root/'Horos/Sources/DCMTKQueryNode.mm').read_text()
final=node[node.index('    @finally {\n        if (localRetrieve && _retrieveInventory) {'):]
final=final[:final.index('[DCMTKQueryNode performSelectorOnMainThread:@selector(errorMessage:)')]
assert 'waitForReceivedImportsRefreshing:' in final, 'the move judges its inventory without waiting for the received instances to be indexed'
assert final.index('waitForReceivedImportsRefreshing:') < final.index('[_retrieveInventory finish];'), 'the wait comes after the inventory is finished'
assert 'if (!NSThread.isMainThread)' in final, 'the wait may block the main thread, whose run loop drives the importer'
assert '|| !receivedIndexed' in final, 'received instances the index never took do not raise the warning'
assert 'importInProgress:^BOOL{ return [DicomDatabase activeLocalDatabase].incomingImportInProgress; }' in final
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
// #646: every missing instance received, the index catching up in three steps 0.3 s apart.
let delayedRows=(1...30).map { ["uid":"7.2.\($0)","series":"7.3"] }
let delayed=RetrieveInventory.begin(study:"7.1",series:"",endpoint:"PACS",database:directory,instances:delayedRows,confirmed:true)
let index=NSLock()
var indexed=Set((1...30).filter { $0 % 2 == 1 }.map { "7.2.\($0)" })
let refresh: () -> Void = { index.lock(); let uids=Array(indexed); index.unlock(); delayed.updateImportedUIDs(uids) }
refresh()
for i in stride(from:2,through:30,by:2) {
 NotificationCenter.default.post(name:Notification.Name("HorosDICOMStoreCompleted"),object:nil,userInfo:["uid":"7.2.\(i)","study":"7.1","series":"7.3","status":0])
}
refresh()
// Judged at once, the retrieve is incomplete although nothing is missing from the transfer.
assert(!delayed.isComplete && delayed.importedCount==15 && delayed.receivedAwaitingImportCount==15 && !delayed.needsAttention)
Thread { for step in 0..<3 { Thread.sleep(forTimeInterval:0.3); index.lock(); for i in stride(from:2,through:30,by:2) where (i/2)%3==step { indexed.insert("7.2.\(i)") }; index.unlock() } }.start()
var started=Date()
assert(delayed.waitForReceivedImports(refreshing:refresh,patience:2,cancelled:{ false }))
var waited=Date().timeIntervalSince(started)
assert(waited>=0.8 && waited<2.5, "waited \(waited) s for an index that took 0.9 s")
assert(delayed.isComplete && delayed.importedCount==30 && delayed.receivedAwaitingImportCount==0 && !delayed.needsAttention)
delayed.finish()
// A single batch can work longer than the idle timeout without committing a UID.
let busy=RetrieveInventory.begin(study:"7.4",series:"",endpoint:"PACS",database:directory,instances:delayedRows,confirmed:true)
busy.updateImportedUIDs([])
for row in delayedRows { busy.record(uid:row["uid"]!,status:0) }
started=Date()
let busyRefresh: () -> Void = {
 if Date().timeIntervalSince(started)>=1.2 { busy.updateImportedUIDs(delayedRows.map { $0["uid"]! }) }
}
assert(busy.waitForReceivedImports(refreshing:busyRefresh,importInProgress:{ true },patience:0.4,cancelled:{ false }))
assert(Date().timeIntervalSince(started)>=1.2 && busy.isComplete)
busy.finish()
// Really incomplete: one instance never sent. Nothing received is left to wait for, and it still needs attention.
let omitted=RetrieveInventory.begin(study:"8.1",series:"",endpoint:"PACS",database:directory,instances:delayedRows,confirmed:true)
omitted.updateImportedUIDs([])
for i in 1...29 { omitted.record(uid:"7.2.\(i)",status:0) }
omitted.updateImportedUIDs((1...29).map { "7.2.\($0)" })
started=Date()
assert(omitted.waitForReceivedImports(refreshing:{},patience:2,cancelled:{ false }))
assert(Date().timeIntervalSince(started)<0.5 && !omitted.isComplete && omitted.needsAttention && omitted.missingUIDs==["7.2.30"])
omitted.finish()
// Received but never indexed: the wait gives up after its patience, and says so.
let rejected=RetrieveInventory.begin(study:"9.1",series:"",endpoint:"PACS",database:directory,instances:delayedRows,confirmed:true)
rejected.updateImportedUIDs([])
for i in 1...30 { rejected.record(uid:"7.2.\(i)",status:0) }
rejected.updateImportedUIDs((1...28).map { "7.2.\($0)" })
started=Date()
assert(!rejected.waitForReceivedImports(refreshing:{},patience:0.5,cancelled:{ false }))
waited=Date().timeIntervalSince(started)
assert(waited>=0.5 && waited<1.5 && rejected.receivedAwaitingImportCount==2, "gave up after \(waited) s")
// Cancelled: no wait at all.
started=Date()
assert(!rejected.waitForReceivedImports(refreshing:{},patience:5,cancelled:{ true }) && Date().timeIntervalSince(started)<0.5)
// Work ends without indexing the received files: the idle timeout still fires.
started=Date()
assert(!rejected.waitForReceivedImports(refreshing:{},importInProgress:{ Date().timeIntervalSince(started)<0.8 },
                                      patience:0.5,cancelled:{ false }))
waited=Date().timeIntervalSince(started)
assert(waited>=1.1 && waited<2, "busy worker suppressed the idle timeout: \(waited)")
// Cancellation interrupts even a worker that remains busy.
started=Date()
assert(!rejected.waitForReceivedImports(refreshing:{},importInProgress:{ true },patience:5,
                                      cancelled:{ Date().timeIntervalSince(started)>=0.3 }))
assert(Date().timeIntervalSince(started)<0.8)
rejected.finish()
print("ok: exact UID reconciliation, duplicate/rejection history, pending import, unknown inventory, concurrent store events and the wait for received instances to be indexed")
'''
with tempfile.TemporaryDirectory(prefix='horos-inventory-') as d:
 p=Path(d);(p/'main.swift').write_text(driver)
 subprocess.run(['xcrun','swiftc',str(root/'Horos/Sources/RetrieveInventory.swift'),str(p/'main.swift'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test'),d],check=True,timeout=20)
 # Compile the real database activity getter against its lock/queue collaborators.
 database=(root/'Horos/Sources/DicomDatabase.mm').read_text()
 activity=database[database.index('-(BOOL)incomingImportInProgress'):]
 activity=activity[:activity.index('\n}\n')+3]
 (p/'activity.m').write_text(r'''
#import <Cocoa/Cocoa.h>
@interface DicomDatabase : NSObject {
@public NSRecursiveLock *_importFilesFromIncomingDirLock, *_processFilesLock;
NSMutableArray *_compressQueue, *_decompressQueue;
}
@property BOOL isMainDatabase;
@property DicomDatabase *mainDatabase;
@property NSThread *compressDecompressThread;
@end
@implementation DicomDatabase
''' + activity + r'''
@end
int main(void) { @autoreleasepool {
 DicomDatabase *db=[DicomDatabase new]; db.isMainDatabase=YES;
 db->_importFilesFromIncomingDirLock=[NSRecursiveLock new]; db->_processFilesLock=[NSRecursiveLock new];
 db->_compressQueue=[NSMutableArray new]; db->_decompressQueue=[NSMutableArray new];
 NSCAssert(![db incomingImportInProgress], @"idle database reported busy");
 for (NSRecursiveLock *lock in @[db->_importFilesFromIncomingDirLock, db->_processFilesLock]) {
  dispatch_semaphore_t locked=dispatch_semaphore_create(0), release=dispatch_semaphore_create(0), done=dispatch_semaphore_create(0);
  [NSThread detachNewThreadWithBlock:^{
   [lock lock]; dispatch_semaphore_signal(locked);
   dispatch_semaphore_wait(release, DISPATCH_TIME_FOREVER); [lock unlock]; dispatch_semaphore_signal(done);
  }];
  dispatch_semaphore_wait(locked, DISPATCH_TIME_FOREVER);
  NSCAssert([db incomingImportInProgress], @"active import/conversion was missed");
  dispatch_semaphore_signal(release); dispatch_semaphore_wait(done, DISPATCH_TIME_FOREVER);
  NSCAssert(![db incomingImportInProgress], @"completed work stayed busy");
 }
 for (NSMutableArray *queue in @[db->_compressQueue, db->_decompressQueue]) {
  [queue addObject:@"queued.dcm"]; NSCAssert([db incomingImportInProgress], @"queued conversion missed");
  [queue removeAllObjects]; NSCAssert(![db incomingImportInProgress], @"empty queue stayed busy");
 }
 dispatch_semaphore_t active=dispatch_semaphore_create(0), finish=dispatch_semaphore_create(0);
 db.compressDecompressThread=[[NSThread alloc] initWithBlock:^{
  dispatch_semaphore_signal(active); dispatch_semaphore_wait(finish, DISPATCH_TIME_FOREVER);
 }];
 [db.compressDecompressThread start]; dispatch_semaphore_wait(active, DISPATCH_TIME_FOREVER);
 NSCAssert([db incomingImportInProgress], @"conversion fallback missed");
 dispatch_semaphore_signal(finish);
 while (!db.compressDecompressThread.isFinished) [NSThread sleepForTimeInterval:0.001];
 NSCAssert(![db incomingImportInProgress], @"finished conversion stayed busy");
} return 0; }
''')
 subprocess.run(['xcrun','clang','-fobjc-arc','-framework','Cocoa',str(p/'activity.m'),'-o',str(p/'activity')],check=True)
 subprocess.run([str(p/'activity')],check=True,timeout=10)
