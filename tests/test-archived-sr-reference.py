#!/usr/bin/env python3
"""A study's archived SRs refer to one of its images, and are written readable (#651).

The report, annotations and windows state SRs took `[[[self.series anyObject]
valueForKey:@"images"] anyObject]` as the image they refer to and read the patient
from. Once a study held the app's own SRs, that could be one of them: the image
reference came out with no SOP class, the SR could not be read back and its import
was refused behind a modal alert - on the computer sharing the database, for an
edit made by a client. Or the file was being rewritten, and the SR was written with
no patient and no series description, and became a study of its own ("No name").

Now the reference is the first image of the first image series
(`HorosArchivedSRReference`), an SR without both UIDs has no image reference, the
patient comes from the study when the file cannot be read, and a report archive the
app wrote that is refused is logged rather than shown in a modal alert.
"""
from pathlib import Path
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
failures = []

study = (root / 'Horos/Sources/DicomStudy.m').read_bytes().decode('latin1')
if '[[[self.series anyObject] valueForKey:@"images"] anyObject]]' in study.replace(
        '?: [[[self.series anyObject] valueForKey:@"images"] anyObject];', ''):
    failures.append('an archived SR still refers to any image of any series')
if study.count('forImage: [self archivedSRReferenceImage]') != 4:
    failures.append('not every archived SR (annotations, windows state, URL and file reports) takes the reference image')
if '[HorosArchivedSRReference imageInSeries: [self.series allObjects]]' not in study:
    failures.append('the reference image is not chosen among the image series')

annotation = (root / 'Horos/Sources/SRAnnotation.mm').read_text()
write = annotation[annotation.index('- (BOOL)writeToFileAtPath:(NSString *)path'):]
if 'if( namedFromFile == NO)' not in write:
    failures.append('an unreadable reference file still leaves the SR without a patient')
if 'if( referencedClass.length && referencedInstance.length)' not in write:
    failures.append('an image reference is still written without both UIDs')

database = (root / 'Horos/Sources/DicomDatabase.mm').read_text()
if 'if (rejectedReports && generatedByOsiriX)' not in database:
    failures.append("a refused report archive the app wrote still opens a modal alert")

project = (root / 'Horos.xcodeproj/project.pbxproj').read_text()
if project.count('/* ArchivedSRReference.swift in Sources */') != 2 or 'path = "ArchivedSRReference.swift";' not in project:
    failures.append('ArchivedSRReference.swift is not built into the app')

source = r'''
import Foundation

func image(_ uid: String?, _ number: Int?) -> NSDictionary {
    let entry = NSMutableDictionary()
    if let uid { entry["sopInstanceUID"] = uid }
    if let number { entry["instanceNumber"] = NSNumber(value: number) }
    return entry
}
func series(_ sopClass: String?, id: Int?, date: TimeInterval? = nil, images: [NSDictionary]) -> NSDictionary {
    let entry = NSMutableDictionary()
    if let sopClass { entry["seriesSOPClassUID"] = sopClass }
    if let id { entry["id"] = NSNumber(value: id) }
    if let date { entry["date"] = Date(timeIntervalSinceReferenceDate: date) }
    entry["images"] = NSSet(array: images)
    return entry
}
func uid(_ chosen: Any?) -> String? { (chosen as? NSDictionary)?["sopInstanceUID"] as? String }

let ct = "1.2.840.10008.5.1.4.1.1.2"
let basicTextSR = "1.2.840.10008.5.1.4.1.1.88.11"
let pdf = "1.2.840.10008.5.1.4.1.1.104.1"

// The app's SRs come first (report 5003, annotations 5004) and a PDF: the CT series is chosen, its first instance.
let study = [series(basicTextSR, id: 5003, images: [image("report", 1)]),
             series(basicTextSR, id: 5004, images: [image("annotations", 1)]),
             series(pdf, id: 2, images: [image("pdf", 1)]),
             series(ct, id: 3, images: [image("ct-3", 3), image("ct-1", 1), image("ct-2", 2)])]
for order in [[0, 1, 2, 3], [3, 2, 1, 0], [1, 3, 0, 2]] {
    precondition(uid(ArchivedSRReference.image(inSeries: order.map { study[$0] })) == "ct-1", "\(order)")
}

// Series by number, then by date; a series without a class, or an image without a UID, is passed over.
precondition(uid(ArchivedSRReference.image(inSeries: [
    series(ct, id: 7, images: [image("seven", 1)]),
    series(ct, id: 4, date: 20, images: [image("four-late", 1)]),
    series(ct, id: 4, date: 10, images: [image("four-early", 1)]),
])) == "four-early")
precondition(uid(ArchivedSRReference.image(inSeries: [
    series(nil, id: 1, images: [image("no-class", 1)]),
    series("", id: 1, images: [image("empty-class", 1)]),
    series(ct, id: 2, images: [image(nil, 1), image("", 2), image("with-uid", 3)]),
])) == "with-uid")

// Nothing to refer to: the app's SRs alone, no series, nil.
precondition(ArchivedSRReference.image(inSeries: [series(basicTextSR, id: 5004, images: [image("annotations", 1)])]) == nil)
precondition(ArchivedSRReference.image(inSeries: []) == nil)
precondition(ArchivedSRReference.image(inSeries: nil) == nil)
print("ok")
'''

with tempfile.TemporaryDirectory() as temporary:
    work = Path(temporary)
    (work / 'main.swift').write_text(source)
    binary = work / 'reference'
    compiled = subprocess.run(['xcrun', 'swiftc', '-module-name', 'Reference', str(root / 'Horos/Sources/ArchivedSRReference.swift'),
                               str(work / 'main.swift'), '-o', str(binary)], capture_output=True, text=True)
    if compiled.returncode != 0:
        failures.append('ArchivedSRReference.swift does not compile: ' + compiled.stderr[-800:])
    else:
        run = subprocess.run([str(binary)], capture_output=True, text=True)
        if run.returncode != 0 or run.stdout.strip() != 'ok':
            failures.append('the reference image is not the one expected: ' + (run.stderr or run.stdout)[-800:])

if failures:
    print('\n'.join('FAIL: ' + f for f in failures))
    raise SystemExit(1)
print('archived SRs: one image of an image series as reference, readable without it, no modal alert for the app\'s own')
