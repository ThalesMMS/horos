#!/usr/bin/env python3
"""A file with no identifier of its own is still given one that UI can hold.

A DICOM without SeriesInstanceUID was indexed with an empty series identifier,
and one without StudyInstanceUID under the patient's name. Both are what the
C-FIND SCP answers with, as a UI - which allows 64 characters of digits and dots.
Measured before the change, a SERIES level query against the database answered
with an empty (0020,000e) and a (0020,000d) of `Noname`.

The identifier is derived from what the importer already groups the object on,
so the same file imported twice lands in the same series; that is why it is not
dcmGenerateUniqueIdentifier, which the exporter uses to make something new.

HorosDerivedUID is compiled and run here.
"""
from pathlib import Path
import re
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
failures = []
importer = (root / 'Horos/Sources/DicomFileDCMTKCategory.mm').read_bytes().decode('latin1')
database = (root / 'Horos/Sources/DicomDatabase.mm').read_bytes().decode('latin1')

DRIVER = r'''
#import <Foundation/Foundation.h>
#import "HorosDerivedUID.h"
static void emit(NSString *key, NSString *value) {
    printf("%s\t%s\n", key.UTF8String, value.UTF8String);
}
int main(void) { @autoreleasepool {
    NSString *a = [HorosDerivedUID seriesUIDForKey: @"study|series one"];
    NSString *b = [HorosDerivedUID seriesUIDForKey: @"study|series one"];
    NSString *c = [HorosDerivedUID seriesUIDForKey: @"study|series two"];
    emit(@"series", a);
    emit(@"stable", [a isEqualToString: b] ? @"yes" : @"no");
    emit(@"distinct", [a isEqualToString: c] ? @"no" : @"yes");
    emit(@"seriesLength", [NSString stringWithFormat: @"%d", (int) a.length]);
    emit(@"seriesConformant", [HorosDerivedUID isConformantUID: a] ? @"yes" : @"no");
    emit(@"seriesRoot", [a hasPrefix: [HorosDerivedUID seriesRoot]] ? @"yes" : @"no");

    NSString *study = [HorosDerivedUID studyUIDForKey: @"QA^NoUID"];
    emit(@"studyConformant", [HorosDerivedUID isConformantUID: study] ? @"yes" : @"no");
    emit(@"studyLength", [NSString stringWithFormat: @"%d", (int) study.length]);
    emit(@"studyRoot", [study hasPrefix: [HorosDerivedUID studyRoot]] ? @"yes" : @"no");
    emit(@"rootsDiffer", [[HorosDerivedUID studyRoot] isEqualToString: [HorosDerivedUID seriesRoot]] ? @"no" : @"yes");

    // An empty key is still a usable identifier, not a crash and not a bare root.
    NSString *empty = [HorosDerivedUID seriesUIDForKey: @""];
    emit(@"emptyKeyConformant", [HorosDerivedUID isConformantUID: empty] ? @"yes" : @"no");
    emit(@"emptyKeyDistinct", [empty isEqualToString: a] ? @"no" : @"yes");
    emit(@"nilKeyConformant", [HorosDerivedUID isConformantUID: [HorosDerivedUID seriesUIDForKey: nil]] ? @"yes" : @"no");

    // What UI cannot hold.
    emit(@"rejectsEmpty", [HorosDerivedUID isConformantUID: @""] ? @"no" : @"yes");
    emit(@"rejectsNil", [HorosDerivedUID isConformantUID: nil] ? @"no" : @"yes");
    emit(@"rejectsLetters", [HorosDerivedUID isConformantUID: @"LOCALIZER1.2.3"] ? @"no" : @"yes");
    emit(@"rejectsDoubleDot", [HorosDerivedUID isConformantUID: @"1..2"] ? @"no" : @"yes");
    emit(@"rejectsLeadingZero", [HorosDerivedUID isConformantUID: @"1.02"] ? @"no" : @"yes");
    emit(@"rejectsTooLong", [HorosDerivedUID isConformantUID:
        [@"" stringByPaddingToLength: 65 withString: @"1" startingAtIndex: 0]] ? @"no" : @"yes");
    emit(@"acceptsZeroComponent", [HorosDerivedUID isConformantUID: @"1.0.2"] ? @"yes" : @"no");
    return 0;
} }
'''

results = {}
with tempfile.TemporaryDirectory(prefix='horos-derived-uid-') as directory:
    work = Path(directory)
    (work / 'main.m').write_text(DRIVER)
    built = subprocess.run(['xcrun', 'clang', '-fobjc-arc',
                            '-I', str(root / 'Horos/Sources'),
                            str(work / 'main.m'), str(root / 'Horos/Sources/HorosDerivedUID.m'),
                            '-framework', 'Foundation', '-o', str(work / 'derive')],
                           capture_output=True, text=True)
    if built.returncode != 0:
        failures.append('HorosDerivedUID does not compile:\n%s' % built.stderr[-1200:])
    else:
        run = subprocess.run([str(work / 'derive')], capture_output=True, text=True)
        if run.returncode != 0:
            failures.append('the driver failed: %s' % run.stderr[-600:])
        for line in run.stdout.splitlines():
            key, _, value = line.partition('\t')
            results[key] = value

if results:
    for key in ('stable', 'distinct', 'seriesConformant', 'seriesRoot', 'studyConformant',
                'studyRoot', 'rootsDiffer', 'emptyKeyConformant', 'emptyKeyDistinct',
                'nilKeyConformant', 'rejectsEmpty', 'rejectsNil', 'rejectsLetters',
                'rejectsDoubleDot', 'rejectsLeadingZero', 'rejectsTooLong',
                'acceptsZeroComponent'):
        if results.get(key) != 'yes':
            failures.append('%s is %r, expected yes' % (key, results.get(key)))
    for key in ('seriesLength', 'studyLength'):
        length = int(results.get(key, '0') or 0)
        if not 30 <= length <= 64:
            failures.append('%s is %d, which is not a usable UID length' % (key, length))

# --- the importer derives when the file carries nothing ----------------------
if 'HorosDerivedUID studyUIDForKey:' not in importer:
    failures.append('a file with no StudyInstanceUID is still indexed under the patient name')
if 'HorosDerivedUID seriesUIDForKey:' not in importer:
    failures.append('a file with no SeriesInstanceUID still leaves the identifier empty')
if not re.search(r'\[\[dicomElements objectForKey: @"seriesDICOMUID"\] length\] == 0', importer):
    failures.append('the derivation does not check whether the file already carried one')
# And the grouping must be unchanged: the derived value comes from the key the
# importer groups on, not from something new.
at = importer.find('HorosDerivedUID seriesUIDForKey:')
if at > 0 and 'self.serieID' not in importer[at - 200:at + 200]:
    failures.append('the derived series identifier does not come from the grouping key, so a '
                    're-import would land somewhere else')

# --- and rows indexed before that are repaired -------------------------------
if 'repairEmptySeriesIdentifiersInContext:' not in database:
    failures.append('series indexed before this still answer C-FIND with an empty identifier')
else:
    at = database.find('+(void)repairEmptySeriesIdentifiersInContext:(NSManagedObjectContext*)context {')
    body = database[at:at + 2000]
    if 'seriesDICOMUID == nil OR seriesDICOMUID ==' not in body:
        failures.append('the repair does not select the rows that have no identifier')
    if '[context save:' not in body:
        failures.append('the repair does not save through the context, so nothing persists')
    if 'seriesInstanceUID' not in body or 'study.studyInstanceUID' not in body:
        failures.append('the repair does not derive from what the row is grouped on')
    if 'repairEmptySeriesIdentifiersInContext: self.managedObjectContext' not in database:
        failures.append('the repair is never run')

for failure in failures:
    print('FAIL: %s' % failure)
if failures:
    sys.exit(1)
print('ok: an object with no identifier gets a conformant one derived from what it is grouped '
      'on, the same one every time, and rows indexed before are repaired at open')
