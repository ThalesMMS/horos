#!/usr/bin/env python3
"""Loopback-only fault proxy: truncate DATAB while preserving negotiation."""
import argparse
import socket
import threading
import struct
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--port',type=int,default=11282)
p.add_argument('--target-port',type=int,default=11280)
p.add_argument('--bytes',type=int,default=1024)
p.add_argument('--reset-once',action='store_true')
p.add_argument('--legacy',action='store_true',help='simulate an older protected server without AUTHV')
a=p.parse_args()
lock=threading.Lock()
transfers=0
def request(client):
    global transfers
    with client, socket.create_connection(('127.0.0.1',a.target_port)) as upstream:
        command=b''
        while len(command)<6:
            data=client.recv(6-len(command))
            if not data:return
            command+=data
        if a.legacy:
            print('legacy command '+command[:5].decode('ascii',errors='replace'),flush=True)
            if command==b'AUTHV\0':return
        header=command
        if command==b'AUTHR\0':
            def exact(count):
                result=b''
                while len(result)<count:
                    chunk=client.recv(count-len(result))
                    if not chunk:raise OSError('incomplete authorization envelope')
                    result+=chunk
                return result
            size=exact(4);length=int.from_bytes(size,'big')
            if not 0<length<=4096:return
            envelope=exact(length+6)
            header+=size+envelope
            command=envelope[-6:]
        upstream.sendall(header)
        def forward():
            try:
                while data:=client.recv(65536):upstream.sendall(data)
            except OSError:pass
        if command==b'PASWD\0':threading.Thread(target=forward,daemon=True).start()
        with lock:
            if command==b'DATAB\0':transfers+=1
            first=transfers==1
        remaining=a.bytes if command==b'DATAB\0' and (not a.reset_once or first) else None
        try:
            while data:=upstream.recv(65536):
                if remaining is not None:
                    data=data[:remaining];remaining-=len(data)
                client.sendall(data)
                if remaining==0:
                    print('truncated DATAB after %d bytes'%a.bytes,flush=True)
                    if a.reset_once:
                        client.setsockopt(socket.SOL_SOCKET,socket.SO_LINGER,struct.pack('ii',1,0))
                    else:client.shutdown(socket.SHUT_RDWR)
                    return
        except OSError:pass
server=socket.socket();server.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
server.bind(('127.0.0.1',a.port));server.listen()
print('shared-index fault proxy ready',flush=True)
while True:
    client,_=server.accept();threading.Thread(target=request,args=(client,),daemon=True).start()
