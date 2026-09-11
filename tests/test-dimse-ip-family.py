#!/usr/bin/env python3
"""Real C-ECHO over both IP families and DNS fallback, using the linked DCMTK."""
from pathlib import Path
import socket
import subprocess
import tempfile
from dcmtk_build import ROOT, dcmtk_flags

code = r'''
#include "HorosDIMSEAssociation.h"
#include <dcmtk/dcmnet/dimse.h>
#include <dcmtk/dcmdata/dcuid.h>
#include <cassert>
#include <cstdio>
#include <cstring>
void checked(OFCondition status) { if(status.bad()){fprintf(stderr,"%s\n",status.text());exit(1);} }
int main(int argc,char **argv) {
 assert(argc==4); const int port=atoi(argv[3]);
 T_ASC_Network *network=NULL;
 if(strcmp(argv[1],"server")==0) {
  dcmIncomingProtocolFamily.set(ASC_AF_UNSPEC);
  checked(ASC_initializeNetwork(NET_ACCEPTOR, port, 5, &network));
  puts("READY");fflush(stdout);
  for(int index=0;index<3;index++) {
   T_ASC_Association *association=NULL;void *pdu=NULL;unsigned long size=0;
   checked(ASC_receiveAssociation(network,&association,ASC_DEFAULTMAXPDU,&pdu,&size,OFFalse,DUL_BLOCK,5));
   checked(HorosDIMSEValidateAssociationPDU(pdu,size));free(pdu);
   const char *transfer[]={UID_LittleEndianExplicitTransferSyntax,UID_LittleEndianImplicitTransferSyntax};
   const char *services[]={UID_VerificationSOPClass};
   checked(ASC_acceptContextsWithPreferredTransferSyntaxes(association->params,services,1,transfer,2));
   checked(ASC_acknowledgeAssociation(association));
   T_DIMSE_Message message;T_ASC_PresentationContextID id=0;
   checked(DIMSE_receiveCommand(association,DIMSE_NONBLOCKING,5,&id,&message,NULL));
   assert(message.CommandField==DIMSE_C_ECHO_RQ);
   checked(DIMSE_sendEchoResponse(association,id,&message.msg.CEchoRQ,STATUS_Success,NULL));
   assert(DIMSE_receiveCommand(association,DIMSE_NONBLOCKING,5,&id,&message,NULL)==DUL_PEERREQUESTEDRELEASE);
   checked(ASC_acknowledgeRelease(association));
   ASC_dropAssociation(association);ASC_destroyAssociation(&association);
  }
 } else {
  checked(ASC_initializeNetwork(NET_REQUESTOR,0,5,&network));
  T_ASC_Parameters *params=NULL;T_ASC_Association *association=NULL;
  checked(ASC_createAssociationParameters(&params,ASC_DEFAULTMAXPDU,5));
  checked(ASC_setAPTitles(params,"HOROSTEST","FIXTURE",NULL));
  checked(HorosDIMSESetPeerAddress(params,"localhost",argv[2],port));
  const char *transfer[]={UID_LittleEndianExplicitTransferSyntax,UID_LittleEndianImplicitTransferSyntax};
  checked(ASC_addPresentationContext(params,1,UID_VerificationSOPClass,transfer,2));
  checked(HorosDIMSERequestAssociation(network,params,&association));
  Uint16 status=0xffff;DcmDataset *detail=NULL;
  checked(DIMSE_echoUser(association,1,DIMSE_NONBLOCKING,5,&status,&detail));
  delete detail;assert(status==0);
  checked(ASC_releaseAssociation(association));
  ASC_destroyAssociation(&association);
 }
 ASC_dropNetwork(&network);
}
'''
flags = dcmtk_flags('dcmnet')
with tempfile.TemporaryDirectory(prefix='horos-ip-family-') as directory:
    folder = Path(directory)
    (folder / 'main.cc').write_text(code)
    policy = folder / 'libPolicy.dylib'
    subprocess.run(['xcrun', 'swiftc', '-parse-as-library', '-emit-library',
                    str(ROOT / 'Horos/Sources/HorosDIMSEAssociationPolicy.swift'),
                    '-o', str(policy)], check=True)
    binary = folder / 'echo'
    subprocess.run(['xcrun', 'clang++', '-std=c++11', str(folder / 'main.cc'),
                    *flags, str(policy), '-o', str(binary)], check=True)
    with socket.socket(socket.AF_INET6, socket.SOCK_STREAM) as reservation:
        reservation.bind(('::', 0))
        port = reservation.getsockname()[1]
    server = subprocess.Popen([str(binary), 'server', '::', str(port)],
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        assert server.stdout.readline().strip() == 'READY'
        for host in ('127.0.0.1', '::1', '[::1]'):
            subprocess.run([str(binary), 'client', host, str(port)], check=True, timeout=15)
        output, error = server.communicate(timeout=10)
        assert server.returncode == 0, error
    finally:
        if server.poll() is None:
            server.terminate()
            server.wait(timeout=5)
    python = ROOT / 'local-validation/venv/bin/python'
    if not python.is_file():
        print('skipped: DNS fallback requires local-validation/venv with pynetdicom')
        raise SystemExit(2)
    # localhost resolves ::1 first here. A peer bound only to IPv4 must still
    # accept the second address; no failed TLS/AE negotiation may be retried.
    peer = r'''
from pynetdicom import AE,evt
from pynetdicom.sop_class import Verification
import time
server=AE(ae_title='FIXTURE');server.add_supported_context(Verification)
listener=server.start_server(('127.0.0.1',0),block=False,evt_handlers=[(evt.EVT_C_ECHO,lambda event:0)])
print(listener.server_address[1],flush=True)
try: time.sleep(25)
finally: listener.shutdown()
'''
    process = subprocess.Popen([str(python), '-c', peer], stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, text=True)
    try:
        port = int(process.stdout.readline().strip())
        subprocess.run([str(binary), 'client', 'localhost', str(port)], check=True, timeout=15)
    finally:
        process.terminate()
        process.wait(timeout=5)
    print('PASS: actual DCMTK C-ECHO on IPv4, IPv6, bracketed IPv6 and an IPv4-only localhost peer')
