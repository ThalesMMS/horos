#!/usr/bin/env python3
"""Run production attachment transaction against Core Data and real files."""
from pathlib import Path
import subprocess
import tempfile
import xml.etree.ElementTree as ET
root=Path(__file__).resolve().parent.parent
source=(root/'Horos/Sources/BrowserController.m').read_bytes().decode('latin1')
start=source.index('- (BOOL) importReport:(NSString*) path UID:')
method=source[start:source.index('\n- (IBAction)attachExistingReport:',start)]
program=r'''
#import <CoreData/CoreData.h>
#import "HorosReportFileReplacement.h"
#define DicomStudy NSManagedObject
@interface TestContext : NSManagedObjectContext
@property BOOL failSave;
@end
@implementation TestContext
- (BOOL)save:(NSError**)error { if(self.failSave) { if(error) *error=[NSError errorWithDomain:@"Test" code:1 userInfo:nil]; return NO; } return [super save:error]; }
@end
@interface Database : NSObject
@property BOOL isLocal;
@property BOOL isReadOnly;
@property(retain) TestContext *managedObjectContext;
@property(retain) NSManagedObjectModel *managedObjectModel;
@property(copy) NSString *reportsDirPath;
@end
@implementation Database
@end
@interface Browser : NSObject
@property(retain) Database *database;
- (BOOL)importReport:(NSString*)path UID:(NSString*)uid error:(NSError**)error;
@end
@implementation Browser
METHOD
@end
#define check(v) NSCAssert((v), @"failed: %s", #v)
static NSManagedObject *add(TestContext *context, NSString *uid) {
 NSManagedObject *study=[NSEntityDescription insertNewObjectForEntityForName:@"Study" inManagedObjectContext:context];
 [study setValue:uid forKey:@"studyInstanceUID"]; return study;
}
int main(int argc,char **argv) { @autoreleasepool {
 NSString *dir=[NSString stringWithUTF8String:argv[1]];
 NSManagedObjectModel *model=[NSManagedObjectModel new];
 NSEntityDescription *entity=[NSEntityDescription new];entity.name=@"Study";entity.managedObjectClassName=@"NSManagedObject";
 NSMutableArray *properties=[NSMutableArray array];
 for(NSString *name in @[@"studyInstanceUID",@"reportURL",@"lockedStudy"]) {
  NSAttributeDescription *a=[NSAttributeDescription new];a.name=name;a.attributeType=[name isEqual:@"lockedStudy"] ? NSBooleanAttributeType : NSStringAttributeType;a.optional=YES;[properties addObject:a];
 }
 entity.properties=properties;model.entities=@[entity];
 NSPersistentStoreCoordinator *coordinator=[[NSPersistentStoreCoordinator alloc] initWithManagedObjectModel:model];
 check([coordinator addPersistentStoreWithType:NSInMemoryStoreType configuration:nil URL:nil options:nil error:NULL]);
 TestContext *context=[[TestContext alloc] initWithConcurrencyType:NSMainQueueConcurrencyType];context.persistentStoreCoordinator=coordinator;
 Database *db=[Database new];db.isLocal=YES;db.managedObjectContext=context;db.managedObjectModel=model;
 db.reportsDirPath=[dir stringByAppendingPathComponent:@"reports"];
 check([NSFileManager.defaultManager createDirectoryAtPath:db.reportsDirPath withIntermediateDirectories:YES attributes:nil error:NULL]);
 Browser *browser=[Browser new];browser.database=db;
 NSString *source=[dir stringByAppendingPathComponent:@"external.rtf"];
 NSData *bytes=[@"{\\rtf1 Synthetic attached report, no template text.}" dataUsingEncoding:NSUTF8StringEncoding];check([bytes writeToFile:source atomically:YES]);
 NSManagedObject *study=add(context,@"1.2.3"), *other=add(context,@"1.2.4");
 NSString *old=[db.reportsDirPath stringByAppendingPathComponent:@"old.rtf"];
 NSData *oldBytes=[@"old document" dataUsingEncoding:NSUTF8StringEncoding];check([oldBytes writeToFile:old atomically:YES]);[study setValue:old forKey:@"reportURL"];
 check([context save:NULL]);
 NSError *error=nil;
 check(![browser importReport:@"/missing/source" UID:@"1.2.3" error:&error]);check(error);
 check([[study valueForKey:@"reportURL"] isEqual:old]);check([[NSData dataWithContentsOfFile:old] isEqual:oldBytes]);
 context.failSave=YES;
 check(![browser importReport:source UID:@"1.2.3" error:&error]);
 check([[study valueForKey:@"reportURL"] isEqual:old]);check([[NSFileManager.defaultManager contentsOfDirectoryAtPath:db.reportsDirPath error:NULL] count]==1);
 context.failSave=NO;
 check([browser importReport:source UID:@"1.2.3" error:&error]);
 NSString *attached=[[study valueForKey:@"reportURL"] copy];check(![attached isEqual:source]);
 check([[NSData dataWithContentsOfFile:attached] isEqual:bytes]);check([[NSData dataWithContentsOfFile:source] isEqual:bytes]);check([[NSData dataWithContentsOfFile:old] isEqual:oldBytes]);check(![other valueForKey:@"reportURL"]);
 // Importing an already-owned file must not delete it or copy onto itself.
 check([browser importReport:attached UID:@"1.2.3" error:&error]);check([[NSData dataWithContentsOfFile:attached] isEqual:bytes]);
 NSString *latest=[study valueForKey:@"reportURL"];
 db.isReadOnly=YES;check(![browser importReport:source UID:@"1.2.3" error:&error]);db.isReadOnly=NO;
 db.isLocal=NO;check(![browser importReport:source UID:@"1.2.3" error:&error]);db.isLocal=YES;
 [study setValue:@YES forKey:@"lockedStudy"];check(![browser importReport:source UID:@"1.2.3" error:&error]);[study setValue:@NO forKey:@"lockedStudy"];
 check(![browser importReport:source UID:@"missing" error:&error]);
 add(context,@"1.2.3");check(![browser importReport:source UID:@"1.2.3" error:&error]);check([[study valueForKey:@"reportURL"] isEqual:latest]);
 NSLog(@"PASS: byte-preserving report attachment; correct study; copy/save failure rollback; old/source files retained; self-import; ambiguous/missing/locked/remote/read-only rejection");
} }
'''.replace('METHOD',method)
with tempfile.TemporaryDirectory(prefix='horos-report-attach-') as directory:
 p=Path(directory);(p/'test.m').write_text(program)
 subprocess.run(['xcrun','clang','-fblocks','-fsanitize=address','-framework','Foundation','-framework','CoreData','-I',str(root/'Horos/Sources'),str(p/'test.m'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test'),str(p)],check=True)
menus=list((root/'Horos/Resources').glob('*.lproj/MainMenu.xib'))
for menu in menus:
 tree=ET.parse(menu)
 report=tree.find('.//menu[@id="12354"]')
 if report is not None:
  actions=report.findall('.//action[@selector="attachExistingReport:"]')
  assert len(actions)==1 and actions[0].attrib['target']=='898',menu
print('PASS: report menus expose one attachment action in every localized main menu')
