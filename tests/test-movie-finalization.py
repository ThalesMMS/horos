#!/usr/bin/env python3
"""Exercise actual movie finalization with delayed and failing writer peers."""
from pathlib import Path
import subprocess, tempfile, sys
root=Path(__file__).resolve().parents[1]
s=(subprocess.check_output(['git','show',sys.argv[1]+':Horos/Sources/QuicktimeExport.m']) if len(sys.argv)>1 else (root/'Horos/Sources/QuicktimeExport.m').read_bytes()).decode('utf-8')
a=s.index('                [writerInput markAsFinished];') if '                if( writer.status == AVAssetWriterStatusWriting)\n                    [writerInput markAsFinished];' not in s else s.index('                if( writer.status == AVAssetWriterStatusWriting)\n                    [writerInput markAsFinished];')
b=s.index('                [object performSelector:',a)
body=s[a:b]
code=r'''
#import <Foundation/Foundation.h>
#import <AVFoundation/AVFoundation.h>
#import <dispatch/dispatch.h>
@interface Writer:NSObject { @public AVAssetWriterStatus status; BOOL fail,called; NSError *error; }
- (AVAssetWriterStatus)status;
- (NSError*)error;
- (void)finishWritingWithCompletionHandler:(void(^)(void))block;
- (void)cancelWriting;
@end
@implementation Writer
- (AVAssetWriterStatus)status{return status;}
- (NSError*)error{return error;}
- (void)finishWritingWithCompletionHandler:(void(^)(void))block {
 called=YES;
 dispatch_after(dispatch_time(DISPATCH_TIME_NOW,50*NSEC_PER_MSEC),dispatch_get_global_queue(QOS_CLASS_DEFAULT,0),^{
  status=fail?AVAssetWriterStatusFailed:AVAssetWriterStatusCompleted;
  if(fail)error=[[NSError alloc] initWithDomain:@"WriterTest" code:17 userInfo:nil];
  block();
 });
}
- (void)cancelWriting{status=AVAssetWriterStatusCancelled;}
- (void)dealloc{[error release];[super dealloc];}
@end
@interface Input:NSObject
- (void)markAsFinished;
@end
@implementation Input
- (void)markAsFinished{}
@end
int main(){@autoreleasepool{
 for(int scenario=0;scenario<5;scenario++){
  Writer *writer=[Writer new];writer->status=scenario==3?AVAssetWriterStatusFailed:AVAssetWriterStatusWriting;writer->fail=scenario==1;
  Input *writerInput=[Input new];
  BOOL completed=NO,failed=scenario==4,aborted=scenario==2;NSError *error=nil;
BODY
  if(scenario==0 && (!completed || writer.status!=AVAssetWriterStatusCompleted)){fprintf(stderr,"FAIL: returned before writer finished\n");return 1;}
  if(scenario==1 && (completed || error.code!=17)){fprintf(stderr,"FAIL: failed finalization reported success or lost error\n");return 1;}
  if((scenario==2 || scenario==4) && (completed || writer->called || writer.status!=AVAssetWriterStatusCancelled)){fprintf(stderr,"FAIL: cancelled writer finalized\n");return 1;}
  if(scenario==3 && (completed || writer->called)){fprintf(stderr,"FAIL: failed writer finalized again\n");return 1;}
  [writerInput release];[writer release];
 }
 puts("PASS: waits for delayed completion; preserves failure error; cancels without finalizing; rejects failed writer");
}}
'''.replace('BODY',body)
with tempfile.TemporaryDirectory(prefix='horos-movie-finalization-') as folder:
 p=Path(folder);(p/'test.m').write_text(code)
 subprocess.run(['xcrun','clang','-fblocks','-fsanitize=address',str(p/'test.m'),'-framework','Foundation','-framework','AVFoundation','-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
