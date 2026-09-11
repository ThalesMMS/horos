#!/usr/bin/env python3
"""Every native DIMSE client uses the application address policy; listener is dual-stack.
Actual network exchanges are in test-dimse-ip-family.py.
"""
from pathlib import Path
root = Path(__file__).resolve().parents[1]
for name in ('DCMTKQueryNode.mm', 'DCMTKStoreSCU.mm', 'DCMTKVerifySCU.mm', 'HorosDICOMMoveContext.mm'):
    source = (root / 'Horos/Sources' / name).read_text(encoding='latin1')
    assert 'HorosDIMSESetPeerAddress(' in source, name
    assert 'HorosDIMSERequestAssociation(' in source, name
    assert 'sprintf(peerHost,' not in source and 'sprintf(dstHostNamePlusPort,' not in source, name
policy = (root / 'Horos/Sources/HorosDIMSEAssociation.h').read_text()
assert 'hints.ai_family = AF_UNSPEC' in policy
assert 'answer = answer->ai_next' in policy
assert "host.front() == '[' && host.back() == ']'" in policy
assert "address.find_last_of(':')" in policy
assert 'condition.code() != DULC_TCPINITERROR' in policy
listener = (root / 'Horos/Sources/DCMTKQueryRetrieveSCP.mm').read_text(encoding='latin1')
assert 'dcmIncomingProtocolFamily.set(ASC_AF_UNSPEC)' in listener
upstream = (root / 'DCMTK/dcmnet/libsrc/dul.cc').read_text()
assert 'IPV6_V6ONLY' in upstream and 'ASC_AF_UNSPEC' in upstream
print('PASS: all clients use checked dual-stack addresses and TCP-only retries; the native listener selects both IP families')
