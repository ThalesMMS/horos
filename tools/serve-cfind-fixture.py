#!/usr/bin/env python3
"""A C-FIND SCP that records the identifier it was asked with, verbatim.

A query for several studies at once is one attribute holding several values
separated by `\\` — UID List matching, PS3.4 C.2.2.2.2. Whether that reaches the
server intact cannot be seen from the requestor: the value can be trimmed,
escaped or split anywhere between the field and the wire. This writes down every
identifier exactly as it arrives, and answers with UID List matching so that the
result says whether the list was understood as a list.

Four studies, one instance each, so a query naming two of them has an
unambiguous right answer.
"""
import argparse
import json
import threading
from pathlib import Path

from pydicom.dataset import Dataset
from pydicom.uid import generate_uid
from pynetdicom import AE, ALL_TRANSFER_SYNTAXES, evt
from pynetdicom.sop_class import (PatientRootQueryRetrieveInformationModelFind,
                                  StudyRootQueryRetrieveInformationModelFind, Verification)

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('evidence', type=Path, help='directory for the result file')
parser.add_argument('--port', type=int, default=11199)
parser.add_argument('--aetitle', default='CFINDFIX')
arguments = parser.parse_args()
arguments.evidence.mkdir(parents=True, exist_ok=True)

STUDIES = []
for index in range(4):
    STUDIES.append({
        'StudyInstanceUID': generate_uid(),
        'PatientID': 'CFIND-169-%d' % index,
        'PatientName': 'CFIND^STUDY%d' % index,
        'StudyDescription': 'Study %d' % index,
        'AccessionNumber': 'ACC%d' % index,
        'StudyDate': '2026010%d' % (index + 1),
        'StudyTime': '120000',
        'StudyID': str(index),
        'ModalitiesInStudy': 'CT',
        'NumberOfStudyRelatedInstances': 1,
        'NumberOfStudyRelatedSeries': 1,
    })

record = {'studies': [s['StudyInstanceUID'] for s in STUDIES], 'queries': []}
lock = threading.Lock()


def values(element):
    """The values of an element as a list, whether it is single- or multi-valued."""
    if element is None:
        return []
    value = element.value
    if value is None or value == '':
        return []
    # A multi-valued element is a MultiValue, which is neither a list nor a
    # tuple; treating it as a single value is how a UID list silently becomes
    # one long string that matches nothing.
    if isinstance(value, (str, bytes)) or not hasattr(value, '__iter__'):
        return [str(value)]
    return [str(one) for one in value]


def matches(study, query):
    for element in query:
        if element.keyword in ('QueryRetrieveLevel', 'SpecificCharacterSet'):
            continue
        wanted = values(element)
        if not wanted:
            continue  # a return key, not a matching key
        held = str(study.get(element.keyword, ''))
        # UID List matching: any of the values is a match. Everything else here
        # is a single-value exact match, which is all this fixture needs.
        if not any(held == one for one in wanted):
            return False
    return True


def on_find(event):
    query = event.identifier
    entry = {
        'level': str(getattr(query, 'QueryRetrieveLevel', '')),
        'elements': {},
        'raw': {},
    }
    for element in query:
        entry['elements'][element.keyword or str(element.tag)] = values(element)
        entry['raw'][element.keyword or str(element.tag)] = repr(element.value)
    answers = [s for s in STUDIES if matches(s, query)]
    entry['answers'] = [s['StudyInstanceUID'] for s in answers]
    with lock:
        record['queries'].append(entry)
        arguments.evidence.joinpath('cfind-queries.json').write_text(json.dumps(record, indent=2))
    print('C-FIND %s: %s -> %d answer(s)'
          % (entry['level'],
             ', '.join('%s=%s' % (k, '\\'.join(v)) for k, v in entry['elements'].items() if v) or 'no keys',
             len(answers)), flush=True)

    for study in answers:
        answer = Dataset()
        answer.QueryRetrieveLevel = 'STUDY'
        for key, value in study.items():
            setattr(answer, key, value)
        yield 0xFF00, answer


handlers = [(evt.EVT_C_FIND, on_find)]

ae = AE(ae_title=arguments.aetitle)
ae.add_supported_context(Verification, ALL_TRANSFER_SYNTAXES)
for model in (StudyRootQueryRetrieveInformationModelFind,
              PatientRootQueryRetrieveInformationModelFind):
    ae.add_supported_context(model, ALL_TRANSFER_SYNTAXES)

for study in STUDIES:
    print('study %s  %s' % (study['StudyInstanceUID'], study['PatientID']))
print('%s listening on port %d' % (arguments.aetitle, arguments.port), flush=True)
try:
    ae.start_server(('127.0.0.1', arguments.port), evt_handlers=handlers)
except KeyboardInterrupt:
    pass
finally:
    arguments.evidence.joinpath('cfind-queries.json').write_text(json.dumps(record, indent=2))
