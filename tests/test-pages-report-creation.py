#!/usr/bin/env python3
"""Exercise the production Pages creation method with controlled app launching."""
from pathlib import Path
import subprocess
import tempfile
root = Path(__file__).resolve().parent.parent
source = (root / 'Horos/Sources/Reports.m').read_bytes().decode('latin1')
start = source.index('- (BOOL)createNewPagesReportForStudy:')
method = source[start:source.index('\n+ (NSString*) pathForPagesTemplate:', start)]
program = r'''
#import <Foundation/Foundation.h>
#import "HorosReportFileReplacement.h"
#import "HorosReportFields.h"
#define NSManagedObject NSMutableDictionary
static NSString *model, *alert;
static BOOL installed, launchSuccess, legacyArchive, fillSucceeds;
static int launches, fills;
// Which kind of template this is, read out of the archive by the real one.
static BOOL HorosPagesArchiveHasIndexXML(NSData *data) { return legacyArchive; }
static NSInteger TestAlert(NSString *title, NSString *format, NSString *ok, id a, id b, NSString *message) { alert=message; return 0; }
#define NSRunCriticalAlertPanel TestAlert
@interface NSWorkspace : NSObject
+ (instancetype)sharedWorkspace;
- (BOOL)openFile:(NSString*)path withApplication:(NSString*)app andDeactivate:(BOOL)flag;
@end
@implementation NSWorkspace
+ (instancetype)sharedWorkspace { static NSWorkspace *w; if(!w) w=[self new]; return w; }
- (BOOL)openFile:(NSString*)path withApplication:(NSString*)app andDeactivate:(BOOL)flag { launches++; NSCAssert([app isEqual:@"/Applications/Pages.app"], @"resolved app"); return launchSuccess; }
@end
// Where Pages is, asked for as the production code asks for it: one lookup that
// tries both bundle identifiers and then the Pages document type.
@interface HorosPagesApplication : NSObject
+ (NSURL*)url;
@end
@implementation HorosPagesApplication
+ (NSURL*)url { return installed ? [NSURL fileURLWithPath:@"/Applications/Pages.app"] : nil; }
@end
// Pages filling in a template it alone can edit.
@interface HorosPagesDocumentFill : NSObject
+ (BOOL)fillDocumentAtPath:(NSString*)path substitute:(NSString *(^)(NSString *))substitute;
@end
@implementation HorosPagesDocumentFill
+ (BOOL)fillDocumentAtPath:(NSString*)path substitute:(NSString *(^)(NSString *))substitute {
    fills++;
    // The block is what fills a line in; exercise it so a broken one is caught.
    NSCAssert([substitute(@"name: \u00abname\u00bb") isEqual:@"name: Synthetic"], @"substitute");
    return fillSucceeds;
}
@end
@interface BrowserController : NSObject
+ (instancetype)currentBrowser;
- (NSArray*)childrenArray:(id)study;
- (NSArray*)imagesPathArray:(id)series;
@end
@implementation BrowserController
+ (instancetype)currentBrowser { static BrowserController *b; if(!b) b=[self new]; return b; }
- (NSArray*)childrenArray:(id)study { return @[]; }
- (NSArray*)imagesPathArray:(id)series { return @[]; }
@end
@interface Reports : NSObject { NSString *templateName; }
+ (NSString*)pathForPagesTemplate:(NSString*)name;
- (BOOL)decompressPagesFileIfNecessary:(NSString*)path;
- (void)searchAndReplaceFieldsFromStudy:(id)study inString:(NSMutableString*)xml;
- (NSDictionary*)reportFieldValuesForStudy:(id)study;
- (NSString*)getDICOMStringValueForField:(NSString*)field inDICOMFile:(NSString*)path;
- (BOOL)createNewPagesReportForStudy:(NSMutableDictionary*)study toDestinationPath:(NSString*)path;
@end
@implementation Reports
+ (NSString*)pathForPagesTemplate:(NSString*)name { return model; }
- (BOOL)decompressPagesFileIfNecessary:(NSString*)path { return YES; }
- (NSDictionary*)reportFieldValuesForStudy:(id)study { return @{@"name": @"Synthetic"}; }
- (NSString*)getDICOMStringValueForField:(NSString*)field inDICOMFile:(NSString*)path { return @""; }
- (void)searchAndReplaceFieldsFromStudy:(id)study inString:(NSMutableString*)xml { [xml replaceOccurrencesOfString:@"PATIENT" withString:@"Synthetic" options:0 range:NSMakeRange(0,xml.length)]; }
METHOD
@end
#define check(v) NSCAssert((v), @"failed: %s", #v)
int main(int argc,char **argv) { @autoreleasepool {
 NSString *dir=[NSString stringWithUTF8String:argv[1]];
 NSString *dest=[dir stringByAppendingPathComponent:@"report.pages"];
 NSData *old=[@"previous" dataUsingEncoding:NSUTF8StringEncoding];
 check([old writeToFile:dest atomically:YES]);
 NSMutableDictionary *study=[@{@"reportURL":@"old association"} mutableCopy];
 Reports *reports=[Reports new];
 check(![reports createNewPagesReportForStudy:study toDestinationPath:dest]);
 check([alert containsString:@"not installed"] && launches==0);
 installed=YES;
 check(![reports createNewPagesReportForStudy:study toDestinationPath:dest]);
 check([alert containsString:@"template could not be found"]);
 model=[dir stringByAppendingPathComponent:@"model.pages"];
 check([NSFileManager.defaultManager createDirectoryAtPath:model withIntermediateDirectories:YES attributes:nil error:NULL]);
 // A template with no index.xml is one Pages 5 or later wrote, and Pages fills
 // it in. When it cannot, what was there is preserved and the reason is said.
 check(![reports createNewPagesReportForStudy:study toDestinationPath:dest]);
 check(fills==1 && [alert containsString:@"allowed to control Pages"]);
 check([[NSData dataWithContentsOfFile:dest] isEqual:old]);
 check([study[@"reportURL"] isEqual:@"old association"] && launches==0);
 // And when Pages does fill it in, the report is published and opened.
 fillSucceeds=YES;
 check(![reports createNewPagesReportForStudy:study toDestinationPath:dest]);
 check(fills==2 && launches==1 && [alert containsString:@"could not open"]);
 check([study[@"reportURL"] isEqual:dest]);
 fillSucceeds=NO;
 launches=0;
 // A template that does carry index.xml is filled in here, and Pages is not
 // asked to do anything until the report is opened.
 NSString *index=[model stringByAppendingPathComponent:@"index.xml"];
 check([@"<text>PATIENT</text>" writeToFile:index atomically:YES encoding:NSUTF8StringEncoding error:NULL]);
 check(![reports createNewPagesReportForStudy:study toDestinationPath:dest]);
 check([alert containsString:@"could not open"] && launches==1 && fills==2);
 check([study[@"reportURL"] isEqual:dest]);
 check([[NSString stringWithContentsOfFile:[dest stringByAppendingPathComponent:@"index.xml"] encoding:NSUTF8StringEncoding error:NULL] isEqual:@"<text>Synthetic</text>"]);
 launchSuccess=YES;
 check([reports createNewPagesReportForStudy:study toDestinationPath:dest] && launches==2 && fills==2);
 check([[NSString stringWithContentsOfFile:index encoding:NSUTF8StringEncoding error:NULL] isEqual:@"<text>PATIENT</text>"]);
 NSLog(@"PASS: missing Pages and missing template preserve the existing report; a template Pages must fill is handed to Pages and its failure preserves what was there; a template with index.xml is filled in here and Pages is not asked to; the template is never modified");
} }
'''.replace('METHOD', method)
with tempfile.TemporaryDirectory(prefix='horos-pages-create-') as directory:
    p=Path(directory)
    (p/'test.m').write_text(program)
    subprocess.run(['xcrun','clang','-fno-objc-arc','-fblocks','-fsanitize=address','-framework','Foundation','-I',str(root/'Horos/Sources'),str(p/'test.m'),'-o',str(p/'test')],check=True)
    subprocess.run([str(p/'test'),str(p)],check=True)
