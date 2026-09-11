#!/usr/bin/env python3
"""First-use eligibility must never redirect configured or existing databases."""
from pathlib import Path
import subprocess,tempfile
root=Path(__file__).resolve().parents[1]
main=r'''
import Foundation
let name="horos-first-use-test-\(UUID().uuidString)"
let defaults=UserDefaults(suiteName:name)!
defer {defaults.removePersistentDomain(forName:name)}
let documents=URL(fileURLWithPath:CommandLine.arguments[1])
assert(DatabaseFirstUse.needsChoice(defaults:defaults,documents:documents))
for key in ["DATABASELOCATION","DEFAULT_DATABASELOCATION","DATABASELOCATIONURL","DEFAULT_DATABASELOCATIONURL"] {
 defaults.setVolatileDomain([key:0],forName:UserDefaults.argumentDomain)
 assert(!DatabaseFirstUse.needsChoice(defaults:defaults,documents:documents))
}
defaults.setVolatileDomain([:],forName:UserDefaults.argumentDomain)
defaults.set(1,forKey:"DEFAULT_DATABASELOCATION")
assert(!DatabaseFirstUse.needsChoice(defaults:defaults,documents:documents))
defaults.set(0,forKey:"DEFAULT_DATABASELOCATION")
defaults.set(true,forKey:DatabaseFirstUse.completedKey)
assert(!DatabaseFirstUse.needsChoice(defaults:defaults,documents:documents))
defaults.set(false,forKey:DatabaseFirstUse.completedKey)
try FileManager.default.createDirectory(at:documents.appendingPathComponent("Horos Data"),withIntermediateDirectories:true)
assert(!DatabaseFirstUse.needsChoice(defaults:defaults,documents:documents))
defaults.set(true,forKey:DatabaseFirstUse.pendingKey)
assert(DatabaseFirstUse.needsChoice(defaults:defaults,documents:documents))
print("PASS: fresh install prompts; configured, explicit and existing locations preserved")
'''
with tempfile.TemporaryDirectory(prefix='horos-first-use-') as tmp:
 p=Path(tmp);(p/'main.swift').write_text(main)
 subprocess.run(['swiftc',str(root/'Horos/Sources/CloudFileAccess.swift'),str(root/'Horos/Sources/DatabaseFirstUse.swift'),str(p/'main.swift'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test'),str(p/'Documents')],check=True)
