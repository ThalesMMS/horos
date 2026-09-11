#!/usr/bin/env python3
"""Exercise the production study predicate against a temporary SQLite Core Data store."""
from pathlib import Path
import subprocess,tempfile
root=Path(__file__).resolve().parents[1]
s=(root/'Horos/Sources/BrowserController.m').read_bytes().decode('latin1')
a=s.index('- (NSPredicate *)createFilterPredicate');method=s[a:s.index('- (NSArray *) databaseSelection',a)]
code=r'''
#import <CoreData/CoreData.h>
#define check(c) NSCAssert((c), @"failed: %s",#c)
@interface BrowserFixture:NSObject { @public NSString *_searchString; int searchType; }
- (NSPredicate*)patientsnamePredicate:(NSString*)s;
- (NSPredicate*)createFilterPredicate;
@end
@implementation BrowserFixture
- (NSPredicate*)patientsnamePredicate:(NSString*)s{return [NSPredicate predicateWithValue:YES];}
METHOD
@end
static NSAttributeDescription *attribute(NSString *name) {NSAttributeDescription *a=[NSAttributeDescription new];a.name=name;a.attributeType=NSStringAttributeType;a.optional=YES;return a;}
int main(int argc,char **argv) {@autoreleasepool {
 NSEntityDescription *study=[NSEntityDescription new];study.name=@"Study";study.managedObjectClassName=@"NSManagedObject";
 NSEntityDescription *series=[NSEntityDescription new];series.name=@"Series";series.managedObjectClassName=@"NSManagedObject";
 NSRelationshipDescription *children=[NSRelationshipDescription new];children.name=@"series";children.destinationEntity=series;children.minCount=0;children.maxCount=0;children.optional=YES;
 NSRelationshipDescription *parent=[NSRelationshipDescription new];parent.name=@"study";parent.destinationEntity=study;parent.maxCount=1;parent.optional=YES;children.inverseRelationship=parent;parent.inverseRelationship=children;
 study.properties=@[attribute(@"uid"),children];series.properties=@[attribute(@"uid"),attribute(@"name"),parent];
 NSManagedObjectModel *model=[NSManagedObjectModel new];model.entities=@[study,series];
 NSPersistentStoreCoordinator *psc=[[NSPersistentStoreCoordinator alloc] initWithManagedObjectModel:model];NSError *error=nil;
 check([psc addPersistentStoreWithType:NSSQLiteStoreType configuration:nil URL:[NSURL fileURLWithPath:[NSString stringWithUTF8String:argv[1]]] options:nil error:&error]!=nil);
 NSManagedObjectContext *ctx=[[NSManagedObjectContext alloc] initWithConcurrencyType:NSMainQueueConcurrencyType];ctx.persistentStoreCoordinator=psc;
 NSMutableArray *original=[NSMutableArray array];
 for(int i=0;i<2;i++) {
  NSManagedObject *st=[NSEntityDescription insertNewObjectForEntityForName:@"Study" inManagedObjectContext:ctx];[st setValue:i?@"other":@"target" forKey:@"uid"];
  for(NSString *name in i?@[@"Unrelated"]:@[@"Localízador",@"T2 Axial",@"T1 Sagital"]) {
   NSManagedObject *se=[NSEntityDescription insertNewObjectForEntityForName:@"Series" inManagedObjectContext:ctx];[se setValue:name forKey:@"name"];[se setValue:name forKey:@"uid"];[se setValue:st forKey:@"study"];[original addObject:se];
  }
 }
 check([ctx save:&error]);NSArray *ids=[original valueForKey:@"objectID"];
 BrowserFixture *browser=[BrowserFixture new];browser->searchType=11;
 for(NSString *term in @[@"LOCALIZADOR",@"localíz",@"t2 axial",@"Sagital",@"absent",@"",@"' OR 1=1"]) {
  browser->_searchString=term;NSFetchRequest *request=[NSFetchRequest fetchRequestWithEntityName:@"Study"];request.predicate=[browser createFilterPredicate];
  NSArray *result=[ctx executeFetchRequest:request error:&error];check(result!=nil);
  NSUInteger expected=term.length==0?2:([term isEqual:@"absent"]||[term isEqual:@"' OR 1=1"]?0:1);check(result.count==expected);
  if(expected==1) {check([[result[0] valueForKey:@"uid"] isEqual:@"target"]);check([[result[0] valueForKey:@"series"] count]==3);}
  check(!ctx.hasChanges);check([[original valueForKey:@"objectID"] isEqual:ids]);
 }
 NSLog(@"PASS: case/diacritics, empty/missing/literal terms, complete study context, stable series identities and no mutations");
} }
'''.replace('METHOD',method)
with tempfile.TemporaryDirectory(prefix='horos-series-search-') as tmp:
 p=Path(tmp);(p/'test.m').write_text(code)
 subprocess.run(['xcrun','clang','-fobjc-arc','-framework','CoreData',str(p/'test.m'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test'),str(p/'test.sql')],check=True)
