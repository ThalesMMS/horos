/*
 * Reads each file named on the command line with the DCMTK the application
 * compiles - the pinned upstream library - and prints what came back.
 *
 * The point is not what it parses but that reading a file which lies about its
 * own structure stays inside the buffers it was given. Built with
 * AddressSanitizer by tests/test-dcmtk-parser-robustness.py.
 */
#include <dcmtk/dcmdata/dcfilefo.h>
#include <dcmtk/dcmdata/dcdeftag.h>
#include <dcmtk/dcmdata/dcistrmf.h>
#include <cstdio>
int main(int argc, char **argv) {
    if (argc < 2) { printf("usage: parse <file>...\n"); return 2; }
    for (int i = 1; i < argc; i++) {
        DcmFileFormat file;
        OFCondition status = file.loadFile(argv[i], EXS_Unknown, EGL_noChange, DCM_MaxReadLength, ERM_autoDetect);
        const char *sop = NULL;
        unsigned short rows = 0;
        if (status.good()) {
            file.getDataset()->findAndGetString(DCM_SOPClassUID, sop, OFFalse);
            file.getDataset()->findAndGetUint16(DCM_Rows, rows, 0, OFFalse);
        }
        printf("%-28s %-28s rows=%u sop=%s\n", argv[i], status.text(), (unsigned) rows, sop ? sop : "-");
        fflush(stdout);
    }
    return 0;
}
