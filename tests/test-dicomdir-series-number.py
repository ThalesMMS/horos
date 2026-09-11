#!/usr/bin/env python3
"""Run the actual DICOMDIR series-number extraction with destructive attribute reads."""
from pathlib import Path
import subprocess,tempfile,sys
root=Path(__file__).resolve().parent.parent
source=(subprocess.check_output(['git','show',sys.argv[1]+':Horos/Sources/DicomDatabase+Scan.mm']) if len(sys.argv)>1 else (root/'Horos/Sources/DicomDatabase+Scan.mm').read_bytes()).decode('latin1')
start=source.index('            id seriesNumberAttribute') if '            id seriesNumberAttribute' in source else source.index('            NSString *seriesNumber =')
end=source.index('forKey:@"seriesNumber"];',start)+len('forKey:@"seriesNumber"];')
program=r'''
#import <Foundation/Foundation.h>
@interface NSMutableDictionary(Extraction)
- (id)objectForKeyRemove:(id)key;
- (void)conditionallySetObject:(id)object forKey:(id)key;
@end
@implementation NSMutableDictionary(Extraction)
- (id)objectForKeyRemove:(id)key { id value=[[[self objectForKey:key] retain] autorelease];[self removeObjectForKey:key];return value; }
- (void)conditionallySetObject:(id)object forKey:(id)key { if(object)[self setObject:object forKey:key]; }
@end
@interface NSNumber(Attribute)
- (NSNumber*)integerNumberValue;
- (NSString*)stringValueWithEncodings:(id)encodings;
@end
@implementation NSNumber(Attribute)
- (NSNumber*)integerNumberValue { return self; }
- (NSString*)stringValueWithEncodings:(id)encodings { return self.stringValue; }
@end
int main(){ @autoreleasepool {
 for(NSNumber *number in @[@0,@7,@-1]) {
 NSMutableDictionary *elements=[@{@"0020,0011":number} mutableCopy];
 NSMutableDictionary *item=[@{@"seriesDICOMUID":@"uid"} mutableCopy];id encodings=nil;
 BLOCK
 if(![item[@"seriesNumber"] isEqual:number]) {fprintf(stderr,"FAIL: series number lost after destructive read\n");return 1;}
 NSCAssert(elements.count==0,@"Consume attribute once");
 NSCAssert(([item[@"seriesID"] isEqual:[NSString stringWithFormat:@"%8.8d uid",number.intValue]]),@"Preserve series identity formatting");
 }
 puts("PASS: DICOMDIR series numbers survive attribute removal (zero, positive, negative)");
} }
'''.replace('BLOCK',source[start:end])
with tempfile.TemporaryDirectory(prefix='horos-dicomdir-number-') as directory:
 p=Path(directory);(p/'test.m').write_text(program)
 subprocess.run(['xcrun','clang','-fsanitize=address','-framework','Foundation',str(p/'test.m'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
