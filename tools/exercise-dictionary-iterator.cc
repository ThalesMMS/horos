// Traverse a small hash dictionary from begin() to end() and stop.
#include "HorosDictionaryLookup.h"
#include <dcmtk/dcmdata/dchashdi.h>
#include <dcmtk/dcmdata/dcdicent.h>
#include <cstdio>
#include <cstring>

int main(int argc, char **argv)
{
    DcmHashDict dict;
    dict.put(new DcmDictEntry(0x0010, 0x0010, EVR_PN, "PatientName", 1, 1, NULL, OFFalse, NULL));
    dict.put(new DcmDictEntry(0x0008, 0x0060, EVR_CS, "Modality", 1, 1, NULL, OFFalse, NULL));
    dict.put(new DcmDictEntry(0x0018, 0x0015, EVR_CS, "BodyPartExamined", 1, 1, NULL, OFFalse, NULL));

    int seen = 0;
    for (DcmHashDictIterator it = dict.begin(); it != dict.end(); ++it) {
        if (*it == NULL) { printf("NULL ENTRY\n"); return 3; }
        ++seen;
        if (seen > 1000) { printf("DID NOT TERMINATE\n"); return 2; }
    }
    printf("entries=%d seen=%d\n", (int) dict.size(), seen);

    // and the lookup that used to walk off the end
    int found = 0;
    for (DcmHashDictIterator it = dict.begin(); it != dict.end(); ++it)
        if ((*it)->contains("NotARealDicomField")) found++;
    printf("unknown-name matches=%d\n", found);

    // an entry with no name must answer "no", not crash
    DcmDictEntry nameless(0x0009, 0x0001, EVR_UN, NULL, 1, 1, NULL, OFFalse, NULL);
    printf("nameless.contains=%d\n", HorosDictionaryEntryMatchesName(&nameless, "PatientName"));
    DcmDataDictionary names(OFFalse, OFFalse);
    names.addEntry(new DcmDictEntry(nameless));
    names.addEntry(new DcmDictEntry(0x0010, 0x0010, EVR_PN, "PatientName", 1, 1, NULL, OFFalse, NULL));
    if (!HorosFindStandardDicomEntry(names, "PatientName") ||
        HorosFindStandardDicomEntry(names, "NotARealDicomField")) return 4;
    printf("OK\n");
    return 0;
}
