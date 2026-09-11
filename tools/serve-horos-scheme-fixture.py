#!/usr/bin/env python3
"""Loopback page for the native #299 acceptance; contains synthetic identifiers only."""
import argparse
import html
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from urllib.parse import urlencode

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--port', type=int, default=0)
args = parser.parse_args()
patient = 'LOCAL-URL+QA&é Тест'
url = 'horos://?' + urlencode({'methodName': 'DisplayStudy', 'PatientID': patient})
# Horos intentionally keeps '+' literal for image= SOP separators; encode spaces.
url = url.replace('+', '%20')


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        page = '''<!doctype html><meta charset="utf-8"><title>Horos URL acceptance</title>
<h1>Horos URL acceptance — synthetic local study</h1>
<p>Use only with the isolated development database and restore the original handler afterwards.</p>
<p><a href="{{URL}}">Open synthetic study by encoded PatientID</a></p>
<p><button onclick='location.href={{JS_URL}}'>Open through JavaScript with a user gesture</button></p>
<p><a href="horos://?methodName=DisplayStudy">Reject missing identifiers</a></p>
<p><a href="/automatic">Navigate automatically after page load</a></p>
<p id="activation">Automatic navigation has not run.</p>
'''.replace('{{JS_URL}}', html.escape(json.dumps(url), quote=True)).replace('{{URL}}', html.escape(url, quote=True))
        if self.path == '/automatic':
            page += '''<script>setTimeout(() => {
document.getElementById('activation').textContent =
    'Before automatic navigation: isActive=' + navigator.userActivation.isActive +
    ', hasBeenActive=' + navigator.userActivation.hasBeenActive;
location.href = ''' + json.dumps(url) + '; }, 1500);</script>'
        data = page.encode()
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass


server = HTTPServer(('127.0.0.1', args.port), Handler)
print(f'http://127.0.0.1:{server.server_port}/', flush=True)
server.serve_forever()
