#!/usr/bin/env python3
"""The Web Portal offers a standard zip, keeps the legacy one, and labels both.

Three parts: the Swift decision compiled and asked directly, the archive command
the application runs checked against /usr/bin/unzip on synthetic DICOM files, and
a scan of the two routes that download one.
"""
from pathlib import Path
import hashlib
import re
import struct
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
failures = []

# ------------------------------------------------------------------ the Swift
main = r'''
import Foundation

var failures = 0
func check(_ condition: Bool, _ what: String) {
    if !condition { print("FAIL \(what)"); failures += 1 }
}
func equal(_ got: String, _ want: String, _ what: String) {
    if got != want { print("FAIL \(what): got \(got), want \(want)"); failures += 1 }
}

let format = WebPortalArchiveFormat.self

// The labels themselves.
equal(format.standard.pathExtension, "zip", "the standard extension")
equal(format.standard.mimeType, "application/zip", "the standard type")
check(!format.standard.isLegacy, "the standard format is not legacy")
equal(format.legacy.pathExtension, "osirixzip", "the legacy extension")
equal(format.legacy.mimeType, "application/osirixzip", "the legacy type")
check(format.legacy.isLegacy, "the legacy format is legacy")

// The requested path settles it, because the portal's own pages generate it.
// Both routes are reachable from either client.
for macOS in [true, false] {
    check(format.format(forRequestedPath: "/study/x.zip", parameters: nil, clientIsMacOS: macOS) === format.standard,
          "a .zip link is standard for macOS=\(macOS)")
    check(format.format(forRequestedPath: "/study/x.osirixzip", parameters: nil, clientIsMacOS: macOS) === format.legacy,
          "an .osirixzip link is legacy for macOS=\(macOS)")
    check(format.format(forRequestedPath: "/STUDY/X.OSIRIXZIP", parameters: nil, clientIsMacOS: macOS) === format.legacy,
          "the suffix is matched without case for macOS=\(macOS)")
}

// Then an explicit request.
for macOS in [true, false] {
    check(format.format(forRequestedPath: "/wado", parameters: ["archive": "zip"], clientIsMacOS: macOS) === format.standard,
          "archive=zip is standard for macOS=\(macOS)")
    check(format.format(forRequestedPath: "/wado", parameters: ["archive": "osirixzip"], clientIsMacOS: macOS) === format.legacy,
          "archive=osirixzip is legacy for macOS=\(macOS)")
    check(format.format(forRequestedPath: "/wado", parameters: ["archive": "STANDARD"], clientIsMacOS: macOS) === format.standard,
          "archive=standard is standard for macOS=\(macOS)")
}

// And with neither - the WADO case - a Mac keeps what it has always been sent.
check(format.format(forRequestedPath: "/wado", parameters: nil, clientIsMacOS: true) === format.legacy,
      "WADO to a Mac stays legacy")
check(format.format(forRequestedPath: "/wado", parameters: nil, clientIsMacOS: false) === format.standard,
      "WADO to anything else is standard")
check(format.format(forRequestedPath: nil, parameters: nil, clientIsMacOS: false) === format.standard,
      "no path at all is standard")
check(format.format(forRequestedPath: "/wado", parameters: ["archive": 7], clientIsMacOS: false) === format.standard,
      "a parameter that is not a string does not decide anything")
check(format.format(forRequestedPath: "/wado", parameters: ["archive": "tar"], clientIsMacOS: true) === format.legacy,
      "an archive we do not offer falls back to the client default")

// The name the client saves under.
equal(format.standard.fileName(forStudyName: "SMITH^JOHN"), "SMITH^JOHN.zip", "a plain name")
equal(format.legacy.fileName(forStudyName: "SMITH^JOHN"), "SMITH^JOHN.osirixzip", "a plain legacy name")
equal(format.standard.fileName(forStudyName: "A/B\\C:D\"E"), "A B C D E.zip", "separators and quotes are removed")
equal(format.standard.fileName(forStudyName: "line\nbreak"), "line break.zip", "a newline cannot break the header")
equal(format.standard.fileName(forStudyName: "  padded  "), "padded.zip", "surrounding space is trimmed")
equal(format.standard.fileName(forStudyName: "../../etc/passwd"), "etc passwd.zip", "a relative path cannot escape")
equal(format.standard.fileName(forStudyName: ""), "Horos.zip", "an empty name still has one")
equal(format.standard.fileName(forStudyName: nil), "Horos.zip", "a missing name still has one")
equal(format.standard.fileName(forStudyName: "ANDRÉ^JOSÉ"), "ANDRÉ^JOSÉ.zip", "an accented name is kept")

// Content-Disposition. A study name is patient text and is often not ASCII.
equal(format.standard.contentDisposition(forStudyName: "SMITH^JOHN"),
      "attachment; filename=\"SMITH^JOHN.zip\"", "a plain disposition")
let accented = format.standard.contentDisposition(forStudyName: "ANDRÉ^JOSÉ")
check(accented.hasPrefix("attachment; filename=\"ANDRE^JOSE.zip\""),
      "the ASCII fallback is transliterated: \(accented)")
check(accented.contains("filename*=UTF-8''ANDR%C3%89%5EJOS%C3%89.zip"),
      "the real name is carried too: \(accented)")
let quoted = format.standard.contentDisposition(forStudyName: "a\"b")
check(!quoted.dropFirst("attachment; filename=\"".count).dropLast().contains("\""),
      "no quote survives into the header: \(quoted)")

if failures > 0 { print("\(failures) failure(s)"); exit(1) }
print("ok")
'''

with tempfile.TemporaryDirectory() as directory:
    path = Path(directory)
    (path / 'main.swift').write_text(main)
    build = subprocess.run(['xcrun', 'swiftc',
                            str(root / 'Horos/Sources/WebPortalArchiveFormat.swift'),
                            str(path / 'main.swift'), '-o', str(path / 'test')],
                           capture_output=True, text=True)
    if build.returncode != 0:
        print(build.stderr)
        failures.append('WebPortalArchiveFormat.swift does not compile')
        swift_result = 1
    else:
        swift_result = subprocess.run([str(path / 'test')]).returncode

# ------------------------------------------------- the archive the app makes
#
# The command comes out of BrowserController, so this checks what the
# application runs, not a command written here.
browser = (root / 'Horos/Sources/BrowserController.m').read_bytes().decode('latin1')
# The unencrypted branch: the encrypted one differs only by -e and a password.
command = re.search(r'else\s*\n\s*args = \[NSArray arrayWithObjects: (@"-q"[^\]]*?), destFile, nil\];', browser)
if not command:
    failures.append('BrowserController.m: the zip command changed shape; this test is stale')
else:
    arguments = [part.strip().strip('@"') for part in command.group(1).split(',')]
    arguments = [a for a in arguments if a.startswith('-')]

    def element(group, number, vr, payload):
        if len(payload) % 2:
            payload += b'\x00' if vr == b'UI' else b' '
        return struct.pack('<HH2sH', group, number, vr, len(payload)) + payload

    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory)
        source = path / 'source'
        source.mkdir()
        digests = {}
        for index in range(3):
            uid = ('1.2.826.0.1.3680043.8.498.%d' % (100 + index)).encode()
            meta = (element(0x0002, 0x0002, b'UI', b'1.2.840.10008.5.1.4.1.1.7')
                    + element(0x0002, 0x0003, b'UI', uid)
                    + element(0x0002, 0x0010, b'UI', b'1.2.840.10008.1.2.1'))
            meta = element(0x0002, 0x0000, b'UL', struct.pack('<I', len(meta))) + meta
            dataset = (element(0x0008, 0x0018, b'UI', uid)
                       + element(0x0010, 0x0010, b'PN', b'ANDRE^JOSE')
                       + element(0x0020, 0x0013, b'IS', str(index + 1).encode()))
            name = 'IM-0001-%04d.dcm' % (index + 1)
            content = b'\x00' * 128 + b'DICM' + meta + dataset
            (source / name).write_bytes(content)
            digests[name] = hashlib.sha256(content).hexdigest()

        archive = path / 'study.zip'
        zipped = subprocess.run(['/usr/bin/zip'] + arguments + [str(archive)] +
                                [str(source / name) for name in sorted(digests)],
                                capture_output=True, text=True)
        if zipped.returncode != 0:
            failures.append('/usr/bin/zip %s failed: %s' % (arguments, zipped.stderr))
        else:
            tested = subprocess.run(['/usr/bin/unzip', '-t', str(archive)],
                                    capture_output=True, text=True)
            if tested.returncode != 0:
                failures.append('a common zip client rejected the archive: %s' % tested.stdout)
            extracted = path / 'extracted'
            subprocess.run(['/usr/bin/unzip', '-q', '-o', str(archive), '-d', str(extracted)],
                           check=True, capture_output=True)
            found = sorted(p.name for p in extracted.rglob('*') if p.is_file())
            if found != sorted(digests):
                failures.append('the archive holds %r, not the instances put in it' % found)
            else:
                for name, digest in digests.items():
                    again = hashlib.sha256((extracted / name).read_bytes()).hexdigest()
                    if again != digest:
                        failures.append('%s came back changed' % name)
                print('ok: /usr/bin/zip %s round-tripped %d instances through /usr/bin/unzip byte for byte'
                      % (' '.join(arguments), len(digests)))

# --------------------------------------------------------------- the wiring
data = (root / 'Horos/Sources/WebPortalConnection+Data.mm').read_bytes().decode('latin1')
for route, marker in (('WADO', 'This is a \'special case\''), ('processZip', '-(void)processZip')):
    begin = data.index(marker)
    end = data.index('\n}\n', begin)
    body = data[begin:end]
    if 'HorosWebPortalArchiveFormat formatForRequestedPath' not in body:
        failures.append('%s does not ask for the archive format' % route)
    if 'archiveFormat.pathExtension' not in body:
        failures.append('%s does not name the file by the format' % route)
    if 'archiveFormat.mimeType' not in body:
        failures.append('%s does not send the format\'s content type' % route)
    if 'Content-Disposition' not in body:
        failures.append('%s does not send a file name' % route)
    if 'osirixzip' in body:
        failures.append('%s still hardcodes the legacy extension' % route)

for failure in failures:
    print('FAIL: %s' % failure)
sys.exit(1 if (failures or swift_result) else 0)
