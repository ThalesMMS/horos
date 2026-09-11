#!/usr/bin/env python3
"""Exercise production folder allocation for absent and colliding series metadata."""
from pathlib import Path
import subprocess,tempfile
root=Path(__file__).resolve().parent.parent
program=r'''
#import "HorosRasterSeriesFolder.h"
int main(){ @autoreleasepool {
 NSMutableDictionary *assignments=[NSMutableDictionary dictionary];NSMutableSet *reserved=[NSMutableSet set];
 NSObject *a=[NSObject new],*b=[NSObject new],*c=[NSObject new],*d=[NSObject new];
 NSString *first=HorosRasterSeriesFolder(nil,nil,@"/study",a,assignments,reserved);
 NSCAssert([first isEqual:@"series"],@"Missing metadata must not emit null");
 NSCAssert([HorosRasterSeriesFolder(nil,nil,@"/study",b,assignments,reserved) isEqual:@"series_2"],@"Distinct missing series must not merge");
 NSCAssert([HorosRasterSeriesFolder(@"series",@2,@"/study",c,assignments,reserved) isEqual:@"series_2_2"],@"Numbered names can collide with fallback suffixes");
 NSCAssert([HorosRasterSeriesFolder(@"other",@99,@"/study",a,assignments,reserved) isEqual:first],@"Same series keeps assigned folder");
 NSCAssert([HorosRasterSeriesFolder(@"CT",@4,@"/study",d,assignments,reserved) isEqual:@"CT_4"],@"Preserve ordinary names");
 NSCAssert([HorosRasterSeriesFolder(nil,nil,@"/other-study",b,assignments,reserved) isEqual:@"series"],@"Parent namespaces independent");
 NSObject *e=[NSObject new];
 NSCAssert([HorosRasterSeriesFolder(@"ct",@4,@"/study",e,assignments,reserved) isEqual:@"ct_4_2"],@"Case-insensitive volumes must not merge series");
 puts("PASS: missing metadata, duplicate names, fallback collisions, stable assignment and ordinary names");
} }
'''
with tempfile.TemporaryDirectory(prefix='horos-raster-names-') as directory:
 p=Path(directory);(p/'test.m').write_text(program)
 subprocess.run(['xcrun','clang','-fsanitize=address','-framework','Foundation','-I',str(root/'Horos/Sources'),str(p/'test.m'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
