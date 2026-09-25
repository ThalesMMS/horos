#!/usr/bin/env python3
"""Drawing a row of the database list neither writes to the database nor reads the disk.

Scrolling the list asks every visible cell for its value at every redraw, and
several columns answered with far more work than showing a value needs:

- the report date called -[DicomStudy reportImage], which merges duplicate
  report series, deletes objects and saves the context before sorting images;
- the report icon checked the file on disk, and cleared `reportURL` on the
  study, from inside -willDisplayCell:;
- the age ran one or two calendar computations per row;
- the number of series sorted the series of the study to count them;
- the bold font searched an array for every row;
- the origin of a federated row canonicalised two paths for every row.

The age cache and the report date are compiled from the sources and run here
against direct computation and against the #645 rule (the latest report); the
rest is checked in source.
"""
from pathlib import Path
import re
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
failures = []
study = (root / 'Horos/Sources/DicomStudy.m').read_bytes().decode('latin1')
browser = (root / 'Horos/Sources/BrowserController.m').read_bytes().decode('latin1')


def between(text, start, end):
    a = text.find(start)
    if a < 0:
        return None
    b = text.find(end, a + len(start))
    return text[a:b] if b >= 0 else None


def compile_and_run(name, code):
    with tempfile.TemporaryDirectory(prefix='horos-row-drawing-') as folder:
        source = Path(folder) / (name + '.m')
        binary = Path(folder) / name
        source.write_text(code, encoding='latin1')
        built = subprocess.run(['xcrun', 'clang', '-fno-objc-arc', '-Wno-deprecated-declarations',
                                '-framework', 'Foundation', str(source), '-o', str(binary)],
                               capture_output=True, text=True)
        if built.returncode != 0:
            failures.append('%s does not compile:\n%s' % (name, built.stderr[-2000:]))
            return None
        run = subprocess.run([str(binary)], capture_output=True, text=True)
        if run.returncode != 0:
            failures.append('%s failed:\n%s%s' % (name, run.stdout[-1500:], run.stderr[-1500:]))
            return None
        return run.stdout


# --- the age ------------------------------------------------------------------
ages = between(study, 'static NSCache *DicomStudyAgeCache(void)', '\n- (NSString*) yearOld\n')
if ages is None:
    failures.append('the age cache is gone from DicomStudy.m')
else:
    AGE = r'''
#import <Foundation/Foundation.h>
#import <objc/runtime.h>
#define check(c) do { if (!(c)) { printf("FAIL: %s (line %d)\n", #c, __LINE__); return 1; } } while (0)
@interface DicomStudy : NSObject
@property (retain) NSDate *date, *dateOfBirth;
+ (NSString*) yearOldAcquisition:(NSDate*) acquisitionDate FromDateOfBirth: (NSDate*) dateOfBirth;
+ (NSString*) computeYearOldAcquisition:(NSDate*) acquisitionDate FromDateOfBirth: (NSDate*) dateOfBirth;
+ (NSString*) yearOldFromDateOfBirth: (NSDate*) dateOfBirth;
+ (NSString*) computeYearOldFromDateOfBirth: (NSDate*) dateOfBirth;
@end
@implementation DicomStudy
AGES
@end
static int computed;
@implementation DicomStudy (Counted)
+ (NSString*) countedAcquisition:(NSDate*) a FromDateOfBirth: (NSDate*) b { computed++; return [self countedAcquisition: a FromDateOfBirth: b]; }
+ (NSString*) countedToday: (NSDate*) b { computed++; return [self countedToday: b]; }
@end
static void count(SEL original, SEL counted) {
    Class meta = object_getClass([DicomStudy class]);
    method_exchangeImplementations(class_getClassMethod(meta, original), class_getClassMethod(meta, counted));
}
int main(void) { @autoreleasepool {
    count(@selector(computeYearOldAcquisition:FromDateOfBirth:), @selector(countedAcquisition:FromDateOfBirth:));
    count(@selector(computeYearOldFromDateOfBirth:), @selector(countedToday:));
    NSDate *now = [NSDate date];
    NSMutableArray *births = [NSMutableArray array];
    // Newborns in days, months, the second year, adults, and a birth after the study.
    for (NSNumber *days in @[@0, @1, @6, @29, @31, @45, @200, @364, @366, @400, @700, @731, @4000, @20000, @-3])
        [births addObject: [now dateByAddingTimeInterval: -86400. * days.doubleValue]];
    [births addObject: [NSDate dateWithTimeIntervalSinceReferenceDate: -30. * 365.25 * 86400. + 43200.]];
    for (NSString *zone in @[@"America/Sao_Paulo", @"UTC", @"Asia/Tokyo"]) {
        [NSTimeZone setDefaultTimeZone: [NSTimeZone timeZoneWithName: zone]];
        for (NSDate *birth in births) {
            double minute = floor([NSDate timeIntervalSinceReferenceDate] / 60.);
            NSString *today = [DicomStudy yearOldFromDateOfBirth: birth];
            int before = computed;
            // Asked again, it is the kept answer, not a new computation - unless
            // the minute turned in between, which is when it is asked anew.
            check([[DicomStudy yearOldFromDateOfBirth: birth] isEqualToString: today]);
            check(computed == before || floor([NSDate timeIntervalSinceReferenceDate] / 60.) != minute);
            check([today isEqualToString: [DicomStudy computeYearOldFromDateOfBirth: birth]]);
            for (NSNumber *after in @[@0, @3, @40, @400, @9000]) {
                NSDate *acquired = [birth dateByAddingTimeInterval: 86400. * after.doubleValue + 3600.];
                NSString *age = [DicomStudy yearOldAcquisition: acquired FromDateOfBirth: birth];
                before = computed;
                check([[DicomStudy yearOldAcquisition: acquired FromDateOfBirth: birth] isEqualToString: age]);
                check(computed == before);
                check([age isEqualToString: [DicomStudy computeYearOldAcquisition: acquired FromDateOfBirth: birth]]);
            }
        }
    }
    // The time zone is part of the key: the same dates asked in another zone
    // are computed again, and agree with direct computation there.
    NSDate *birth = [NSDate dateWithTimeIntervalSinceReferenceDate: 3600.];
    NSDate *acquired = [birth dateByAddingTimeInterval: 29. * 86400. + 1800.];
    [NSTimeZone setDefaultTimeZone: [NSTimeZone timeZoneWithName: @"UTC"]];
    [DicomStudy yearOldAcquisition: acquired FromDateOfBirth: birth];
    int before = computed;
    [NSTimeZone setDefaultTimeZone: [NSTimeZone timeZoneWithName: @"America/Sao_Paulo"]];
    NSString *local = [DicomStudy yearOldAcquisition: acquired FromDateOfBirth: birth];
    check(computed == before + 1);
    check([local isEqualToString: [DicomStudy computeYearOldAcquisition: acquired FromDateOfBirth: birth]]);
    check([[DicomStudy yearOldAcquisition: nil FromDateOfBirth: birth] isEqualToString: @""]);
    check([[DicomStudy yearOldAcquisition: acquired FromDateOfBirth: nil] isEqualToString: @""]);
    check([[DicomStudy yearOldFromDateOfBirth: nil] isEqualToString: @""]);
    printf("ages ok\n");
    return 0;
}}
'''.replace('AGES', ages)
    compile_and_run('ages', AGE)

# --- the report date ----------------------------------------------------------
report = between(browser, 'if( [[tableColumn identifier] isEqualToString:@"reportURL"])',
                 '\n    if( [[tableColumn identifier] isEqualToString:@"stateText"])')
if report is None:
    failures.append('the report date column is gone from BrowserController.m')
else:
    REPORT = r'''
#import <Foundation/Foundation.h>
#define DicomSeries NSDictionary
#define DicomImage NSDictionary
#define DicomStudy NSDictionary
#define check(c) do { if (!(c)) { printf("FAIL: %s (line %d)\n", #c, __LINE__); return 1; } } while (0)
@interface DCMAbstractSyntaxUID : NSObject
+ (BOOL) isStructuredReport: (NSString*) uid;
@end
@implementation DCMAbstractSyntaxUID
+ (BOOL) isStructuredReport: (NSString*) uid { return [uid hasPrefix: @"1.2.840.10008.5.1.4.1.1.88."]; }
@end
@interface Column : NSObject
@property (copy) NSString *identifier;
@end
@implementation Column
@end
static id value(id item) {
    Column *tableColumn = [[Column new] autorelease];
    tableColumn.identifier = @"reportURL";
    REPORT
    return @"not answered";
}
static NSDate *at(double seconds) { return [NSDate dateWithTimeIntervalSinceReferenceDate: seconds]; }
static NSDictionary *image(NSDate *date) { return date ? @{@"date": date} : @{}; }
static NSDictionary *series(int number, NSString *name, NSString *sop, NSArray *images) {
    return @{@"id": @(number), @"name": name, @"seriesSOPClassUID": sop, @"images": [NSSet setWithArray: images]};
}
int main(void) { @autoreleasepool {
    NSString *sr = @"1.2.840.10008.5.1.4.1.1.88.33", *ct = @"1.2.840.10008.5.1.4.1.1.2";
    // Two report series, as a crash or a second machine leaves them: the latest image of either.
    NSDictionary *twoReports = @{@"type": @"Study", @"reportURL": @"/r.docx", @"series": [NSSet setWithArray: @[
        series(5003, @"OsiriX Report SR", sr, @[image(at(100)), image(at(300))]),
        series(5003, @"OsiriX Report SR", sr, @[image(at(200)), image(nil)]),
        series(5003, @"OsiriX ROI SR", sr, @[image(at(900))]),
        series(1, @"OsiriX Report SR", sr, @[image(at(800))]),
        series(5003, @"OsiriX Report SR", ct, @[image(at(700))]),
        series(2, @"Axial", ct, @[image(at(1000))])]]};
    check([value(twoReports) isEqual: at(300)]);
    NSDictionary *undated = @{@"type": @"Study", @"reportURL": @"/r.docx", @"series": [NSSet setWithArray: @[
        series(5003, @"OsiriX Report SR", sr, @[image(nil)])]]};
    check(value(undated) == nil);
    NSDictionary *noReport = @{@"type": @"Study", @"series": [NSSet setWithArray: @[
        series(5003, @"OsiriX Report SR", sr, @[image(at(5))])]]};
    check(value(noReport) == nil);
    NSDictionary *aSeries = @{@"type": @"Series", @"reportURL": @"/r.docx"};
    check(value(aSeries) == nil);
    printf("report ok\n");
    return 0;
}}
'''.replace('REPORT', report)
    compile_and_run('report', REPORT)

# --- what drawing a row may do ------------------------------------------------
value_method = between(browser, '- (id)intOutlineView:(NSOutlineView *)outlineView objectValueForTableColumn:',
                       '\n- (')
display_method = between(browser, '- (void)outlineView: (NSOutlineView *)outlineView willDisplayCell:', '\n- (')
for name, body in (('the value of a cell', value_method), ('the display of a cell', display_method)):
    if body is None:
        failures.append('%s: the method is gone' % name)
        continue
    for forbidden, why in (('reportImage', 'merges report series and saves'),
                           ('fileExistsAtPath', 'reads the disk'),
                           ('setValue: nil forKey: @"reportURL"', 'edits the study'),
                           ('save:', 'saves the database'),
                           ('originalOutlineViewArray containsObject', 'searches an array for every row')):
        if forbidden in body:
            failures.append('%s %s (%s)' % (name, why, forbidden))
if value_method and 'numberOfImageSeries' not in value_method:
    failures.append('the number of series is not counted without sorting')
if value_method and 'origin != _database' not in value_method:
    failures.append('the origin of every row is compared by canonical path')
if display_method and 'originalOutlineViewStudies containsObject' not in display_method:
    failures.append('the bold font no longer asks the set of original studies')

# The set follows the array: nothing assigns the array except the one method
# that rebuilds both.
if browser.count('originalOutlineViewArray = ') != 1 or browser.count('originalOutlineViewStudies = ') != 1:
    failures.append('originalOutlineViewArray can be assigned without rebuilding its set')

# The unsorted count is the sorted one's predicate.
count = between(study, '- (NSUInteger)numberOfImageSeries', '\n}\n')
if count is None or 'displaySeriesWithSOPClassUID:series.seriesSOPClassUID andSeriesDescription:series.name]' not in count:
    failures.append('numberOfImageSeries does not count what imageSeries lists')
if 'return [self imageSeriesContainingPixels: NO];' not in study or \
        'return [self displaySeriesWithSOPClassUID: uid andSeriesDescription: description containingOnlyPixels: NO];' not in study:
    failures.append('imageSeries no longer lists what numberOfImageSeries counts')

for failure in failures:
    print('FAIL: %s' % failure)
if failures:
    sys.exit(1)
print('ok: drawing a row of the database list neither saves, edits nor reads the disk; the age '
      'is kept per input, time zone and minute, and the report date is the latest report')
