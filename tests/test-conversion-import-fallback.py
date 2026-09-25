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
let good = ConversionImportFallback.recover(files: [path("valid.dcm")], allocateDestination: { path("indexed.dcm") }, importFiles: { paths in
    assert(paths == [path("indexed.dcm")])
    assert(try! Data(contentsOf: URL(fileURLWithPath: paths[0])) == expected)
    return [paths[0]: 4]
})
assert(good.contains("valid.dcm: indexed unchanged"))
assert(!manager.fileExists(atPath: path("valid.dcm")))
assert(try! Data(contentsOf: URL(fileURLWithPath: path("indexed.dcm"))) == expected)
put("truncated.dcm")
let bad = ConversionImportFallback.recover(files: [path("truncated.dcm")], allocateDestination: { path("unreadable-copy.dcm") }, importFiles: { paths in
    try! manager.removeItem(atPath: paths[0]) // importer's configured unreadable-file policy
    return [:]
})
assert(bad.contains("truncated.dcm")); assert(bad.contains("Original retained"))
assert(try! Data(contentsOf: URL(fileURLWithPath: path("truncated.dcm"))) == expected)
put("collision.dcm");put("protected.dcm")
let collision = ConversionImportFallback.recover(files: [path("collision.dcm")], allocateDestination: { path("protected.dcm") }, importFiles: { _ in fatalError("must not index failed copy") })
assert(collision.contains("fallback copy failed"))
assert(try! Data(contentsOf: URL(fileURLWithPath: path("protected.dcm"))) == expected)
assert(try! Data(contentsOf: URL(fileURLWithPath: path("collision.dcm"))) == expected)
let allocation = ConversionImportFallback.recover(files: [path("collision.dcm")], allocateDestination: { nil }, importFiles: { _ in fatalError("no destination") })
assert(allocation.contains("cannot allocate"))
put("archive.zip")
assert(ConversionImportFallback.recover(files: [path("already-converted.dcm"),path("archive.zip")], allocateDestination: { fatalError("must skip archives and removed sources") }, importFiles: { _ in fatalError("nothing to import") }).isEmpty)
assert(manager.fileExists(atPath: path("archive.zip")))
try! manager.createDirectory(atPath: path("readonly"), withIntermediateDirectories: false)
try! manager.setAttributes([.posixPermissions: 0o500], ofItemAtPath: path("readonly"))
let readonly = ConversionImportFallback.recover(files: [path("collision.dcm")], allocateDestination: { path("readonly/copy.dcm") }, importFiles: { _ in fatalError("no copied file") })
try! manager.setAttributes([.posixPermissions: 0o700], ofItemAtPath: path("readonly"))
assert(readonly.contains("fallback copy failed"));assert(manager.fileExists(atPath: path("collision.dcm")))
// A batch is indexed in one call, and each file still gets its own verdict (#694).
put("a.dcm"); put("b.dcm"); put("c.dcm")
var destinations = ["batch-c.dcm", "batch-b.dcm", "batch-a.dcm"].map(path)
var calls = 0
let batch = ConversionImportFallback.recover(files: [path("a.dcm"), path("b.dcm"), path("c.dcm")],
    allocateDestination: { destinations.popLast() }, importFiles: { paths in
    calls += 1
    assert(paths == ["batch-a.dcm", "batch-b.dcm", "batch-c.dcm"].map(path))
    try! manager.removeItem(atPath: paths[1]) // b is unreadable
    // The importer reports the same file through another spelling of its path.
    return [paths[0]: 1, root.appendingPathComponent("./batch-c.dcm").path: 2]
})
assert(calls == 1)
assert(batch.contains("a.dcm: indexed unchanged after conversion failed (1 image records)"))
assert(batch.contains("c.dcm: indexed unchanged after conversion failed (2 image records)"))
assert(batch.contains("b.dcm: conversion failed and the original could not be indexed"))
assert(!manager.fileExists(atPath: path("a.dcm")) && !manager.fileExists(atPath: path("c.dcm")))
assert(try! Data(contentsOf: URL(fileURLWithPath: path("b.dcm"))) == expected)
print("PASS: one import call per batch, unchanged import, unreadable rejection, allocation/copy failures and archive isolation preserve originals and return named verdicts")
'''
with tempfile.TemporaryDirectory(prefix='horos-conversion-fallback-') as folder:
    p = Path(folder)
    (p / 'main.swift').write_text(main)
    subprocess.run(['swiftc', str(source), str(p / 'main.swift'), '-o', str(p / 'test')], check=True)
    subprocess.run([str(p / 'test'), str(p)], check=True)
