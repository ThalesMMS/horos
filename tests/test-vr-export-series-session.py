#!/usr/bin/env python3
"""Verify each accepted single-frame export owns a fresh exporter session."""
from pathlib import Path
import subprocess, tempfile, sys
root=Path(__file__).resolve().parents[1]
s=(subprocess.check_output(['git','show',sys.argv[1]+':Horos/Sources/VRView.mm']) if len(sys.argv)>1 else (root/'Horos/Sources/VRView.mm').read_bytes()).decode('latin1')
a=s.index('\n        {',s.index('// CURRENT image only'))+len('\n        {')
b=s.index('// 4th dimension',a)
body=s[a:b].rsplit('        }',1)[0].replace('[NSCalendarDate date]','[FixedDate date]')
code=r'''
#import <Foundation/Foundation.h>
#include <cassert>
static int created, destroyed;
@interface FixedDate:NSObject
+ (FixedDate*)date;
- (int)minuteOfHour;
- (int)secondOfMinute;
@end
@implementation FixedDate
+ (FixedDate*)date{return [[[self alloc] init] autorelease];}
- (int)minuteOfHour{return 3;}
- (int)secondOfMinute{return 4;}
@end
@interface DICOMExport:NSObject { @public int serial,instance; long number; }
- (void)setSeriesNumber:(long)value;
@end
@implementation DICOMExport
- (id)init {if((self=[super init])){serial=++created;instance=1;}return self;}
- (void)setSeriesNumber:(long)value {number=value;}
- (void)dealloc {destroyed++;[super dealloc];}
@end
@interface Peer:NSObject { @public DICOMExport *exportDCM; }
- (NSDictionary*)exportDCMCurrentImageIn16bit:(BOOL)depth;
- (NSDictionary*)request:(BOOL)depth;
@end
@implementation Peer
- (NSDictionary*)exportDCMCurrentImageIn16bit:(BOOL)depth {
 return @{ @"session":@(exportDCM->serial), @"instance":@(exportDCM->instance++), @"number":@(exportDCM->number), @"depth":@(depth) };
}
- (NSDictionary*)request:(BOOL)fullDepthCapture {
 NSMutableArray *producedFiles=[NSMutableArray array];
BODY
 return [producedFiles lastObject];
}
- (void)dealloc {[exportDCM release];[super dealloc];}
@end
int main(){@autoreleasepool{
 Peer *view=[Peer new];
 for(int i=1;i<=100;i++){
  NSDictionary *r=[view request:i%2];
  if([r[@"session"] intValue]!=i || [r[@"instance"] intValue]!=1){fprintf(stderr,"FAIL: independent request reused its prior exporter session\n");return 1;}
  assert([r[@"number"] intValue]==5227);assert([r[@"depth"] boolValue]==(i%2));
  assert(created==i && destroyed==i-1);
 }
 [view release];assert(created==destroyed);
 puts("PASS: 100 requests within the same clock second create fresh sessions, reset instance state and release prior ownership");
}}
'''.replace('BODY',body)
with tempfile.TemporaryDirectory(prefix='horos-export-session-') as d:
 p=Path(d);(p/'test.mm').write_text(code)
 subprocess.run(['xcrun','clang++','-std=c++11','-fsanitize=address',str(p/'test.mm'),'-framework','Foundation','-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
