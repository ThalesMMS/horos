#!/usr/bin/env python3
"""Run the actual host finalization and diagnostic code with injected cleanup errors."""
from pathlib import Path
import subprocess
import tempfile
root = Path(__file__).resolve().parents[1]
source = (root / 'Horos/Sources/HorosQueryRetrieveServer.mm').read_text()
a = source.index('        if (result == DUL_PEERREQUESTEDRELEASE)', source.index('void handleAssociation()'))
b = source.index('        database_.reset();', a)
finalize = source[a:b]
a = source.index('    void notifyDIMSEError(')
b = source.index('    void notifyAssociationRequest(', a)
report = source[a:b].replace(' override', '')
code = r'''
#import <Foundation/Foundation.h>
#include <cassert>
#include <cstring>
#include <initializer_list>
struct OFCondition {
 int value; bool bad()const{return value!=0;} int module()const{return 6;} int code()const{return value;}
 const char*text()const{return value==0?"Normal":value==1?"Peer release":value==2?"Peer abort":value==3?"Invalid PDU":"Timeout";}
 bool operator==(OFCondition rhs)const{return value==rhs.value;}
};
const OFCondition EC_Normal{0},DUL_PEERREQUESTEDRELEASE{1},DUL_PEERABORTEDASSOCIATION{2};
struct Parameters {struct {char callingAPTitle[65]="SENDER",calledAPTitle[65]="RECEIVER";} DULparams;};
struct T_ASC_Association {Parameters*params;};
static bool forkedProcess=false;static OFCondition cleanup{0};static int closes=0,releases=0,aborts=0;
static NSString *message=nil;
@interface AppController : NSObject
+(id)sharedAppController;
-(void)displayListenerError:(NSString*)value;
@end
@implementation AppController
+(id)sharedAppController{static id app=[self new];return app;}
-(void)displayListenerError:(NSString*)value{message=value;}
-(void)performSelectorOnMainThread:(SEL)selector withObject:(id)value waitUntilDone:(BOOL)wait{message=value;}
@end
OFCondition ASC_acknowledgeRelease(T_ASC_Association*){releases++;return cleanup;}
void ASC_closeTransportConnection(T_ASC_Association*){closes++;}
struct DcmSCP {void notifyDIMSEError(const OFCondition&){};};
struct Worker:DcmSCP {
 T_ASC_Association*association_;OFCondition lastFailure{0};bool cancel=false;
 bool cancelled()const{return cancel;}
 void notifyReleaseRequest(){}void notifyAbortRequest(){aborts++;}
 REPORT
 OFCondition finish(OFCondition result){FINALIZE return result;}
};
int main(){@autoreleasepool{
 Parameters parameters;T_ASC_Association association{&parameters};
 for(int failure:{2,3,4})for(int cleanupFailure:{0,4}){
  Worker worker;worker.association_=&association;cleanup={cleanupFailure};closes=aborts=releases=0;message=nil;
  assert(worker.finish({failure}).value==failure);assert(worker.lastFailure.value==failure);
  assert([message containsString:@"SENDER"] && [message containsString:@"RECEIVER"]);
  assert([message containsString:[NSString stringWithUTF8String:worker.lastFailure.text()]]);
  assert(![message containsString:@"Normal"]);assert(closes==(failure==2?0:1));assert(aborts==(failure==2?1:0));
 }
 Worker worker;worker.association_=&association;message=nil;cleanup=EC_Normal;releases=closes=0;
 assert(worker.finish(DUL_PEERREQUESTEDRELEASE).value==0);assert(message==nil);assert(releases==1&&closes==0);
 worker.cancel=true;assert(worker.finish(EC_Normal).value==0);assert(message==nil);assert(closes==1);
 puts("PASS: original peer/DIMSE failures survive cleanup; native feedback names both AEs; release and cancellation retain their semantics");
}}
'''.replace('REPORT', report).replace('FINALIZE', finalize)
with tempfile.TemporaryDirectory(prefix='horos-listener-result-') as folder:
    folder=Path(folder);(folder/'test.mm').write_text(code)
    subprocess.run(['xcrun','clang++','-std=c++11','-framework','Foundation',str(folder/'test.mm'),'-o',str(folder/'test')],check=True)
    subprocess.run([str(folder/'test')],check=True)

fork = source[source.index('if (!options_.singleProcess_)'):source.index('// Poll before receiving commands')]
assert 'initWithDatabase:database concurrencyType:NSConfinementConcurrencyType' in fork
assert fork.index('fork()') < fork.index('addPersistentStoreWithType:')
assert 'NSReadOnlyPersistentStoreOption:@YES' in fork
assert '[database save]' not in fork
print('PASS: fork keeps database path ownership and opens its read-only SQLite store only in the child')
