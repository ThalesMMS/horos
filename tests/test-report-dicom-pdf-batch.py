#!/usr/bin/env python3
"""Generating DICOM PDFs for a selection indexes each file once (#654).

`-[BrowserController convertReportToDICOMSR:]` - the menu item that writes the
selected studies' reports as DICOM PDFs - called `-addFilesAtPaths:…` inside its
loop, always with the whole list accumulated so far. For N studies the first file
was indexed N times, the second N-1, and so on: N(N+1)/2 additions, each one
rereading a file already indexed (`rereadExistingItems:YES`).

The shipped method is compiled here over four studies, one of whose reports
cannot be converted:

* one addition, with the three files that were written;
* the study that failed is named to the user and its file is not indexed;
* nothing is indexed when no report could be converted.

    python3 tests/test-report-dicom-pdf-batch.py [<git revision>]
"""
from pathlib import Path
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
path = 'Horos/Sources/BrowserController.m'
source = (subprocess.check_output(['git', '-C', str(root), 'show', sys.argv[1] + ':' + path])
          if len(sys.argv) > 1 else (root / path).read_bytes()).decode('latin1')

start = source.index('- (IBAction) convertReportToDICOMSR: (id)sender')
opening = source.index('{', start)
depth = 0
for end in range(opening, len(source)):
    if source[end] == '{':
        depth += 1
    elif source[end] == '}':
        depth -= 1
        if depth == 0:
            break
method = source[start:end + 1]

code = r'''
#import <Foundation/Foundation.h>
#include <stdio.h>
static int additions = 0, indexed = 0, alerts = 0;
static NSMutableArray *alerted = nil;
// The panel's three button arguments come between the message and its values.
#define NSRunAlertPanel(title, format, first, second, third, ...) (alerts++, [alerted addObject:[NSString stringWithFormat:format, ##__VA_ARGS__]], (NSInteger)1)

// The selection is Core Data objects in the app; here, the studies themselves.
@compatibility_alias NSManagedObject NSObject;
@interface DicomStudy : NSObject
@property(copy) NSString *name;
@property BOOL failing;
- (void)saveReportAsDicomAtPath:(NSString*)path;
@end
@implementation DicomStudy
- (void)saveReportAsDicomAtPath:(NSString*)path {
    if (self.failing)
        [NSException raise:NSGenericException format:@"The report could not be converted to PDF."];
    [[NSData dataWithBytes:"DICM" length:4] writeToFile:path atomically:YES];
}
- (id)valueForKey:(NSString*)key { return [key isEqualToString:@"type"] ? @"Study" : [super valueForKey:key]; }
@end
@interface Database : NSObject
- (void)addFilesAtPaths:(NSArray*)paths postNotifications:(BOOL)post dicomOnly:(BOOL)dicom rereadExistingItems:(BOOL)reread generatedByOsiriX:(BOOL)generated;
@end
@implementation Database
- (void)addFilesAtPaths:(NSArray*)paths postNotifications:(BOOL)post dicomOnly:(BOOL)dicom rereadExistingItems:(BOOL)reread generatedByOsiriX:(BOOL)generated {
    additions++;
    indexed += (int)paths.count;
}
@end
@interface AppController : NSObject
+ (void)printStackTrace:(NSException*)e;
@end
@implementation AppController
+ (void)printStackTrace:(NSException*)e {}
@end
@interface BrowserController : NSObject {
    Database *_database;
}
@property(retain) NSArray *selection;
@property(retain) NSString *directory;
- (NSArray*)databaseSelection;
- (NSString*)getNewFileDatabasePath:(NSString*)extension;
- (void)updateReportToolbarIcon:(id)sender;
- (IBAction)convertReportToDICOMSR:(id)sender;
@end
@implementation BrowserController
- (id)init { if ((self = [super init])) _database = [Database new]; return self; }
- (NSArray*)databaseSelection { return self.selection; }
- (NSString*)getNewFileDatabasePath:(NSString*)extension {
    static int number = 0;
    return [self.directory stringByAppendingPathComponent:[NSString stringWithFormat:@"report-%d.%@", ++number, extension]];
}
- (void)updateReportToolbarIcon:(id)sender {}
METHOD
@end

static DicomStudy *study(NSString *name, BOOL failing) {
    DicomStudy *s = [DicomStudy new];
    s.name = name;
    s.failing = failing;
    return s;
}

int main(int argc, char **argv) {
    @autoreleasepool {
        alerted = [NSMutableArray array];
        BrowserController *browser = [BrowserController new];
        browser.directory = @(argv[1]);
        int failed = 0;

        browser.selection = @[study(@"A", NO), study(@"B", YES), study(@"C", NO), study(@"D", NO)];
        [browser convertReportToDICOMSR:nil];
        if (additions != 1) { printf("FAIL: %d additions for four studies, one expected\n", additions); failed++; }
        if (indexed != 3) { printf("FAIL: %d files indexed, the three that were written expected\n", indexed); failed++; }
        if (alerts != 1 || ![alerted.lastObject containsString:@"B"]) {
            printf("FAIL: the study whose report failed is not named: %d alerts, %s\n", alerts, alerted.description.UTF8String);
            failed++;
        }

        additions = indexed = alerts = 0;
        [alerted removeAllObjects];
        browser.selection = @[study(@"E", YES)];
        [browser convertReportToDICOMSR:nil];
        if (additions != 0 || indexed != 0) { printf("FAIL: %d additions with nothing written\n", additions); failed++; }
        if (alerts != 1) { printf("FAIL: nothing was said about the only report, which failed\n"); failed++; }

        if (failed) return 1;
        puts("ok");
    }
    return 0;
}
'''.replace('METHOD', method)

with tempfile.TemporaryDirectory(prefix='horos-pdf-batch-') as temporary:
    work = Path(temporary)
    (work / 'main.m').write_text(code)
    files = work / 'files'
    files.mkdir()
    built = subprocess.run(['xcrun', 'clang', '-fobjc-arc', '-Wno-objc-method-access', '-framework', 'Foundation',
                            str(work / 'main.m'), '-o', str(work / 'probe')], capture_output=True, text=True)
    if built.returncode != 0:
        print('FAIL: the method does not build: ' + built.stderr[-2000:])
        raise SystemExit(1)
    run = subprocess.run([str(work / 'probe'), str(files)], capture_output=True, text=True, timeout=60)
    if run.returncode != 0:
        print((run.stdout + run.stderr).strip() or f'FAIL: exit {run.returncode}')
        raise SystemExit(1)
print('DICOM PDF batch: one indexing of the files written, and the failed report named')
