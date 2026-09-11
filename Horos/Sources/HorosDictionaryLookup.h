#pragma once
#include <dcmtk/config/osconfig.h>
#include <dcmtk/dcmdata/dcdict.h>
#include <dcmtk/dcmdata/dcdicent.h>

inline bool HorosDictionaryEntryMatchesName(const DcmDictEntry *entry, const char *name) {
    return entry && entry->getTagName() && name && entry->contains(name);
}

// Plugin dictionaries can contain unnamed entries. Use the public iterators
// under the dictionary lock so an unknown keyword cannot dereference a nil name.
inline const DcmDictEntry *HorosFindStandardDicomEntry(DcmDataDictionary& dictionary, const char *name) {
    if (!name || !*name) return NULL;
    for (auto iterator = dictionary.normalBegin(); iterator != dictionary.normalEnd(); ++iterator)
        if (!((*iterator)->getGroup() % 2) && HorosDictionaryEntryMatchesName(*iterator, name))
            return *iterator;
    for (auto iterator = dictionary.repeatingBegin(); iterator != dictionary.repeatingEnd(); ++iterator)
        if (!((*iterator)->getGroup() % 2) && HorosDictionaryEntryMatchesName(*iterator, name))
            return *iterator;
    return NULL;
}
