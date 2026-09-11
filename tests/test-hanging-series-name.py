#!/usr/bin/env python3
"""Execute both production hanging-protocol ordering blocks on real Core Data objects."""
from pathlib import Path
import subprocess, tempfile
root=Path(__file__).resolve().parents[1]
s=(root/'Horos/Sources/BrowserController.m').read_bytes().decode('latin1')
marker='// Sort series according to SeriesOrder, if available'
a=s.index(marker);b=s.index('// Prepare the series to be displayed',a);current=s[a:b]
a=s.index(marker,b);b=s.index('if( series.count > n)',a);comparative=s[a:b]
a=s.index('// Expand comparatives study according to NumberOfSeriesPerComparative')
b=s.index('// Prepare the series',a);expansion=s[a:b]
a=s.index('// Go to the series level, if we are at study level (comparatives)',b)
b=s.index('[self viewerDICOMInt:',a);normalization=s[a:b]
n2=(root/'Nitrogen/Sources/NSString+N2.mm').read_bytes().decode('latin1')
a=n2.index('-(BOOL)contains:');contains=n2[a:n2.index('\n}',a)+2]
code=r'''
#import <Foundation/Foundation.h>
#import <CoreData/CoreData.h>
#define check(c) NSCAssert((c),@"failed: %s",#c)
@interface NSString (Contains)
- (BOOL)contains:(NSString*)value;
@end
@implementation NSString (Contains)
CONTAINS
@end
@interface DicomSeries:NSManagedObject
@property(retain) NSString *name;
@property(retain) NSString *comment;
@end
@implementation DicomSeries
@dynamic name,comment;
@end
@interface DicomStudy:NSObject
@property(retain) NSArray *imageSeries;
@property(retain) NSArray *pixelSeries;
- (NSArray*)imageSeriesContainingPixels:(BOOL)pixels;
@end
@implementation DicomStudy
- (NSArray*)imageSeriesContainingPixels:(BOOL)pixels { return self.pixelSeries; }
@end
static NSArray *expanded(NSArray *studies, NSDictionary *currentHangingProtocol) {
 NSMutableArray *comparatives=[NSMutableArray arrayWithArray:studies];
EXPANSION
 NSMutableArray *seriesArray=comparatives;
NORMALIZATION
 return seriesArray;
}
static NSArray *current(NSArray *input, NSDictionary *currentHangingProtocol) {
 NSMutableArray *seriesArray=[NSMutableArray arrayWithArray:input];
CURRENT
 return seriesArray;
}
static NSArray *comparative(NSArray *input, NSDictionary *currentHangingProtocol) {
 NSMutableArray *series=[NSMutableArray arrayWithArray:input];
COMPARATIVE
 return series;
}
int main(void) { @autoreleasepool {
 NSEntityDescription *entity=[NSEntityDescription new];entity.name=@"Series";entity.managedObjectClassName=@"DicomSeries";
 NSMutableArray *properties=[NSMutableArray array];
 for(NSString *name in @[@"name",@"comment"]) {
  NSAttributeDescription *a=[NSAttributeDescription new];a.name=name;a.attributeType=NSStringAttributeType;a.optional=YES;[properties addObject:a];
 }
 entity.properties=properties;
 NSManagedObjectModel *model=[NSManagedObjectModel new];model.entities=@[entity];
 NSPersistentStoreCoordinator *coordinator=[[NSPersistentStoreCoordinator alloc] initWithManagedObjectModel:model];
 check([coordinator addPersistentStoreWithType:NSInMemoryStoreType configuration:nil URL:nil options:nil error:nil]!=nil);
 NSManagedObjectContext *context=[[NSManagedObjectContext alloc] initWithConcurrencyType:NSMainQueueConcurrencyType];context.persistentStoreCoordinator=coordinator;
 NSMutableArray *input=[NSMutableArray array];
 for(NSString *name in @[@"T2 Axial",@"Scout",@"T1 Sagittal"]) {
  DicomSeries *series=[[DicomSeries alloc] initWithEntity:entity insertIntoManagedObjectContext:context];series.name=name;[input addObject:series];
 }
 ((DicomSeries*)input[1]).comment=@"T2 Axial -- unrelated note";
 for(int path=0;path<2;path++) {
  NSArray* (^sort)(NSDictionary*)=^NSArray*(NSDictionary *p){return path ? comparative(input,p) : current(input,p);};
  check([sort(@{@"SeriesOrder":@"T2"}) isEqual:input]);
  check([sort(@{@"SeriesOrder":@"t2",@"SeriesOrderIgnoreCase":@YES}) isEqual:input]);
  check([sort(@{@"SeriesOrder":@"t2",@"SeriesOrderIgnoreCase":@NO}) isEqual:input]);
  NSArray *expected=@[input[2],input[0],input[1]];
  check([sort(@{@"SeriesOrder":@"T1, T2"}) isEqual:expected]);
  check([sort(@{@"SeriesOrder":@" , \n"}) isEqual:input]);
  check([sort(@{}) isEqual:input]);
  ((DicomSeries*)input[0]).name=@"T2 Coração";
  NSArray *unicodeExpected=@[input[0],input[2],input[1]];
  check([sort(@{@"SeriesOrder":@"Coração,T1"}) isEqual:unicodeExpected]);
  ((DicomSeries*)input[0]).name=@"T2 Axial";
  ((DicomSeries*)input[1]).name=nil;
  check([sort(@{@"SeriesOrder":@"T2"}) isEqual:input]);
  ((DicomSeries*)input[1]).name=@"Scout";
 }
 DicomStudy *study=[DicomStudy new];study.imageSeries=@[input[1],input[2],input[0]];study.pixelSeries=study.imageSeries;
 NSArray *one=@[input[0]], *two=@[input[0],input[1]];
 check([expanded(@[study],@{@"SeriesOrder":@"T2",@"NumberOfSeriesPerComparative":@1}) isEqual:one]);
 check([expanded(@[study],@{@"SeriesOrder":@"T2",@"NumberOfSeriesPerComparative":@2}) isEqual:two]);
 check([expanded(@[study],@{@"SeriesOrder":@"T2"}) isEqual:one]);
 check([expanded(@[study],@{@"SeriesOrder":@"T2",@"NumberOfSeriesPerComparative":@0}) isEqual:one]);
 check([expanded(@[study],@{}) isEqual:@[input[1]]]);
 study.pixelSeries=@[];
 check([expanded(@[study],@{@"SeriesOrder":@"T2",@"NumberOfSeriesPerComparative":@1}) isEqual:one]);
 check(expanded(@[],@{@"SeriesOrder":@"T2"}).count==0);
 NSLog(@"PASS: single/multiple comparative selection and fallback; current/comparative series names; unrelated comments, case modes, fallback and missing names");
}}
'''.replace('CONTAINS',contains).replace('CURRENT',current).replace('COMPARATIVE',comparative).replace('EXPANSION',expansion).replace('NORMALIZATION',normalization)
with tempfile.TemporaryDirectory(prefix='horos-hanging-name-') as directory:
 p=Path(directory);(p/'test.m').write_text(code)
 subprocess.run(['xcrun','clang','-fno-objc-arc','-fblocks','-framework','Foundation','-framework','CoreData',str(p/'test.m'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
