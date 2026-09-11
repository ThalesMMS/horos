#!/usr/bin/env python3
"""#513 regression: reset cleanup must preserve another owner and free its alias.

The wrapper allocates a foreign pipe at the transport opening boundary, then
calls the real readiness API on a loopback peer that has sent RST. A historical
source argument uses CFReadStreamOpen at the same boundary. Both low and high
descriptors run under ASan/UBSan. A second close must preserve a reused FD too.
"""
from pathlib import Path
import os
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else ROOT / 'cocoahttpserver/AsyncSocket.m'
HEADER = Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else ROOT / 'cocoahttpserver/AsyncSocket.h'
DRIVER = r'''
#import "AsyncSocket.h"
#import <Foundation/Foundation.h>
#import <CFNetwork/CFNetwork.h>
#import <libproc.h>
#import <pthread.h>
#import <sys/socket.h>
#import <netinet/in.h>
#import <fcntl.h>
#import <signal.h>
#import <poll.h>
#import <unistd.h>
static int foreignPipe[2]={-1,-1};
static pthread_mutex_t mutex=PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t cond=PTHREAD_COND_INITIALIZER;
static int state=0;
static void *otherOwner(void *unused) {
 pthread_mutex_lock(&mutex);
 while(state==0)pthread_cond_wait(&cond,&mutex);
 if(pipe(foreignPipe)!=0)abort();
 state=2;pthread_cond_signal(&cond);
 while(state==2)pthread_cond_wait(&cond,&mutex);
 close(foreignPipe[0]);close(foreignPipe[1]);pthread_mutex_unlock(&mutex);return NULL;
}
// Redirect only the opening boundary. Never close FDs found by the observer.
static void allocateOtherOwner(void) {
 pthread_mutex_lock(&mutex);if(state!=0){pthread_mutex_unlock(&mutex);return;}
 state=1;pthread_cond_signal(&cond);
 while(state!=2)pthread_cond_wait(&cond,&mutex);
 pthread_mutex_unlock(&mutex);
}
Boolean ProbeCFReadStreamOpen(CFReadStreamRef stream) { allocateOtherOwner(); return CFReadStreamOpen(stream); }
int ProbePoll(struct pollfd *fds, nfds_t count, int timeout) { allocateOtherOwner(); return poll(fds,count,timeout); }
@interface AsyncSocket (ProbePrivate)
- (BOOL)createStreamsFromNative:(CFSocketNativeHandle)native error:(NSError **)error;
- (BOOL)openStreamsAndReturnError:(NSError **)error;
- (void)close;
@end
static void *closeOtherThread(void *sock) { @autoreleasepool {[(AsyncSocket *)sock close];} return NULL; }
@interface AdoptedSocket:AsyncSocket
- (BOOL)adopt:(int)fd;
@end
@implementation AdoptedSocket
- (BOOL)adopt:(int)fd {theNativeSocket4=fd;return [self createStreamsFromNative:fd error:NULL];}
@end
static uint64_t identity(int fd) {
 struct socket_fdinfo info={0};
 return proc_pidfdinfo(getpid(),fd,PROC_PIDFDSOCKETINFO,&info,sizeof(info))==sizeof(info)?info.psi.soi_so:0;
}
static int aliases(uint64_t target) {
 struct proc_fdinfo descriptors[2048];int count=proc_pidinfo(getpid(),PROC_PIDLISTFDS,0,descriptors,sizeof(descriptors)),found=0;
 for(int i=0;i<count/(int)sizeof(*descriptors);i++)if(descriptors[i].proc_fdtype==PROX_FDTYPE_SOCKET && identity(descriptors[i].proc_fd)==target)found++;
 return found;
}
int main(int argc,char **argv) { @autoreleasepool {
 signal(SIGPIPE,SIG_IGN);
 BOOL opening=NO,high=NO;
 for(int i=1;i<argc;i++){if(!strcmp(argv[i],"opened"))opening=YES;if(!strcmp(argv[i],"high"))high=YES;}
 int fillers[512],filled=0;
 if(high)while(filled<512){int fd=open("/dev/null",O_RDONLY);if(fd<0)abort();fillers[filled++]=fd;if(fd>=300)break;}
 int listener=socket(AF_INET,SOCK_STREAM,0),client=socket(AF_INET,SOCK_STREAM,0);
 struct sockaddr_in a={.sin_len=sizeof(a),.sin_family=AF_INET,.sin_addr.s_addr=htonl(INADDR_LOOPBACK)};socklen_t length=sizeof(a);
 if(bind(listener,(void*)&a,sizeof(a))||listen(listener,1)||getsockname(listener,(void*)&a,&length)||connect(client,(void*)&a,length))abort();
 int native=accept(listener,NULL,NULL);if(native<0)abort();close(listener);
 uint64_t socketIdentity=identity(native);if(!socketIdentity)abort();
 AdoptedSocket *sock=[[AdoptedSocket alloc]init];if(![sock adopt:native])abort();
 struct linger linger={1,0};setsockopt(client,SOL_SOCKET,SO_LINGER,&linger,sizeof(linger));if(!opening)close(client);
 pthread_t thread;if(pthread_create(&thread,NULL,otherOwner,NULL))abort();
 BOOL opened=[sock openStreamsAndReturnError:NULL];
 if(opening){
  [[NSRunLoop currentRunLoop]runUntilDate:[NSDate dateWithTimeIntervalSinceNow:0.02]];
  close(client);
  pthread_t closers[2];for(int i=0;i<2;i++)if(pthread_create(&closers[i],NULL,closeOtherThread,sock))abort();
  for(int i=0;i<2;i++)pthread_join(closers[i],NULL);
 }else [sock disconnect];
 char sent='x',received=0;
 BOOL otherIntact=write(foreignPipe[1],&sent,1)==1 && read(foreignPipe[0],&received,1)==1 && received==sent;
 int leaked=aliases(socketIdentity);
 printf("original_fd=%d open=%d foreign_fd=%d other_intact=%d aliases_after_close=%d\n",native,opened,foreignPipe[0],otherIntact,leaked);
 // Force reuse of the exact original number after cleanup. A second close
 // (including dealloc) must not close this new owner.
 int replacement=open("/dev/null",O_RDONLY);if(replacement<0)abort();
 if(replacement!=native){if(dup2(replacement,native)!=native)abort();close(replacement);}
 [sock disconnect];[sock release];
 BOOL reusedIntact=fcntl(native,F_GETFD)!=-1;close(native);
 printf("reused_original_preserved=%d\n",reusedIntact);
 pthread_mutex_lock(&mutex);state=3;pthread_cond_signal(&cond);pthread_mutex_unlock(&mutex);pthread_join(thread,NULL);
 for(int i=0;i<filled;i++)close(fillers[i]);
 if(opened!=opening || !otherIntact || !reusedIntact || leaked){fprintf(stderr,"FAIL: reset cleanup must preserve the other owner and release its own socket\n");return 1;}
 }return 0;}
'''

with tempfile.TemporaryDirectory(prefix='horos-socket-ownership-') as tmp:
    work = Path(tmp)
    (work / 'main.m').write_text(DRIVER)
    (work / 'AsyncSocket.m').write_text(SOURCE.read_text())
    (work / 'AsyncSocket.h').write_text(HEADER.read_text())
    common = ['xcrun', 'clang', '-fno-objc-arc', '-fobjc-exceptions', '-g',
              '-fsanitize=address,undefined', '-Wno-deprecated-declarations',
              '-Wno-objc-method-access', '-I', str(work)]
    subprocess.run(common + [('-DCFReadStreamOpen=ProbeCFReadStreamOpen' if 'rememberFailedOpenCopiedNative' in SOURCE.read_text() else '-Dpoll=ProbePoll'), '-c',
                              str(work / 'AsyncSocket.m'), '-o', str(work / 'AsyncSocket.o')],
                   check=True, capture_output=True, text=True, timeout=60)
    subprocess.run(common + [str(work / 'main.m'), str(work / 'AsyncSocket.o'),
                              '-framework', 'Foundation', '-framework', 'CoreServices', '-framework', 'Security',
                              '-o', str(work / 'probe')],
                   check=True, capture_output=True, text=True, timeout=60)
    environment = dict(os.environ,
                       ASAN_OPTIONS='abort_on_error=1:detect_leaks=0:halt_on_error=1',
                       UBSAN_OPTIONS='halt_on_error=1:print_stacktrace=1')
    failures = 0
    for arguments in ([], ['high'], ['opened'], ['high', 'opened']):
        result = subprocess.run([str(work / 'probe')] + arguments, env=environment,
                                capture_output=True, text=True, timeout=8)
        print(result.stdout.strip())
        if result.returncode:
            failures += 1
            print(result.stderr.strip(), file=sys.stderr)
    if failures:
        raise SystemExit(1)
print('PASS: reset frees its own socket and preserves the other descriptor owner')
