#!/usr/bin/env python3
"""Compile the real send context and exercise concurrent ownership and cleanup."""
from pathlib import Path
import subprocess,tempfile
root=Path(__file__).resolve().parents[1]
s=(root/'Horos/Sources/DCMTKStoreSCU.mm').read_text(encoding='latin1')
a=s.index('struct StoreSendContext {');o=s.index('{',a);depth=1;j=o+1
while depth:
 if s[j]=='{':depth+=1
 elif s[j]=='}':depth-=1
 j+=1
context=s[a:j+1]
code=r'''
#import <Foundation/Foundation.h>
#include <thread>
#include <string>
#include <type_traits>
#include <memory>
#include <cassert>
typedef bool OFBool;const bool OFTrue=true,OFFalse=false;
typedef unsigned long OFCmdUnsignedInt;typedef int E_TransferSyntax;
typedef int T_DIMSE_BlockingMode;
const int DIMSE_NONBLOCKING=1,ASC_DEFAULTMAXPDU=16384,STATUS_Success=0,EXS_LittleEndianExplicit=2;
#define WITH_OPENSSL 1
#define OPENSSL_VERSION_NUMBER 0x10101000L
#define TLS1_TXT_RSA_WITH_AES_128_SHA "fixture-a"
#define SSL3_TXT_RSA_DES_192_CBC3_SHA "fixture-b"
typedef std::string OFString;
@class HorosStoreReport;
ACTUAL_CONTEXT
static_assert(!std::is_copy_constructible<StoreSendContext>::value,"context ownership cannot be copied");
int main(int argc,char**argv){@autoreleasepool{
 NSString *root=@(argv[1]),*a=[root stringByAppendingPathComponent:@"a"],*b=[root stringByAppendingPathComponent:@"b"];
 for(NSString *path in @[a,b])[NSFileManager.defaultManager createDirectoryAtPath:path withIntermediateDirectories:YES attributes:nil error:NULL];
 auto first=std::unique_ptr<StoreSendContext>(new StoreSendContext());
 auto second=std::unique_ptr<StoreSendContext>(new StoreSendContext());
 first->temporaryDirectory=[a retain];second->temporaryDirectory=[b retain];
 first->opt_dimse_timeout=3;second->opt_dimse_timeout=7;
 auto exercise=[](StoreSendContext *c,int identity){for(int i=0;i<20000;i++){c->opt_Quality=identity;c->opt_networkTransferSyntax=identity;c->lastStatusCode=identity;std::this_thread::yield();assert(c->opt_Quality==identity&&c->lastStatusCode==identity&&c->opt_networkTransferSyntax==identity);}};
 std::thread t1(exercise,first.get(),1),t2(exercise,second.get(),2);t1.join();t2.join();
 assert(first->opt_dimse_timeout==3&&second->opt_dimse_timeout==7);
 NSString *fa=[a stringByAppendingPathComponent:@"0.dcm"],*fb=[b stringByAppendingPathComponent:@"0.dcm"];
 [@"a" writeToFile:fa atomically:YES encoding:NSUTF8StringEncoding error:NULL];[@"b" writeToFile:fb atomically:YES encoding:NSUTF8StringEncoding error:NULL];
 first.reset();assert(![NSFileManager.defaultManager fileExistsAtPath:a]);assert([[NSString stringWithContentsOfFile:fb encoding:NSUTF8StringEncoding error:NULL] isEqualToString:@"b"]);
 second.reset();assert(![NSFileManager.defaultManager fileExistsAtPath:b]);
 [NSFileManager.defaultManager createDirectoryAtPath:a withIntermediateDirectories:YES attributes:nil error:NULL];
 try {StoreSendContext failing;failing.temporaryDirectory=[a retain];throw 1;}catch(int){}
 assert(![NSFileManager.defaultManager fileExistsAtPath:a]);
 puts("ok: concurrent per-send options, independent timeouts, unique namespaces and exception cleanup");
}}
'''.replace('ACTUAL_CONTEXT',context)
with tempfile.TemporaryDirectory(prefix='horos-store-context-') as t:
 p=Path(t);(p/'main.mm').write_text(code)
 r=subprocess.run(['xcrun','clang++','-std=c++11','-fno-objc-arc','-framework','Foundation',str(p/'main.mm'),'-o',str(p/'probe')],capture_output=True,text=True)
 assert r.returncode==0,r.stderr
 r=subprocess.run([str(p/'probe'),str(p)],capture_output=True,text=True,timeout=20);assert r.returncode==0,r.stdout+r.stderr
 print(r.stdout,end='')
for name in ('addStoragePresentationContexts','compressFile','storeSCU','cstore'):
 assert name+'(StoreSendContext &context,' in s,name
assert 'progressCallback, &context,' in s and 'StoreSendContext context;' in s
assert 'NSString *storedPath = sourcePath;' in s
assert 'static long seed' not in s and 'static HorosStoreReport *storeReport' not in s
print('ok: helpers/callback receive context and reports keep original file paths')

assert "static DcmTLSTransportLayer" not in s and "opt_ciphersuites" not in s
assert "DcmTLSTransportLayer *tLayer = NULL;" in s
assert "HorosConfigureTLSCipherSuites(*tLayer, _cipherSuites)" in s
