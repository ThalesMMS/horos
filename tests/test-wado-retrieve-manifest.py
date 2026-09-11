#!/usr/bin/env python3
"""A WADO retrieval records which instances did not arrive, and asks again.

WADODownload knew a retrieval was incomplete - it counted successes and logged
`errors: 2 / total: 8` - but the counts were numbers, not identities. Nothing
recorded which instances were missing, so nothing could ask for those and only
those, and the alert said the same thing whether one instance was lost or two
hundred.

The manifest is Swift and is compiled and run here. The download loop that fills
it is checked in source, including the temporary filename: it used to be the
remaining-thread count and the object pointer, and -WADORetrieve: calls the same
downloader again for each batch of more than 50 instances, so a batch overwrote
files an earlier one had written and the importer had not yet moved away.
"""
from pathlib import Path
import json
import re
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

root = Path(__file__).resolve().parents[1]
failures = []
manifest = root / 'Horos/Sources/RetrieveManifest.swift'
download = (root / 'Horos/Sources/WADODownload.m').read_bytes().decode('latin1')

DRIVER = r'''
import Foundation

func url(_ uid: String, extra: String = "") -> URL {
    return URL(string: "http://h/wado?requestType=WADO&studyUID=1.2.3&objectUID=" + uid + extra)!
}

func emit(_ key: String, _ value: String) { print(key + "\t" + value) }
func emit(_ key: String, _ value: [String]) { emit(key, value.joined(separator: ",")) }
func emit(_ key: String, _ value: Bool) { emit(key, value ? "yes" : "no") }
func emit(_ key: String, _ value: Int) { emit(key, String(value)) }

// Four instances: two arrive, one is refused for good, one fails in a way that
// is worth repeating.
let mixed = RetrieveManifest(urls: [url("a"), url("b"), url("c"), url("d")])
mixed.recordSuccess(forURL: url("a"))
mixed.recordSuccess(forURL: url("b"))
mixed.recordFailure(forURL: url("c"), statusCode: 404, reason: "HTTP 404")
mixed.recordFailure(forURL: url("d"), statusCode: 503, reason: "HTTP 503")
emit("mixed.requested", mixed.requestedCount)
emit("mixed.received", mixed.receivedCount)
emit("mixed.complete", mixed.isComplete)
emit("mixed.missing", mixed.missingObjectUIDs)
emit("mixed.rejected", mixed.rejectedObjectUIDs)
emit("mixed.retry", mixed.retryableURLs.map { RetrieveManifest.objectUID(for: $0) })
emit("mixed.summary", mixed.summary)

// The repeat of the transient one succeeds; the refused one is still missing.
mixed.recordSuccess(forURL: url("d"))
emit("afterRetry.complete", mixed.isComplete)
emit("afterRetry.missing", mixed.missingObjectUIDs)
emit("afterRetry.retry", mixed.retryableURLs.map { RetrieveManifest.objectUID(for: $0) })
emit("afterRetry.summary", mixed.summary)

// When the only failure was transient, the repeat closes the manifest.
let recovered = RetrieveManifest(urls: [url("r1"), url("r2")])
recovered.recordSuccess(forURL: url("r1"))
recovered.recordFailure(forURL: url("r2"), statusCode: 503, reason: "HTTP 503")
recovered.recordSuccess(forURL: url("r2"))
emit("recovered.complete", recovered.isComplete)
emit("recovered.summary", recovered.summary)

// A transport failure has no status at all, and is worth repeating.
let dropped = RetrieveManifest(urls: [url("e")])
dropped.recordFailure(forURL: url("e"), statusCode: 0, reason: "connection lost")
emit("dropped.retry", dropped.retryableURLs.map { RetrieveManifest.objectUID(for: $0) })
emit("dropped.reason", dropped.reason(forObjectUID: "e") ?? "none")

// The same instance under two URLs is asked for once and counted as duplicated.
let twice = RetrieveManifest(urls: [url("f"), url("f", extra: "&transferSyntax=1.2.840.10008.1.2.1")])
emit("twice.requested", twice.requested_count_shim)
emit("twice.duplicates", twice.duplicateObjectUIDs)

// And so is one that arrives twice.
let again = RetrieveManifest(urls: [url("g")])
again.recordSuccess(forURL: url("g"))
again.recordSuccess(forURL: url("g"))
emit("again.duplicates", again.duplicateObjectUIDs)
emit("again.summary", again.summary)

// Nothing was heard about the rest: missing, but not refused.
let cut = RetrieveManifest(urls: [url("h"), url("i")])
cut.recordSuccess(forURL: url("h"))
cut.recordAbandoned(url: url("h"))
cut.recordAbandoned(url: url("i"))
emit("cut.missing", cut.missingObjectUIDs)
emit("cut.rejected", cut.rejectedObjectUIDs)
emit("cut.retry", cut.retryableURLs.map { RetrieveManifest.objectUID(for: $0) })

// A URL that names no instance is its own identity, so the manifest balances.
let plain = URL(string: "http://h/file.dcm")!
emit("plain.uid", RetrieveManifest.objectUID(for: plain))

// The detail names the instances rather than counting them, and is bounded.
let many = RetrieveManifest(urls: (1...5).map { url("m\($0)") })
many.recordFailure(forURL: url("m1"), statusCode: 404, reason: "HTTP 404")
emit("detail", many.detail(limit: 2).replacingOccurrences(of: "\n", with: " | "))
'''

extension = 'extension RetrieveManifest { var requested_count_shim: Int { requestedCount } }\n'

# --- the manifest, compiled and run ------------------------------------------
results = {}
swiftc = subprocess.run(['xcrun', '--sdk', 'macosx', '-f', 'swiftc'], capture_output=True, text=True)
if swiftc.returncode != 0:
    failures.append('no swiftc here: %s' % (swiftc.stderr or '').strip())
else:
    with tempfile.TemporaryDirectory(prefix='horos-manifest-') as directory:
        # Top-level statements are only allowed in a file called main.swift.
        (Path(directory) / 'main.swift').write_text(DRIVER)
        (Path(directory) / 'shim.swift').write_text(extension)
        binary = Path(directory) / 'manifest'
        built = subprocess.run(['xcrun', '--sdk', 'macosx', 'swiftc', '-o', str(binary),
                                str(manifest), str(Path(directory) / 'main.swift'),
                                str(Path(directory) / 'shim.swift')],
                               capture_output=True, text=True)
        if built.returncode != 0:
            failures.append('the manifest does not compile:\n%s' % built.stderr[-1500:])
        else:
            run = subprocess.run([str(binary)], capture_output=True, text=True)
            if run.returncode != 0:
                failures.append('the manifest driver failed: %s' % run.stderr[-800:])
            for line in run.stdout.splitlines():
                key, _, value = line.partition('\t')
                results[key] = value

if results:
    expected = {
        'mixed.requested': '4',
        'mixed.received': '2',
        'mixed.complete': 'no',
        'mixed.missing': 'c,d',
        # Only the one the server refused outright; asking again for it is waste.
        'mixed.rejected': 'c',
        'mixed.retry': 'd',
        # The transient one arrived; the refused one is still missing, and
        # there is nothing left worth asking for.
        'afterRetry.complete': 'no',
        'afterRetry.missing': 'c',
        'afterRetry.retry': '',
        'recovered.complete': 'yes',
        'recovered.summary': '2 of 2 instances received.',
        'dropped.retry': 'e',
        'dropped.reason': 'connection lost',
        'twice.requested': '1',
        'twice.duplicates': 'f',
        'again.duplicates': 'g',
        'cut.missing': 'i',
        'cut.rejected': '',
        'cut.retry': 'i',
        'plain.uid': 'http://h/file.dcm',
    }
    for key, value in expected.items():
        if results.get(key) != value:
            failures.append('%s is %r, expected %r' % (key, results.get(key), value))
    if '2 of 4 instances received, 2 missing (1 refused by the server)' not in results.get('mixed.summary', ''):
        failures.append('the summary does not say what is missing: %r' % results.get('mixed.summary'))
    if 'duplicated' not in results.get('again.summary', ''):
        failures.append('an instance received twice is not reported: %r' % results.get('again.summary'))
    if 'm1: HTTP 404' not in results.get('detail', '') or 'and 3 more' not in results.get('detail', ''):
        failures.append('the detail does not name the missing instances, bounded: %r'
                        % results.get('detail'))

# --- the download loop -------------------------------------------------------
if '- (BOOL) WADODownloadPass:' not in download:
    failures.append('the download is no longer a pass that can be repeated')
driver = download[download.find('- (void) WADODownload: (NSArray*) urlToDownload'):]
if not driver:
    failures.append('the public download method is gone')
else:
    for expected, missing in (
            ('initWithURLs:', 'the manifest is not built from the list that will be asked for'),
            ('retryableURLs', 'the retry does not ask the manifest what is worth repeating'),
            ('WADORetryAttempts', 'the number of attempts is not configurable'),
            ('recordAbandonedURL:', 'a retrieval cut short is recorded as absent instead of unknown'),
            ('WADO Retrieve Incomplete', 'an incomplete retrieval is not reported')):
        if expected not in driver:
            failures.append(missing)
    # The alert has to wait for the end: reporting the first failure said the
    # same thing whether one instance was lost or two hundred.
    if 'firstWadoErrorDisplayed' in download:
        failures.append('the alert still fires on the first failure')

# Every file left in the incoming directory needs a name of its own.
if re.search(r'stringWithFormat:@"\.WADO-%d-%ld", WADOThreads', download):
    failures.append('the incoming filename is the thread count again, so batches overwrite '
                    'each other')
if 'NSUUID UUID' not in download:
    failures.append('the incoming filename is not unique per file')

# The successes of every pass count, so the caller's sub-operation total is right.
if re.search(r'self\.countOfSuccesses = 0;\s*\n\s*WADOTotal', download):
    failures.append('the success count is reset inside the pass, so a retry loses the first pass')

# --- the fixture models the case ---------------------------------------------
def interpreter():
    for candidate in [sys.executable] + [str(p) for p in
                                         Path('/private/tmp').glob('*/*/*/scratchpad/*venv*/bin/python')]:
        if subprocess.run([candidate, '-c', 'import pydicom, pynetdicom'],
                          capture_output=True).returncode == 0:
            return candidate
    return None


python = interpreter()
if python is None:
    failures.append('no interpreter here has pydicom and pynetdicom. Create one with:\n'
                    '  python3 -m venv /tmp/horos-dicom-venv\n'
                    "  /tmp/horos-dicom-venv/bin/python -m pip install 'pydicom>=3,<4' pynetdicom")
else:
    with tempfile.TemporaryDirectory(prefix='horos-fail-once-') as directory:
        path = Path(directory)
        port = 11171
        log = path / 'server.log'
        server = subprocess.Popen(
            [python, str(root / 'tools/serve-wado-fixture.py'), str(path / 'fixture'),
             str(path / 'evidence'), '--dicom-port', str(port), '--wado-port', str(port + 1),
             '--series', '1', '--instances', '2', '--fail-once', '1'],
            stdout=log.open('w'), stderr=subprocess.STDOUT, text=True)
        try:
            state, results_file = None, path / 'evidence/wado-results.json'
            for _ in range(150):
                if server.poll() is not None:
                    break
                if results_file.is_file():
                    try:
                        with socket.create_connection(('127.0.0.1', port + 1), 0.2):
                            state = json.loads(results_file.read_text())
                            break
                    except OSError:
                        pass
                time.sleep(0.2)
            if not state:
                failures.append('the fixture server did not start: %s' % log.read_text()[-400:])
            else:
                uid = state['transient_instances'][0]
                address = ('http://127.0.0.1:%d/wado?requestType=WADO&studyUID=%s&objectUID=%s'
                           % (port + 1, state['study'], uid))

                def status():
                    try:
                        with urllib.request.urlopen(address, timeout=10) as answer:
                            return answer.status
                    except urllib.error.HTTPError as error:
                        return error.code

                first, second = status(), status()
                if (first, second) != (503, 200):
                    failures.append('--fail-once answered %s then %s, expected 503 then 200; '
                                    'the transient case is not being exercised' % (first, second))
                else:
                    print('ok: the fixture refuses an instance once and serves it on the retry')
        finally:
            server.terminate()
            try:
                server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server.kill()

for failure in failures:
    print('FAIL: %s' % failure)
if failures:
    sys.exit(1)
print('ok: the manifest names the instances that did not arrive, separates the ones a server '
      'refused from the ones worth asking again, and the download asks again for those only')
