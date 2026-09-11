#!/usr/bin/env python3
"""Execute the real clipboard description setup with macOS date formatting."""
from pathlib import Path
import subprocess,sys,tempfile
root=Path(__file__).resolve().parents[1]
s=(subprocess.check_output(['git','show',sys.argv[1]+':Horos/Sources/BrowserController.m']) if len(sys.argv)>1 else (root/'Horos/Sources/BrowserController.m').read_bytes()).decode('latin1')
a=s.index('        DICOMExport *e =',s.index('- (IBAction) pasteImageForSourceFile:'));b=s.index('        [e setSeriesNumber:',a)
block=s[a:b]
program=r'''
#import <Foundation/Foundation.h>
@interface DICOMExport:NSObject
@property(retain) NSString *seriesDescription;
@end
@implementation DICOMExport
@synthesize seriesDescription;
- (void)dealloc {[seriesDescription release];[super dealloc];}
@end
@interface BrowserController:NSObject @end
@implementation BrowserController
+ (NSString*)DateTimeWithSecondsFormat:(NSDate*)date {
 NSDateFormatter *f=[[[NSDateFormatter alloc] init] autorelease];
 f.locale=[NSLocale localeWithLocaleIdentifier:@"en_US"];f.dateStyle=NSDateFormatterShortStyle;f.timeStyle=NSDateFormatterMediumStyle;
 return [f stringFromDate:date];
}
@end
int main(){@autoreleasepool {
 BLOCK
 const char *text=[e.seriesDescription cStringUsingEncoding:NSISOLatin1StringEncoding];
 if(!text || !strlen(text)) {puts("FAIL: generated description cannot be encoded in source Latin1");return 1;}
 NSRegularExpression *re=[NSRegularExpression regularExpressionWithPattern:@"^Clipboard - [0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}$" options:0 error:NULL];
 if([re numberOfMatchesInString:e.seriesDescription options:0 range:NSMakeRange(0,e.seriesDescription.length)]!=1)return 2;
 puts("PASS: generated clipboard timestamp remains Latin1/ASCII representable on current macOS");
}}
'''.replace('BLOCK',block)
with tempfile.TemporaryDirectory(prefix='horos-clipboard-date-') as folder:
 p=Path(folder);(p/'test.m').write_text(program)
 subprocess.run(['xcrun','clang','-fsanitize=address',str(p/'test.m'),'-framework','Foundation','-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
