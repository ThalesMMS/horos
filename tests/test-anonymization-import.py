#!/usr/bin/env python3
"""Exercise production anonymization import and transactions with disposable SQLite.
The parser/indexer and progress UI are fault-injection doubles; filesystem copies,
Core Data saves/rollbacks and the production orchestration are real.
"""
from pathlib import Path
import subprocess
import tempfile
root = Path(__file__).resolve().parents[1]
browser = (root/'Horos/Sources/BrowserController.m').read_text(encoding="utf-8", errors="replace")
method = browser[browser.index('- (BOOL)importAnonymizedFiles:'):browser.index('-(void)anonymizationSavePanelDidEnd:')]
context = (root/'Nitrogen/Sources/N2ManagedDatabase.mm').read_text(encoding="utf-8", errors="replace")
context = context[context.index('- (void)performAfterSuccessfulSave:'):context.index('-(NSManagedObject*)existingObjectWithID:')]
image_source = (root/'Horos/Sources/DicomImage.m').read_text(encoding="utf-8", errors="replace")
delete_method = image_source[image_source.index('- (BOOL)validateForDelete:'):image_source.index('- (NSSet *)paths')]
harness = r'''
#import <Cocoa/Cocoa.h>
#import <CoreData/CoreData.h>
#import "HorosAnonymizationSafety.h"
static NSString *mode, *folder;
static NSInteger copies, imports, polls, refreshes;
static BOOL rejectSave;
static void check(BOOL ok, NSString *why) { if (!ok) { NSLog(@"FAIL %@: %@",mode,why); exit(1); } }
@interface N2ManagedObjectContext : NSManagedObjectContext {
 NSMutableArray *_afterSuccessfulSaveActions, *_nextSuccessfulSaveActions, *_discardedChangesActions;
 BOOL _defersSaves, _atomicChangesCancelled;
}
- (BOOL)performAtomicChanges:(BOOL (^)(NSError **))changes error:(NSError **)error;
- (void)performAfterSuccessfulSave:(void (^)(void))action;
@end
@implementation N2ManagedObjectContext
CONTEXT
@end
@class DicomDatabase;
@interface BrowserController : NSObject
@property(retain) DicomDatabase *database;
+ (id)currentBrowser;
- (void)addFileToDeleteQueue:(NSString *)path;
- (void)outlineViewRefresh;
- (void)refreshAlbums;
@end
static BrowserController *currentBrowser;
@interface DicomStudy : NSManagedObject
@property(retain) NSNumber *lockedStudy, *numberOfImages;
@property(retain) NSSet *series;
@end
@implementation DicomStudy
@dynamic lockedStudy, numberOfImages, series;
@end
@interface DicomSeries : NSManagedObject
@property(retain) DicomStudy *study;
@property(retain) NSSet *images;
@property(retain) NSNumber *numberOfImages;
@property(retain) NSData *thumbnail;
@end
@implementation DicomSeries
@dynamic study, images, numberOfImages, thumbnail;
@end
@interface DicomImage : NSManagedObject
@property(retain) NSString *completePath;
@property(readonly) NSNumber *inDatabaseFolder;
@property(readonly) NSString *path;
@property(retain) DicomSeries *series;
@end
@implementation DicomImage
@dynamic completePath, series;
- (NSNumber *)inDatabaseFolder { return @YES; }
- (NSString *)path { return self.completePath; }
DELETE_METHOD
- (BOOL)validateForUpdate:(NSError **)error {
 if(rejectSave) { if(error)*error=[NSError errorWithDomain:@"InjectedSaveFailure" code:1 userInfo:nil];return NO; }
 return [super validateForUpdate:error];
}
- (BOOL)validateForInsert:(NSError **)error {
 if(rejectSave) { if(error)*error=[NSError errorWithDomain:@"InjectedSaveFailure" code:1 userInfo:nil];return NO; }
 return [super validateForInsert:error];
}
@end
@interface Wait : NSObject
- (id)initWithString:(NSString *)s;
- (id)progress;
- (void)setMaxValue:(double)n;
- (void)setCancel:(BOOL)b;
- (void)showWindow:(id)s;
- (BOOL)pollCancellation;
- (void)incrementBy:(double)n;
- (void)close;
@end
@implementation Wait
- (id)initWithString:(NSString *)s { return [super init]; }
- (id)progress { return self; }
- (void)setMaxValue:(double)n {} - (void)setCancel:(BOOL)b {} - (void)showWindow:(id)s {}
- (BOOL)pollCancellation { polls++; return [mode isEqual:@"cancel"] && imports>0; }
- (void)incrementBy:(double)n {} - (void)close {}
@end
@interface DicomFile : NSObject
@property(retain) NSDictionary *dicomElements;
- (id)init:(NSString *)p DICOMOnly:(BOOL)b;
@end
@implementation DicomFile
- (id)init:(NSString *)p DICOMOnly:(BOOL)b {
 if((self=[super init])) self.dicomElements=([mode isEqual:@"format"] && copies==2)?nil:@{@"numberOfFrames":@1,@"numberOfSeries":@1};
 return self;
}
@end
@interface ViewerController : NSObject
+ (NSArray *)getDisplayed2DViewers;
- (NSArray *)fileList;
- (NSWindow *)window;
@end
@implementation ViewerController
+ (NSArray *)getDisplayed2DViewers { return @[]; }
- (NSArray *)fileList { return @[]; } - (NSWindow *)window { return nil; }
@end
@interface DicomDatabase : NSObject
@property(retain) N2ManagedObjectContext *managedObjectContext;
@property BOOL isReadOnly;
- (BOOL)save:(NSError **)error;
- (NSString *)uniquePathForNewDataFileWithExtension:(NSString *)ext;
- (NSArray *)addFilesAtPaths:(NSArray *)paths postNotifications:(BOOL)a dicomOnly:(BOOL)b rereadExistingItems:(BOOL)c generatedByOsiriX:(BOOL)d importedFiles:(BOOL)e returnArray:(BOOL)f;
@end
@implementation DicomDatabase
- (BOOL)save:(NSError **)error { return [self.managedObjectContext save:error]; }
- (NSString *)uniquePathForNewDataFileWithExtension:(NSString *)ext {
 copies++;
 if([mode isEqual:@"copy"] && copies==2) return [folder stringByAppendingPathComponent:@"missing/destination"];
 return [folder stringByAppendingPathComponent:[NSString stringWithFormat:@"copy-%ld.dcm",(long)copies]];
}
- (NSArray *)addFilesAtPaths:(NSArray *)paths postNotifications:(BOOL)a dicomOnly:(BOOL)b rereadExistingItems:(BOOL)c generatedByOsiriX:(BOOL)d importedFiles:(BOOL)e returnArray:(BOOL)f {
 imports++;
 NSMutableArray *objects=[NSMutableArray array];
 DicomSeries *series=[NSEntityDescription insertNewObjectForEntityForName:@"Series" inManagedObjectContext:self.managedObjectContext];
 DicomStudy *study=[NSEntityDescription insertNewObjectForEntityForName:@"Study" inManagedObjectContext:self.managedObjectContext];
 series.study=study;
 for(NSString *path in paths) {
  DicomImage *im;
  if([mode isEqual:@"duplicate-uid"]) {
   NSFetchRequest *request=[NSFetchRequest fetchRequestWithEntityName:@"Image"];
   request.sortDescriptors=@[[NSSortDescriptor sortDescriptorWithKey:@"completePath" ascending:YES]];
   im=[[self.managedObjectContext executeFetchRequest:request error:NULL] firstObject];
  } else im=[NSEntityDescription insertNewObjectForEntityForName:@"Image" inManagedObjectContext:self.managedObjectContext];
  im.completePath=path; im.series=series; [objects addObject:im];
  if([mode isEqual:@"partial"]) break;
 }
 check([self.managedObjectContext obtainPermanentIDsForObjects:objects error:NULL],@"permanent IDs");
 check([self.managedObjectContext save:NULL],@"nested save is deferred");
 if([mode isEqual:@"exception"]) [NSException raise:@"InjectedImport" format:@"failure after nested save"];
 if([mode isEqual:@"import"] || ([mode isEqual:@"late-import"] && imports==2)) return nil;
 return [objects valueForKey:@"objectID"];
}
@end
@implementation BrowserController
+ (id)currentBrowser { return currentBrowser; }
- (void)addFileToDeleteQueue:(NSString *)path { [NSFileManager.defaultManager removeItemAtPath:path error:NULL]; }
- (void)outlineViewRefresh { refreshes++; } - (void)refreshAlbums {}
METHOD
@end
static NSAttributeDescription *attr(NSString *name, NSAttributeType type) {
 NSAttributeDescription *a=[NSAttributeDescription new]; a.name=name;a.attributeType=type;a.optional=YES;return a;
}
static void fixtureRelation(NSEntityDescription *parent, NSString *many, NSEntityDescription *child, NSString *one) {
 NSRelationshipDescription *a=[NSRelationshipDescription new], *b=[NSRelationshipDescription new];
 a.name=many; a.destinationEntity=child;a.maxCount=0;a.optional=YES;a.deleteRule=NSCascadeDeleteRule;
 b.name=one;b.destinationEntity=parent;b.maxCount=1;b.optional=YES;b.deleteRule=NSNullifyDeleteRule;
 a.inverseRelationship=b;b.inverseRelationship=a;
 parent.properties=[parent.properties arrayByAddingObject:a];child.properties=[child.properties arrayByAddingObject:b];
}
int main(int argc,char **argv) { @autoreleasepool {
 mode=[NSString stringWithUTF8String:argv[1]];folder=[NSString stringWithUTF8String:argv[2]];
 NSManagedObjectModel *model=[NSManagedObjectModel new];
 NSEntityDescription *study=[NSEntityDescription new], *series=[NSEntityDescription new], *image=[NSEntityDescription new];
 study.name=@"Study";study.managedObjectClassName=@"DicomStudy";study.properties=@[attr(@"lockedStudy",NSBooleanAttributeType),attr(@"numberOfImages",NSInteger64AttributeType)];
 series.name=@"Series";series.managedObjectClassName=@"DicomSeries";series.properties=@[attr(@"numberOfImages",NSInteger64AttributeType),attr(@"thumbnail",NSBinaryDataAttributeType)];
 image.name=@"Image";image.managedObjectClassName=@"DicomImage";image.properties=@[attr(@"completePath",NSStringAttributeType)];
 fixtureRelation(study,@"series",series,@"study");fixtureRelation(series,@"images",image,@"series");model.entities=@[study,series,image];
 NSPersistentStoreCoordinator *psc=[[NSPersistentStoreCoordinator alloc] initWithManagedObjectModel:model];
 check([psc addPersistentStoreWithType:NSSQLiteStoreType configuration:nil URL:[NSURL fileURLWithPath:[folder stringByAppendingPathComponent:@"index.sqlite"]] options:nil error:NULL]!=nil,@"SQLite store");
 N2ManagedObjectContext *ctx=[[N2ManagedObjectContext alloc] initWithConcurrencyType:NSConfinementConcurrencyType];ctx.persistentStoreCoordinator=psc;
 DicomDatabase *db=[DicomDatabase new];db.managedObjectContext=ctx;
 BrowserController *browser=[BrowserController new];browser.database=db;currentBrowser=browser;
 DicomStudy *st=[NSEntityDescription insertNewObjectForEntityForName:@"Study" inManagedObjectContext:ctx];
 st.lockedStudy=@([mode isEqual:@"locked"]);
 DicomSeries *se=[NSEntityDescription insertNewObjectForEntityForName:@"Series" inManagedObjectContext:ctx];se.study=st;
 NSMutableDictionary *files=[NSMutableDictionary dictionary];NSMutableArray *originals=[NSMutableArray array];
 int count=[mode hasPrefix:@"late-"]?35:3;
 for(int i=0;i<count;i++) {
  NSString *src=[folder stringByAppendingPathComponent:[NSString stringWithFormat:@"original-%d.dcm",i]];
  NSString *out=[folder stringByAppendingPathComponent:[NSString stringWithFormat:@"output-%d.dcm",i]];
  check([@"original bytes" writeToFile:src atomically:YES encoding:NSUTF8StringEncoding error:NULL],@"original file");
  check([@"anonymized bytes" writeToFile:out atomically:YES encoding:NSUTF8StringEncoding error:NULL],@"output file");
  files[src]=out;
  DicomImage *im=[NSEntityDescription insertNewObjectForEntityForName:@"Image" inManagedObjectContext:ctx];im.completePath=src;im.series=se;[originals addObject:im];
 }
 check([ctx save:NULL],@"initial save");
 if([mode isEqual:@"empty"]) [@"" writeToFile:files.allValues[0] atomically:YES encoding:NSUTF8StringEncoding error:NULL];
 if([mode isEqual:@"missing"]) [NSFileManager.defaultManager removeItemAtPath:files.allValues[0] error:NULL];
 db.isReadOnly=[mode isEqual:@"readonly"];rejectSave=[mode isEqual:@"save"];
 NSError *error=nil;
 BOOL add=[mode isEqual:@"add"], success=[mode isEqual:@"success"]||add;
 BOOL result=[browser importAnonymizedFiles:files originalImages:originals replace:!add error:&error];
 check(result==success,@"operation result");
 if(!success) {
  NSArray *rows=error.userInfo[@"HorosAnonymizationFileResults"];
  check(rows.count==files.count,@"all requested sources have import results");
  check([[NSSet setWithArray:[rows valueForKey:@"source"]] isEqual:[NSSet setWithArray:files.allKeys]],@"import report original paths");
  if([mode isEqual:@"partial"]||[mode isEqual:@"duplicate-uid"])
   check([[rows filteredArrayUsingPredicate:[NSPredicate predicateWithFormat:@"outcome == 'failed'"]] count]>0,@"incomplete per-file record counts reported");
 }
 NSManagedObjectContext *reader=[[NSManagedObjectContext alloc] initWithConcurrencyType:NSConfinementConcurrencyType];reader.persistentStoreCoordinator=psc;
 NSArray *persisted=[reader executeFetchRequest:[NSFetchRequest fetchRequestWithEntityName:@"Image"] error:NULL];
 check(persisted.count==(add?2*count:count),@"durable image count");
 for(NSManagedObject *im in persisted) {
  NSString *p=[im valueForKey:@"completePath"];
  check([NSFileManager.defaultManager fileExistsAtPath:p],@"persisted image has file");
 }
 for(NSString *p in files) {
  if(success&&!add) check(![NSFileManager.defaultManager fileExistsAtPath:p],@"original retired after commit");
  else check([[NSString stringWithContentsOfFile:p encoding:NSUTF8StringEncoding error:NULL] isEqual:@"original bytes"],@"original bytes preserved");
 }
 for(NSString *name in [NSFileManager.defaultManager contentsOfDirectoryAtPath:folder error:NULL])
  if([name hasPrefix:@"copy-"]) check(success,@"failed import staging cleaned");
 check(!ctx.hasChanges,@"context clean after commit or rollback");check(refreshes==(success?1:0),@"refresh only after commit");
 NSLog(@"PASS %@: durable records and original bytes verified",mode);
} }
'''.replace('CONTEXT', context).replace('DELETE_METHOD', delete_method).replace('METHOD', method)
with tempfile.TemporaryDirectory(prefix='horos-anonymization-') as tmp:
    path=Path(tmp)
    (path/'test.mm').write_text(harness)
    subprocess.run(['xcrun','clang','-x','objective-c','-DNDEBUG','-DOSIRIX_VIEWER','-fblocks','-fobjc-exceptions','-Wno-deprecated-declarations','-I'+str(root/'Horos/Sources'),'-framework','Cocoa','-framework','CoreData',str(path/'test.mm'),'-o',str(path/'test')],check=True)
    for mode in ['empty','missing','readonly','locked','copy','format','partial','duplicate-uid','import','exception','late-import','cancel','save','success','add']:
        folder=path/mode;folder.mkdir()
        subprocess.run([str(path/'test'),mode,str(folder)],check=True)
