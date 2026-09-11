#!/usr/bin/env python3
"""Host contract for Word report merge — mock/compilation, not native Word.

Issue #157's remaining acceptance is a real merge in Microsoft Word. This file
does not launch Word, send mail, or write a .doc. It checks that the already-
shipped host still: resolves .doc/.docx by exact name, prepares on a private
copy, publishes only a regular non-empty file, and on AppleScript failure closes
only the merge documents it opened.
"""
from pathlib import Path
import argparse
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
failures = []

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--reports-source', type=Path, default=root / 'Horos/Sources/Reports.m',
                    help='alternate revision for a before/after regression check')
reports = parser.parse_args().reports_source.read_bytes().decode('latin1')
replacement = (root / 'Horos/Sources/HorosReportFileReplacement.h').read_text()
placement = (root / 'Horos/Sources/ReportImagePlacement.swift').read_text()
conversion = (root / 'Horos/Sources/PagesPDFConversion.swift').read_text()

source = reports
if 'createNewWordReportForStudy:' not in source:
    failures.append('createNewWordReportForStudy: is missing')
    print('FAIL:\n- ' + '\n- '.join(failures))
    sys.exit(1)

for needle, reason in (
    ('HorosCreateReportFromTemplate', 'the merge still prepares a private copy before publishing'),
    (r'tell application \"Microsoft Word\"', 'the merge still talks to Word'),
    ('on error errorMessage number errorNumber', 'a refused merge must keep the AppleScript number'),
    # Both documents are closed through the helper now: Word rejects a command
    # sent to a stored `active document`, and the variables the old handler
    # tested were undefined whenever `open` was the statement that failed.
    ('my closeReportDocument(mergedName)', 'a failed merge must close the merged document'),
    ('my closeReportDocument(templateName)', 'a failed merge must close the template window'),
    ('on closeReportDocument(theName)', 'the handler that closes the documents is missing'),
    ('The merge did not create a new document.', 'a merge that edited the template in place is a failure'),
    ('hasPrefix: @"doc"', 'exact .doc/.docx names must still resolve'),
):
    if needle not in source:
        failures.append(reason)

templates = reports[reports.find('+(NSString*)databaseWordTemplatesDirPath'):]
templates = templates[:templates.find('+(NSString*)resolvedDatabaseWordTemplatesDirPath')]
if 'must never be removed' not in templates and 'never be removed' not in templates:
    failures.append('creating WORD TEMPLATES must not delete a colliding file')
if 'createDirectoryAtPath:folder' not in templates:
    failures.append('WORD TEMPLATES is no longer created without deleting a collision')

if 'HorosCreateReportFromTemplate' not in replacement:
    failures.append('HorosCreateReportFromTemplate is missing')

# Image insertion (#153) and Pages→PDF (#129) stay on their own types.
if 'PagesPDFConversion' in placement:
    failures.append('image insertion was mixed into the Pages PDF converter')
if 'insertSelectedImagesIntoReport' in conversion or 'HorosReportImageInsertion' in conversion:
    failures.append('Pages PDF conversion now inserts report images')
if 'createNewWordReportForStudy' in placement:
    failures.append('image insertion absorbed the Word merge')

if failures:
    print('FAIL:\n- ' + '\n- '.join(failures))
    sys.exit(1)
print('PASS: Word merge host still prepares privately, closes only its windows on error, '
      'and stays off the Pages PDF and image-insertion types')

# Execute the production creation method with an editor substitute. In
# particular, refusing consent must happen before opening/preparing a document,
# not merely before publishing its bytes or its study association.
start = reports.rindex('- (BOOL)createNewWordReportForStudy:')
method = reports[start:reports.index('\n#pragma mark -\n#pragma mark OpenDocument', start)]
program = r'''
#import <Foundation/Foundation.h>
#import "HorosReportFileReplacement.h"
#define NSManagedObject NSMutableDictionary
static NSString *templates, *alert;
static NSInteger consentStatus;
static int consentChecks, dataWrites, scripts, launches;
static BOOL cancelMerge, missingConfirmation;
static NSInteger TestAlert(NSString *title, NSString *format, id ok, id a, id b, ...) {
    va_list args; va_start(args, b);
    alert=[[[NSString alloc] initWithFormat:format arguments:args] autorelease];
    va_end(args); return 0;
}
#define NSRunCriticalAlertPanel TestAlert
@interface HorosWordReportAutomation : NSObject
+ (NSError*)consentErrorWithoutPrompt;
@end
@implementation HorosWordReportAutomation
+ (NSError*)consentErrorWithoutPrompt {
    consentChecks++;
    return consentStatus ? [NSError errorWithDomain:@"ControlledConsent" code:consentStatus
        userInfo:@{NSLocalizedDescriptionKey:@"Controlled refusal"}] : nil;
}
@end
@interface NSWorkspace : NSObject
+ (instancetype)sharedWorkspace;
- (BOOL)openFile:(NSString*)path withApplication:(NSString*)app andDeactivate:(BOOL)flag;
@end
@implementation NSWorkspace
+ (instancetype)sharedWorkspace { static NSWorkspace *w; if(!w) w=[self new]; return w; }
- (BOOL)openFile:(NSString*)path withApplication:(NSString*)app andDeactivate:(BOOL)flag { launches++; return YES; }
@end
@interface Reports : NSObject { NSString *templateName; }
+ (NSArray*)wordTemplatesList;
+ (NSString*)resolvedDatabaseWordTemplatesDirPath;
+ (id)_runAppleScript:(NSString*)source withArguments:(NSArray*)args;
- (NSString*)generateWordReportMergeDataForStudy:(id)study toPath:(NSString*)path;
@end
@implementation Reports
+ (NSArray*)wordTemplatesList { return @[@"Synthetic.docx"]; }
+ (NSString*)resolvedDatabaseWordTemplatesDirPath { return templates; }
+ (id)_runAppleScript:(NSString*)source withArguments:(NSArray*)args {
    scripts++;
    NSCAssert([args[2] hasSuffix:@"-template.docx"] && [args[2] containsString:@"horos-report-template-"], @"unique private template");
    NSCAssert([[NSFileManager.defaultManager attributesOfItemAtPath:args[2] error:NULL].fileType isEqual:NSFileTypeRegular], @"template exists");
    NSCAssert([args[1] hasSuffix:@"-merged.docx"] && [args[1] containsString:@"horos-report-template-"], @"unique private output");
    NSCAssert([NSFileManager.defaultManager contentsEqualAtPath:args[1] andPath:args[2]], @"output exists before Word opens it");
    if (missingConfirmation) return nil;
    NSCAssert([@"controlled merged bytes" writeToFile:args[1] atomically:YES encoding:NSUTF8StringEncoding error:NULL], @"output");
    if(cancelMerge) [NSException raise:@"Controlled cancellation" format:@"Cancelled (-128)"];
    return @YES;
}
- (NSString*)generateWordReportMergeDataForStudy:(id)study toPath:(NSString*)path { dataWrites++; return path; }
METHOD
@end
#define check(v) NSCAssert((v), @"failed: %s", #v)
int main(int argc, char **argv) { @autoreleasepool {
    NSString *dir=[NSString stringWithUTF8String:argv[1]];
    templates=[dir stringByAppendingPathComponent:@"templates"];
    check([NSFileManager.defaultManager createDirectoryAtPath:templates withIntermediateDirectories:YES attributes:nil error:NULL]);
    NSString *model=[templates stringByAppendingPathComponent:@"Synthetic.docx"];
    NSString *dest=[dir stringByAppendingPathComponent:@"existing.docx"];
    NSData *original=[@"original template" dataUsingEncoding:NSUTF8StringEncoding];
    NSData *previous=[@"previous report" dataUsingEncoding:NSUTF8StringEncoding];
    check([original writeToFile:model atomically:YES] && [previous writeToFile:dest atomically:YES]);
    NSMutableDictionary *study=[@{@"reportURL":@"previous association"} mutableCopy];
    Reports *report=[Reports new];
    for (NSNumber *status in @[@(-1743), @(-1744), @(-1712), @(-600)]) {
        consentStatus=status.integerValue;
        check(![report createNewWordReportForStudy:study toDestinationPath:dest]);
        check(dataWrites==0 && scripts==0 && launches==0);
        check([alert isEqual:@"Controlled refusal"]);
        check([study[@"reportURL"] isEqual:@"previous association"]);
        check([[NSData dataWithContentsOfFile:dest] isEqual:previous]);
    }
    check(consentChecks==4);
    consentStatus=0; cancelMerge=YES;
    check(![report createNewWordReportForStudy:study toDestinationPath:dest]);
    check(dataWrites==1 && scripts==1 && launches==0 && [alert containsString:@"-128"]);
    check([study[@"reportURL"] isEqual:@"previous association"]);
    check([[NSData dataWithContentsOfFile:dest] isEqual:previous]);
    cancelMerge=NO; missingConfirmation=YES;
    check(![report createNewWordReportForStudy:study toDestinationPath:dest]);
    check(dataWrites==2 && scripts==2 && launches==0);
    check([study[@"reportURL"] isEqual:@"previous association"]);
    check([[NSData dataWithContentsOfFile:dest] isEqual:previous]);
    missingConfirmation=NO;
    check([report createNewWordReportForStudy:study toDestinationPath:dest]);
    check(dataWrites==3 && scripts==3 && launches==1);
    check([study[@"reportURL"] isEqual:dest]);
    check([[NSString stringWithContentsOfFile:dest encoding:NSUTF8StringEncoding error:NULL] isEqual:@"controlled merged bytes"]);
    check([[NSData dataWithContentsOfFile:model] isEqual:original]);
    puts("PASS: production Word creation refuses before preparing/opening, preserves prior bytes/association on cancellation, publishes on controlled success");
} }
'''.replace('METHOD', method)
swift = r'''
import Foundation
precondition(WordReportAutomation.error(forStatus: 0) == nil)
for status: Int32 in [-1743, -1744, -1712, -600] {
    let error = WordReportAutomation.error(forStatus: status)!
    precondition(error.code == Int(status))
    precondition(error.localizedDescription.contains(String(status)))
    precondition(error.localizedDescription.contains("No report document was opened or changed"))
    if status != -600 { precondition(error.localizedDescription.contains("System Settings")) }
}
print("PASS: production Swift consent errors preserve the native status and recovery text")
for status: Int32 in [0, -1743, -1744, -600] {
    let error = WordReportAutomation.checkWithoutPrompt {
        precondition(!Thread.isMainThread)
        return status
    }
    precondition(error?.code == (status == 0 ? nil : Int(status)))
}
let releaseSlowCheck = DispatchSemaphore(value: 0)
let timeoutError = WordReportAutomation.checkWithoutPrompt(timeout: .milliseconds(25)) {
    releaseSlowCheck.wait()
    return 0
}
precondition(timeoutError?.code == -1712)
releaseSlowCheck.signal()

func spin(until condition: () -> Bool) {
    let deadline = Date(timeIntervalSinceNow: 3)
    while Date() < deadline {
        if condition() { return }
        RunLoop.current.run(until: Date(timeIntervalSinceNow: 0.005))
    }
    preconditionFailure("main-thread completion did not arrive")
}
@MainActor func settle(until condition: () -> Bool) async {
    for _ in 0..<300 {
        if condition() { return }
        try! await Task.sleep(nanoseconds: 10_000_000)
    }
    preconditionFailure("asynchronous consent did not complete")
}
var asynchronousTestsFinished = false
Task { @MainActor in
    let started = DispatchSemaphore(value: 0)
    let respond = DispatchSemaphore(value: 0)
    var completed = false, heartbeat = false, calls = 0
    WordReportAutomation.requestConsent(using: {
        precondition(!Thread.isMainThread)
        started.signal()
        respond.wait()
        return -1743
    }) { error in
        precondition(Thread.isMainThread && error?.code == -1743)
        calls += 1; completed = true
    }
    // The native API may take arbitrarily long. AppKit must still be able to
    // service events while that worker waits for the person's response.
    DispatchQueue.main.async { heartbeat = true }
    await settle { heartbeat && started.wait(timeout: .now()) == .success }
    precondition(!completed)
    WordReportAutomation.requestConsent(using: {
        fatalError("a second consent request must not create another blocked worker")
    }) { error in precondition(error?.code == 1) }
    respond.signal()
    await settle { completed }
    precondition(calls == 1)
    // A completed refusal releases the request slot so retry can succeed.
    completed = false
    WordReportAutomation.requestConsent(using: { 0 }) { error in
        precondition(Thread.isMainThread && error == nil)
        calls += 1; completed = true
    }
    await settle { completed }
    precondition(calls == 2)
    asynchronousTestsFinished = true
}
spin { asynchronousTestsFinished }
print("PASS: blocking consent stays off-main, main events run, duplicate requests are bounded, refusal/retry and synchronous timeout propagate")
'''
with tempfile.TemporaryDirectory(prefix='horos-word-host-') as folder:
    p = Path(folder)
    (p / 'host.m').write_text(program)
    subprocess.run(['xcrun', 'clang', '-fno-objc-arc', '-fblocks', '-fsanitize=address',
                    '-framework', 'Foundation', '-I', str(root / 'Horos/Sources'),
                    str(p / 'host.m'), '-o', str(p / 'host')], check=True)
    subprocess.run([str(p / 'host'), str(p)], check=True)
    (p / 'main.swift').write_text(swift)
    subprocess.run(['xcrun', 'swiftc', '-sanitize=address',
                    str(root / 'Horos/Sources/WordReportAutomation.swift'), str(p / 'main.swift'),
                    '-o', str(p / 'consent')], check=True)
    subprocess.run([str(p / 'consent')], check=True)
