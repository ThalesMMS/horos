#!/usr/bin/env python3
"""A UID longer than the caller's buffer is refused, not copied or truncated."""
from pathlib import Path
from dcmtk_build import dcmtk_flags
import re, subprocess, sys, tempfile

root = Path(__file__).resolve().parents[1]
code = r'''
#include <stdio.h>
#include <string.h>
#include <stdlib.h>

#include "HorosDICOMIdentity.h"

#define check(...) do{if(!(__VA_ARGS__)){printf("FAIL: %s\n",#__VA_ARGS__);return 1;}}while(0)

// What the C-STORE sender declares on its stack.
#define DIC_UI_LEN 64
typedef char DIC_UI[DIC_UI_LEN + 1];

int main(void)
{
    DcmDataset dataset;
    // A canary right after the buffer catches a copy that runs past its end.
    struct { DIC_UI sopClass; char guardA[16]; DIC_UI sopInstance; char guardB[16]; } frame;
    const char guard[16] = {1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16};

    char legal[DIC_UI_LEN + 1];
    memset(legal, '1', DIC_UI_LEN); legal[DIC_UI_LEN] = 0;   // exactly 64 characters
    char oversized[301];
    memset(oversized, '2', 300); oversized[300] = 0;

    // A legal UID still goes through, and the identifiers are exact.
    memcpy(frame.guardA, guard, 16); memcpy(frame.guardB, guard, 16);
    dataset.putAndInsertString(DCM_SOPClassUID, "1.2.840.10008.5.1.4.1.1.2");
    dataset.putAndInsertString(DCM_SOPInstanceUID, legal);
    check(HorosFindSOPClassAndInstanceInDataSet(&dataset, frame.sopClass, sizeof(frame.sopClass),
                                              frame.sopInstance, sizeof(frame.sopInstance), OFFalse));
    check(strcmp(frame.sopClass, "1.2.840.10008.5.1.4.1.1.2") == 0);
    check(strcmp(frame.sopInstance, legal) == 0);
    check(memcmp(frame.guardA, guard, 16) == 0 && memcmp(frame.guardB, guard, 16) == 0);

    // One character past the buffer is refused, and nothing is written past it.
    char justOver[DIC_UI_LEN + 2];
    memset(justOver, '3', DIC_UI_LEN + 1); justOver[DIC_UI_LEN + 1] = 0;  // 65 characters
    memcpy(frame.guardA, guard, 16); memcpy(frame.guardB, guard, 16);
    dataset.putAndInsertString(DCM_SOPInstanceUID, justOver);
    check(!HorosFindSOPClassAndInstanceInDataSet(&dataset, frame.sopClass, sizeof(frame.sopClass),
                                               frame.sopInstance, sizeof(frame.sopInstance), OFFalse));
    check(memcmp(frame.guardA, guard, 16) == 0 && memcmp(frame.guardB, guard, 16) == 0);

    // Far over: this is the case that overwrote the stack.
    memcpy(frame.guardA, guard, 16); memcpy(frame.guardB, guard, 16);
    dataset.putAndInsertString(DCM_SOPInstanceUID, oversized);
    check(!HorosFindSOPClassAndInstanceInDataSet(&dataset, frame.sopClass, sizeof(frame.sopClass),
                                               frame.sopInstance, sizeof(frame.sopInstance), OFFalse));
    check(memcmp(frame.guardA, guard, 16) == 0 && memcmp(frame.guardB, guard, 16) == 0);

    // An oversized SOP Class is refused the same way.
    memcpy(frame.guardA, guard, 16); memcpy(frame.guardB, guard, 16);
    dataset.putAndInsertString(DCM_SOPClassUID, oversized); dataset.putAndInsertString(DCM_SOPInstanceUID, legal);
    check(!HorosFindSOPClassAndInstanceInDataSet(&dataset, frame.sopClass, sizeof(frame.sopClass),
                                               frame.sopInstance, sizeof(frame.sopInstance), OFFalse));
    check(memcmp(frame.guardA, guard, 16) == 0 && memcmp(frame.guardB, guard, 16) == 0);

    // An empty value is a legitimate answer, not an overflow.
    dataset.putAndInsertString(DCM_SOPClassUID, ""); dataset.putAndInsertString(DCM_SOPInstanceUID, "");
    check(HorosFindSOPClassAndInstanceInDataSet(&dataset, frame.sopClass, sizeof(frame.sopClass),
                                              frame.sopInstance, sizeof(frame.sopInstance), OFFalse));
    check(frame.sopClass[0] == 0 && frame.sopInstance[0] == 0);

    // A null destination or a zero size is refused rather than dereferenced.
    check(!HorosGetStringDOElement(&dataset, DCM_SOPClassUID, NULL, 64));
    check(!HorosGetStringDOElement(&dataset, DCM_SOPClassUID, frame.sopClass, 0));

    // Space padded UIDs are still trimmed, and a padded value that only fits
    // once trimmed is still refused: the buffer has to hold what was read.
    dataset.putAndInsertString(DCM_SOPClassUID, "1.2.3 "); dataset.putAndInsertString(DCM_SOPInstanceUID, "1.2.4 ");
    check(HorosFindSOPClassAndInstanceInDataSet(&dataset, frame.sopClass, sizeof(frame.sopClass),
                                              frame.sopInstance, sizeof(frame.sopInstance), OFTrue));
    check(strcmp(frame.sopClass, "1.2.3") == 0 && strcmp(frame.sopInstance, "1.2.4") == 0);

    printf("PASS: a 64 character UID is accepted exactly, 65 and 300 character UIDs are "
           "refused with the surrounding stack untouched, empty values and null "
           "destinations are handled, and space padding is still trimmed\n");
    return 0;
}
'''

with tempfile.TemporaryDirectory(prefix='horos-uid-bounds-') as folder:
    p = Path(folder)
    (p / 'test.cc').write_text(code)
    subprocess.run(['xcrun', 'clang++', '-std=c++17', '-fsanitize=address,undefined',
                    '-fno-sanitize-recover=all', str(p / 'test.cc'), *dcmtk_flags(), '-o', str(p / 'test')], check=True)
    subprocess.run([str(p / 'test')], check=True)

server = (root / 'Horos/Sources/HorosQueryRetrieveServer.mm').read_text()
callback = server[server.index('void storeCallback('):server.index('class QueryRetrieveAssociation')]
assert callback.index('HorosFindSOPClassAndInstanceInDataSet(') < callback.index('context->callbackHandler(')
assert 'DU_findSOPClassAndInstanceIn' not in (root / 'Horos/Sources/DCMTKStoreSCU.mm').read_text(encoding='latin1')
