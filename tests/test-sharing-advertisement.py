#!/usr/bin/env python3
"""Run the actual Bonjour advertisement lifecycle with controlled publication."""
from pathlib import Path
import subprocess,tempfile
root=Path(__file__).resolve().parents[1]
source=(root/'Horos/Sources/BonjourPublisher.m').read_text(encoding='latin1')
def method(signature):
 start=source.index(signature);opening=source.index('{',start);depth=0
 for end in range(opening,len(source)):
  if source[end]=='{':depth+=1
  elif source[end]=='}':
   depth-=1
   if depth==0:return source[start:end+1]
code=r'''
#import <Foundation/Foundation.h>
@interface NSUserDefaults(Probe)
+ (NSString*)bonjourSharingName;
@end
@implementation NSUserDefaults(Probe)
+ (NSString*)bonjourSharingName{return @"synthetic sharing";}
@end
@interface AppController:NSObject
+ (NSString*)UID;
@end
@implementation AppController
+ (NSString*)UID{return @"synthetic";}
@end
@interface Listener:NSObject
@property NSInteger port;
@end
@implementation Listener
@end
@interface FakeService:NSObject
@property NSInteger port;
@property(assign) id delegate;
@property BOOL published;
- (id)initWithDomain:(id)d type:(id)t name:(id)n port:(NSInteger)p;
+ (NSData*)dataFromTXTRecordDictionary:(id)d;
- (BOOL)setTXTRecordData:(id)d;
- (void)publish;- (void)stop;
@end
@implementation FakeService
- (id)initWithDomain:(id)d type:(id)t name:(id)n port:(NSInteger)p{self=[super init];self.port=p;return self;}
+ (NSData*)dataFromTXTRecordDictionary:(id)d{return [NSData data];}
- (BOOL)setTXTRecordData:(id)d{return YES;}
- (void)publish{self.published=YES;}
- (void)stop{self.published=NO;}
@end
#define NSNetService FakeService
@interface BonjourPublisher:NSObject {
@public Listener *_listener;FakeService *_bonjour;
}
- (void)updateBonjour;
- (void)netService:(NSNetService*)sender didNotPublish:(NSDictionary*)errorDict;
@end
@implementation BonjourPublisher
ACTUAL_METHODS
@end
int main(){@autoreleasepool{
 BonjourPublisher *p=[BonjourPublisher new];[p updateBonjour];
 NSCAssert(p->_bonjour==nil,@"disabled startup must not reserve a zero-port service");
 p->_listener=[Listener new];p->_listener.port=8780;[p updateBonjour];
 NSCAssert(p->_bonjour.port==8780 && p->_bonjour.published,@"first activation advertises live port");
 FakeService *old=[p->_bonjour retain];p->_listener=nil;[p updateBonjour];
 NSCAssert(p->_bonjour==nil && !old.published && !old.delegate,@"disable stops and releases service");
 p->_listener=[Listener new];p->_listener.port=8781;[p updateBonjour];
 NSCAssert(p->_bonjour.port==8781,@"reenable uses new endpoint");
 [p netService:old didNotPublish:@{}];
 NSCAssert(p->_bonjour.port==8781,@"stale failure must not clear new service");
 [p netService:p->_bonjour didNotPublish:@{}];NSCAssert(p->_bonjour==nil,@"failure clears service");
 [p updateBonjour];NSCAssert(p->_bonjour.port==8781 && p->_bonjour.published,@"recovery publishes live endpoint");
 [old release];puts("ok: disabled startup, real port, disable, changed port, stale failure and recovery");
}}
'''.replace('ACTUAL_METHODS','\n'.join(method(s) for s in ('- (void)updateBonjour {','- (void)netService:(NSNetService*)sender didNotPublish:')))
with tempfile.TemporaryDirectory(prefix='horos-sharing-') as t:
 p=Path(t);(p/'main.m').write_text(code)
 r=subprocess.run(['xcrun','clang','-fno-objc-arc','-framework','Foundation',str(p/'main.m'),'-o',str(p/'probe')],capture_output=True,text=True)
 assert r.returncode==0,r.stderr
 r=subprocess.run([str(p/'probe')],capture_output=True,text=True,timeout=10)
 assert r.returncode==0,r.stdout+r.stderr
 print(r.stdout,end='')
