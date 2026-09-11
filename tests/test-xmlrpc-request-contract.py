#!/usr/bin/env python3
"""An XML-RPC request that cannot be carried out is answered with a fault.

Horos answers XML-RPC over an HTTP port. Requests it would not carry out used to
be answered with a status line and no body: `500 -[NSInvocation
setArgument:atIndex:]: index (4) out of bounds [-1, 3]` for a call with one
parameter too many, `500 -[NSTaggedPointerString objectForKey:]: unrecognized
selector` for a parameter that was not a struct, and `400` followed by an entire
XML document sitting in the reason phrase for a call missing a parameter. A
client could read none of them.

The contract that decides this is Swift, and it is compiled and run here: the
fault documents it produces are parsed as XML and checked against the fault code
convention. The dispatcher that uses it is checked in source, including the part
that used to dispatch to any selector the delegate happened to respond to.
"""
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ElementTree

root = Path(__file__).resolve().parents[1]
failures = []

contract = root / 'Horos/Sources/XMLRPCRequestContract.swift'
connection = (root / 'Nitrogen/Sources/N2XMLRPCConnection.mm').read_bytes().decode('latin1')

DRIVER = r'''
import Foundation

func emit(_ key: String, _ value: String?) {
    print(key + "\t" + (value ?? "nil").replacingOccurrences(of: "\n", with: " "))
}

let structure: [AnyHashable: Any] = ["serverName": "FIXTURE"]

emit("unknown", XMLRPCRequestContract.fault(forUnknownMethodName: "nosuchmethod").document)
emit("tooMany", XMLRPCRequestContract.fault(forParameters: [structure, structure],
                                            methodName: "Retrieve",
                                            acceptedCount: 1)?.document)
emit("notStruct", XMLRPCRequestContract.fault(forParameters: ["notastruct"],
                                              methodName: "Retrieve",
                                              acceptedCount: 1)?.document)
emit("oneStruct", XMLRPCRequestContract.fault(forParameters: [structure],
                                              methodName: "Retrieve",
                                              acceptedCount: 1)?.document)
emit("noParameters", XMLRPCRequestContract.fault(forParameters: [],
                                                 methodName: "Retrieve",
                                                 acceptedCount: 1)?.document)
emit("raised", XMLRPCRequestContract.fault(forFailedMethodName: "Retrieve",
                                           reason: "it went <wrong> & stayed wrong").document)
emit("unparsable", XMLRPCRequestContract.fault(forUnparsableRequest: "not xml").document)

// A method reports an application-level failure by putting a whole
// methodResponse in the error description; that document is the answer.
let application = "<?xml version=\"1.0\"?><methodResponse><params><param><value><struct>"
    + "<member><name>error</name><value>400</value></member>"
    + "</struct></value></param></params></methodResponse>"
emit("passthrough", XMLRPCRequestContract.responseDocument(
    for: NSError(domain: NSCocoaErrorDomain, code: 400,
                 userInfo: [NSLocalizedDescriptionKey: application])))
emit("wrapped", XMLRPCRequestContract.responseDocument(
    for: NSError(domain: NSCocoaErrorDomain, code: 7,
                 userInfo: [NSLocalizedDescriptionKey: "boom"])))
'''

# --- the contract, compiled and run ------------------------------------------
swiftc = subprocess.run(['xcrun', '--sdk', 'macosx', '-f', 'swiftc'], capture_output=True, text=True)
results = {}
if swiftc.returncode != 0:
    failures.append('no swiftc here: %s' % (swiftc.stderr or '').strip())
else:
    with tempfile.TemporaryDirectory(prefix='horos-xmlrpc-') as directory:
        # Top-level statements are only allowed in a file called main.swift.
        driver = Path(directory) / 'main.swift'
        driver.write_text(DRIVER)
        binary = Path(directory) / 'contract'
        # xcrun places the macOS SDK, which swiftc needs to find the standard
        # library, in the environment it runs the compiler in.
        built = subprocess.run(['xcrun', '--sdk', 'macosx', 'swiftc', '-o', str(binary),
                                str(contract), str(driver)],
                               capture_output=True, text=True)
        if built.returncode != 0:
            failures.append('the contract does not compile:\n%s' % built.stderr[-1500:])
        else:
            run = subprocess.run([str(binary)], capture_output=True, text=True)
            if run.returncode != 0:
                failures.append('the contract driver failed: %s' % run.stderr[-800:])
            for line in run.stdout.splitlines():
                key, _, value = line.partition('\t')
                results[key] = value


def fault(key):
    """The faultCode and faultString of a document, or None if it is not a fault."""
    document = results.get(key)
    if not document or document == 'nil':
        return None
    try:
        tree = ElementTree.fromstring(document)
    except ElementTree.ParseError as parse_error:
        failures.append('%s is not well formed XML: %s' % (key, parse_error))
        return None
    members = tree.findall('./fault/value/struct/member')
    if not members:
        return None
    values = {}
    for member in members:
        values[member.find('name').text] = ''.join(member.find('value').itertext()).strip()
    return values


if results:
    # A method that does not exist, and one that does but was called wrongly,
    # are different faults; a client can tell them apart by the code.
    for key, code, expected in (('unknown', '-32601', 'nosuchmethod'),
                                ('tooMany', '-32602', 'Retrieve'),
                                ('notStruct', '-32602', 'struct'),
                                ('raised', '-32500', 'went <wrong> & stayed wrong'),
                                ('unparsable', '-32700', 'not xml')):
        values = fault(key)
        if values is None:
            failures.append('%s did not produce a fault: %r' % (key, results.get(key)))
            continue
        if values.get('faultCode') != code:
            failures.append('%s has faultCode %s, expected %s' % (key, values.get('faultCode'), code))
        if expected not in values.get('faultString', ''):
            failures.append('%s does not say what went wrong: %r' % (key, values.get('faultString')))

    # The two that have to be let through.
    for key in ('oneStruct', 'noParameters'):
        if results.get(key) != 'nil':
            failures.append('%s was refused: %r' % (key, results.get(key)))

    # An application-level error keeps its own document, so the {error: "400"}
    # struct the in-process callers see is what the HTTP callers see too.
    if '<member><name>error</name><value>400</value></member>' not in results.get('passthrough', ''):
        failures.append('an application error no longer answers with its own document: %r'
                        % results.get('passthrough'))
    if fault('wrapped') is None or fault('wrapped').get('faultCode') != '-32500':
        failures.append('an error that is not a methodResponse is not turned into a fault')

    # The fault string is XML, and the reason may contain anything.
    if '&lt;wrong&gt; &amp; stayed' not in results.get('raised', ''):
        failures.append('the fault string is not escaped: %r' % results.get('raised'))

# --- the dispatcher ----------------------------------------------------------
at = connection.find('-(id)methodCall:(NSString*)methodName params:(NSArray*)params error:(NSError**)error')
if at < 0:
    failures.append('the dispatcher is gone')
else:
    opening = connection.index('{', at)
    depth, index = 0, opening
    body = ''
    while index < len(connection):
        if connection[index] == '{':
            depth += 1
        elif connection[index] == '}':
            depth -= 1
            if depth == 0:
                body = connection[opening:index + 1]
                break
        index += 1
    # Nothing is invoked before the parameters have been checked against the
    # method signature.
    for expected, missing in (
            ('faultForParameters:', 'the parameters are no longer checked before the call'),
            ('numberOfArguments', 'the accepted parameter count no longer comes from the signature'),
            ('faultForUnknownMethodName:', 'an unknown method no longer produces a fault')):
        if expected not in body:
            failures.append(missing)
    if 'NSException raise' in body:
        failures.append('the dispatcher still raises instead of reporting a fault')
    if body.find('faultForParameters:') > body.find('invocationWithSelector'):
        failures.append('the parameters are checked after the invocation is built')
    # The error argument goes in the last slot of the signature, not one past
    # however many parameters happened to arrive.
    if 'setArgument:&error atIndex:2+paramIndex' in body:
        failures.append('the error argument index is still derived from the parameter count')
    # And a selector the delegate merely responds to is not enough.
    if not re.search(r'allowed\s*=\s*methodSelectorIsValidated', body):
        failures.append('the dispatcher no longer requires the delegate to publish the method')
    if re.search(r'!methodSelectorIsValidated\s*&&\s*\(!\[_delegate respondsToSelector', body):
        failures.append('any selector the delegate responds to is dispatchable again')

# --- the responses -----------------------------------------------------------
if 'CFHTTPMessageCreateResponse(kCFAllocatorDefault, 500,' in connection:
    failures.append('a failure is still reported as a bare 500 with the reason in the status line')
if 'CFHTTPMessageCreateResponse(kCFAllocatorDefault, error.code,' in connection:
    failures.append('an application error still puts its document in the HTTP reason phrase')
if 'writeDocument:' not in connection:
    failures.append('there is no writer that puts the document in the body')

# The AppleScript bridge passes nil parameters when a script supplies none.
methods = (root / 'Horos/Sources/XMLRPCMethods.mm').read_bytes().decode('latin1')
bridge = methods[methods.find('-(id)methodCall:(NSString*)methodName parameters:'):]
bridge = bridge[:bridge.find('\n}')]
if 'if (!parameters)' not in bridge:
    failures.append('a call with no parameters still reaches +arrayWithObject: as nil')

for failure in failures:
    print('FAIL: %s' % failure)
if failures:
    sys.exit(1)
print('ok: the contract refuses an unpublished method, too many parameters and a parameter '
      'that is not a struct, each with its own fault code, and every answer is a document in '
      'the response body')
