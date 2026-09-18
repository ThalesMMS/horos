#!/usr/bin/env python3
"""A study reads back its most recent archived SR, even when several share a second (#645).

Every edit of a study's comment, state or key images writes a new annotations SR
(`-[DicomStudy archiveAnnotationsAsDICOMSR]`), imports it, and after an import the
study applies the annotations of its most recent SR (`-reapplyAnnotationsFromDICOMSR`).
The most recent was the last one sorted by `date` - the SR's content date and time,
parsed to the second. Three edits within one second made three SRs with one date,
the sort returned them in any order, and the SR written before the state changed
could be applied over it: through a shared database the state went back from 2 to
0 (#645). The report SR and the windows state SR are chosen the same way.

Within one date, the SR stored later - under the higher number in the database
folder - is the more recent.
"""
from pathlib import Path
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
failures = []

study = (root / 'Horos/Sources/DicomStudy.m').read_bytes().decode('latin1')


def method(signature):
    begin = study.index(signature)
    end = study.index('\n}\n', begin)
    return study[begin:end]


for name, signature in (('the annotations SR', '- (NSManagedObject *) annotationsSRImage'),
                        ('the report SR', '- (DicomImage*) reportImage'),
                        ('the windows state SR', '- (NSArray*) allWindowsStateSRSeries')):
    body = method(signature)
    if '[HorosArchivedSRImages sortedOldestFirst: images]' not in body:
        failures.append('%s is not chosen with the stored order as tie-break' % name)
    if 'sortDescriptorWithKey:@"date"' in body:
        failures.append('%s is still sorted by date alone' % name)
if '#import "Horos-Swift.h"' not in study:
    failures.append('DicomStudy.m does not see the Swift helper')

project = (root / 'Horos.xcodeproj/project.pbxproj').read_text()
if project.count('/* ArchivedSRImages.swift in Sources */') != 2 or 'path = "ArchivedSRImages.swift";' not in project:
    failures.append('ArchivedSRImages.swift is not built into the app')

source = r'''
import Foundation

func sr(_ seconds: TimeInterval?, _ number: Int?) -> NSDictionary {
    let entry = NSMutableDictionary()
    if let seconds { entry["date"] = Date(timeIntervalSinceReferenceDate: seconds) }
    if let number { entry["pathNumber"] = NSNumber(value: number) }
    return entry
}
func numbers(_ images: [Any]) -> [Int] { images.map { (($0 as! NSDictionary)["pathNumber"] as? NSNumber)?.intValue ?? -1 } }

// Three SRs written within one second, in every order a set can hand them over: the last stored is the newest.
let tied = [sr(811348100, 9), sr(811348100, 10), sr(811348100, 11)]
for order in [[0, 1, 2], [0, 2, 1], [1, 0, 2], [1, 2, 0], [2, 0, 1], [2, 1, 0]] {
    let sorted = ArchivedSRImages.sortedOldestFirst(order.map { tied[$0] })
    precondition(numbers(sorted) == [9, 10, 11], "\(order) -> \(numbers(sorted))")
}

// A later date is newer whatever its number: an SR received from elsewhere, stored later, is not.
precondition(numbers(ArchivedSRImages.sortedOldestFirst([sr(811348104, 12), sr(811348000, 40)])) == [40, 12])

// No date is the oldest; no number comes before a number within a date.
precondition(numbers(ArchivedSRImages.sortedOldestFirst([sr(811348100, 3), sr(nil, 99)])) == [99, 3])
precondition(numbers(ArchivedSRImages.sortedOldestFirst([sr(811348100, 5), sr(811348100, nil)])) == [-1, 5])

// Nothing to sort.
precondition(ArchivedSRImages.sortedOldestFirst(nil).isEmpty)
precondition(ArchivedSRImages.sortedOldestFirst([]).isEmpty)
precondition(ArchivedSRImages.sortedOldestFirst([sr(1, 1)]).count == 1)
print("ok")
'''

with tempfile.TemporaryDirectory() as temporary:
    work = Path(temporary)
    (work / 'main.swift').write_text(source)
    binary = work / 'sr'
    compiled = subprocess.run(['xcrun', 'swiftc', '-module-name', 'ArchivedSR', str(root / 'Horos/Sources/ArchivedSRImages.swift'),
                               str(work / 'main.swift'), '-o', str(binary)], capture_output=True, text=True)
    if compiled.returncode != 0:
        failures.append('ArchivedSRImages.swift does not compile: ' + compiled.stderr[-800:])
    else:
        run = subprocess.run([str(binary)], capture_output=True, text=True)
        if run.returncode != 0 or run.stdout.strip() != 'ok':
            failures.append('the archived SRs are not in the order they were stored: ' + (run.stderr or run.stdout)[-800:])

if failures:
    print('\n'.join(failures))
    sys.exit(1)
print('archived SRs: the most recent is the last stored within a date, for annotations, report and windows state')
