#!/usr/bin/env python3
"""The image list is fetched hierarchically, not with a relational query.

A hierarchical C-FIND carries the unique key of every level above the one it asks
for. An IMAGE level query holding only the study is a relational query: optional
in the standard, gated on an extended negotiation this application never
proposes, and answered with nothing by a strictly hierarchical SCP. Both places
that listed a study's images did exactly that.

The walk now goes STUDY, SERIES, then one IMAGE query per series carrying both
UIDs, and falls back to the relational form only when the series cannot be
listed.
"""
from pathlib import Path
import json
import socket
import subprocess
import sys
import tempfile
import time

root = Path(__file__).resolve().parents[1]
failures = []

source = (root / 'Horos/Sources/DCMTKQueryNode.mm').read_bytes().decode('latin1')


def block(text, start):
    opening = text.index('{', start)
    depth, index = 0, opening
    while index < len(text):
        if text[index] == '{':
            depth += 1
        elif text[index] == '}':
            depth -= 1
            if depth == 0:
                return text[opening:index + 1]
        index += 1
    return ''


# --- the walk ---------------------------------------------------------------
at = source.find('- (BOOL) queryImagesHierarchicallyForStudy:')
if at < 0:
    failures.append('the hierarchical walk is gone')
else:
    walk = block(source, at)
    if '"SERIES"' not in walk:
        failures.append('the walk no longer lists the series first')
    image = walk[walk.find('"IMAGE"') - 900:walk.find('"IMAGE"') + 40] if '"IMAGE"' in walk else ''
    for tag in ('DCM_StudyInstanceUID', 'DCM_SeriesInstanceUID'):
        if tag not in image:
            failures.append('the IMAGE query no longer carries %s' % tag)
    # The series answers must not reach the caller's own children: -addChild:
    # sorts a response by its level, and the caller drains those as images.
    if 'DCMTKStudyQueryNode queryNodeWithDataset' not in walk:
        failures.append('the walk queries the series on the node the caller drains')
    if '[self queryWithValues' in walk:
        failures.append('the walk still queries self, whose children are purged per query')
    # And each series has to be added to what is already there.
    if 'addObjectsFromArray' not in walk:
        failures.append('the walk replaces the children instead of accumulating them')

# --- both callers, each with the relational fallback -------------------------
callers = ('- (void) WADOCFindThread: (id) sender', '- (void) CFINDThread: (NSString*) studyInstanceUID')
for caller in callers:
    at = source.find(caller)
    if at < 0:
        failures.append('%s is gone' % caller.strip())
        continue
    body = block(source, at)
    if 'queryImagesHierarchicallyForStudy' not in body:
        failures.append('%s does not walk the series' % caller.strip())
    if 'putAndInsertString(DCM_QueryRetrieveLevel, "IMAGE"' not in body:
        failures.append('%s has no relational fallback' % caller.strip())

# --- the SCP that refuses a relational query --------------------------------
def interpreter():
    """A python that can run the fixture server."""
    for candidate in [sys.executable] + [str(p) for p in
                                         Path('/private/tmp').glob('*/*/*/scratchpad/*venv*/bin/python')]:
        check = subprocess.run([candidate, '-c', 'import pydicom, pynetdicom'], capture_output=True)
        if check.returncode == 0:
            return candidate
    return None


findscu = next((root / p / 'bin/findscu' for p in
                ('build/Build/Intermediates.noindex/Horos.build/Release/DCMTK.build/Install',
                 'build/Build/Intermediates.noindex/Horos.build/Debug/DCMTK.build/Install')
                if (root / p / 'bin/findscu').is_file()), None)
python = interpreter()
if findscu is None:
    print('skipped: needs a built DCMTK; there is no findscu to query with', file=sys.stderr)
    sys.exit(2)
elif python is None:
    failures.append('no interpreter here has pydicom and pynetdicom. Create one with:\n'
                    '  python3 -m venv /tmp/horos-dicom-venv\n'
                    "  /tmp/horos-dicom-venv/bin/python -m pip install 'pydicom>=3,<4' pynetdicom")
else:
    with tempfile.TemporaryDirectory(prefix='horos-hierarchical-') as directory:
        path = Path(directory)
        port = None
        log = path / 'server.log'
        server = subprocess.Popen(
            [python, str(root / 'tools/serve-wado-fixture.py'), str(path / 'fixture'),
             str(path / 'evidence'), '--dicom-port', '0', '--wado-port', '0',
             '--strict', '--series', '2', '--instances', '3', '--odd-length-series-uids'],
            stdout=log.open('w'), stderr=subprocess.STDOUT, text=True)
        try:
            # The study identifier comes out of the evidence file rather than the
            # log, and the port has to be accepting before anything is asked of it.
            study, results = None, path / 'evidence/wado-results.json'
            for _ in range(150):
                if server.poll() is not None:
                    break
                if results.is_file():
                    try:
                        state = json.loads(results.read_text())
                        if state.get('ready'):
                            port = state['dicom_port']
                            for endpoint in (port, state['wado_port']):
                                with socket.create_connection(('127.0.0.1', endpoint), 0.2):
                                    pass
                            study = state['study']
                            print('fixture ready: DICOM=%d HTTP=%d' % (port, state['wado_port']))
                            break
                    except (OSError, ValueError):
                        pass
                time.sleep(0.2)
            if not study:
                failures.append('the fixture server did not start: %s'
                                % log.read_text()[-400:])
            else:
                query_logs = []
                def query(*keys):
                    # findscu prints the responses on stderr.
                    done = subprocess.run(
                        [str(findscu), '-S', '-aec', 'WADOFIX', '-aet', 'HOROSTEST']
                        + [a for key in keys for a in ('-k', key)]
                        + ['127.0.0.1', str(port)], capture_output=True, text=True, timeout=30)
                    output = (done.stdout or '') + (done.stderr or '')
                    query_logs.append((keys, done.returncode, output))
                    return output

                # The series of the study, hierarchically: two of them.
                series = query('QueryRetrieveLevel=SERIES', 'StudyInstanceUID=' + study,
                               'SeriesInstanceUID')
                if '\0' in series:
                    print('observed DICOM NUL padding in SERIES response')
                # UI values may carry a trailing DICOM NUL padding byte in
                # this legacy findscu's printed output. It is not part of the UID
                # and cannot be passed to exec as an argument.
                found = [line.split('[')[1].split(']')[0].strip().rstrip('\0')
                         for line in series.splitlines() if 'SeriesInstanceUID' in line
                         and '[' in line]
                if len(set(found)) != 2:
                    failures.append('a hierarchical SERIES query returned %d series, expected 2'
                                    % len(set(found)))
                # The images of one series, hierarchically: three of them.
                if found:
                    images = query('QueryRetrieveLevel=IMAGE', 'StudyInstanceUID=' + study,
                                   'SeriesInstanceUID=' + found[0], 'SOPInstanceUID')
                    count = sum(1 for line in images.splitlines()
                                if 'SOPInstanceUID' in line and '[' in line)
                    if count != 3:
                        failures.append('a hierarchical IMAGE query returned %d instances, expected 3'
                                        % count)
                # The relational form - the study alone - is refused, which is
                # the whole reason the walk exists.
                relational = query('QueryRetrieveLevel=IMAGE', 'StudyInstanceUID=' + study,
                                   'SeriesInstanceUID', 'SOPInstanceUID')
                if sum(1 for line in relational.splitlines()
                       if 'SOPInstanceUID' in line and '[' in line):
                    failures.append('the strict SCP answered a relational IMAGE query; '
                                    'this test is not exercising the case')
                elif not json.loads(results.read_text())['relational']:
                    failures.append('the fixture did not record the expected relational refusal')
                else:
                    print('ok: the strict SCP answers the hierarchical queries and refuses the '
                          'relational one')
        except (OSError, ValueError) as error:
            failures.append("query setup failed: %s" % error)
        except subprocess.TimeoutExpired as error:
            failures.append('query timed out: %s' % error.cmd)
        finally:
            if failures:
                print('fixture diagnostic:\n' + log.read_text()[-4000:])
                for keys, status, output in locals().get('query_logs', []):
                    print('query %r exited %d:\n%s' % (keys, status, output[-4000:]))
            server.terminate()
            try:
                server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait(timeout=10)

for failure in failures:
    print('FAIL: %s' % failure)
if failures:
    sys.exit(1)
print('ok: both image listings walk the series and query each one by study and series, '
      'accumulating the results, with the relational query kept only as a fallback')
