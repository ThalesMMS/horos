#!/usr/bin/env python3
"""Run the Swift fallback with real file operations and injected import outcomes."""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
source = root / 'Horos/Sources/ConversionImportFallback.swift'
main = r'''
import Foundation
let root = URL(fileURLWithPath: CommandLine.arguments[1])
let manager = FileManager.default
func path(_ name: String) -> String { root.appendingPathComponent(name).path }
func put(_ name: String) { try! Data("preserved original".utf8).write(to: root.appendingPathComponent(name)) }
let expected = Data("preserved original".utf8)
put("valid.dcm")
let good = ConversionImportFallback.recover(files: [path("valid.dcm")], allocateDestination: { path("indexed.dcm") }, importFile: {
    assert(try! Data(contentsOf: URL(fileURLWithPath: $0)) == expected)
    return 4
})
assert(good.contains("valid.dcm: indexed unchanged"))
assert(!manager.fileExists(atPath: path("valid.dcm")))
assert(try! Data(contentsOf: URL(fileURLWithPath: path("indexed.dcm"))) == expected)
put("truncated.dcm")
let bad = ConversionImportFallback.recover(files: [path("truncated.dcm")], allocateDestination: { path("unreadable-copy.dcm") }, importFile: {
    try! manager.removeItem(atPath: $0) // importer's configured unreadable-file policy
    return 0
})
assert(bad.contains("truncated.dcm")); assert(bad.contains("Original retained"))
assert(try! Data(contentsOf: URL(fileURLWithPath: path("truncated.dcm"))) == expected)
put("collision.dcm");put("protected.dcm")
let collision = ConversionImportFallback.recover(files: [path("collision.dcm")], allocateDestination: { path("protected.dcm") }, importFile: { _ in fatalError("must not index failed copy") })
assert(collision.contains("fallback copy failed"))
assert(try! Data(contentsOf: URL(fileURLWithPath: path("protected.dcm"))) == expected)
assert(try! Data(contentsOf: URL(fileURLWithPath: path("collision.dcm"))) == expected)
let allocation = ConversionImportFallback.recover(files: [path("collision.dcm")], allocateDestination: { nil }, importFile: { _ in fatalError("no destination") })
assert(allocation.contains("cannot allocate"))
put("archive.zip")
assert(ConversionImportFallback.recover(files: [path("already-converted.dcm"),path("archive.zip")], allocateDestination: { fatalError("must skip archives and removed sources") }, importFile: { _ in 0 }).isEmpty)
assert(manager.fileExists(atPath: path("archive.zip")))
try! manager.createDirectory(atPath: path("readonly"), withIntermediateDirectories: false)
try! manager.setAttributes([.posixPermissions: 0o500], ofItemAtPath: path("readonly"))
let readonly = ConversionImportFallback.recover(files: [path("collision.dcm")], allocateDestination: { path("readonly/copy.dcm") }, importFile: { _ in fatalError("no copied file") })
try! manager.setAttributes([.posixPermissions: 0o700], ofItemAtPath: path("readonly"))
assert(readonly.contains("fallback copy failed"));assert(manager.fileExists(atPath: path("collision.dcm")))
print("PASS: unchanged import, unreadable rejection, allocation/copy failures and archive isolation preserve originals and return named verdicts")
'''
with tempfile.TemporaryDirectory(prefix='horos-conversion-fallback-') as folder:
    p = Path(folder)
    (p / 'main.swift').write_text(main)
    subprocess.run(['swiftc', str(source), str(p / 'main.swift'), '-o', str(p / 'test')], check=True)
    subprocess.run([str(p / 'test'), str(p)], check=True)
