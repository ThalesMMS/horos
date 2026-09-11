#!/usr/bin/env python3
"""Sources and the database publisher use the native Bonjour path (#606).

Source level, with `<git revision>` as an optional argument for the negative
control:

* the Sources helper browses with `HorosBonjourBrowser` for both service types
  and stops them on teardown;
* it handles find, remove and **update**, and an update refreshes the row it
  already has instead of removing and re-adding it;
* the database publisher advertises through `HorosBonjourAdvertisement`,
  created only for a live listener's port and stopped with it;
* the NSNetService-typed API other code and plugins still use is kept: the
  deprecated `-netService` accessor, `AppController.dicomBonjourPublisher` and
  the DCM framework's `DCMNetServiceDelegate` are untouched;
* no Bonjour TXT record carries a token or a secret.
"""
from pathlib import Path
import re
import subprocess
import sys

root = Path(__file__).resolve().parents[1]


def read(path):
    if len(sys.argv) > 1:
        return subprocess.check_output(['git', '-C', str(root), 'show', sys.argv[1] + ':' + path]).decode('latin1')
    return (root / path).read_bytes().decode('latin1')


sources = read('Horos/Sources/BrowserController+Sources.m')
publisher = read('Horos/Sources/BonjourPublisher.m')
publisher_header = read('Horos/Sources/BonjourPublisher.h')
app_header = read('Horos/Sources/AppController.h')
dcm_header = read('DCM Framework/DCMNetServiceDelegate.h')
failures = []


def method(source, signature, terminator='\n}\n'):
    start = source.find(signature)
    if start < 0:
        return ''
    return source[start:source.find(terminator, start) + len(terminator)]


# --- Sources ------------------------------------------------------------------
if 'HorosBonjourBrowser* _nsbOsirix' not in sources or 'HorosBonjourBrowser* _nsbDicom' not in sources:
    failures.append('the Sources helper still browses with NSNetServiceBrowser')
if 'HorosBonjourBrowserDelegate' not in sources:
    failures.append('the Sources helper does not implement the native browser delegate')
for selector in ('didFindService:', 'didRemoveService:', 'didUpdateService:', 'didNotSearch:'):
    if 'horosBonjourBrowser:(HorosBonjourBrowser*)nsb ' + selector not in sources:
        failures.append('the Sources helper does not handle %s' % selector)
update = method(sources, '-(void)horosBonjourBrowser:(HorosBonjourBrowser*)nsb didUpdateService:(HorosBonjourService*)service\n')
if 'resolveWithTimeout' not in update:
    failures.append('an updated service is not resolved again')
if 'removeObject' in update or 'didRemoveService' in update:
    failures.append('an update must refresh the row, never remove it')
if '[_nsbDicom stop]' not in sources or '[_nsbOsirix stop]' not in sources:
    failures.append('the browsers are not stopped on teardown')
if re.search(r'_nsb(Osirix|Dicom) = \[\[NSNetServiceBrowser', sources):
    failures.append('an NSNetServiceBrowser is still constructed for the Sources list')

# --- publisher ----------------------------------------------------------------
update_bonjour = method(publisher, '- (void)updateBonjour {\n')
if 'HorosBonjourAdvertisement alloc] initWithName:' not in update_bonjour:
    failures.append('the database publisher does not advertise natively')
if 'port:[_listener port]' not in update_bonjour:
    failures.append('the advertisement is not created from the live listener port')
if 'publishWithTXTRecord: txtrec' not in update_bonjour:
    failures.append('the advertisement does not publish the TXT record the host builds')
if '[_advertisement stop]' not in update_bonjour:
    failures.append('the advertisement is not stopped when the listener goes')
if publisher.count('[_advertisement release]') < 2:
    failures.append('the advertisement is not released on teardown and on listener change')
if '- (NSNetService*)netService' not in publisher:
    failures.append('the deprecated netService accessor was removed while it still has callers')
# Two registrations of one name and port from one process make the daemon rename
# one of them: the legacy object stays for its accessor's type, unpublished.
if re.search(r'\[_bonjour publish\]', update_bonjour):
    failures.append('the legacy NSNetService is published beside the native advertisement')

# --- preserved public API -----------------------------------------------------
if 'NSNetService* dicomBonjourPublisher' not in app_header:
    failures.append('AppController.dicomBonjourPublisher changed type; plugins read it')
if '- (void) setPublisher: (NSNetService*) p;' not in dcm_header:
    failures.append('the DCM framework net-service API changed; it is public and typed on NSNetService')
if '- (HorosBonjourAdvertisement*)advertisement;' not in publisher_header:
    failures.append('the publisher does not expose its advertisement for validation')
if 'HorosBonjourAdvertisement* _advertisement;' not in publisher_header:
    failures.append('the publisher has no advertisement ivar')

# --- no secrets on the wire ---------------------------------------------------
txt_keys = set(re.findall(r'\[txtrec setObject:[^;]*?forKey:@"([^"]+)"\]', publisher))
forbidden = {key for key in txt_keys if re.search(r'token|secret|password|key$|credential', key, re.I)}
if forbidden:
    failures.append('a Bonjour TXT record would carry %s' % ', '.join(sorted(forbidden)))
if not {'AETitle', 'port'} <= txt_keys:
    failures.append('the advertised TXT lost the AE title or the port: %s' % sorted(txt_keys))

if failures:
    for failure in failures:
        print('FAIL:', failure)
    raise SystemExit(1)
print('ok: Sources and the database publisher use native Bonjour; NSNetService API preserved')
