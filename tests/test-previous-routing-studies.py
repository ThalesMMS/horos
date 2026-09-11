#!/usr/bin/env python3
"""Compile prior-study policy and exercise durable, concurrent admission limits."""
import subprocess,tempfile
from pathlib import Path
root=Path(__file__).resolve().parents[1]
driver=r'''
import Foundation
let directory=CommandLine.arguments[1]
let now=Date(timeIntervalSince1970:200000)
let current:[String:Any] = ["date":now,"modality":"CT\\MR","studyName":"CURRENT"]
func prior(_ mod:String="CT",_ name:String="CURRENT",_ seconds:Double = -1)->[String:Any] {
 ["date":now.addingTimeInterval(seconds),"modality":mod,"studyName":name]
}
func check(_ study:[String:Any],_ mod:Bool,_ desc:Bool)->Bool {
 PreviousRoutingStudies.matches(study,currentStudy:current,modality:mod,description:desc)
}
assert(check(prior(),true,true))
assert(check(prior("US","OTHER"),false,false))
assert(!check(prior("US"),true,false))
assert(!check(prior("CT","OTHER"),false,true))
assert(!check(prior("CT","CURRENT",0),false,false))
assert(!check(prior("CT","CURRENT",1),false,false))
assert(!check([:],false,false))
assert(!check(prior("",""),true,true))
let server:[String:Any] = ["Address":"localhost","Port":11330,"AETitle":"ONE"]
func reserve(_ uid:String,_ time:Date=now,_ node:[String:Any]=server)->Bool {
 PreviousRoutingStudies.reserve(study:uid,server:node,databasePath:directory,now:time)
}
assert(reserve("study"))
assert(!reserve("study"))
assert(!reserve("study",now.addingTimeInterval(10799)))
assert(reserve("study",now.addingTimeInterval(10800)))
assert(reserve("study",now,["Address":"localhost","Port":"11331","AETitle":"ONE"]))
assert(!reserve("study",now,["Address":"LOCALHOST","Port":11331,"AETitle":"ONE","Description":"renamed"]))
assert(reserve("study",now,["Address":"localhost","Port":11330,"AETitle":"TWO"]))
let mutex=NSLock();var accepted=0
DispatchQueue.concurrentPerform(iterations:32){_ in
 if reserve("concurrent") {mutex.lock();accepted += 1;mutex.unlock()}
}
assert(accepted==1)
// A fresh executable invocation must read the persisted history too.
let child=Process();child.executableURL=URL(fileURLWithPath:CommandLine.arguments[0]);child.arguments=[directory,"child"]
'''
# Branch before driver declarations to make persistence check a separate process.
prefix='''import Foundation
if CommandLine.arguments.count > 2 {
 let server:[String:Any] = ["Address":"localhost","Port":11330,"AETitle":"ONE"]
 assert(!PreviousRoutingStudies.reserve(study:"concurrent",server:server,databasePath:CommandLine.arguments[1],now:Date(timeIntervalSince1970:200000)))
 exit(0)
}
'''
suffix=r'''
try child.run();child.waitUntilExit();assert(child.terminationStatus==0)
let file=URL(fileURLWithPath:directory).appendingPathComponent("PreviousRoutingStudies.json")
try Data("invalid".utf8).write(to:file)
assert(!reserve("new"))
assert(!PreviousRoutingStudies.reserve(study:"x",server:server,databasePath:directory+"/absent",now:now))
print("ok: date/filter policy, expiry, destination identity, concurrent claims, restart and persistence failure")
'''
with tempfile.TemporaryDirectory(prefix='horos-prior-routing-') as d:
 p=Path(d);(p/'main.swift').write_text(prefix+driver+suffix)
 subprocess.run(['xcrun','swiftc',str(root/'Horos/Sources/PreviousRoutingStudies.swift'),str(p/'main.swift'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test'),d],check=True,timeout=20)
s=(root/'Horos/Sources/DicomDatabase+Routing.mm').read_text(encoding='latin1')
assert 'patientUID == %@' in s and 'HorosPreviousRoutingStudies reserveStudy:' in s
assert '[currentStudies containsObject:prior]' in s and '!imagesOnly || image.isImageStorage.boolValue' in s
