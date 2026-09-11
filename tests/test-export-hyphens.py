#!/usr/bin/env python3
"""Exercise the real sanitizer's normal-folder and legacy/DICOMDIR policies."""
from pathlib import Path
import subprocess,tempfile,sys
root=Path(__file__).resolve().parents[1]
s=(subprocess.check_output(['git','show',sys.argv[1]+':Horos/Sources/BrowserController.m']) if len(sys.argv)>1 else (root/'Horos/Sources/BrowserController.m').read_bytes()).decode('latin1')
a=s.index('+ (NSMutableString*) replaceNotAdmitted:');b=s.index('\n#ifndef OSIRIX_LIGHT',a)
code=r'''
#import <Foundation/Foundation.h>
@interface NSString(Range)
- (NSRange)range;
@end
@implementation NSString(Range)
- (NSRange)range{return NSMakeRange(0,self.length);}
@end
@interface Browser:NSObject
+ (NSMutableString*)replaceNotAdmitted:(NSString*)name preserveHyphens:(BOOL)preserveHyphens;
@end
@implementation Browser
BODY
@end
int main(){@autoreleasepool{
 NSArray *names=@[@"Chr-P03R",@"ChrP03R",@"Chr_P03R",@"A--B",@"A-B_C",@"João-Silva"];
 NSMutableSet *outputs=[NSMutableSet set];
 for(NSString *name in names){
  NSString *result=[Browser replaceNotAdmitted:[NSMutableString stringWithString:name] preserveHyphens:YES];
  NSCAssert([result isEqual:name],@"valid hyphen/underscore changed");[outputs addObject:result];
  NSString *legacy=[Browser replaceNotAdmitted:[NSMutableString stringWithString:name]];
  NSCAssert([legacy isEqual:[name stringByReplacingOccurrencesOfString:@"-" withString:@""]],@"legacy naming changed");
  NSCAssert([legacy isEqual:[Browser replaceNotAdmitted:[NSMutableString stringWithString:name] preserveHyphens:NO]],@"DICOMDIR compatibility changed");
 }
 for(NSString *immutable in @[@"Chr-P03R", [NSString stringWithFormat:@"%@",@"A-B"], [NSString stringWithFormat:@"%@ %@",@"A-long-hyphenated-name",@"with-a-second-component"]]) {
  NSString *before=[[immutable copy] autorelease];
  NSString *filtered=[Browser replaceNotAdmitted:immutable preserveHyphens:YES];
  NSCAssert([immutable isEqual:before],@"immutable source changed");
  NSCAssert([filtered isEqual:[before stringByReplacingOccurrencesOfString:@" " withString:@"_"]],@"immutable result incorrect");
  NSCAssert([filtered isKindOfClass:[NSMutableString class]],@"result is not mutable");
  [(NSMutableString*)filtered appendString:@"_proof"];
 }
 NSCAssert(outputs.count==names.count,@"valid names collided");
 NSMutableString *mutable=[NSMutableString stringWithString:@"A-B / C:*?\\D"];
 id result=[Browser replaceNotAdmitted:mutable preserveHyphens:YES];
 NSCAssert(result==mutable && [mutable isEqual:@"A-B__CD"],@"mutation/unsafe-character policy changed");
 NSCAssert([Browser replaceNotAdmitted:nil preserveHyphens:YES]==nil,@"nil changed");
 puts("PASS: hyphen/underscore distinctions preserved for ordinary folders; legacy policy, unsafe-character filtering and mutable callers preserved; immutable constant/tagged/heap strings copied safely");
}}
'''.replace('BODY',s[a:b])
with tempfile.TemporaryDirectory(prefix='horos-export-hyphen-') as folder:
 p=Path(folder);(p/'test.m').write_text(code)
 subprocess.run(['xcrun','clang','-fsanitize=address',str(p/'test.m'),'-framework','Foundation','-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
