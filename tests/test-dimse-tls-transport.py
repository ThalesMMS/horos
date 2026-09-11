#!/usr/bin/env python3
"""Real TLS C-ECHO using Horos's archives, cipher helper and verification mapping."""
import os
from pathlib import Path
import socket
import subprocess
import tempfile
from dcmtk_build import ROOT, BUILD, dcmtk_flags

python = ROOT/'local-validation/dcmtk-venv/bin/python'
openssl = BUILD/'OpenSSL.build/Install'
if not python.is_file() or not (openssl/'lib/libssl.a').is_file():
    print('skipped: needs built OpenSSL and local-validation/dcmtk-venv with pynetdicom')
    raise SystemExit(2)
source = (ROOT/'Horos/Sources/DCMTKQueryNode.mm').read_text(encoding='latin1')
start = source.index('DcmCertificateVerification _certVerification;')
end = source.index('tLayer->setCertificateVerification(_certVerification);', start)
mapping = source[start:end + len('tLayer->setCertificateVerification(_certVerification);')]
code = r'''
#import <Foundation/Foundation.h>
#import "Policy-Swift.h"
#include "HorosDIMSEAssociation.h"
#include "HorosTLSConfiguration.h"
#include <dcmtk/dcmnet/dimse.h>
#include <dcmtk/dcmdata/dcuid.h>
#include <cassert>
#include <cstdio>
static void check(OFCondition c){if(c.bad()){fprintf(stderr,"%s\n",c.text());exit(3);}}
int main(int argc,char**argv){@autoreleasepool{
 assert(argc==8); const bool server=!strcmp(argv[1],"server");const int port=atoi(argv[2]);
 const int certVerification=(int)[HorosTLSVerificationPolicy normalise:atoi(argv[3])];
 const int RequirePeerCertificate=0,VerifyPeerCertificate=1;
 DcmTLSTransportLayer layer(server?NET_ACCEPTOR:NET_REQUESTOR,NULL,OFTrue);assert(layer);
 DcmTLSTransportLayer*tLayer=&layer;
 MAPPING
 OFList<OFString> suites;
 if(strcmp(argv[7],"default"))suites.push_back(argv[7]);
 check(HorosConfigureTLSCipherSuites(layer,suites));
 if(strcmp(argv[4],"none"))check(layer.addTrustedCertificateFile(argv[4],DCF_Filetype_PEM));
 if(strcmp(argv[5],"none")){
  check(layer.setPrivateKeyFile(argv[6],DCF_Filetype_PEM));
  check(layer.setCertificateFile(argv[5],DCF_Filetype_PEM,layer.getTLSProfile()));
  assert(layer.checkPrivateKeyMatchesCertificate());
 }
 T_ASC_Network*network=NULL;T_ASC_Association*association=NULL;
 check(ASC_initializeNetwork(server?NET_ACCEPTOR:NET_REQUESTOR,server?port:0,5,&network));
 check(ASC_setTransportLayer(network,&layer,0));
 OFCondition status=EC_Normal;
 const char*transfers[]={UID_LittleEndianExplicitTransferSyntax,UID_LittleEndianImplicitTransferSyntax};
 if(server){
  puts("READY");fflush(stdout);
  void*pdu=NULL;unsigned long length=0;
  status=ASC_receiveAssociation(network,&association,ASC_DEFAULTMAXPDU,&pdu,&length,OFTrue,DUL_BLOCK,5);
  if(status.good())status=HorosDIMSEValidateAssociationPDU(pdu,length);free(pdu);
  if(status.good()){
   const char*abstracts[]={UID_VerificationSOPClass};
   check(ASC_acceptContextsWithPreferredTransferSyntaxes(association->params,abstracts,1,transfers,2));
   check(ASC_acknowledgeAssociation(association));
   T_ASC_PresentationContextID id=0;T_DIMSE_Message message={};
   status=DIMSE_receiveCommand(association,DIMSE_NONBLOCKING,5,&id,&message,NULL);
   if(status.good()){
    assert(message.CommandField==DIMSE_C_ECHO_RQ);
    status=DIMSE_sendEchoResponse(association,id,&message.msg.CEchoRQ,0,NULL);
    if(status.good()&&DIMSE_receiveCommand(association,DIMSE_NONBLOCKING,5,&id,&message,NULL)==DUL_PEERREQUESTEDRELEASE)
     check(ASC_acknowledgeRelease(association));
   }
  }
 }else{
  T_ASC_Parameters*params=NULL;check(ASC_createAssociationParameters(&params,ASC_DEFAULTMAXPDU,5));
  check(ASC_setAPTitles(params,"HOROSTLS","FIXTURE",NULL));
  check(HorosDIMSESetPeerAddress(params,"localhost","127.0.0.1",port));
  check(ASC_setTransportLayerType(params,OFTrue));
  check(ASC_addPresentationContext(params,1,UID_VerificationSOPClass,transfers,2));
  status=HorosDIMSERequestAssociation(network,params,&association);
  if(status.good()){
   Uint16 response=0xffff;DcmDataset*detail=NULL;
   status=DIMSE_echoUser(association,1,DIMSE_NONBLOCKING,5,&response,&detail);delete detail;
   if(status.good()){assert(response==0);check(ASC_releaseAssociation(association));}
  }
 }
 if(association){ASC_closeTransportConnection(association);ASC_destroyAssociation(&association);}
 ASC_dropNetwork(&network);
 printf("RESULT %d %s\n",status.good()?0:1,status.text());return status.good()?0:1;
}}
'''.replace('MAPPING', mapping)
peer = r'''
import ssl,sys,time
from pynetdicom import AE,evt
from pynetdicom.sop_class import Verification
role,port,ca,cert,key=sys.argv[1:];port=int(port)
context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER if role=='server' else ssl.PROTOCOL_TLS_CLIENT)
context.minimum_version=context.maximum_version=ssl.TLSVersion.TLSv1_2
context.set_alpn_protocols(['dicom'])
if role=='client':context.check_hostname=False;context.verify_mode=ssl.CERT_REQUIRED;context.load_verify_locations(ca)
if cert!='none':context.load_cert_chain(cert,key)
ae=AE(ae_title='FIXTURE');ae.acse_timeout=5;ae.dimse_timeout=5
if role=='server':
 ae.add_supported_context(Verification)
 server=ae.start_server(('127.0.0.1',port),block=False,ssl_context=context,evt_handlers=[(evt.EVT_C_ECHO,lambda e:0)])
 print('READY',flush=True)
 try:time.sleep(50)
 finally:server.shutdown()
else:
 ae.add_requested_context(Verification)
 association=ae.associate('127.0.0.1',port,ae_title='HOROSTLS',tls_args=(context,None))
 passed=False
 if association.is_established:
  status=association.send_c_echo();passed='Status' in status and status.Status==0;association.release()
 print('RESULT',int(not passed));sys.exit(0 if passed else 1)
'''

with tempfile.TemporaryDirectory(prefix='horos-tls-') as directory:
    p = Path(directory); (p/'main.mm').write_text(code); (p/'peer.py').write_text(peer)
    subprocess.run(['xcrun', 'swiftc', '-parse-as-library', '-emit-library', '-module-name', 'Policy',
        '-emit-objc-header-path', str(p/'Policy-Swift.h'),
        str(ROOT/'Horos/Sources/TLSVerificationPolicy.swift'), str(ROOT/'Horos/Sources/HorosDIMSEAssociationPolicy.swift'),
        '-o', str(p/'libPolicy.dylib')], check=True)
    subprocess.run(['xcrun', 'clang++', '-std=c++11', '-I'+str(openssl/'include'), str(p/'main.mm'),
        *dcmtk_flags('dcmtls', 'dcmnet'), str(openssl/'lib/libssl.a'), str(openssl/'lib/libcrypto.a'),
        str(p/'libPolicy.dylib'), '-framework', 'Foundation', '-framework', 'Security', '-o', str(p/'driver')], check=True)
    # Certificates and private keys are disposable test data, never keychain items.
    executable = str(openssl/'bin/openssl') if (openssl/'bin/openssl').exists() else 'openssl'
    (p/'openssl.cnf').write_text('[req]\ndistinguished_name=dn\nx509_extensions=ext\n[dn]\n[ext]\nbasicConstraints=critical,CA:TRUE\nkeyUsage=critical,digitalSignature,keyEncipherment,keyCertSign\n')
    for name in ('trusted', 'untrusted'):
        subprocess.run([executable, 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-sha256', '-days', '1',
            '-subj', '/CN=Horos synthetic TLS '+name, '-config', str(p/'openssl.cnf'),
            '-keyout', str(p/(name+'.key')), '-out', str(p/(name+'.pem'))], check=True, capture_output=True)
    cases = [('client', 0, 'trusted', True), ('client', 1, 'trusted', True),
             ('client', 0, 'untrusted', False), ('client', 1, 'untrusted', False),
             ('client', 2, 'untrusted', True), ('client', 99, 'untrusted', False),
             ('server', 0, 'trusted', True), ('server', 1, 'trusted', True),
             ('server', 0, 'none', False), ('server', 1, 'none', True),
             ('server', 1, 'untrusted', False), ('server', 2, 'untrusted', True)]
    for role, mode, identity, success in cases:
        with socket.socket() as reservation:
            reservation.bind(('127.0.0.1', 0)); port = reservation.getsockname()[1]
        cert = str(p/(identity+'.pem')) if identity != 'none' else 'none'
        key = str(p/(identity+'.key')) if identity != 'none' else 'none'
        driver = [str(p/'driver'), role, str(port), str(mode), str(p/'trusted.pem'),
                  str(p/'trusted.pem') if role=='server' else 'none', str(p/'trusted.key'),
                  'TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256' if mode==1 else 'default']
        remote = [str(python), str(p/'peer.py'), 'server' if role=='client' else 'client', str(port), str(p/'trusted.pem'), cert, key]
        first, second = (remote, driver) if role=='client' else (driver, remote)
        process = subprocess.Popen(first, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            assert process.stdout.readline().strip() == 'READY'
            completed = subprocess.run(second, capture_output=True, text=True, timeout=15)
            assert (completed.returncode == 0) == success, (role, mode, identity, completed.stdout, completed.stderr)
            if role=='server':
                output, error = process.communicate(timeout=10)
                assert (process.returncode == 0) == success, (role, mode, identity, output, error)
        finally:
            if process.poll() is None: process.terminate(); process.wait(timeout=5)
        print('PASS TLS', role, mode, identity, 'accepted' if success else 'rejected', flush=True)
    rejected = subprocess.run([str(p/'driver'), 'client', '1', '2', 'none', 'none', 'none', 'NOT_A_TLS_CIPHER'], capture_output=True)
    assert rejected.returncode == 3, 'Unknown saved cipher must fail during configuration'
    print('PASS: real TLS 1.2 C-ECHO, default/explicit profiles, three verification modes, unknown preference and invalid cipher')
