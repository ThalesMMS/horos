#!/usr/bin/env python3
"""Exercise production tag sorting, including duplicate values and pixel identity."""
from pathlib import Path
import subprocess
import tempfile
root = Path(__file__).resolve().parents[1]
s = (root/'Horos/Sources/ViewerController.m').read_bytes().decode('latin1')
a=s.index('- (BOOL) sortSeriesByDICOMGroup:')
method=s[a:s.index('\n#endif',a)]
value_start=s.index('- (BOOL) sortSeriesByValue: (NSString*)')
method += s[value_start:a]
code=r'''
#import <Foundation/Foundation.h>
#import "Sorter-Swift.h"
#define N2LogExceptionWithStackTrace(e) NSLog(@"%@", e)
#define check(c) NSCAssert((c), @"failed: %s", #c)
static NSDictionary *attributes;
@interface DCMAttributeTag:NSObject
+ (id)tagWithGroup:(int)group element:(int)element;
@end
@implementation DCMAttributeTag
+ (id)tagWithGroup:(int)group element:(int)element { return @"test"; }
@end
@interface DCMAttribute:NSObject
@property(retain) NSArray *values;
@end
@implementation DCMAttribute
@end
@interface DCMObject:NSObject
@property(retain) DCMAttribute *attribute;
+ (id)objectWithContentsOfFile:(NSString*)path decodingPixelData:(BOOL)decode;
- (DCMAttribute*)attributeForTag:(id)tag;
@end
@implementation DCMObject
+ (id)objectWithContentsOfFile:(NSString*)path decodingPixelData:(BOOL)decode {
 DCMObject *o=[DCMObject new];o.attribute=attributes[path];return [o autorelease];
}
- (DCMAttribute*)attributeForTag:(id)tag {return self.attribute;}
@end
@interface DicomFile:NSObject
+ (NSDictionary*)acquisitionTimingForFile:(NSString*)path;
@end
@implementation DicomFile
+ (NSDictionary*)acquisitionTimingForFile:(NSString*)path {
 NSArray *values=[(DCMAttribute*)attributes[path] values];
 return values.count ? @{@"AcquisitionDateTime":values[0]} : @{};
}
@end
@interface DCMPix:NSObject <NSCopying>
@property(retain) NSString *srcFile;
@property(setter=setfImage:) float *fImage;
- (int)pwidth;
- (int)pheight;
@end
@implementation DCMPix
- (int)pwidth{return 1;}
- (int)pheight{return 1;}
- (id)copyWithZone:(NSZone*)zone {DCMPix *p=[DCMPix new];p.srcFile=self.srcFile;p.fImage=self.fImage;return p;}
@end
@interface ImageProbe:NSObject
- (void)setIndex:(int)index;
- (void)sendSyncMessage:(int)value;
@end
@implementation ImageProbe
- (void)setIndex:(int)index {}
- (void)sendSyncMessage:(int)value {}
@end
@interface ViewerController:NSObject {
@public
 int maxMovieIndex;
 NSMutableArray *pixList[2], *fileList[2];
 NSData *volumeData[2];
 ImageProbe *imageView;
 BOOL postprocessed;
}
@property(retain) NSMutableArray *results;
- (void)checkEverythingLoaded;
- (void)changeImageData:(id)p :(id)f :(id)d :(BOOL)value;
- (void)addMovieSerie:(id)p :(id)f :(id)d;
- (void)computeInterval;
- (void)setWindowTitle:(id)sender;
- (void)adjustSlider;
@end
@implementation ViewerController
- (void)checkEverythingLoaded {}
- (void)changeImageData:(id)p :(id)f :(id)d :(BOOL)value {[self.results addObject:@[p,f,d]];}
- (void)addMovieSerie:(id)p :(id)f :(id)d {[self.results addObject:@[p,f,d]];}
- (void)computeInterval {}
- (void)setWindowTitle:(id)sender {}
- (void)adjustSlider {}
METHOD
@end
static BOOL acquisition, descriptor;
static void runCase(NSArray *values, NSArray *expected) {
 ViewerController *v=[ViewerController new];v->maxMovieIndex=2;
 v->imageView=[ImageProbe new];v.results=[NSMutableArray array];
 NSMutableDictionary *map=[NSMutableDictionary dictionary];
 for(int phase=0;phase<2;phase++) {
  NSMutableData *data=[NSMutableData dataWithLength:values.count*sizeof(float)];
  v->volumeData[phase]=data;
  v->pixList[phase]=[NSMutableArray array];v->fileList[phase]=[NSMutableArray array];
  for(NSUInteger i=0;i<values.count;i++) {
   NSString *path=[NSString stringWithFormat:@"%d-%lu",phase,(unsigned long)i];
   DCMAttribute *attr=[DCMAttribute new];attr.values=values[i];map[path]=attr;
   DCMPix *p=[DCMPix new];p.srcFile=path;p.fImage=(float*)data.mutableBytes+i;
   *p.fImage=phase*100+i;
   [v->pixList[phase] addObject:p];[v->fileList[phase] addObject:path];
  }
 }
 attributes=map;
 check(descriptor ? [v sortSeriesByValue:@"self" ascending:NO] : acquisition ? [v sortSeriesByValue:nil ascending:YES] : [v sortSeriesByDICOMGroup:8 element:0x32]);
 check(v.results.count==2);check(v->postprocessed);
 for(int phase=0;phase<2;phase++) {
  NSArray *r=v.results[phase];NSArray *pixels=r[0],*files=r[1];NSData *data=r[2];
  check(files.count==expected.count);
  check([NSSet setWithArray:files].count==files.count);
  for(NSUInteger i=0;i<expected.count;i++) {
   NSInteger old=[expected[i] integerValue];
   check(([files[i] isEqual:[NSString stringWithFormat:@"%d-%ld",phase,(long)old]]));
   check(((const float*)data.bytes)[i]==phase*100+old);
   check(*[(DCMPix*)pixels[i] fImage]==phase*100+old);
  }
 }
}
int main(void) {@autoreleasepool {
 // Equal numeric values may share the same NSNumber object (tagged pointers).
 runCase(@[@[@"3"],@[@"1"],@[@"1"],@[@"2"]],@[@1,@2,@3,@0]);
 runCase(@[@[@"B"],@[@"A"],@[@"A"],@[@"C"]],@[@1,@2,@0,@3]);
 // Empty value arrays must follow the existing missing-value policy (numeric zero).
 runCase(@[@[@"2"],@[],@[@"0"],@[]],@[@1,@2,@3,@0]);
 acquisition=YES;
 runCase(@[@[@"20260907120000.000002"],@[@"20260907120000.000001"],@[@"20260907120000.000001"],@[]],@[@1,@2,@0,@3]);
 descriptor=YES;
 runCase(@[@[@"3"],@[@"1"],@[@"1"],@[@"2"]],@[@3,@2,@1,@0]);
 NSLog(@"PASS: descriptor and acquisition pipeline; duplicate numeric/string keys, stable ties, empty values, two phases, unique files and pixel buffers");
}}
'''.replace('METHOD',method)
with tempfile.TemporaryDirectory(prefix='horos-tag-sort-') as directory:
    p=Path(directory);(p/'test.m').write_text(code)
    subprocess.run(['xcrun','swiftc','-emit-library','-emit-objc-header','-emit-objc-header-path',str(p/'Sorter-Swift.h'),'-module-name','Sorter',str(root/'Horos/Sources/AcquisitionTimeOrdering.swift'),'-o',str(p/'libSorter.dylib')],check=True)
    subprocess.run(['xcrun','clang','-fno-objc-arc','-fblocks','-framework','Foundation','-L'+str(p),'-lSorter','-Wl,-rpath,'+str(p),str(p/'test.m'),'-o',str(p/'test')],check=True)
    subprocess.run([str(p/'test')],check=True)
