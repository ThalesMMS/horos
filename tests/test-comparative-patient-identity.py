#!/usr/bin/env python3
"""Exercise the production local-comparative predicate with Core Data stores."""
from pathlib import Path
import re
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
source = (root / 'Horos/Sources/BrowserController.m').read_bytes().decode('latin1')
start = source.index('- (NSArray*) subSearchForComparativeStudies:')
match = re.search(r'predicate: \[NSPredicate predicateWithFormat: (@"[^"]+"), studySelected.patientUID\]', source[start:])
assert match, 'production local-comparative predicate not found'
code = r'''
#import <Foundation/Foundation.h>
#import <CoreData/CoreData.h>
#define check(c) NSCAssert((c), @"failed: %s", #c)
int main(int argc, const char **argv) { @autoreleasepool {
 for (NSString *type in @[NSInMemoryStoreType, NSSQLiteStoreType]) {
  NSEntityDescription *entity=[NSEntityDescription new]; entity.name=@"Study"; entity.managedObjectClassName=@"NSManagedObject";
  NSAttributeDescription *uid=[NSAttributeDescription new]; uid.name=@"patientUID"; uid.attributeType=NSStringAttributeType; uid.optional=YES;
  entity.properties=@[uid];
  NSManagedObjectModel *model=[NSManagedObjectModel new]; model.entities=@[entity];
  NSPersistentStoreCoordinator *coordinator=[[NSPersistentStoreCoordinator alloc] initWithManagedObjectModel:model];
  NSURL *url=[type isEqualToString:NSSQLiteStoreType] ? [NSURL fileURLWithPath:[NSString stringWithUTF8String:argv[1]]] : nil;
  NSError *error=nil;
  check([coordinator addPersistentStoreWithType:type configuration:nil URL:url options:nil error:&error]!=nil);
  NSManagedObjectContext *context=[[NSManagedObjectContext alloc] initWithConcurrencyType:NSMainQueueConcurrencyType];context.persistentStoreCoordinator=coordinator;
  // Composite patient UID format is NAME-ID-BIRTHDATE. Birthdate is empty when disabled.
  for (id value in @[@"QA-A-", @"qa-a-", @"QA-A-B-", @"QA-A-C-", @"OTHER-A-", @"QA-AB-", @"JOSE-X-", @"José-X-", @"JOSE-X-Y-", @"QA-A*?-", @"QA-AXY-", [NSNull null]]) {
   NSManagedObject *study=[NSEntityDescription insertNewObjectForEntityForName:@"Study" inManagedObjectContext:context];
   if(value != [NSNull null]) [study setValue:value forKey:@"patientUID"];
  }
  check([context save:&error]);
  for(NSString *patient in @[@"QA-A-", @"JOSE-X-", @"QA-A*?-", @"NOT-PRESENT-"]) {
   NSFetchRequest *request=[NSFetchRequest fetchRequestWithEntityName:@"Study"];
   request.predicate=[NSPredicate predicateWithFormat:PRODUCTION_PREDICATE, patient];
   NSArray *result=[context executeFetchRequest:request error:&error]; check(result!=nil);
   NSUInteger expected=[patient isEqualToString:@"NOT-PRESENT-"] ? 0 : ([patient isEqualToString:@"QA-A*?-"] ? 1 : 2);
   check(result.count==expected);
   for(NSManagedObject *study in result)
    check([[study valueForKey:@"patientUID"] compare:patient options:NSCaseInsensitiveSearch|NSDiacriticInsensitiveSearch]==NSOrderedSame);
  }
 }
 NSLog(@"PASS: exact comparative identity; hyphen-prefix collisions excluded; case/diacritic matching, literal wildcards, missing values; memory and SQLite stores");
} }
'''.replace('PRODUCTION_PREDICATE', match.group(1))
with tempfile.TemporaryDirectory(prefix='horos-comparative-patient-') as tmp:
    tmp = Path(tmp)
    (tmp / 'test.m').write_text(code)
    subprocess.run(['xcrun', 'clang', '-fobjc-arc', '-framework', 'Foundation', '-framework', 'CoreData', str(tmp/'test.m'), '-o', str(tmp/'test')], check=True)
    subprocess.run([str(tmp/'test'), str(tmp/'studies.sqlite')], check=True)
