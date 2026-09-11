#!/usr/bin/env python3
"""Exercise HTTP failures, timeout, cancellation and redirect isolation locally."""
import http.server, threading, time, subprocess, tempfile, json, urllib.parse
from pathlib import Path
root=Path(__file__).resolve().parents[1]
redirect_hits=[]
class Handler(http.server.BaseHTTPRequestHandler):
 def log_message(self,*args):pass
 def do_GET(self):
  path=self.path.split('?')[0]
  if path=='/redirect-target':redirect_hits.append(True)
  status={'/unauthorized':401,'/forbidden':403,'/failure':500,'/redirect':302,'/empty':204}.get(path,200)
  self.send_response(status)
  special=None
  if path in ['/paged','/repeat']:
   offset=int(urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query).get('offset',['0'])[0])
   numbers=[1] if path=='/repeat' else list(range(1,4))[offset:offset+2]
   special=json.dumps([{'0020000D':{'vr':'UI','Value':[f'2.25.{n}']}} for n in numbers]).encode()
   if path=='/repeat' or offset==0:self.send_header('Warning','299 more results')
  if path=='/redirect':self.send_header('Location','/redirect-target')
  self.send_header('Content-Type','application/dicom+json')
  body=b'[]' if status==200 else b'secret-marker-should-not-appear'
  if special is not None:body=special
  if status==204:body=b''
  self.send_header('Content-Length',str(len(body)));self.end_headers()
  if path=='/slow':time.sleep(3)
  try:self.wfile.write(body)
  except (BrokenPipeError,ConnectionResetError):pass
server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler)
threading.Thread(target=server.serve_forever,daemon=True).start()
source=r'''
import Foundation
@main struct Check {
 static func main() {
  let done=DispatchSemaphore(value:0)
  Thread.detachNewThread {
   defer{done.signal()}
   do {
    let client=try DICOMwebClient(endpoint:CommandLine.arguments[1],credentialIdentifier:"",timeout:1)
    let credentialCancel=Date().addingTimeInterval(0.2)
    do {_ = try client.authorization(cancelled:{Date()>=credentialCancel}) {Thread.sleep(forTimeInterval:2);return "secret"};fatalError("credential cancel ignored")}
    catch {precondition((error as NSError).code==NSURLErrorCancelled);precondition(Date().timeIntervalSince(credentialCancel)<0.5)}
    do {_ = try client.authorization(cancelled:{false}) {Thread.sleep(forTimeInterval:2);return "secret"};fatalError("credential timeout ignored")}
    catch {precondition((error as NSError).code==NSURLErrorTimedOut)}
    let results=try client.query(path:"studies",parameters:[:]);precondition(results.isEmpty)
    let pages=try client.query(path:"paged",parameters:[:]);precondition(pages.count==3)
    do {_ = try client.query(path:"repeat",parameters:[:]);fatalError("accepted repeated page")}
    catch {precondition((error as NSError).code==4)}
    let empty=try client.query(path:"empty",parameters:[:]);precondition(empty.isEmpty)
    for (path,expected) in [("unauthorized",401),("forbidden",403),("failure",500),("redirect",302),("slow",NSURLErrorTimedOut)] {
     do {_ = try client.query(path:path,parameters:[:]);fatalError("accepted failure")}
     catch {let e=error as NSError;precondition(e.code==expected);precondition(!String(describing:e.userInfo).contains("secret-marker"));precondition(!String(describing:e.userInfo).contains("127.0.0.1"))}
    }
    let deadline=Date().addingTimeInterval(0.2)
    do {_ = try client.query(path:"slow",parameters:[:],cancelled:{Date()>=deadline});fatalError("accepted cancellation")}
    catch {precondition((error as NSError).code==NSURLErrorCancelled)}
    for url in ["http://example.com/dicom-web","https://user:password@example.com","https://example.com?token=secret"] {
     do {_ = try DICOMwebClient(endpoint:url,credentialIdentifier:"",timeout:1);fatalError("accepted unsafe endpoint")}
     catch {}
    }
    print("PASS: QIDO/204, 401/403/500, redirects, timeout, cancellation and sanitized errors")
   } catch {print("FAIL",error);exit(1)}
  }
  done.wait()
 }
}
'''
try:
 with tempfile.TemporaryDirectory(prefix='horos-dicomweb-http-') as tmp:
  p=Path(tmp);(p/'check.swift').write_text(source)
  sources=[str(root/'Horos/Sources'/name) for name in ['DICOMwebCredentials.swift','DICOMwebMultipart.swift','DICOMwebClient.swift']]
  subprocess.run(['xcrun','swiftc','-parse-as-library',*sources,str(p/'check.swift'),'-o',str(p/'check')],check=True)
  subprocess.run([str(p/'check'),f'http://127.0.0.1:{server.server_port}'],check=True,timeout=20)
  assert not redirect_hits, 'Redirect request reached another resource'
finally:server.shutdown();server.server_close()
