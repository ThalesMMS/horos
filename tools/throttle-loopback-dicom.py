#!/usr/bin/env python3
"""Loopback-only TCP relay for a synthetic C-STORE in-progress cancellation test."""
import argparse
import socket
import threading
import time
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--port',type=int,default=11273)
p.add_argument('--target-port',type=int,default=11272)
p.add_argument('--delay',type=float,default=.02)
p.add_argument('--reverse-delay',type=float,default=0)
args=p.parse_args()
def relay(source,destination,delay):
    try:
        while data:=source.recv(16384):
            if delay:time.sleep(delay)
            destination.sendall(data)
    except OSError:pass
    finally:
        try:destination.shutdown(socket.SHUT_WR)
        except OSError:pass
def connection(source):
    with source, socket.create_connection(('127.0.0.1',args.target_port)) as destination:
        back=threading.Thread(target=relay,args=(destination,source,args.reverse_delay),daemon=True);back.start()
        relay(source,destination,args.delay);back.join()
s=socket.socket();s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
s.bind(('127.0.0.1',args.port));s.listen()
while True:
    source,_=s.accept();threading.Thread(target=connection,args=(source,),daemon=True).start()
