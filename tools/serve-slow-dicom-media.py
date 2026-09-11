#!/usr/bin/env python3
"""Serve a synthetic fixture as a read-only loopback WebDAV volume with delayed reads.

Install wsgidav and cheroot in a local virtual environment. Mount with macOS
mount_webdav -S -o rdonly http://127.0.0.1:18074/ <empty-local-mountpoint>.
Use generated synthetic data only. Evidence records GET paths, chunk counts and
elapsed seconds; keep it local with the fixture.
"""
import argparse
import json
import math
import time
from pathlib import Path

from cheroot import wsgi
from wsgidav.fs_dav_provider import FilesystemProvider
from wsgidav.wsgidav_app import WsgiDAVApp


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('fixture', type=Path)
    parser.add_argument('--delay-file', type=Path, required=True,
                        help='Seconds to delay each GET chunk; read on every chunk')
    parser.add_argument('--evidence', type=Path, required=True)
    parser.add_argument('--port', type=int, default=18074)
    args = parser.parse_args()
    if not args.fixture.is_dir() or not 1 <= args.port <= 65535:
        parser.error('Invalid fixture directory or port')
    app = WsgiDAVApp({
        'provider_mapping': {'/': FilesystemProvider(str(args.fixture.resolve()), readonly=True)},
        'simple_dc': {'user_mapping': {'*': True}},
        'http_authenticator': {'domain_controller': None},
        'verbose': 0,
    })

    def slow(environ, start_response):
        result = app(environ, start_response)
        started = time.monotonic()
        chunks = 0
        try:
            for data in result:
                if environ['REQUEST_METHOD'] == 'GET':
                    delay = float(args.delay_file.read_text())
                    if not math.isfinite(delay) or not 0 <= delay <= 10:
                        raise ValueError('Delay must be between 0 and 10 seconds')
                    time.sleep(delay)
                    chunks += 1
                yield data
        finally:
            if hasattr(result, 'close'):
                result.close()
            if environ['REQUEST_METHOD'] == 'GET':
                record = {'path': environ['PATH_INFO'], 'chunks': chunks,
                          'seconds': time.monotonic() - started}
                with args.evidence.open('a') as stream:
                    stream.write(json.dumps(record) + '\n')

    server = wsgi.Server(('127.0.0.1', args.port), slow)
    try:
        server.start()
    except KeyboardInterrupt:
        pass
    finally:
        server.stop()


if __name__ == '__main__':
    main()
