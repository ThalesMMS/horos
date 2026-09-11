#!/usr/bin/env python3
"""Loopback-only failure injection for a synthetic Orthanc DICOMweb fixture.

Write pass, 401, 401-wado, slow, or slow-wado to --mode-file. No request headers,
credentials, URLs or response bodies are logged. The upstream must be local.
"""
import argparse
import http.client
import http.server
import time
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode-file', type=Path, required=True)
    parser.add_argument('--port', type=int, default=18043)
    parser.add_argument('--upstream-port', type=int, default=18042)
    parser.add_argument('--delay', type=float, default=90)
    args = parser.parse_args()
    if not (1 <= args.port <= 65535 and 1 <= args.upstream_port <= 65535 and args.delay >= 0):
        parser.error('Invalid port or delay')

    class Proxy(http.server.BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_GET(self):
            try:
                mode = args.mode_file.read_text().strip()
            except OSError:
                mode = 'invalid'
            if mode not in ('pass', '401', '401-wado', 'slow', 'slow-wado'):
                self.send_response(503)
                self.send_header('Content-Length', '0')
                self.end_headers()
                return
            wado = 'multipart/' in self.headers.get('Accept', '').lower()
            if mode == '401' or (mode == '401-wado' and wado):
                self.send_response(401)
                self.send_header('Content-Length', '0')
                self.end_headers()
                return
            if mode == 'slow' or (mode == 'slow-wado' and wado):
                time.sleep(args.delay)
            upstream = http.client.HTTPConnection('127.0.0.1', args.upstream_port, timeout=10)
            try:
                upstream.request('GET', self.path, headers={
                    key: value for key, value in self.headers.items() if key.lower() != 'host'
                })
                response = upstream.getresponse()
                data = response.read()
                self.send_response(response.status)
                for key, value in response.getheaders():
                    if key.lower() not in ('connection', 'transfer-encoding', 'content-length'):
                        self.send_header(key, value)
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            except (OSError, http.client.HTTPException):
                # An intentionally cancelled client commonly closes this connection.
                pass
            finally:
                upstream.close()

    server = http.server.ThreadingHTTPServer(('127.0.0.1', args.port), Proxy)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
