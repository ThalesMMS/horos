#!/usr/bin/env python3
"""Exercise production NSURLSession catalog transport against local HTTP and untrusted TLS."""
from pathlib import Path
import http.server
import json
import plistlib
import socket
import ssl
import subprocess
import tempfile
import threading
import time
root=Path(__file__).resolve().parent.parent
entry={'name':'Synthetic Catalog Entry','version':'1.0','download_url':'https://example.invalid/test.zip'}
class Handler(http.server.BaseHTTPRequestHandler):
 def log_message(self,*args): pass
 def do_GET(self):
  if self.path=='/timeout': time.sleep(2)
  code=503 if self.path=='/http' else 200
  data=plistlib.dumps([entry]) if self.path=='/valid' else b'[]' if self.path=='/empty' else b'{"invalid":'
  self.send_response(code);self.end_headers()
  try:self.wfile.write(data)
  except (BrokenPipeError,ConnectionResetError):pass
program=r'''
#import <Foundation/Foundation.h>
#import "HorosPluginCatalogTransport.h"
static dispatch_semaphore_t done;
static NSString *address,*expected;
static int outcome;
@interface Runner:NSObject
- (void)run;
@end
@implementation Runner
- (void)run { @autoreleasepool {
 NSError *error=nil;
 NSArray *catalog=HorosLoadPluginCatalog([NSURL URLWithString:address],0.5,&error);
 BOOL valid=NO;
 if ([expected isEqual:@"valid"]) valid=catalog.count==1 && !error;
 if ([expected isEqual:@"empty"]) valid=catalog && catalog.count==0 && !error;
 if ([expected isEqual:@"http"]) valid=!catalog && [error.domain isEqual:@"HorosPluginCatalog"] && error.code==2 && [error.localizedDescription containsString:@"503"];
 if ([expected isEqual:@"malformed"]) valid=!catalog && [error.domain isEqual:@"HorosPluginCatalog"] && error.code==3;
 if ([expected isEqual:@"timeout"]) valid=!catalog && [error.domain isEqual:NSURLErrorDomain] && error.code==NSURLErrorTimedOut;
 if ([expected isEqual:@"offline"]) valid=!catalog && [error.domain isEqual:NSURLErrorDomain] && error.code==NSURLErrorCannotConnectToHost;
 if ([expected isEqual:@"tls"]) valid=!catalog && [error.domain isEqual:NSURLErrorDomain] && (error.code==NSURLErrorServerCertificateUntrusted || error.code==NSURLErrorSecureConnectionFailed);
 if (!valid) fprintf(stderr,"Unexpected result: %s code=%ld count=%lu\n",error.domain.UTF8String,(long)error.code,(unsigned long)catalog.count);
 outcome=valid?0:1;dispatch_semaphore_signal(done);
} }
@end
int main(int argc,char **argv) { @autoreleasepool {
 address=[[NSString stringWithUTF8String:argv[1]] retain];expected=[[NSString stringWithUTF8String:argv[2]] retain];
 NSError *mainError=nil; if(HorosLoadPluginCatalog([NSURL URLWithString:address],0.5,&mainError) || mainError.code!=1) return 2;
 done=dispatch_semaphore_create(0);[NSThread detachNewThreadSelector:@selector(run) toTarget:[Runner new] withObject:nil];
 dispatch_semaphore_wait(done,DISPATCH_TIME_FOREVER);return outcome;
} }
'''
with tempfile.TemporaryDirectory(prefix='horos-catalog-network-') as directory:
 p=Path(directory);(p/'test.m').write_text(program)
 subprocess.run(['xcrun','clang','-fblocks','-framework','Foundation','-I',str(root/'Horos/Sources'),str(p/'test.m'),'-o',str(p/'test')],check=True)
 subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-days','1','-subj','/CN=localhost','-keyout',str(p/'key.pem'),'-out',str(p/'cert.pem')],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
 http_server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler)
 tls=http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler)
 context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);context.load_cert_chain(p/'cert.pem',p/'key.pem');tls.socket=context.wrap_socket(tls.socket,server_side=True)
 for server in [http_server,tls]:threading.Thread(target=server.serve_forever,daemon=True).start()
 try:
  for case in ['valid','empty','http','malformed','timeout','tls','offline']:
   port=tls.server_port if case=='tls' else http_server.server_port
   if case=='offline':
    with socket.socket() as closed:closed.bind(('127.0.0.1',0));port=closed.getsockname()[1]
   url=f'{"https" if case=="tls" else "http"}://127.0.0.1:{port}/{case}'
   subprocess.run([str(p/'test'),url,case],check=True,timeout=8)
   print('PASS:',case,flush=True)
 finally:
  for server in [http_server,tls]:server.shutdown();server.server_close()
