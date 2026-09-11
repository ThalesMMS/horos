#pragma once
#include <dcmtk/config/osconfig.h>
#include <dcmtk/dcmdata/dctk.h>
#include <dcmtk/dcmdata/dcmetinf.h>
#include <cstring>

// Upstream's DU helper copies with truncation and still returns success. A
// truncated SOP identity must never become a different, apparently valid UID.
inline OFBool HorosGetStringDOElement(DcmItem *item, DcmTagKey tag, char *output, size_t capacity) {
    if (!item || !output || !capacity) return OFFalse;
    output[0] = '\0';
    DcmElement *element = NULL;
    if (item->findAndGetElement(tag, element).bad() || !element) return OFFalse;
    char *value = NULL;
    Uint32 length = 0;
    if (element->getString(value, length).bad()) return OFFalse;
    if (length >= capacity || (length && !value)) return OFFalse;
    if (length) std::memcpy(output, value, length);
    output[length] = '\0';
    return OFTrue;
}

inline OFBool HorosFindSOPClassAndInstanceInDataSet(DcmItem *item,
    char *sopClass, size_t classCapacity, char *sopInstance, size_t instanceCapacity,
    OFBool tolerateSpacePadding = OFFalse) {
    const OFBool result = HorosGetStringDOElement(item, DCM_SOPClassUID, sopClass, classCapacity) &&
        HorosGetStringDOElement(item, DCM_SOPInstanceUID, sopInstance, instanceCapacity);
    if (result && tolerateSpacePadding) {
        for (char *value : {sopClass, sopInstance}) {
            const size_t length = std::strlen(value);
            if (length && value[length - 1] == ' ') value[length - 1] = '\0';
        }
    }
    return result;
}

inline OFBool HorosFindSOPClassAndInstanceInFile(const char *path,
    char *sopClass, size_t classCapacity, char *sopInstance, size_t instanceCapacity,
    OFBool tolerateSpacePadding = OFFalse) {
    DcmFileFormat file;
    if (file.loadFileUntilTag(path, EXS_Unknown, EGL_noChange, DCM_MaxReadLength,
                             ERM_autoDetect, DCM_PixelData).bad()) return OFFalse;
    return HorosFindSOPClassAndInstanceInDataSet(file.getDataset(), sopClass, classCapacity,
                                               sopInstance, instanceCapacity, tolerateSpacePadding);
}
