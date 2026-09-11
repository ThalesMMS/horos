/*
 * Ask the dictionary Horos actually compiles — Binaries/dcmtk-source/dcdictbi.cc —
 * what PatientName is, then apply the same load-and-resolve path getDicomField:
 * uses and print what that answers.
 *
 * The process does not read Resources/dicom.dic or the cmake DCMTK dictionary
 * on its own. This helper is how a test sees the same table the application
 * walks, without launching the application.
 */
#import <Foundation/Foundation.h>
#import "DICOMDataDictionary.h"

#include <dcmtk/dcmdata/dcdict.h>
#include <dcmtk/dcmdata/dcdicent.h>

#include <cstdio>


static void printLookup(const char *label, const char *name)
{
    const DcmDataDictionary& dictionary = dcmDataDict.rdlock();
    const DcmDictEntry *entry = dictionary.findEntry(name);
    if (entry)
        printf("%s %s=%04x,%04x name=%s private=%s\n", label, name,
               entry->getGroup(), entry->getElement(), entry->getTagName(),
               (entry->getGroup() % 2) ? "yes" : "no");
    else
        printf("%s %s=ffff,ffff\n", label, name);
    dcmDataDict.rdunlock();
}

static void printTagName(const char *label, unsigned group, unsigned element)
{
    const DcmDataDictionary& dictionary = dcmDataDict.rdlock();
    const DcmDictEntry *entry = dictionary.findEntry(DcmTagKey(group, element), NULL);
    printf("%s (%04x,%04x)=%s entries=%d\n", label, group, element,
           entry ? entry->getTagName() : "(absent)",
           dictionary.numberOfEntries());
    dcmDataDict.rdunlock();
}

int main(int argc, char **argv)
{
    @autoreleasepool
    {
        printf("builtin DCMTK=%s%s\n", PACKAGE_VERSION, PACKAGE_VERSION_SUFFIX);
        printf("builtin DCM_DICT_DEFAULT_PATH=%s\n", DCM_DICT_DEFAULT_PATH);
        const char *env = getenv(DCM_DICT_ENVIRONMENT_VARIABLE);
        printf("builtin %s=%s\n", DCM_DICT_ENVIRONMENT_VARIABLE, env && env[0] ? env : "(unset)");
        printLookup("builtin", "PatientName");
        printLookup("builtin", "PatientsName");
        printTagName("builtin", 0x0010, 0x0010);

        if (argc < 2)
        {
            fprintf(stderr, "usage: %s /path/to/dicom.dic\n", argv[0]);
            return 2;
        }

        if (!HorosLoadVendoredDicomDictionary(@(argv[1])))
        {
            fprintf(stderr, "could not load %s\n", argv[1]);
            return 1;
        }

        printTagName("loaded", 0x0010, 0x0010);

        const char *keywords[] = {
            "PatientName", "PatientsName",
            "PatientBirthDate", "PatientsBirthDate",
            "PatientSex", "PatientsSex",
            "ReferringPhysicianName", "ReferringPhysiciansName",
            "PatientID",
            NULL
        };
        int failed = 0;
        for (const char **keyword = keywords; *keyword; ++keyword)
        {
            unsigned group = 0xffff, element = 0xffff;
            BOOL ok = HorosResolveDicomKeyword(@(*keyword), &group, &element);
            printf("resolve %s=%04x,%04x\n", *keyword, group, element);
            if (!ok)
                failed = 1;
        }
        return failed;
    }
}
