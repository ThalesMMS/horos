#!/usr/bin/env python3
"""Saving the WADO sheet leaves the node's DIMSE TLS settings alone.

The commit block of -editWADO: is extracted and run against a node dictionary,
so what the sheet writes is read off the production source rather than described.
"""
from pathlib import Path
import re
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
pane = root / 'Preference Panes/OSILocationsPreferencePane/OSILocationsPreferencePanePref.m'
source = pane.read_bytes().decode('latin1')

action = source[source.index('- (IBAction) editWADO: (id) sender'):]
action = action[:action.index('\n}\n')]
commit = action[action.index('if( result == NSRunStoppedResponse)'):]
# The sheet's own persistence is not what this test drives.
commit = commit.replace('[[NSUserDefaults standardUserDefaults] setObject: [dicomNodes arrangedObjects] forKey: @"SERVERS"];', '')

failures = []

# The TLS keys the DIMSE association reads, from the code that reads them.
users = [root / 'Horos/Sources/QueryController.mm',
         root / 'Horos/Sources/DCMTKStoreSCU.mm',
         root / 'Horos/Sources/DCMTKServiceClassUser.mm']
reads_tls = any('TLSEnabled' in path.read_bytes().decode('latin1') for path in users)
if not reads_tls:
    failures.append('no DIMSE client reads TLSEnabled any more; this test is stale')

# Static: the WADO sheet must not write any TLS key at all.
for key in re.findall(r'forKey:\s*@"(\w+)"', commit):
    if key.startswith('TLS'):
        failures.append('the WADO sheet still writes %s' % key)

code = r'''
#import <Foundation/Foundation.h>

// AppKit is not linked here; the sheet returns this when the user clicks OK.
#define NSRunStoppedResponse 1000

static int failures;
#define check(c) do { if (!(c)) { printf("FAIL %s:%d %s\n", __FILE__, __LINE__, #c); failures++; } } while (0)

// A node configured for TLS only: authenticated DIMSE, a chosen cipher suite,
// a peer certificate rule, and no WADO settings yet.
static NSMutableDictionary *tlsNode(void)
{
    return [@{ @"Address": @"pacs.example.org",
               @"Port": @11112,
               @"AETitle": @"SECUREPACS",
               @"retrieveMode": @0,                 // C-MOVE
               @"TLSEnabled": @YES,
               @"TLSAuthenticated": @YES,
               @"TLSCipherSuites": @[@{@"Cipher": @"TLS_RSA_WITH_AES_128_CBC_SHA", @"Supported": @YES}],
               @"TLSCertificateVerification": @1,
               @"TLSUseDHParameterFileURL": @YES,
               @"TLSDHParameterFileURL": @"/tmp/dh.pem" } mutableCopy];
}

// What the sheet leaves in its fields when the user clicks OK.
static void commitWADO(NSMutableDictionary *aServer, int WADOPort, int WADOTransferSyntax,
                       int WADOhttps, NSString *WADOUrl, NSString *WADOUsername, NSString *WADOPassword)
{
    int result = NSRunStoppedResponse;
    COMMIT
}

int main(void) { @autoreleasepool {
    NSMutableDictionary *node = tlsNode();
    NSDictionary *before = [node copy];

    commitWADO(node, 8443, -1, 1, @"wado", @"reader", @"secret");

    // WADO is configured.
    check([node[@"retrieveMode"] intValue] == 2);
    check([node[@"WADOPort"] intValue] == 8443);
    check([node[@"WADOhttps"] intValue] == 1);
    check([node[@"WADOUrl"] isEqual: @"wado"]);
    check([node[@"WADOUsername"] isEqual: @"reader"]);
    check([node[@"WADOPassword"] isEqual: @"secret"]);
    check([node[@"WADOTransferSyntax"] intValue] == -1);

    // Every TLS setting the DIMSE association reads survives untouched.
    for (NSString *key in before) {
        if ([key hasPrefix: @"TLS"])
            check([node[key] isEqual: before[key]]);
    }
    check([node[@"TLSEnabled"] boolValue] == YES);
    check([node[@"TLSAuthenticated"] boolValue] == YES);
    check([node[@"TLSCipherSuites"] count] == 1);
    check([node[@"TLSCertificateVerification"] intValue] == 1);

    // So does the identity of the node itself.
    check([node[@"Address"] isEqual: before[@"Address"]]);
    check([node[@"Port"] isEqual: before[@"Port"]]);
    check([node[@"AETitle"] isEqual: before[@"AETitle"]]);

    // Committing again is not a second chance to lose it.
    commitWADO(node, 8080, 0, 0, @"wado2", nil, nil);
    check([node[@"TLSEnabled"] boolValue] == YES);
    check([node[@"WADOPort"] intValue] == 8080);
    check([node[@"WADOhttps"] intValue] == 0);
    // Fields the sheet leaves empty do not erase what is stored.
    check([node[@"WADOUsername"] isEqual: @"reader"]);

    // A plain node is unaffected either way.
    NSMutableDictionary *plain = [@{ @"retrieveMode": @0, @"TLSEnabled": @NO } mutableCopy];
    commitWADO(plain, 8080, -1, 0, @"wado", nil, nil);
    check([plain[@"TLSEnabled"] boolValue] == NO);
    check([plain[@"retrieveMode"] intValue] == 2);

    if (failures) { printf("%d failure(s)\n", failures); return 1; }
    printf("ok\n");
    return 0;
} }
'''

code = code.replace('COMMIT', commit)

with tempfile.TemporaryDirectory() as directory:
    path = Path(directory)
    (path / 'main.m').write_text(code)
    build = subprocess.run(['xcrun', 'clang', '-fobjc-arc', '-Wno-unused-variable',
                            str(path / 'main.m'), '-framework', 'Foundation',
                            '-o', str(path / 'test')], capture_output=True, text=True)
    if build.returncode != 0:
        print(build.stderr)
        sys.exit(1)
    result = subprocess.run([str(path / 'test')])

for failure in failures:
    print('FAIL: %s' % failure)
sys.exit(1 if (failures or result.returncode) else 0)
