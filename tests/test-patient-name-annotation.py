#!/usr/bin/env python3
"""Run the actual PatientName presentation branch on Core Data image/series/study objects."""
from pathlib import Path
import subprocess,tempfile,re
root=Path(__file__).resolve().parents[1]
s=(root/'Horos/Sources/DCMView.m').read_bytes().decode('latin1')
a=s.index('else if( [[annot objectAtIndex:j] isEqualToString: @"PatientName"])')
b=s.index('else if( fullText)',a)
branch=s[a:b]
header=(root/'Horos/Sources/DCMView.h').read_bytes().decode('latin1')
annotation_enum=re.search(r'enum \{ annotNone = 0, annotGraphics, annotBase, annotFull \};',header).group(0)
code=r'''
#import <Foundation/Foundation.h>
#import <CoreData/CoreData.h>
#define check(...) NSCAssert((__VA_ARGS__),@"failed: %s",#__VA_ARGS__)
ANNOTATION_ENUM
static NSString *render(NSArray *dcmFilesList,NSInteger curImage,NSInteger annotationType) {
 NSArray *annot=@[@"PatientName"];NSInteger j=0;
 NSMutableString *tempString=[NSMutableString string];
 if(NO) {}
BRANCH
 return tempString;
}
int main(void) { @autoreleasepool {
 NSEntityDescription *study=[NSEntityDescription new];study.name=@"Study";study.managedObjectClassName=@"NSManagedObject";
 NSAttributeDescription *name=[NSAttributeDescription new];name.name=@"name";name.attributeType=NSStringAttributeType;name.optional=YES;study.properties=@[name];
 NSEntityDescription *series=[NSEntityDescription new];series.name=@"Series";series.managedObjectClassName=@"NSManagedObject";
 NSRelationshipDescription *sr=[NSRelationshipDescription new];sr.name=@"study";sr.destinationEntity=study;sr.maxCount=1;sr.optional=YES;series.properties=@[sr];
 NSEntityDescription *image=[NSEntityDescription new];image.name=@"Image";image.managedObjectClassName=@"NSManagedObject";
 NSRelationshipDescription *ir=[NSRelationshipDescription new];ir.name=@"series";ir.destinationEntity=series;ir.maxCount=1;ir.optional=YES;image.properties=@[ir];
 NSManagedObjectModel *model=[NSManagedObjectModel new];model.entities=@[study,series,image];
 NSPersistentStoreCoordinator *coordinator=[[NSPersistentStoreCoordinator alloc] initWithManagedObjectModel:model];
 check([coordinator addPersistentStoreWithType:NSInMemoryStoreType configuration:nil URL:nil options:nil error:nil]);
 NSManagedObjectContext *context=[[NSManagedObjectContext alloc] initWithConcurrencyType:NSMainQueueConcurrencyType];context.persistentStoreCoordinator=coordinator;
 NSMutableArray *files=[NSMutableArray array];
 for(id value in @[@"QA Alice",@"QA Béatrice",[NSNull null],@""]) {
  NSManagedObject *s=[NSEntityDescription insertNewObjectForEntityForName:@"Study" inManagedObjectContext:context];
  if(value!=[NSNull null])[s setValue:value forKey:@"name"];
  NSManagedObject *se=[NSEntityDescription insertNewObjectForEntityForName:@"Series" inManagedObjectContext:context];[se setValue:s forKey:@"study"];
  NSManagedObject *im=[NSEntityDescription insertNewObjectForEntityForName:@"Image" inManagedObjectContext:context];[im setValue:se forKey:@"series"];[files addObject:im];
 }
 check([render(files,1,annotFull) isEqualToString:@"QA Béatrice"]);
 check([render(files,0,annotFull) isEqualToString:@"QA Alice"]);
 check([render(files,2,annotFull) isEqualToString:@""]);
 check([render(files,3,annotFull) isEqualToString:@""]);
 check([render(files,1,annotGraphics) isEqualToString:@""]);
 check([render(files,1,annotBase) isEqualToString:@""]);
 check([render(files,1,annotNone) isEqualToString:@""]);
 check([render(@[],0,annotFull) isEqualToString:@""]);
 check([render(files,-1,annotFull) isEqualToString:@""]);
 check([render(files,files.count,annotFull) isEqualToString:@""]);
 check([render(@[files[1],files[0]],1,annotFull) isEqualToString:@"QA Alice"]);
 NSLog(@"PASS: PatientName follows current image, including reordered lists; missing/empty names, reduced modes, absent list and invalid selection never borrow the first patient's name");
} }
'''.replace('BRANCH',branch).replace('ANNOTATION_ENUM',annotation_enum)
with tempfile.TemporaryDirectory(prefix='horos-patient-annotation-') as t:
 p=Path(t);(p/'test.m').write_text(code)
 subprocess.run(['xcrun','clang','-fobjc-arc','-framework','Foundation','-framework','CoreData',str(p/'test.m'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
