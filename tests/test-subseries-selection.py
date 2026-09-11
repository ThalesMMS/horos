#!/usr/bin/env python3
"""Run production subset selection with editable boundary values."""
from pathlib import Path
import subprocess,sys,tempfile
root=Path(__file__).resolve().parents[1]
s=subprocess.check_output(['git','show',sys.argv[1]+':Horos/Sources/BrowserController.m']).decode('latin1') if len(sys.argv)>1 else (root/'Horos/Sources/BrowserController.m').read_bytes().decode('latin1')
a=s.index('- (NSArray*)produceNewArray:');b=s.index('\n- (IBAction) checkMemory:',a)
code=r'''
#import <Foundation/Foundation.h>
#include <limits.h>
#define NSManagedObject NSObject
@interface NSNumber(Test)
-(id)series;-(NSArray*)sortDescriptorsForImages;
@end
@implementation NSNumber(Test)
-(id)series{return self;}
-(NSArray*)sortDescriptorsForImages{return @[];}
@end
@interface Browser:NSObject { @public int subFrom,subTo,subInterval; }
-(NSArray*)produceNewArray:(NSArray*)a;
@end
@implementation Browser
METHOD
@end
#define check(...) do{if(!(__VA_ARGS__)){NSLog(@"FAIL: %s",#__VA_ARGS__);return 1;}}while(0)
int main(){@autoreleasepool{
 Browser*b=[Browser new];NSArray*input=@[@[@0,@1,@2,@3,@4],@[@5,@6],@[]];
 b->subFrom=1;b->subTo=5;b->subInterval=1;
 check([[b produceNewArray:input] isEqual:@[@[@0,@1,@2,@3,@4],@[@5,@6]]]);
 b->subFrom=2;b->subInterval=2;
 check([[b produceNewArray:input] isEqual:@[@[@2,@4]]]);
 b->subFrom=0;b->subInterval=0;
 check([[b produceNewArray:input] isEqual:@[@[@0,@1,@2,@3,@4],@[@5,@6]]]);
 b->subFrom=INT_MIN;b->subInterval=-1;b->subTo=INT_MAX;
 check([[b produceNewArray:input] isEqual:@[@[@0,@1,@2,@3,@4],@[@5,@6]]]);
 b->subFrom=4;b->subTo=2;check([b produceNewArray:input].count==0);
 b->subFrom=INT_MAX;b->subTo=INT_MAX;check([b produceNewArray:input].count==0);
 b->subFrom=1;b->subTo=-1;check([b produceNewArray:input].count==0);
 check([b produceNewArray:@[]].count==0);
 NSLog(@"PASS: normal sampling, unequal series, zero/negative/extreme bounds and reversed ranges");
}}
'''.replace('METHOD',s[a:b])
with tempfile.TemporaryDirectory(prefix='horos-subseries-') as d:
 p=Path(d);(p/'test.m').write_text(code)
 subprocess.run(['xcrun','clang','-fobjc-arc','-fsanitize=undefined','-framework','Foundation',str(p/'test.m'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
