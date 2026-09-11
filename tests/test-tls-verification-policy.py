#!/usr/bin/env python3
"""#371/#317: an unrecognised TLS setting must not mean "do not check the peer".

`TLSCertificateVerificationType` in `DICOMTLS.h` has three values — require (0),
verify (1), ignore (2) — and four places read it from a preference or a server's
parameter dictionary with `[… intValue]`, which is unbounded. Three of them then
map it onto DCMTK's `DcmCertificateVerification` the same way:

    if(certVerification==RequirePeerCertificate)      … DCV_requireCertificate;
    else if(certVerification==VerifyPeerCertificate)  … DCV_checkCertificate;
    else                                              … DCV_ignoreCertificate;

Anything that is not 0 or 1 lands in that `else` and turns peer verification
**off**: a corrupted preference, a stale plist, a value from a future version, a
negative. A security control that fails open on unexpected input is the wrong way
round.

`HorosTLSVerificationPolicy` normalises first, so the mapping only ever sees a
value it knows and an unknown one becomes the strictest.
"""
from pathlib import Path
import re
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
failures = []

source = root / 'Horos/Sources/TLSVerificationPolicy.swift'
if not source.is_file():
    failures.append('Horos/Sources/TLSVerificationPolicy.swift is missing')
else:
    driver = r'''
import Foundation

@main struct Check {
    static func main() {
        typealias P = TLSVerificationPolicy
        precondition(P.require == 0 && P.verify == 1 && P.ignore == 2,
                     "the values must match DICOMTLS.h")

        // The three it knows pass through.
        precondition(P.normalise(P.require) == P.require)
        precondition(P.normalise(P.verify) == P.verify)
        precondition(P.normalise(P.ignore) == P.ignore)

        // Everything else becomes the strictest, never the loosest. These are
        // the values an unbounded intValue actually produces: a missing key, a
        // string that is not a number, a stale or future setting, a negative.
        for stored in [-1, -2, 3, 4, 7, 99, 1 << 20, Int.min, Int.max] {
            precondition(P.normalise(stored) == P.require,
                         "\(stored) normalised to \(P.normalise(stored))")
            precondition(!P.isRecognised(stored))
            precondition(P.verifiesPeer(stored), "\(stored) would not check the peer")
        }

        // Only a deliberate "ignore" skips the check.
        precondition(P.verifiesPeer(P.require))
        precondition(P.verifiesPeer(P.verify))
        precondition(!P.verifiesPeer(P.ignore))
        precondition(P.isRecognised(P.require) && P.isRecognised(P.verify) && P.isRecognised(P.ignore))
        print("rule ok")
    }
}
'''
    with tempfile.TemporaryDirectory(prefix='horos-tls-policy-') as folder:
        path = Path(folder)
        (path / 'Check.swift').write_text(driver)
        build = subprocess.run(['xcrun', 'swiftc', '-parse-as-library', str(source),
                                str(path / 'Check.swift'), '-o', str(path / 'check')],
                               capture_output=True, text=True)
        if build.returncode:
            failures.append('the policy does not compile: %s' % build.stderr.strip().splitlines()[-3:])
        else:
            run = subprocess.run([str(path / 'check')], capture_output=True, text=True)
            if run.returncode:
                failures.append('the policy fails open: %s' % run.stderr.strip())

# The enum the policy mirrors must not move under it.
tls = (root / 'Horos/Sources/DICOMTLS.h').read_bytes().decode('latin1')
if not re.search(r'RequirePeerCertificate\s*=\s*0,\s*VerifyPeerCertificate,\s*IgnorePeerCertificate',
                 tls, re.S):
    failures.append('TLSCertificateVerificationType changed; HorosTLSVerificationPolicy mirrors it')

# Every place that turns a stored value into a verification level must normalise.
READERS = {
    'Horos/Sources/DCMTKQueryRetrieveSCP.mm': 'TLSStoreSCPCertificateVerification',
    'Horos/Sources/DCMTKServiceClassUser.mm': 'TLSCertificateVerification',
    'Horos/Sources/DCMTKStoreSCU.mm': 'TLSCertificateVerification',
    'Horos/Sources/QueryController.mm': 'TLSCertificateVerification',
}
for name, key in READERS.items():
    text = (root / name).read_bytes().decode('latin1')
    for match in re.finditer(r'^.*objectForKey:@"%s".*intValue\].*$|^.*valueForKey:@"%s".*intValue\].*$'
                             % (key, key), text, re.M):
        if 'HorosTLSVerificationPolicy' not in match.group(0):
            failures.append('%s reads %s without normalising it' % (name, key))

# And the three mappings must still refuse on a known value only, never as a
# fallback for something unexpected.
for name in ('Horos/Sources/DCMTKQueryNode.mm', 'Horos/Sources/DCMTKStoreSCU.mm',
             'Horos/Sources/DCMTKQueryRetrieveSCP.mm'):
    text = (root / name).read_bytes().decode('latin1')
    if 'DCV_ignoreCertificate' not in text:
        failures.append('%s no longer maps the ignore level at all' % name)
    if 'DCV_requireCertificate' not in text or 'DCV_checkCertificate' not in text:
        failures.append('%s no longer maps all three levels' % name)

if failures:
    print('FAIL:')
    for item in failures:
        print(' ', item)
    raise SystemExit(1)

print('PASS: an unrecognised TLS verification setting becomes require, not ignore, and all four '
      'readers normalise before mapping')
