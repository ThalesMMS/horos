#!/usr/bin/env python3
"""The portal's session ids, tokens and challenges are drawn, not derived from the clock.

Three identifiers were built the same way: read the clock, hash the reading with
MD5, print 32 hexadecimal characters. The length says 128 bits; the input says
"whichever moment this was", which anyone who can watch the portal answer can
narrow to a handful of milliseconds. The session id was the worst of the three -
it hashed `random()`, and this application seeds that generator once, from
`time(NULL)`, so the whole sequence follows from the second the application
started.

The Swift generator is checked here against the construction it replaced: given
one reading of the clock, the old one returns the same string every time and the
new one never does. The call sites are checked for taking their bytes from it,
and for still producing the shape a cookie, a URL and a stored model expect.
"""
from pathlib import Path
import ctypes
import re
import subprocess
import sys
import tempfile
import time

root = Path(__file__).resolve().parents[1]
failures = []

session = (root / 'Horos/Sources/WebPortalSession.mm').read_bytes().decode('latin1')
portal = (root / 'Horos/Sources/WebPortal.mm').read_bytes().decode('latin1')
swift = (root / 'Horos/Sources/WebPortalIdentifier.swift').read_text()


def strip(text):
    text = re.sub(r'//[^\n]*', '', text)
    return re.sub(r'/\*.*?\*/', '', text, flags=re.S)


def slice_after(text, marker, length=700):
    at = text.find(marker)
    return text[at:at + length] if at >= 0 else ''


# --- the three call sites draw their bytes, and no longer hash a moment --------
for name, text, marker in (('createToken', session, '-(NSString*)createToken'),
                           ('newChallenge', session, '-(NSString*)newChallenge'),
                           ('newSession', portal, '-(id)newSession')):
    body = slice_after(strip(text), marker)
    if not body:
        failures.append('%s is gone' % name)
        continue
    if 'HorosWebPortalIdentifier unguessable' not in body:
        failures.append('%s does not take its identifier from the random generator' % name)
    for clock in ('timeIntervalSinceReferenceDate', 'random()', 'md5Digest'):
        if clock in body:
            failures.append('%s still builds its identifier out of %s' % (name, clock))

# The generator itself must not consult the clock, or it would be the same bug
# wearing the new name.
for clock in ('Date(', 'timeIntervalSince', 'time(', 'mach_absolute'):
    if clock in strip(swift):
        failures.append('the generator reads the clock (%s), which is what it replaces' % clock)
if 'SecRandomCopyBytes' not in swift:
    failures.append('the generator does not ask the system for random bytes')

for failure in failures:
    print('FAIL: %s' % failure)
reported = len(failures)

main = r'''import Foundation
import CommonCrypto

// Asked for one identifier and nothing else: the driver runs this twice, as two
// processes, inside the same second.
if CommandLine.arguments.contains("one") {
    print(WebPortalIdentifier.unguessable())
    exit(0)
}

// The construction being replaced, so the comparison is against the real thing
// and not a description of it: MD5 over one reading of the clock, printed as hex.
func derivedFromTheClock(_ instant: Double) -> String {
    var reading = instant
    var digest = [UInt8](repeating: 0, count: Int(CC_MD5_DIGEST_LENGTH))
    _ = withUnsafeBytes(of: &reading) { CC_MD5($0.baseAddress, CC_LONG($0.count), &digest) }
    return digest.map { String(format: "%02X", $0) }.joined()
}

// Same instant in, same token out: that is the whole of the old guessability.
let instant = Date.timeIntervalSinceReferenceDate
assert(derivedFromTheClock(instant) == derivedFromTheClock(instant))
assert(WebPortalIdentifier.unguessable() != WebPortalIdentifier.unguessable())

// The shape a cookie, a URL and a stored model already expect: 32 upper-case
// hexadecimal characters, the same as an MD5 digest printed by -[NSData hex].
let sample = WebPortalIdentifier.unguessable()
assert(sample.count == derivedFromTheClock(instant).count, sample)
assert(sample.count == 32, sample)
assert(sample.allSatisfy { $0.isHexDigit && !$0.isLowercase }, sample)

// 128 bits, and every bit of them moving: over many draws each position in the
// digest takes most of the alphabet, which a constant, a counter or a clock
// reading in the low digits fails.
var draws = Set<String>()
var seenAt = [Set<Character>](repeating: [], count: 32)
for _ in 0 ..< 4000 {
    let identifier = WebPortalIdentifier.unguessable()
    draws.insert(identifier)
    for (index, character) in identifier.enumerated() { seenAt[index].insert(character) }
}
assert(draws.count == 4000, "\(4000 - draws.count) of 4000 draws repeated")
for (index, seen) in seenAt.enumerated() {
    assert(seen.count == 16, "position \(index) only ever held \(seen.sorted())")
}

// A caller may ask for more; it may not ask its way down to nothing.
assert(WebPortalIdentifier.unguessable(byteCount: 32).count == 64)
assert(WebPortalIdentifier.unguessable(byteCount: 0).count == 2)

print("PASS: the identifier is drawn at random, keeps the old shape, and owes nothing to the clock")
'''

# --- what the session id used to be worth ------------------------------------
# `random()` is seeded once, in +[AppController initialize], from time(NULL). Two
# runs of the application that start in the same second walk the same sequence,
# so the old sid was reproducible by anyone who knew that second. Shown here
# against the real generator rather than asserted.
libc = ctypes.CDLL(None)
libc.random.restype = ctypes.c_long
second = int(time.time())
libc.srandom(second)
sequence = [libc.random() for _ in range(4)]
libc.srandom(second)
if sequence != [libc.random() for _ in range(4)]:
    failures.append('the C generator did not repeat for one seed, so this test proves nothing')

with tempfile.TemporaryDirectory(prefix='horos-web-portal-identifier-') as tmp:
    p = Path(tmp)
    (p / 'main.swift').write_text(main)
    build = subprocess.run(['swiftc', str(root / 'Horos/Sources/WebPortalIdentifier.swift'),
                            str(p / 'main.swift'), '-o', str(p / 'test')],
                           capture_output=True, text=True)
    if build.returncode:
        print(build.stderr.strip()[-2000:])
        sys.exit('the generator did not compile')
    checks = subprocess.run([str(p / 'test')], capture_output=True, text=True)
    print((checks.stdout + checks.stderr).strip())
    if checks.returncode:
        failures.append('the generator does not have the properties it is used for')
    # And nothing fixed at process start decides the answer either: two processes
    # inside one second, where the old sid would have agreed.
    began = time.time()
    drawn = [subprocess.run([str(p / 'test'), 'one'], capture_output=True,
                            text=True).stdout.strip() for _ in range(2)]
    if time.time() - began < 1.0 and drawn[0] == drawn[1]:
        failures.append('two processes started in the same second drew the same identifier')
    print('%-22s %s' % ('two processes drew', ', '.join(d[:8] + '\u2026' for d in drawn)))

for failure in failures[reported:]:
    print('FAIL: %s' % failure)
if failures:
    sys.exit(1)
print('ok: session ids, tokens and challenges are unguessable and unchanged in shape')
