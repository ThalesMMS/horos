#!/usr/bin/env python3
"""Real TLS C-ECHO using Horos's archives, cipher helper and verification mapping.

The listening side reports READY before the other side connects (#666). The
Python peer binds port 0 itself and reports the port it was given, so its
port cannot be taken in between; the DCMTK driver binds the port the test
reserves, and a case whose driver cannot bind it is retried with another
port, a few times. A listener that exits before READY fails with its exit
code and its standard error.
"""
import os
from pathlib import Path
import re
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
#include <openssl/crypto.h>
#include <cassert>
#include <cstdio>
static void check(OFCondition c){if(c.bad()){fprintf(stderr,"%s\n",c.text());exit(3);}}
int main(int argc,char**argv){@autoreleasepool{
 if(argc==2 && !strcmp(argv[1],"version")){
  // One string comes from DCMTK's compiled headers, the other from the
  // OpenSSL archive actually linked into this process. Stale consumers fail.
  assert(!strcmp(DcmTLSTransportLayer::getOpenSSLVersionName(),OpenSSL_version(OPENSSL_VERSION)));
  puts(OpenSSL_version(OPENSSL_VERSION));return 0;
 }
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
  printf("READY %d\n",port);fflush(stdout);
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
role,port,ca,cert,key,version=sys.argv[1:];port=int(port)
context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER if role=='server' else ssl.PROTOCOL_TLS_CLIENT)
context.minimum_version=context.maximum_version=getattr(ssl.TLSVersion,version)
context.set_alpn_protocols(['dicom'])
if role=='client':context.check_hostname=False;context.verify_mode=ssl.CERT_REQUIRED;context.load_verify_locations(ca)
if cert!='none':context.load_cert_chain(cert,key)
ae=AE(ae_title='FIXTURE');ae.acse_timeout=5;ae.dimse_timeout=5
if role=='server':
 ae.add_supported_context(Verification)
 server=ae.start_server(('127.0.0.1',port),block=False,ssl_context=context,evt_handlers=[(evt.EVT_C_ECHO,lambda e:0)])
 print('READY',server.server_address[1],flush=True)
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
    version_fields = dict(line.split('=', 1) for line in (ROOT/'OpenSSL/upstream/VERSION.dat').read_text().splitlines() if '=' in line)
    expected_version = '.'.join(version_fields[key] for key in ('MAJOR', 'MINOR', 'PATCH'))
    linked_version = subprocess.check_output([str(p/'driver'), 'version'], text=True).strip()
    assert linked_version.startswith('OpenSSL '+expected_version+' '), linked_version
    print('PASS: DCMTK compiled version and linked archive:', linked_version, flush=True)
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
    def listen(command, case):
        """Starts the listening side; returns it and the port it reports, or None if it could not bind."""
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        line = process.stdout.readline().strip()
        if re.fullmatch(r'READY \d+', line):
            return process, int(line.split()[1])
        try:
            output, error = process.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill(); output, error = process.communicate()
        if process.returncode == 3 and re.search(r'bind|address already in use|TCP Initialization Error', error, re.I):
            return None, error
        raise AssertionError('%s: the listener stopped before READY, exit code %s, first line %r, stdout %r, stderr %r'
                             % (case, process.returncode, line, output, error))

    for version, (role, mode, identity, success) in [(v, c) for v in ('TLSv1_2', 'TLSv1_3') for c in cases]:
        case = (version, role, mode, identity)
        cert = str(p/(identity+'.pem')) if identity != 'none' else 'none'
        key = str(p/(identity+'.key')) if identity != 'none' else 'none'

        def driver(port):
            return [str(p/'driver'), role, str(port), str(mode), str(p/'trusted.pem'),
                    str(p/'trusted.pem') if role=='server' else 'none', str(p/'trusted.key'),
                    'TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256' if mode==1 else 'default']

        def remote(port):
            return [str(python), str(p/'peer.py'), 'server' if role=='client' else 'client', str(port), str(p/'trusted.pem'), cert, key, version]

        if role == 'client':
            # The peer listens on the port the system gives it: no race.
            process, port = listen(remote(0), case)
            assert process, (case, 'the peer could not bind port 0', port)
        else:
            # DCMTK binds the port the test reserves; another connection can take
            # it between the reservation and the bind, so that case is retried.
            for attempt in range(5):
                with socket.socket() as reservation:
                    reservation.bind(('127.0.0.1', 0)); reserved = reservation.getsockname()[1]
                process, port = listen(driver(reserved), case)
                if process: break
                print('RETRY', case, 'port', reserved, 'taken before the driver bound it', flush=True)
            assert process, (case, 'the driver could not bind a port in five attempts', port)
        second = driver(port) if role == 'client' else remote(port)
        try:
            completed = subprocess.run(second, capture_output=True, text=True, timeout=15)
            assert (completed.returncode == 0) == success, (version, role, mode, identity, completed.stdout, completed.stderr)
            if role=='server':
                output, error = process.communicate(timeout=10)
                assert (process.returncode == 0) == success, (version, role, mode, identity, output, error)
        finally:
            if process.poll() is None: process.terminate(); process.wait(timeout=5)
        print('PASS', version, role, mode, identity, 'accepted' if success else 'rejected', flush=True)
    # The listener's failures: one that stops before READY says why, and a port
    # another socket holds sends the driver's case to the retry.
    try:
        listen([str(python), '-c', 'import sys; sys.stderr.write("no READY here"); sys.exit(4)'], 'self-check')
    except AssertionError as failure:
        assert 'exit code 4' in str(failure) and 'no READY here' in str(failure), failure
    else:
        raise AssertionError('a listener that stopped before READY did not fail')
    with socket.socket() as occupied:
        # DCMTK listens on every address with SO_REUSEADDR, so only a listener on
        # every address keeps it from binding.
        occupied.bind(('', 0)); occupied.listen(1); taken = occupied.getsockname()[1]
        process, error = listen([str(p/'driver'), 'server', str(taken), '1', str(p/'trusted.pem'), str(p/'trusted.pem'),
                                 str(p/'trusted.key'), 'default'], 'bind self-check')
        assert process is None, 'the driver bound a port another socket holds'
    print('PASS: a listener that stops before READY reports its exit code and stderr; a taken port is retried', flush=True)
    rejected = subprocess.run([str(p/'driver'), 'client', '1', '2', 'none', 'none', 'none', 'NOT_A_TLS_CIPHER'], capture_output=True)
    assert rejected.returncode == 3, 'Unknown saved cipher must fail during configuration'
    print('PASS: real TLS 1.2/1.3 C-ECHO, default/explicit profiles, three verification modes, unknown preference and invalid cipher')
