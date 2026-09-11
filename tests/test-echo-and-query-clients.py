#!/usr/bin/env python3
"""Verification shares the query association setup, TLS and timeout configuration.

Native wire evidence and peer tests are documented in
`docs/dicom-verification-stack-validation.md`.
"""
from pathlib import Path
import re
import sys

root = Path(__file__).resolve().parents[1]
failures = []
pane = (root / 'Preference Panes/OSILocationsPreferencePane/'
        'OSILocationsPreferencePanePref.m').read_bytes().decode('latin1')
reporter = (root / 'tools/report-association-identity.py')

# The framework bridge must reach the executable's query implementation.
live = re.sub(r'//[^\n]*', '', pane)
region = live[live.find('echoAddress:'):live.find('- (void) enableControls:')]
if 'verifyDICOMServer:serverParameters' not in region or 'NSClassFromString(@"DCMTKQueryNode")' not in region:
    failures.append('Locations no longer reaches the application query stack')
if 'NSTask' in region or 'echoscu' in region:
    failures.append('Locations still launches a different DICOM stack')
query = (root/'Horos/Sources/DCMTKQueryNode.mm').read_text(encoding='latin1')
entry = query.split('+ (BOOL)verifyDICOMServer:', 1)[-1].split('// Shared association', 1)[0]
for required in ('[NSUserDefaults defaultAETitle]', 'extraParameters: server',
                 'setupNetworkWithSyntax: UID_VerificationSOPClass'):
    if required not in entry: failures.append('verification lost shared configuration: ' + required)
setup = query.split('// Shared association', 1)[-1].split('- (OFCondition)findSCU:', 1)[0]
for required in ('DIMSE_echoUser', 'DIMSE_NONBLOCKING', '_dimse_timeout',
                 'status != STATUS_Success', 'ASC_createAssociationParameters',
                 'connectionTimeout > 0 ? connectionTimeout : _acse_timeout'):
    if required not in setup: failures.append('verification lost bounded failure handling: ' + required)
if 'detachNewThreadSelector: @selector( testThread:)' not in pane:
    failures.append('the Verify action no longer runs in a background thread')

# --- and the tool that tells the two apart records enough to tell them --------
if not reporter.exists():
    failures.append('the SCP that records who called is gone')
else:
    text = reporter.read_text()
    for needed in ('callingAETitle', 'calledAETitle', "'from'", 'implementationClassUID',
                   'maximumLength', 'abstractSyntax', 'accepted'):
        if needed not in text:
            failures.append('the recorder does not write down %s' % needed)
    if 'EVT_C_ECHO' not in text:
        failures.append('the recorder does not record a C-ECHO, so the two cannot be compared')
    if 'EVT_ABORTED' not in text:
        failures.append('an association that is aborted leaves no record, which is the case the '
                        'report is about')
    if 'keys' not in text:
        failures.append('the query keys are not recorded, so a filter cannot be checked')

for failure in failures:
    print('FAIL: %s' % failure)
if failures:
    sys.exit(1)
print('ok: verification shares query configuration and the recorder compares wire identity')
