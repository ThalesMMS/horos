"""HTTP servers for local fixtures, which bind without asking the DNS (#647).

`http.server.HTTPServer.server_bind` calls `socket.getfqdn(host)` to fill
`server_name`. On a Mac whose reverse resolution of 127.0.0.1 has nowhere to go,
that call takes 35 s, and every fixture paid it before it could listen:
`tests/test-hierarchical-image-query.py` gave up at 30 s with an empty log, and the
others merely took 35 s longer each.

A fixture that listens on a loopback address has nothing to ask a resolver. These
servers bind through `socketserver.TCPServer` and take `server_name` from the
address they were given, which is what `Host:` needs.

    from local_http import LocalHTTPServer, ThreadingLocalHTTPServer
    server = ThreadingLocalHTTPServer(('127.0.0.1', 0), Handler)
"""
import http.server
import socketserver


class LocalHTTPServer(http.server.HTTPServer):
    def server_bind(self):
        socketserver.TCPServer.server_bind(self)
        host, port = self.server_address[:2]
        self.server_name = host
        self.server_port = port


class ThreadingLocalHTTPServer(socketserver.ThreadingMixIn, LocalHTTPServer):
    daemon_threads = True
