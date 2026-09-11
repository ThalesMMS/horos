#!/usr/bin/env python3
"""A template Pages 5 or later saved is filled in by Pages, not by editing it.

A Pages '09 template keeps its text in index.xml and the substitution can be
done here. A template saved by Pages 5 or later is IWA - compressed protocol
buffers under Index/ - so there is nothing here that can edit it, and until now
such a template could only be refused. Pages itself can be asked, which is what
the Word report already does with its mail merge.

Three things measured while writing this, each of which the checks below keep:

  * `set characters i thru j of body text to "x"` assigns the whole string to
    *every* character of the range - one placeholder became twenty copies of the
    value - so the replacement is made a paragraph at a time.
  * Waiting on NSWorkspace's completion handler from the main thread is a
    deadlock: it is delivered on the main queue. Report generation stopped dead
    at that line until the wait was removed.
  * Pages is sandboxed, and an AppleScript `open` of a path of our choosing did
    nothing at all. LaunchServices opens the file, which is what grants Pages it.
"""
from pathlib import Path
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
failures = []

fill = (root / 'Horos/Sources/PagesDocumentFill.swift').read_text()
if 'set paragraph i of body text of d to' not in fill:
    failures.append('the replacement is not made a paragraph at a time')
# The comment explains the trap; the code must not contain the statement.
code = '\n'.join(line for line in fill.split('\n') if not line.strip().startswith('//'))
if 'thru' in code:
    failures.append('a range of characters is assigned again, which writes the whole string '
                    'into every character of it')
if 'DispatchSemaphore' in fill or 'semaphore' in fill.lower():
    failures.append("the main thread waits on NSWorkspace's completion handler again, which is "
                    'delivered on the main queue')
if 'NSWorkspace.shared.open' not in fill:
    failures.append('the file is not opened through LaunchServices, which is what grants a '
                    'sandboxed Pages access to it')
if fill.count('with timeout of') < 3:
    failures.append('a conversation with Pages can still hit the default AppleScript timeout')
if 'reversed()' not in fill:
    failures.append('paragraphs are not replaced last first, so a replacement that is not one '
                    'line renumbers the ones after it')

reports = (root / 'Horos/Sources/Reports.m').read_bytes().decode('utf-8')
if 'HorosPagesArchiveHasIndexXML' not in reports:
    failures.append('the two kinds of template are not told apart before one is unpacked')
if 'HorosPagesDocumentFill fillDocumentAtPath:' not in reports:
    failures.append('a modern template is not handed to Pages')
block = reports[reports.index('- (BOOL)createNewPagesReportForStudy:'):]
block = block[:block.index('\n+ (NSString*) pathForPagesTemplate:')]
if block.index('HorosPagesArchiveHasIndexXML') > block.index('decompressPagesFileIfNecessary'):
    failures.append('the document is unpacked before it is known which kind it is')

extraction = (root / 'Horos/Sources/HorosReportExtraction.h').read_text()
if 'archive_read_next_header' not in extraction.split('HorosPagesArchiveHasIndexXML')[1][:900]:
    failures.append('the kind of template is not decided by reading the archive')

# The substitution itself, which is shared with the RTF report and is the part
# that can be exercised without Pages.
program = r'''
#import <Foundation/Foundation.h>
#import "HorosReportFields.h"

static NSString *filled(NSString *line, NSDictionary *values) {
    NSMutableString *text = [[line mutableCopy] autorelease];
    HorosFillReportText(text, values, ^NSString *(NSString *field) { return [@"dicom:" stringByAppendingString:field]; });
    return text;
}

int main(void) { @autoreleasepool {
    NSDictionary *values = @{@"name": @"Volume Geometry", @"patientID": @"VOL-102", @"blank": @""};

    NSCAssert([filled(@"Patient’s name: «name» («patientID»)", values)
        isEqual:@"Patient’s name: Volume Geometry (VOL-102)"], @"two on one line");
    NSCAssert([filled(@"«blank» after", values) isEqual:@" after"], @"an empty value");
    // A key nobody knows is left alone rather than emptied: it may be a word the
    // template means to print.
    NSCAssert([filled(@"«unknown»", values) isEqual:@"«unknown»"], @"unknown key");
    NSCAssert([filled(@"nothing here", values) isEqual:@"nothing here"], @"untouched");
    NSCAssert([filled(@"«DICOM_FIELD:PatientName»", values) isEqual:@"dicom:PatientName"], @"a dicom field");
    // A value that itself contains guillemets is data, not another template.
    NSDictionary *tricky = @{@"name": @"«patientID»", @"patientID": @"X"};
    NSCAssert([filled(@"«name» «patientID»", tricky) isEqual:@"«patientID» X"], @"no second pass");
    NSCAssert([filled(@"", values) isEqual:@""], @"an empty line");
    NSCAssert([filled(@"«»", values) isEqual:@"«»"], @"an empty key");

    printf("PASS: the substitution fills what it knows, leaves what it does not, and does not "
           "evaluate a value as though it were the template\n");
    return 0;
}}
'''
with tempfile.TemporaryDirectory(prefix='horos-pages-modern-') as tmp:
    p = Path(tmp)
    (p / 'test.m').write_text(program)
    subprocess.run(['xcrun', 'clang', '-fno-objc-arc', '-fblocks', '-fsanitize=address',
                    '-framework', 'Foundation', '-I', str(root / 'Horos/Sources'),
                    str(p / 'test.m'), '-o', str(p / 'test')], check=True)
    subprocess.run([str(p / 'test')], check=True)

for failure in failures:
    print('FAIL: %s' % failure)
if failures:
    sys.exit(1)
print('ok: a modern template is told from a legacy one before either is touched, and Pages '
      'fills the modern one in a paragraph at a time')
