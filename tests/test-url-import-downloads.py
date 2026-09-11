#!/usr/bin/env python3
"""Exercise production Swift downloads against stalled, slow and failed HTTP peers."""
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import subprocess
import tempfile
import threading
import time

root = Path(__file__).resolve().parents[1]
class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_): pass
    def do_GET(self):
        if self.path == '/never':
            time.sleep(10)
            return
        if self.path == '/trickle':
            self.send_response(200)
            self.send_header('Content-Length', '20')
            self.end_headers()
            try:
                for _ in range(20):
                    self.wfile.write(b'x')
                    self.wfile.flush()
                    time.sleep(.2)
            except (BrokenPipeError, ConnectionResetError): pass
            return
        if self.path == '/slow': time.sleep(.3)
        self.send_response(503 if self.path == '/error' else 200)
        self.end_headers()
        try: self.wfile.write(self.path.encode())
        except BrokenPipeError: pass
server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
threading.Thread(target=server.serve_forever, daemon=True).start()
driver = r'''
import Foundation
let base = CommandLine.arguments[1]
let batch = URLImportDownloads(urls: ["never", "fast", "slow", "error"].map { URL(string: base + "/" + $0)! }, requestTimeout: 1, totalTimeout: 2)
let start = Date()
var results: [Int: URLImportDownloadResult] = [:]
while !batch.finished {
    if let result = batch.nextResult() {
        results[result.index] = result
        if result.index == 1 {
            precondition(results[0] == nil, "fast URL waited for stalled URL")
            precondition(result.data == Data("/fast".utf8))
        }
    }
}
precondition(results.count == 4)
precondition(results[0]?.error?.code == NSURLErrorTimedOut)
precondition(results[0]?.error?.localizedDescription.contains("limit") == true)
precondition(results[2]?.data == Data("/slow".utf8))
precondition(results[3]?.error?.code == NSURLErrorBadServerResponse)
let trickle = URLImportDownloads(urls: [URL(string: base + "/trickle")!], requestTimeout: 1, totalTimeout: 2)
var capped = false
while !trickle.finished {
    if let result = trickle.nextResult() { capped = result.error?.code == NSURLErrorTimedOut }
}
precondition(capped, "continuous traffic bypassed the total timeout")
let cancelled = URLImportDownloads(urls: [URL(string: base + "/never")!], requestTimeout: 10, totalTimeout: 20)
let cancelStart = Date()
cancelled.cancel()
precondition(cancelled.nextResult()?.error?.code == NSURLErrorCancelled)
precondition(cancelled.finished)
precondition(Date().timeIntervalSince(cancelStart) < 0.5)
let closed = URLImportDownloads(urls: [URL(string: "http://127.0.0.1:1/")!], requestTimeout: 1, totalTimeout: 2)
var failed = false
while !closed.finished {
    if let result = closed.nextResult() { failed = result.error != nil && result.data == nil }
}
precondition(failed)
print("ok: fast and slow downloads, timeout, HTTP failure, closed port and cancellation")
'''
try:
    with tempfile.TemporaryDirectory(prefix='horos-url-downloads-') as tmp:
        path = Path(tmp)
        (path/'main.swift').write_text(driver)
        subprocess.run(['xcrun', 'swiftc', str(root/'Horos/Sources/URLImportDownloads.swift'), str(path/'main.swift'), '-o', str(path/'test')], check=True)
        subprocess.run([str(path/'test'), f'http://127.0.0.1:{server.server_port}'], check=True, timeout=15)
finally:
    server.shutdown()

# Both event-loop entry points must await completion without synchronously downloading.
browser = (root/'Horos/Sources/BrowserController.m').read_text(encoding='latin1')
scripting = (root/'Horos/Sources/Scripting_Additions.m').read_text(encoding='latin1')
sheet = browser.split('- (void)addURLToDatabaseEnd: (id)sender', 1)[1].split('- (void)addURLToDatabase:', 1)[0]
assert 'importURLs:' in sheet and 'addURLToDatabaseFiles:' not in sheet
command = scripting.split('if( [command isEqualToString:@"DownloadURLFile"])', 1)[1].split('if( [command isEqualToString:@"OpenViewerForSelected"])', 1)[0]
assert '[self suspendExecution]' in command
assert '[self resumeExecutionWithResult: files]' in command
assert 'importURLs:' in command and 'addURLToDatabaseFiles:' not in command

import xml.etree.ElementTree as ET
command_definition = ET.parse(root/'Horos/Resources/Horos.sdef').find(".//command[@name='DownloadURLFile']")
assert command_definition.find('result/type').attrib['type'] == 'text'
assert command_definition.find('result/type').attrib['list'] == 'yes'
