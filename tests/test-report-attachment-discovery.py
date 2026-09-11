#!/usr/bin/env python3
from pathlib import Path
import subprocess
import tempfile
root=Path(__file__).resolve().parent.parent
source=(root/'Horos/Sources/DicomDatabase.mm').read_bytes().decode('latin1')
start=source.index('-(void)checkForExistingReportForStudy:')
method=source[start:source.index('\n-(BOOL)allowAutorouting',start)]
program=r'''
#import <Foundation/Foundation.h>
#define N2LogExceptionWithStackTrace(e) abort()
@interface DicomStudy : NSObject
@property(copy) NSString *reportURL;
@end
@implementation DicomStudy
@end
@interface Reports : NSObject
+ (NSString*)getUniqueFilename:(id)study;
+ (NSString*)getOldUniqueFilename:(id)study;
@end
@implementation Reports
+ (NSString*)getUniqueFilename:(id)study { return @"legacy"; }
+ (NSString*)getOldUniqueFilename:(id)study { return @"older"; }
@end
@interface Database : NSObject
@property(copy) NSString *reportsDirPath;
@end
@implementation Database
METHOD
@end
#define check(v) NSCAssert((v),@"failed: %s",#v)
int main(int argc,char **argv) { @autoreleasepool {
 Database *db=[Database new];db.reportsDirPath=[NSString stringWithUTF8String:argv[1]];
 NSString *legacy=[db.reportsDirPath stringByAppendingPathComponent:@"legacy.rtf"];
 NSString *attached=[db.reportsDirPath stringByAppendingPathComponent:@"Attached-QA.rtf"];
 check([@"legacy template" writeToFile:legacy atomically:YES encoding:NSUTF8StringEncoding error:NULL]);
 check([@"imported report" writeToFile:attached atomically:YES encoding:NSUTF8StringEncoding error:NULL]);
 DicomStudy *study=[DicomStudy new];study.reportURL=attached;
 [db checkForExistingReportForStudy:study];check([study.reportURL isEqual:attached]);
 study.reportURL=@"https://example.invalid/report";[db checkForExistingReportForStudy:study];check([study.reportURL hasPrefix:@"https://"]);
 study.reportURL=@"/missing/report";[db checkForExistingReportForStudy:study];check([study.reportURL isEqual:legacy]);
 study.reportURL=nil;[db checkForExistingReportForStudy:study];check([study.reportURL isEqual:legacy]);
 NSLog(@"PASS: database report discovery preserves explicit local/remote association and still recovers missing legacy reports");
} }
'''.replace('METHOD',method)
with tempfile.TemporaryDirectory(prefix='horos-report-discovery-') as directory:
 p=Path(directory);(p/'test.m').write_text(program)
 subprocess.run(['xcrun','clang','-fobjc-arc','-fsanitize=address','-framework','Foundation',str(p/'test.m'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test'),str(p)],check=True)
