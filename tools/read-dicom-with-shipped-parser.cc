// Read a DICOM file with the parser the application ships and report what it
// says.
//
// Built against the object files of a Debug build of Horos, so it exercises the
// DCMTK the application actually links - the vendored 3.5.4 sources in
// Binaries/dcmtk-source - and not whatever DCMTK is installed on the machine.
// tests/test-dcmtk-parser-robustness.py builds and drives it; see
// docs/dcmtk-version-audit.md.
//
// Nothing fed to it is meant to succeed: the point is that malformed input is
// refused rather than walking off the end of a buffer.
#include "dcfilefo.h"
#include "dcdeftag.h"
#include "dcistrmf.h"
#include <cstdio>

int main(int argc, char **argv)
{
    if (argc < 2) { fprintf(stderr, "usage: %s <file>\n", argv[0]); return 2; }
    DcmFileFormat file;
    OFCondition cond = file.loadFile(argv[1]);
    printf("load: %s\n", cond.good() ? "ok" : cond.text());
    if (cond.good())
    {
        DcmDataset *dataset = file.getDataset();
        OFString value;
        if (dataset->findAndGetOFString(DCM_SOPInstanceUID, value).good())
            printf("sop instance: %s\n", value.c_str());
        printf("elements: %lu\n", (unsigned long) dataset->card());
        // Walk everything, which is what an importer does.
        DcmStack stack;
        unsigned long walked = 0;
        while (dataset->nextObject(stack, OFTrue).good()) walked++;
        printf("walked: %lu\n", walked);
    }
    return cond.good() ? 0 : 1;
}
