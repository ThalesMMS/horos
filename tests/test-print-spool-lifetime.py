#!/usr/bin/env python3
"""#384: a printed page must not outlive the job in the temporary directory.

#384 requires that hidden identifiers not reappear "nos metadados, frames,
páginas ou **temporários**". The database print spools each page as a PDF under
`NSTemporaryDirectory()` — a patient name and a picture, on disk — and nothing
ever removed the directory. Every print left one behind, for good.

`HorosPrintSelection` now owns the directory's whole life: it makes the path,
and it takes it away. The removal refuses any path that is not one of its own
under the temporary directory, so a wrong argument removes nothing rather than
something else.
"""
from pathlib import Path
import re
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
failures = []

DRIVER = r'''
import Foundation

@main struct Check {
    static func main() {
        let manager = FileManager.default

        // The directory it makes is its own, under the temporary directory, and
        // never the same twice.
        let first = PrintSelection.newSpoolDirectory()
        let second = PrintSelection.newSpoolDirectory()
        precondition(first != second, "two jobs must not share a spool directory")
        precondition(PrintSelection.isSpoolDirectory(first))
        precondition((first as NSString).lastPathComponent.hasPrefix(PrintSelection.spoolDirectoryPrefix))

        // It removes one of its own, with whatever is inside it.
        try! manager.createDirectory(atPath: first, withIntermediateDirectories: true)
        let page = (first as NSString).appendingPathComponent("page-1.pdf")
        try! Data("QA^Patient".utf8).write(to: URL(fileURLWithPath: page))
        precondition(manager.fileExists(atPath: page))
        precondition(PrintSelection.discardSpoolDirectory(first))
        precondition(!manager.fileExists(atPath: first), "the spool survived")
        precondition(!manager.fileExists(atPath: page), "a page survived")

        // Removing one that is already gone is not a failure: the job is over
        // either way, and the point is that nothing is left.
        precondition(PrintSelection.discardSpoolDirectory(first))

        // And it refuses everything else. A wrong argument must remove nothing.
        let elsewhere = (NSTemporaryDirectory() as NSString).appendingPathComponent("horos-keep-me")
        try! manager.createDirectory(atPath: elsewhere, withIntermediateDirectories: true)
        precondition(!PrintSelection.isSpoolDirectory(elsewhere))
        precondition(!PrintSelection.discardSpoolDirectory(elsewhere))
        precondition(manager.fileExists(atPath: elsewhere), "a directory that is not a spool was removed")
        try? manager.removeItem(atPath: elsewhere)

        for path in ["/", "/tmp", NSTemporaryDirectory(), NSHomeDirectory(),
                     "/Users/somebody/horos-print-x",
                     (NSTemporaryDirectory() as NSString).appendingPathComponent("horos-print-"),
                     (NSTemporaryDirectory() as NSString).appendingPathComponent("horos-print-a/b")] {
            precondition(!PrintSelection.isSpoolDirectory(path), "would have removed \(path)")
            precondition(!PrintSelection.discardSpoolDirectory(path), "would have removed \(path)")
        }

        print("spool directories are unique, removed with their pages, and nothing else is")
    }
}
'''

swift = (root / 'Horos/Sources/PrintSelection.swift')
if not swift.is_file():
    failures.append('Horos/Sources/PrintSelection.swift is missing')
else:
    with tempfile.TemporaryDirectory(prefix='horos-print-spool-') as folder:
        path = Path(folder)
        (path / 'Check.swift').write_text(DRIVER)
        build = subprocess.run(['xcrun', 'swiftc', '-parse-as-library', str(swift),
                                str(path / 'Check.swift'), '-o', str(path / 'check')],
                               capture_output=True, text=True)
        if build.returncode:
            failures.append('the spool lifetime does not compile: %s'
                            % build.stderr.strip().splitlines()[-3:])
        else:
            run = subprocess.run([str(path / 'check')], capture_output=True, text=True)
            if run.returncode:
                failures.append('the spool lifetime does not hold: %s' % run.stderr.strip()[-400:])

# And the caller has to use both ends of it.
browser = (root / 'Horos/Sources/BrowserController.m').read_bytes().decode('latin1')
if 'newSpoolDirectory' not in browser:
    failures.append('the database print must ask HorosPrintSelection for its spool directory')
if 'discardSpoolDirectory' not in browser:
    failures.append('the database print must remove its spool directory')
if re.search(r'horos-print-%@', browser):
    failures.append('the spool path is built by hand again instead of asked for')
# Every way out of the printing method has to reach the removal.
body = re.search(r'NSString \*dir = \[HorosPrintSelection newSpoolDirectory\];(.*?)\n\}', browser, re.S)
if not body:
    failures.append('the spool directory is no longer created in the print path')
else:
    if '@finally' not in body.group(1):
        failures.append('the removal must be in a @finally: a refusal returns early, and that page '
                        'is as identifiable as a printed one')
    if body.group(1).index('discardSpoolDirectory') < body.group(1).index('printDatabaseSpool'):
        failures.append('the spool must be removed after the job, not before it')

if failures:
    print('FAIL:')
    for item in failures:
        print(' ', item)
    raise SystemExit(1)

print('PASS: the print spool is unique, removed with its pages on every exit, and the removal '
      'refuses anything that is not one of its own')
