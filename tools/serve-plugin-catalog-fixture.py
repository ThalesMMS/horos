#!/usr/bin/env python3
"""Loopback-only catalog fixture for native Plugin Manager validation; never serves plugins."""
import argparse
import http.server
import json
import plistlib
from pathlib import Path
import ssl
import time
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('mode_file',type=Path,help='Local text file: valid, empty, malformed, http, timeout')
parser.add_argument('--port',type=int,default=15963)
parser.add_argument('--cert',type=Path)
parser.add_argument('--key',type=Path)
args=parser.parse_args()
class Handler(http.server.BaseHTTPRequestHandler):
 def log_message(self,*args):pass
 def do_GET(self):
  mode=args.mode_file.read_text().strip()
  if mode=='timeout':time.sleep(12)
  if mode=='valid':body=plistlib.dumps([{'name':'Synthetic Catalog Entry','version':'1.0','download_url':'http://127.0.0.1:1/never-install.horosplugin.zip','url':'about:blank'}])
  elif mode=='empty':body=b'[]'
  else:body=b'{malformed'
  self.send_response(503 if mode=='http' else 200);self.end_headers()
  try:self.wfile.write(body)
  except (BrokenPipeError,ConnectionResetError):pass
server=http.server.ThreadingHTTPServer(('127.0.0.1',args.port),Handler)
if args.cert:
 context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);context.load_cert_chain(args.cert,args.key);server.socket=context.wrap_socket(server.socket,server_side=True)
print(f'Catalog fixture on loopback port {server.server_port}',flush=True)
try:server.serve_forever()
except KeyboardInterrupt:pass
finally:server.server_close()
