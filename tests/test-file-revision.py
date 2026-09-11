#!/usr/bin/env python3
"""A path is not a cache key; the file's revision is (#603).

Compiles `Horos/Sources/FileRevision.swift` with a driver that rewrites a file
every way the product and the outside world do — a rename over the path (new
inode), an in-place rewrite of the same size, a delete-and-recreate under the
same name (the database reuses numbers) — and checks that each yields a new
key, that the unchanged file keeps its key and still `matchesDisk`, that a
removed file no longer matches, and that the refusal names the cause. It also
times the check: one `stat` per lookup, well under a redraw budget.
"""
from pathlib import Path
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
source = root / 'Horos/Sources/FileRevision.swift'
project = (root / 'Horos.xcodeproj/project.pbxproj').read_text()
failures = []
if project.count('FileRevision.swift in Sources') < 1:
    failures.append('FileRevision.swift is not in the Horos target')

DRIVER = r'''
import Foundation
func expect(_ ok: Bool, _ reason: String) { if !ok { print("FAIL: " + reason); exit(1) } }
let directory = FileManager.default.temporaryDirectory.appendingPathComponent("file-revision-" + UUID().uuidString)
try! FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
defer { try? FileManager.default.removeItem(at: directory) }
let path = directory.appendingPathComponent("17.dcm").path
try! Data(repeating: 0x11, count: 4096).write(to: URL(fileURLWithPath: path))

// 1. A revision describes a regular file; a directory or a missing path is refused.
expect(FileRevision(path: directory.path) == nil, "a directory is not a file revision")
expect(FileRevision(path: directory.appendingPathComponent("none.dcm").path) == nil, "a missing file has no revision")
expect(FileRevision(path: "") == nil, "an empty path has no revision")
let first = FileRevision(path: path)!
expect(first.size == 4096 && first.path == path, "size and path are recorded")
expect(first.cacheKey.hasPrefix(path + "|dev="), "the key starts with the path so two files never collide: \(first.cacheKey)")
expect(first.matchesDisk(), "an untouched file matches its own revision")
expect(FileRevision(path: path)! == first, "re-reading an untouched file yields an equal revision")
expect(FileRevision.cacheKey(forPath: path) == first.cacheKey, "the static key equals the instance key")
expect(FileRevision.refusalForReusingFile(loaded: first, current: FileRevision(path: path)) == nil, "no refusal while unchanged")

// 2. Rename over the path: the way an import publishes a file. New inode.
let staging = directory.appendingPathComponent("staging.dcm").path
try! Data(repeating: 0x22, count: 4096).write(to: URL(fileURLWithPath: staging))
_ = try! FileManager.default.replaceItemAt(URL(fileURLWithPath: path), withItemAt: URL(fileURLWithPath: staging))
let renamed = FileRevision(path: path)!
expect(renamed != first, "a rename over the path is a new revision")
expect(renamed.cacheKey != first.cacheKey, "a rename over the path is a new key")
expect(!first.matchesDisk(), "the old revision no longer matches the disk after a rename")
let renameRefusal = FileRevision.refusalForReusingFile(loaded: first, current: renamed)
expect(renameRefusal?.contains("replaced") == true || renameRefusal?.contains("rewritten") == true, "the refusal names the replacement: \(renameRefusal ?? "nil")")

// 3. In-place rewrite of the same size: an editor or a metadata tool. Same inode.
let handle = FileHandle(forWritingAtPath: path)!
handle.seek(toFileOffset: 0); handle.write(Data(repeating: 0x33, count: 4096)); try! handle.close()
let rewritten = FileRevision(path: path)!
expect(rewritten.inode == renamed.inode, "an in-place rewrite keeps the inode (the case a path key cannot see)")
expect(rewritten != renamed && rewritten.cacheKey != renamed.cacheKey, "an in-place same-size rewrite is a new revision")
expect(!renamed.matchesDisk(), "the pre-rewrite revision no longer matches")
expect(FileRevision.refusalForReusingFile(loaded: renamed, current: rewritten)?.contains("rewritten") == true, "the refusal names the rewrite")

// 4. Delete and recreate under the same name: the database reuses numbers.
try! FileManager.default.removeItem(atPath: path)
expect(!rewritten.matchesDisk(), "a removed file matches nothing")
expect(FileRevision.refusalForReusingFile(loaded: rewritten, current: FileRevision(path: path))?.contains("no longer there") == true, "the refusal says the file is gone")
try! Data(repeating: 0x44, count: 2048).write(to: URL(fileURLWithPath: path))
let reused = FileRevision(path: path)!
expect(reused.cacheKey != rewritten.cacheKey, "a reused path is a new key")
expect(FileRevision.refusalForReusingFile(loaded: rewritten, current: reused) != nil, "a reused path is refused")

// 5. Another path with identical contents is never the same key.
let other = directory.appendingPathComponent("18.dcm").path
try! Data(repeating: 0x44, count: 2048).write(to: URL(fileURLWithPath: other))
expect(FileRevision(path: other)!.cacheKey != reused.cacheKey, "two files with equal bytes have different keys")
expect(FileRevision.refusalForReusingFile(loaded: reused, current: FileRevision(path: other))?.contains("cannot stand for") == true, "another path is refused by name")
expect(FileRevision.refusalForReusingFile(loaded: nil, current: reused) != nil, "an unknown loaded revision is refused")

// 6. Cost: one stat per check. Report the number; fail only if absurd.
let started = Date()
var matched = 0
for _ in 0..<10_000 where reused.matchesDisk() { matched += 1 }
let microseconds = Date().timeIntervalSince(started) * 1_000_000 / 10_000
expect(matched == 10_000, "the file did not change during the timing loop")
expect(microseconds < 500, "a revision check costs \(microseconds) µs; that is not one stat")
print(String(format: "ok: file revisions distinguish rename, rewrite and reuse; check costs %.1f µs", microseconds))
'''

if not failures:
    with tempfile.TemporaryDirectory() as tmp:
        driver = Path(tmp) / 'main.swift'
        driver.write_text(DRIVER)
        binary = Path(tmp) / 'driver'
        build = subprocess.run(['xcrun', 'swiftc', '-O', str(source), str(driver), '-o', str(binary)],
                               capture_output=True, text=True)
        if build.returncode != 0:
            failures.append('driver did not compile:\n' + build.stderr[-3000:])
        else:
            run = subprocess.run([str(binary)], capture_output=True, text=True)
            if run.returncode != 0:
                failures.append((run.stdout + run.stderr).strip() or 'driver failed without output')
            else:
                print(run.stdout.strip())

if failures:
    for failure in failures:
        print('FAIL:', failure)
    raise SystemExit(1)
