#!/usr/bin/env python3
"""Loopback-only authorization regression for the native synthetic server probe."""
import argparse,json,socket,sqlite3,struct,time
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('run',type=Path)
p.add_argument('--port',type=int,default=11280)
a=p.parse_args()
assert 'local-validation' in a.run.resolve().parts
assert (a.run/'received.sql').is_file(), 'run the private synthetic native probe first'
secret=b'synthetic-fixture-only'
def exchange(packet,fragment=False):
    with socket.create_connection(('127.0.0.1',a.port),5) as s:
        s.settimeout(5)
        if fragment:
            for part in (packet[:7],packet[7:11],packet[11:]):
                s.sendall(part);time.sleep(.03)
        else:s.sendall(packet)
        result=bytearray()
        try:
            while data:=s.recv(1024*1024):result.extend(data)
        except ConnectionResetError:pass
        return bytes(result)
def authorize(request,password=secret):return b'AUTHR\0'+struct.pack('>I',len(password))+password+request
def text(value):
    data=value.encode()+b'\0';return struct.pack('>I',len(data))+data
commands=['DATAB','DBSIZ','VERSI','SENDD','SENDG','NEWMS','ADDAL','REMAL','SETVA','MFILE','DCMSE','DICOM']
for command in commands:
    request=command.encode()+b'\0'
    assert exchange(request)==b'', 'unauthorized '+command
    assert exchange(authorize(request,b'incorrect-fixture-answer'))==b'', 'wrong password '+command
assert exchange(b'AUTHV\0')==struct.pack('>I',1)
assert exchange(b'ISPWD\0')==struct.pack('>I',1)
assert exchange(b'PASWD\0'+text(secret.decode())+b'DATAB\0')==struct.pack('>I',1), 'legacy password check granted a data session'
assert exchange(b'DATAB\0')==b'', 'authorization leaked between connections'
for malformed in (b'AUTHR\0'+b'\xff'*4,b'PASWD\0'+b'\xff'*4,b'PASWD\0'+struct.pack('>I',2)+b'xx',b'\xff'*5+b'\0'):
    assert exchange(malformed)==b''
size=struct.unpack('>I',exchange(authorize(b'DBSIZ\0'),fragment=True))[0]
data=exchange(authorize(b'DATAB\0'))
assert len(data)==size and data.startswith(b'SQLite format 3\0')
with sqlite3.connect(a.run/'received.sql') as db:
    store_uuid=db.execute('select Z_UUID from Z_METADATA').fetchone()[0]
    pk,uid,comment=db.execute('select Z_PK,ZSTUDYINSTANCEUID,ZCOMMENT from ZSTUDY order by Z_PK limit 1').fetchone()
uri='x-coredata://%s/Study/p%d'%(store_uuid,pk)
request=b'SETVA\0'+text(uri)+text('SYNTHETIC AUTHORIZED UPDATE')+text('comment')
def current_comment():
    content=exchange(authorize(b'DATAB\0'))
    snapshot=a.run/'authorization-check.sql';snapshot.write_bytes(content)
    with sqlite3.connect(snapshot) as db:return db.execute('select ZCOMMENT from ZSTUDY where ZSTUDYINSTANCEUID=?',(uid,)).fetchone()[0]
assert exchange(request)==b'' and current_comment()==comment
assert exchange(authorize(request,b'incorrect-fixture-answer'))==b'' and current_comment()==comment
exchange(authorize(request))
assert current_comment()=='SYNTHETIC AUTHORIZED UPDATE', 'authenticated mutation did not persist'
result={'unauthorizedCommandsDenied':len(commands),'wrongPasswordCommandsDenied':len(commands),
        'authorizedIndexBytes':size,'fragmentedAuthorization':True,'malformedCredentialsDenied':True,
        'legacyPasswordDoesNotAuthorizeData':True,'authorizationIsPerConnection':True,'authenticatedMutation':True}
(a.run/'authorization-results.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
