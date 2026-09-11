#!/usr/bin/env python3
"""Run the actual remote-index receiver with controlled transport failures."""
from pathlib import Path
import subprocess
import tempfile
root=Path(__file__).resolve().parents[1]
source=(root/'Horos/Sources/RemoteDicomDatabase.mm').read_text(encoding='latin1')
def method(signature):
    start=source.index(signature);opening=source.index('{',start);depth=0
    for end in range(opening,len(source)):
        if source[end]=='{':depth+=1
        elif source[end]=='}':
            depth-=1
            if depth==0:return source[start:end+1]
    raise AssertionError(signature)
constructor=method('-(id)initWithHost:')
assert 'tmpDirectoryPathInTmp' in constructor and 'tmpFilePathInTmp' not in constructor
methods='\n'.join(method(s) for s in (
    '-(NSData*)synchronousRequest:(NSData*)request urgent:(BOOL)urgent',
    '- (void)requestDatabasePasswordOnMainThread', '- (BOOL)prepareAuthentication {', '- (NSString *)fetchDatabaseIndex',
    '-(NSInteger)_connection:(N2Connection*)connection handleData_fetchDatabaseIndex:'))
code=r'''
#import <Foundation/Foundation.h>
#import <objc/message.h>
#import <dispatch/dispatch.h>
typedef int OSStatus;
#define noErr 0
#define N2LogExceptionWithStackTrace(e) ((void)0)
#define CurrentDatabaseVersion @"fixture"
static void HorosResetRemoteDownload(id context) {}
static int mode, attempts, operations;
static BOOL cancelPrompt, promptOnMain;
@interface NSThread (Probe)
@property(copy) NSString *status,*progressDetails;
@property double progress;
- (void)enterOperation;- (void)exitOperation;
@end
@implementation NSThread (Probe)
- (void)setStatus:(id)x {} - (id)status{return nil;}
- (void)setProgressDetails:(id)x {} - (id)progressDetails{return nil;}
- (void)setProgress:(double)x {} - (double)progress{return 0;}
- (void)enterOperation{operations++;}- (void)exitOperation{operations--;}
@end
@interface NSFileManager (Probe)
- (NSString*)tmpFilePathInDir:(NSString*)directory;
@end
@implementation NSFileManager (Probe)
- (NSString*)tmpFilePathInDir:(NSString*)directory {
    NSString *path=[directory stringByAppendingPathComponent:NSUUID.UUID.UUIDString];
    [self createFileAtPath:path contents:[NSData data] attributes:nil];return path;
}
@end
@interface N2MutableUInteger:NSObject
@property NSUInteger unsignedIntegerValue;
+ (id)mutableUIntegerWithUInteger:(NSUInteger)n;
@end
@implementation N2MutableUInteger
+ (id)mutableUIntegerWithUInteger:(NSUInteger)n {N2MutableUInteger *x=[self new];x.unsignedIntegerValue=n;return x;}
@end
@interface BrowserController:NSObject
+ (id)currentBrowser;- (NSString*)askPassword;
@end
@implementation BrowserController
+ (id)currentBrowser{return [self new];}
- (NSString*)askPassword {promptOnMain=NSThread.isMainThread;return cancelPrompt?nil:@"fixture";}
@end
@interface N2Connection:NSObject
+ (NSData*)sendSynchronousRequest:(NSData*)request toAddress:(id)host port:(NSInteger)port dataHandlerTarget:(id)target selector:(SEL)selector context:(void*)context;
@end
@implementation N2Connection
+ (NSData*)sendSynchronousRequest:(NSData*)request toAddress:(id)host port:(NSInteger)port dataHandlerTarget:(id)target selector:(SEL)selector context:(void*)context {
    attempts++;
    NSData *data=[(mode==1 || (mode==2 && attempts==1)?@"AB":@"ABCD") dataUsingEncoding:NSUTF8StringEncoding];
    ((NSInteger(*)(id,SEL,id,id,void*))objc_msgSend)(target,selector,nil,data,context);
    if(mode==2 && attempts==1)[NSException raise:NSGenericException format:@"connection reset after partial data"];
    return [NSData data];
}
@end
// Authorization framing is covered separately; this transport exercises decoded index bytes.
@interface HorosSharedDatabaseAuthorization:NSObject
+ (BOOL)isPublicCommand:(NSString*)command;
+ (NSData*)authenticatedRequest:(NSData*)request password:(NSString*)password;
@end
@implementation HorosSharedDatabaseAuthorization
+ (BOOL)isPublicCommand:(NSString*)command{return YES;}
+ (NSData*)authenticatedRequest:(NSData*)request password:(NSString*)password{return request;}
@end
@interface RemoteDicomDatabase:NSObject {
    dispatch_semaphore_t _connectionsSemaphoreId;
    BOOL _requiresAuthenticatedRequests;
}
@property BOOL authenticationKnown, requiresAuthenticatedRequests;
@property(copy) NSString *password,*baseDirPath;
@property id host;
@property NSInteger port;
- (NSString*)fetchDatabaseVersion;- (BOOL)fetchIsPasswordProtected;
- (BOOL)fetchIsRightPassword:(NSString*)password;- (unsigned int)fetchDatabaseIndexSize;
@end
@implementation RemoteDicomDatabase
- (NSString*)fetchDatabaseVersion{return @"fixture";}
- (BOOL)fetchIsPasswordProtected{return YES;}
- (BOOL)fetchIsRightPassword:(NSString*)password{return [password isEqualToString:@"fixture"];}
- (unsigned int)fetchDatabaseIndexSize{return 4;}
- (BOOL)supportsAuthenticatedRequests{return YES;}
ACTUAL_METHODS
@end
int main(int argc,char**argv){@autoreleasepool{
    RemoteDicomDatabase *remote=[RemoteDicomDatabase new];remote.baseDirPath=@(argv[1]);
    __block BOOL done=NO;__block int failed=0;
    [NSThread detachNewThreadWithBlock:^{@autoreleasepool{
        @try {
            NSString *path=[remote fetchDatabaseIndex];
            if(!promptOnMain || ![[NSData dataWithContentsOfFile:path] isEqualToData:[@"ABCD" dataUsingEncoding:NSUTF8StringEncoding]])failed++;
            [NSFileManager.defaultManager removeItemAtPath:path error:NULL];
            mode=1;attempts=0;
            @try {[remote fetchDatabaseIndex];failed++;} @catch(NSException *e) {}
            if([[NSFileManager.defaultManager contentsOfDirectoryAtPath:remote.baseDirPath error:NULL] count]!=0)failed++;
            mode=2;attempts=0;path=[remote fetchDatabaseIndex];
            if(attempts!=2 || ![[NSData dataWithContentsOfFile:path] isEqualToData:[@"ABCD" dataUsingEncoding:NSUTF8StringEncoding]])failed++;
            [NSFileManager.defaultManager removeItemAtPath:path error:NULL];
            remote.password=nil;cancelPrompt=YES;int before=attempts;
            if([remote fetchDatabaseIndex]!=nil || attempts!=before)failed++;
            if(operations!=0)failed++;
        } @catch(NSException *e){NSLog(@"unexpected %@",e);failed++;}
        dispatch_async(dispatch_get_main_queue(),^{done=YES;});
    }}];
    NSDate *deadline=[NSDate dateWithTimeIntervalSinceNow:10];
    while(!done && deadline.timeIntervalSinceNow>0)[NSRunLoop.currentRunLoop runUntilDate:[NSDate dateWithTimeIntervalSinceNow:.01]];
    if(!done || failed)return 1;
    puts("ok: main-thread password, cancel, complete index, truncated cleanup and fresh retry bytes");return 0;
}}
'''.replace('ACTUAL_METHODS',methods)
with tempfile.TemporaryDirectory(prefix='horos-remote-index-') as temporary:
    folder=Path(temporary);driver=folder/'main.m';driver.write_text(code);binary=folder/'probe';data=folder/'data';data.mkdir()
    build=subprocess.run(['xcrun','clang','-fno-objc-arc','-Wno-objc-method-access','-framework','Foundation',str(driver),'-o',str(binary)],capture_output=True,text=True)
    assert build.returncode==0,build.stderr
    run=subprocess.run([str(binary),str(data)],capture_output=True,text=True,timeout=20)
    assert run.returncode==0,run.stdout+run.stderr
    print(run.stdout,end='')
