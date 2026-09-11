#!/usr/bin/env python3
"""#513: native socket queues, TLS, timeout and resets on a delegate run loop.

Certificates are generated locally and imported into process memory, never the
keychain. The Python peer validates the generated certificate and response bytes.
No patients, network peers outside loopback, or persistent preferences are used.
"""
import ast
import concurrent.futures
import hashlib
import os
from pathlib import Path
import select
import socket
import ssl
import struct
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
snapshot_source = ROOT / 'tests/test-asyncsocket-reset-close.py'
tree = ast.parse(snapshot_source.read_text())
snapshot = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                and node.name == 'descriptor_snapshot')
namespace = {'subprocess': subprocess}
exec(compile(ast.Module(body=[snapshot], type_ignores=[]), str(snapshot_source), 'exec'), namespace)
descriptor_snapshot = namespace['descriptor_snapshot']

DRIVER = r'''
#import "AsyncSocket.h"
#import <Security/Security.h>
#import <fcntl.h>
#import <unistd.h>
#import <netinet/in.h>

@interface Client:NSObject { @public BOOL done; BOOL valid; }
@end
@implementation Client
- (void)onSocket:(AsyncSocket *)sock didConnectToHost:(NSString *)host port:(UInt16)port {
 [sock writeData:[@"GET / HTTP/1.1\r\nHost: localhost\r\n\r\n" dataUsingEncoding:NSUTF8StringEncoding] withTimeout:2 tag:0];
 [sock readDataToData:[@"\r\n\r\n" dataUsingEncoding:NSUTF8StringEncoding] withTimeout:2 maxLength:4096 tag:1];
 [sock readDataToLength:2 withTimeout:2 tag:2];
}
- (void)onSocket:(AsyncSocket *)sock didReadData:(NSData *)data withTag:(long)tag {
 if(tag==2){valid=[data isEqual:[@"xx" dataUsingEncoding:NSUTF8StringEncoding]];[sock disconnect];}
}
- (void)onSocketDidDisconnect:(AsyncSocket *)sock { done=YES; }
@end

@interface Listener:NSObject {
 NSMutableArray *clients;
 NSArray *identity;
 NSThread *worker;
 NSRunLoop *loop;
}
- (id)initWithIdentity:(NSArray *)value;
@end
@implementation Listener
- (id)initWithIdentity:(NSArray *)value {
 if((self=[super init])) {
  clients=[NSMutableArray new];identity=[value retain];
  worker=[[NSThread alloc]initWithTarget:self selector:@selector(work) object:nil];[worker start];
  for(;;){@synchronized(self){if(loop)break;}[NSThread sleepForTimeInterval:0.001];}
 }return self;
}
- (void)work { @autoreleasepool {
 NSRunLoop *current=[NSRunLoop currentRunLoop];
 [current addPort:[NSMachPort port] forMode:NSDefaultRunLoopMode];
 @synchronized(self){loop=[current retain];}
 [current run];
}}
- (void)onSocket:(AsyncSocket *)server didAcceptNewSocket:(AsyncSocket *)sock {
 @synchronized(clients){[clients addObject:sock];}
}
- (NSRunLoop *)onSocket:(AsyncSocket *)server wantsRunLoopForNewSocket:(AsyncSocket *)sock { return loop; }
- (void)secure:(AsyncSocket *)sock {
 [sock startTLS:@{(id)kCFStreamSSLIsServer:@YES,(id)kCFStreamSSLCertificates:identity,
  (id)kCFStreamSSLValidatesCertificateChain:@YES,
  (id)kCFStreamSSLLevel:(id)kCFStreamSocketSecurityLevelNegotiatedSSL}];
}
- (BOOL)onSocketWillConnect:(AsyncSocket *)sock {
 if(identity)[self performSelector:@selector(secure:) onThread:worker withObject:sock waitUntilDone:YES];
 return YES;
}
- (void)onSocket:(AsyncSocket *)sock didConnectToHost:(NSString *)host port:(UInt16)port {
 if([NSRunLoop currentRunLoop]!=loop)abort();
 [sock readDataToData:[@"\r\n\r\n" dataUsingEncoding:NSUTF8StringEncoding] withTimeout:0.4 maxLength:4096 tag:0];
}
- (void)onSocketDidSecure:(AsyncSocket *)sock {
 if([NSRunLoop currentRunLoop]!=loop)abort();
}
- (void)onSocket:(AsyncSocket *)sock didReadData:(NSData *)data withTag:(long)tag {
 NSString *request=[[[NSString alloc]initWithData:data encoding:NSUTF8StringEncoding]autorelease];
 NSUInteger size=[request containsString:@"/large"]?6*1024*1024:2;
 NSMutableData *body=[NSMutableData dataWithLength:size];memset(body.mutableBytes,'x',size);
 NSString *head=[NSString stringWithFormat:@"HTTP/1.1 200 OK\r\nContent-Length: %lu\r\nConnection: close\r\n\r\n",size];
 [sock writeData:[head dataUsingEncoding:NSUTF8StringEncoding] withTimeout:2 tag:1];
 [sock writeData:body withTimeout:0.5 tag:2];
 [sock disconnectAfterWriting];
}
- (void)onSocketDidDisconnect:(AsyncSocket *)sock {
 @synchronized(clients){[clients removeObject:sock];}
}
- (void)onSocket:(AsyncSocket *)sock willDisconnectWithError:(NSError *)error { NSLog(@"probe disconnect: %@",error); }
@end
int main(int argc,char **argv) { @autoreleasepool {
 if(argc>3 && !strcmp(argv[1],"client")) {
  Client *delegate=[Client new];AsyncSocket *client=[[AsyncSocket alloc]initWithDelegate:delegate];
  NSError *error=nil;BOOL started;
  if(!strcmp(argv[3],"address")) {
   struct sockaddr_in address={.sin_len=sizeof(address),.sin_family=AF_INET,.sin_port=htons(atoi(argv[2])),.sin_addr.s_addr=htonl(INADDR_LOOPBACK)};
   started=[client connectToAddress:[NSData dataWithBytes:&address length:sizeof(address)] withTimeout:2 error:&error];
  }else started=[client connectToHost:@"127.0.0.1" onPort:atoi(argv[2]) withTimeout:2 error:&error];
  NSDate *limit=[NSDate dateWithTimeIntervalSinceNow:5];
  while(started && !delegate->done && limit.timeIntervalSinceNow>0)
   [[NSRunLoop currentRunLoop]runMode:NSDefaultRunLoopMode beforeDate:limit];
  BOOL valid=delegate->valid;[client disconnect];[client release];[delegate release];
  if(!valid)fprintf(stderr,"client failed: %s\n",error.description.UTF8String);return valid?0:1;
 }
 NSArray *identity=nil;CFArrayRef imported=NULL;
 if(argc>1 && strcmp(argv[1],"plain")) {
  NSData *p12=[NSData dataWithContentsOfFile:[NSString stringWithUTF8String:argv[1]]];
  NSDictionary *options=@{(id)kSecImportExportPassphrase:@"synthetic",(id)kSecImportToMemoryOnly:@YES};
  OSStatus status=SecPKCS12Import((CFDataRef)p12,(CFDictionaryRef)options,&imported);
  if(status){fprintf(stderr,"PKCS12 import: %d\n",(int)status);return 1;}
  identity=@[[[(NSArray *)imported objectAtIndex:0] objectForKey:(id)kSecImportItemIdentity]];
 }
 if(argc>2)while(open("/dev/null",O_RDONLY)<300){}
 Listener *listener=[[Listener alloc]initWithIdentity:identity];
 AsyncSocket *server=[[AsyncSocket alloc]initWithDelegate:listener];NSError *error=nil;
 if(![server acceptOnInterface:@"localhost" port:0 error:&error])abort();
 printf("PORT %u\n",[server localPort]);fflush(stdout);
 [[NSRunLoop currentRunLoop]run];
 }return 0;
}
'''


def run(command, **kwargs):
    result = subprocess.run(command, capture_output=True, text=True, timeout=60, **kwargs)
    assert result.returncode == 0, repr(command) + '\n' + result.stderr[-4000:]
    return result


with tempfile.TemporaryDirectory(prefix='horos-native-tls-') as folder:
    work = Path(folder)
    (work / 'main.m').write_text(DRIVER)
    run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '1',
         '-subj', '/CN=localhost', '-addext', 'subjectAltName=DNS:localhost',
         '-keyout', str(work / 'key.pem'), '-out', str(work / 'cert.pem')])
    run(['openssl', 'pkcs12', '-export', '-inkey', str(work / 'key.pem'),
         '-in', str(work / 'cert.pem'), '-out', str(work / 'identity.p12'),
         '-passout', 'pass:synthetic', '-keypbe', 'PBE-SHA1-3DES', '-certpbe', 'PBE-SHA1-3DES',
         '-macalg', 'sha1'])
    run(['xcrun', 'clang', '-fno-objc-arc', '-fobjc-exceptions', '-g',
         '-fsanitize=address,undefined', '-Wno-deprecated-declarations', '-Wno-objc-method-access',
         '-I', str(ROOT / 'cocoahttpserver'), str(work / 'main.m'),
         str(ROOT / 'cocoahttpserver/AsyncSocket.m'), '-framework', 'Foundation',
         '-framework', 'CoreServices', '-framework', 'Security', '-o', str(work / 'helper')])
    trusted = ssl.create_default_context(cafile=str(work / 'cert.pem'))
    environment = dict(os.environ, ASAN_OPTIONS='abort_on_error=1:detect_leaks=0:halt_on_error=1',
                       UBSAN_OPTIONS='halt_on_error=1:print_stacktrace=1')
    for tls in (False, True):
        for high in (False, True):
            with (work / 'stderr.log').open('w+') as errors:
                server = subprocess.Popen([str(work / 'helper'), str(work / 'identity.p12') if tls else 'plain']
                                          + (['high'] if high else []), stdout=subprocess.PIPE,
                                          stderr=errors, text=True, env=environment)
                try:
                    assert select.select([server.stdout], [], [], 5)[0], 'listener did not start'
                    line = server.stdout.readline()
                    assert line.startswith('PORT '), line
                    port = int(line.split()[1])

                    def connect():
                        peer = socket.create_connection(('127.0.0.1', port), timeout=5)
                        return trusted.wrap_socket(peer, server_hostname='localhost') if tls else peer

                    def complete(large=False):
                        with connect() as peer:
                            request = b'GET /large HTTP/1.1\r\nHost: localhost\r\n\r\n' if large else b'GET / HTTP/1.1\r\nHost: localhost\r\n\r\n'
                            # Split the delimiter between writes to exercise the existing queue/prebuffer.
                            peer.sendall(request[:-1]); peer.sendall(request[-1:])
                            if large:
                                time.sleep(0.15)
                            received = bytearray()
                            while packet := peer.recv(65536):
                                received.extend(packet)
                            head, body = received.split(b'\r\n\r\n', 1)
                            expected = b'x' * (6 * 1024 * 1024 if large else 2)
                            assert hashlib.sha256(body).digest() == hashlib.sha256(expected).digest()
                            assert b'Content-Length: ' + str(len(expected)).encode() in head

                    for _ in range(8):
                        complete()
                    if not tls:
                        for mode in ('host', 'address'):
                            run([str(work / 'helper'), 'client', str(port), mode], env=environment)
                    baseline = descriptor_snapshot(server.pid)
                    complete(large=True)
                    with connect() as peer:
                        peer.sendall(b'GET / HTTP/1.1\r\n')
                        assert peer.recv(1) == b'', 'read timeout did not close'
                    # Stop consuming a large response until its write timer fires.
                    raw = socket.socket()
                    raw.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4096)
                    raw.settimeout(3)
                    raw.connect(('127.0.0.1', port))
                    slow = trusted.wrap_socket(raw, server_hostname='localhost') if tls else raw
                    with slow:
                        slow.sendall(b'GET /large HTTP/1.1\r\nHost: localhost\r\n\r\n')
                        time.sleep(0.8)
                        truncated = bytearray()
                        limit = time.monotonic() + 5
                        while packet := slow.recv(65536):
                            truncated.extend(packet)
                            assert time.monotonic() < limit, 'write timeout failed to close'
                        assert len(truncated) < 6 * 1024 * 1024, 'write timeout was not exercised'
                    if tls:
                        with socket.create_connection(('127.0.0.1', port), timeout=3) as raw:
                            try:
                                with ssl.create_default_context().wrap_socket(raw, server_hostname='localhost'):
                                    raise AssertionError('untrusted certificate accepted')
                            except ssl.SSLCertVerificationError:
                                pass

                    def reset(_):
                        with socket.create_connection(('127.0.0.1', port), timeout=5) as peer:
                            peer.sendall(b'GET / HTTP/1.1\r\nHost: localhost\r\n\r\n')
                            peer.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack('ii', 1, 0))

                    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
                        list(pool.map(reset, range(400)))
                        if tls:
                            def secure_reset(_):
                                with connect() as peer:
                                    peer.sendall(b'GET / HTTP/1.1\r\n')
                                    peer.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack('ii', 1, 0))
                            list(pool.map(secure_reset, range(60)))
                    complete()
                    deadline = time.monotonic() + 30
                    while True:
                        after = descriptor_snapshot(server.pid)
                        if after[0] <= baseline[0] and after[1] <= baseline[1] or time.monotonic() >= deadline:
                            break
                        time.sleep(0.1)
                    assert after[0] <= baseline[0] and after[1] <= baseline[1], (baseline, after)
                    assert server.poll() is None, 'server died'
                    print(f'PASS: tls={tls} high={high}, delegate thread, fragmented read, 6 MiB write, '
                          f'read/write timeouts, 400 resets' + (' + 60 TLS resets' if tls else '')
                          + f', descriptors {baseline} -> {after}', flush=True)
                finally:
                    server.terminate()
                    try:
                        server.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        server.kill(); server.wait()
                    errors.seek(0)
                    stderr = errors.read()
                    if sys.exc_info()[0]:
                        print(stderr[-4000:], file=sys.stderr)
                    assert not any(mark in stderr for mark in ('AddressSanitizer', 'UndefinedBehaviorSanitizer',
                                                              'runtime error:', 'Assertion failure')), stderr[-4000:]
