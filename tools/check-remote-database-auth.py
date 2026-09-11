#!/usr/bin/env python3
"""Verify a private native shared-index/authentication probe run."""
import argparse
import hashlib
from pathlib import Path
import re
import sqlite3
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('run',type=Path)
p.add_argument('--retry',action='store_true')
a=p.parse_args()
assert 'local-validation' in a.run.resolve().parts
log=(a.run/'horos.log').read_text(errors='replace')
assert 'REMOTE_PROBE_EXCEPTION' not in log
prompts=re.findall(r'REMOTE_AUTH_PROMPT main=(\d)',log)
assert len(prompts)>=2 and set(prompts)=={'1'},prompts
for token in ('REMOTE_INDEX_LOADED studies=10000','REMOTE_WRONG_PASSWORD_REJECTED',
              'REMOTE_PASSWORD_CANCELLED result=1','REMOTE_NETWORK_FAILURE_CAUGHT','REMOTE_PROBE_MAIN_ALIVE'):
    assert token in log,token
assert 'REMOTE_WRONG_PASSWORD_ACCEPTED' not in log
assert 'REMOTE_NETWORK_FAILURE_ACCEPTED' not in log
expected=int(re.search(r'REMOTE_INDEX_RECEIVED bytes=(\d+)',log)[1])
files=['received.sql']
if a.retry:
    assert 'REMOTE_RETRY_INDEX_RECEIVED' in log
    files.append('retry.sql')
else:
    assert 'REMOTE_TRUNCATION_REJECTED NSObjectInaccessibleException partials=0' in log
    assert 'REMOTE_TRUNCATION_ACCEPTED' not in log
for name in files:
    path=a.run/name
    assert path.stat().st_size==expected
    with sqlite3.connect('file:'+str(path.resolve())+'?mode=ro',uri=True) as db:
        assert db.execute('pragma quick_check').fetchone()==('ok',)
        assert db.execute('select count(*),count(distinct ZSTUDYINSTANCEUID) from ZSTUDY').fetchone()==(10000,10000)
        assert db.execute("select count(*) from ZSTUDY where ZNAME='SYNTHETIC^SHARED' and length(ZCOMMENT)=2048").fetchone()==(10000,)
if a.retry:
    hashes=[hashlib.sha256((a.run/name).read_bytes()).digest() for name in files]
    assert hashes[0]==hashes[1], 'retry index differs from the unchanged source snapshot'
print('ok: %d-byte index, 10000 unique synthetic studies, main-thread prompts, rejected password/network fault, cancellation%s' % (expected,', identical retry bytes' if a.retry else ', no truncated file'))
