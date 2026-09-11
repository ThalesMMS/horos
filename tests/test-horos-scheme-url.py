#!/usr/bin/env python3
"""horos:// parsing is separate from LaunchServices and from the browser.

A worklist link that used to open a study started failing after Chrome 94. The
handler in AppController was already registered; the scheme is in Info.plist.
What was missing is a parser that can be checked on its own, so a blocked
external-protocol prompt is not mistaken for a bad URL, and DisplayStudy is
handed the parameters the query actually carried - including percent-encoded
values.

This compiles HorosSchemeURL.swift and drives it. The LaunchServices and
browser layers are test-horos-scheme-launch.py.
"""
from pathlib import Path
import re
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
failures = []

source = root / 'Horos/Sources/HorosSchemeURL.swift'
application = (root / 'Horos/Sources/AppController.m').read_bytes().decode('latin1')
info = (root / 'Horos/Info.plist').read_text()
display = (root / 'Horos/Sources/XMLRPCMethods.mm').read_bytes().decode('latin1')

DRIVER = r'''
import Foundation

func emit(_ key: String, _ value: String?) {
    print(key + "\t" + (value ?? "nil").replacingOccurrences(of: "\n", with: " "))
}

func diagnose(_ url: String) -> HorosSchemeDiagnosis {
    return HorosSchemeURL.parse(url)
}

func dump(_ key: String, _ diagnosis: HorosSchemeDiagnosis) {
    emit(key + ".layer", diagnosis.layer)
    emit(key + ".code", diagnosis.code)
    emit(key + ".method", diagnosis.invocation?.methodName)
    let parameters = diagnosis.invocation?.parameters ?? [:]
    let keys = parameters.keys.sorted().joined(separator: ",")
    emit(key + ".keys", keys)
    for name in parameters.keys.sorted() {
        emit(key + ".p." + name, parameters[name])
    }
    emit(key + ".image", diagnosis.invocation?.imageSpecifier)
}

let study = "2.25.287428555831697092999545823839393783259"
dump("display", diagnose("horos://?methodName=DisplayStudy&StudyInstanceUID=" + study))
dump("osirix", diagnose("osirix://?methodName=DisplayStudy&patientID=QA-A&StudyID=1"))
dump("encoded", diagnose("horos://?methodName=DisplayStudy&StudyInstanceUID=1.2.3%261.4"))
dump("quotedQ", diagnose("horos://?methodName=Retrieve&filterValue='a?b'"))
dump("quotedAnd", diagnose("horos://?methodName=Retrieve&filterValue='x&y'"))
dump("image", diagnose("horos://?image=1.2.840.10008.1.2+1.2.3.4.5"))
dump("missing", diagnose("horos://?methodName=DisplayStudy"))
dump("emptyUID", diagnose("horos://?methodName=DisplayStudy&StudyInstanceUID="))
dump("noQuery", diagnose("horos://open"))
dump("http", diagnose("https://example.invalid/study"))
dump("retrieve", diagnose("horos://?methodName=Retrieve&serverName=WADOFIX&filterKey=StudyInstanceUID&filterValue=1.2.3"))
dump("plusNotSpace", diagnose("horos://?methodName=DisplayStudy&StudyInstanceUID=1.2.3+4"))
'''

swiftc = subprocess.run(['xcrun', '--sdk', 'macosx', '-f', 'swiftc'], capture_output=True, text=True)
results = {}
if swiftc.returncode != 0:
    failures.append('no swiftc here: %s' % (swiftc.stderr or '').strip())
elif not source.is_file():
    failures.append('HorosSchemeURL.swift is missing')
else:
    with tempfile.TemporaryDirectory(prefix='horos-scheme-url-') as directory:
        driver = Path(directory) / 'main.swift'
        driver.write_text(DRIVER)
        binary = Path(directory) / 'scheme-url'
        built = subprocess.run(['xcrun', '--sdk', 'macosx', 'swiftc', '-framework', 'AppKit',
                                '-o', str(binary), str(source), str(driver)],
                               capture_output=True, text=True)
        if built.returncode != 0:
            failures.append('HorosSchemeURL.swift does not compile:\n%s' % built.stderr[-1500:])
        else:
            run = subprocess.run([str(binary)], capture_output=True, text=True)
            if run.returncode != 0:
                failures.append('the parser driver failed: %s' % run.stderr[-800:])
            for line in run.stdout.splitlines():
                key, _, value = line.partition('\t')
                results[key] = value


def expect(key, value, detail):
    got = results.get(key)
    if got != value:
        failures.append('%s: expected %r, got %r (%s)' % (key, value, got, detail))


if results:
    expect('display.layer', 'accepted', 'a DisplayStudy URL with a UID is valid')
    expect('display.code', 'ok', 'accepted URLs carry a stable code')
    expect('display.method', 'DisplayStudy', 'DisplayStudy must keep its method name')
    expect('display.p.StudyInstanceUID',
           '2.25.287428555831697092999545823839393783259',
           'DisplayStudy must receive the StudyInstanceUID from the query')

    expect('osirix.layer', 'accepted', 'osirix:// is the same handler')
    expect('osirix.p.patientID', 'QA-A', 'case of parameter names is preserved')
    expect('osirix.p.StudyID', '1', 'StudyID is an accepted DisplayStudy key')

    # Decode after splitting, so %26 stays inside the UID instead of becoming
    # a second parameter.
    expect('encoded.layer', 'accepted', 'a percent-encoded ampersand is still one UID')
    expect('encoded.p.StudyInstanceUID', '1.2.3&1.4',
           'percent-decoding must not resplit the query')
    if 'encoded.p.4' in results or results.get('encoded.keys', '').count(',') > 1:
        failures.append('encoded UID was split on the decoded ampersand: %r'
                        % results.get('encoded.keys'))

    expect('quotedQ.layer', 'accepted', 'quoted question marks are part of the value')
    expect('quotedQ.p.filterValue', 'a?b', 'quotes around a value are stripped')
    expect('quotedAnd.p.filterValue', 'x&y', 'quoted ampersands are part of the value')

    expect('image.layer', 'accepted', 'an image= link is a valid invocation')
    expect('image.image', '1.2.840.10008.1.2+1.2.3.4.5',
           'the SOP Class + SOP Instance separator is a plus, not a space')

    expect('missing.layer', 'parser',
           'DisplayStudy without an identifier is a parser refusal, not a browser block')
    expect('missing.code', 'invalid-parameters',
           'the parser names the refusal')
    expect('emptyUID.layer', 'parser', 'an empty StudyInstanceUID is not an identifier')
    expect('emptyUID.code', 'invalid-parameters', 'empty UID is invalid-parameters')
    expect('noQuery.layer', 'parser', 'a horos URL with no query is a parser error')
    expect('http.layer', 'parser', 'another scheme is not this handler')

    expect('retrieve.layer', 'accepted', 'Retrieve does not need a DisplayStudy identifier')
    expect('retrieve.p.serverName', 'WADOFIX', 'Retrieve keeps its server name')
    expect('plusNotSpace.p.StudyInstanceUID', '1.2.3+4',
           '+ in a query value is not a space; image= uses it as a separator')

# --- getUrl uses the parser and still opens an image= link once --------------
at = application.find('- (void)getUrl:(NSAppleEventDescriptor *)event withReplyEvent:')
handler = application[at:at + 9000] if at >= 0 else ''
if not handler:
    failures.append('getUrl: is gone')
else:
    if 'HorosSchemeURL' not in handler:
        failures.append('getUrl: still parses the query inline instead of HorosSchemeURL')
    if 'parseString:' not in handler and 'parse:' not in handler:
        failures.append('getUrl: does not call the parser')
    if 'methodCall:' not in handler:
        failures.append('getUrl: no longer dispatches methodName')
    if 'invalid-parameters' not in handler and 'parser' not in handler:
        failures.append('getUrl: does not log a parser refusal')
    # One XML-RPC dispatch for a methodName URL: do not also treat it as image=.
    if handler.count('[XMLRPCServer methodCall:') > 1:
        failures.append('getUrl: dispatches the XML-RPC method more than once')
    # The image= path that test-study-not-opened-reason.py watches must remain.
    if 'BOOL succeeded = NO;' not in handler:
        failures.append('the horos:// image handler is gone')
    if handler.count('displayStudy:') < 2:
        failures.append('the image= search no longer asks displayStudy: twice')

# DisplayStudy still reads the keys the parser must populate.
display_at = display.find('- (NSDictionary*)DisplayStudy:(NSDictionary*)paramDict error:')
display_body = display[display_at:display_at + 2500] if display_at >= 0 else ''
if not display_body:
    failures.append('DisplayStudy: is gone')
else:
    for key in ('StudyInstanceUID', 'PatientID', 'AccessionNumber', 'StudyID'):
        if key not in display_body:
            failures.append('DisplayStudy: no longer reads %s' % key)

if '<string>horos</string>' not in info or '<string>osirix</string>' not in info:
    failures.append('Info.plist no longer claims both URL schemes')

for failure in failures:
    print('FAIL: %s' % failure)
if failures:
    sys.exit(1)
print('ok: horos:// parsing accepts DisplayStudy with a UID, keeps encoded '
      'and quoted values, rejects a DisplayStudy with no identifier as a parser '
      'error, and getUrl dispatches the parsed parameters once')
