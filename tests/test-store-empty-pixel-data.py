#!/usr/bin/env python3
"""A stored object that declares an image and carries empty Pixel Data is refused (#695).

An OsiriX MD with a full disk served C-GET sub-operations whose Pixel Data had
length zero: CT and CR that declare 512 x 512 or 2320 x 2828 and hold no
picture. Horos stored and indexed them, and the retrieve inventory counted them
as received, so the query window showed the study as complete. The store
provider now refuses them with 0xA900, which the inventory records as a
rejection, so a later retrieve asks again.

Compile the production predicate against the DCMTK archives the app links, and
exercise it on data sets built in memory and read back from files, as the
network provider sees them.
"""
from pathlib import Path
import re
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dcmtk_build import ROOT, dcmtk_flags  # noqa: E402

failures = []
server = (ROOT / 'Horos/Sources/HorosQueryRetrieveServer.mm').read_bytes().decode('latin1')
callback = server[server.find('void storeCallback('):]
callback = callback[:callback.find('\nclass ')]
if not re.search(r'HorosDataSetLacksDeclaredPixels\(\*dataset\)\)\s*\{\s*context->setStatus\(STATUS_STORE_Error_DataSetDoesNotMatchSOPClass\)',
                 callback):
    failures.append('the store callback does not refuse an image with empty Pixel Data')
if callback.find('HorosDataSetLacksDeclaredPixels') > callback.find('context->callbackHandler('):
    failures.append('the refusal comes after the file is written')
inventory = (ROOT / 'Horos/Sources/RetrieveInventory.swift').read_text()
if 'else if status != 0 { data.rejected[uid' not in inventory:
    failures.append('the retrieve inventory no longer records a refused store as rejected')

DRIVER = r'''
#include "HorosDICOMIdentity.h"
#include <dcmtk/dcmdata/dcpixseq.h>
#include <dcmtk/dcmdata/dcpxitem.h>
#include <cstdio>
#include <string>

static void identity(DcmItem &item, Uint16 rows, Uint16 columns) {
    item.putAndInsertString(DCM_SOPClassUID, UID_CTImageStorage);
    item.putAndInsertString(DCM_SOPInstanceUID, "1.2.826.0.1.3680043.2.1125.695.1");
    if (rows) item.putAndInsertUint16(DCM_Rows, rows);
    if (columns) item.putAndInsertUint16(DCM_Columns, columns);
    item.putAndInsertUint16(DCM_BitsAllocated, 16);
    item.putAndInsertUint16(DCM_SamplesPerPixel, 1);
}

static bool roundTrip(DcmFileFormat &file, E_TransferSyntax xfer, const std::string &path) {
    if (file.saveFile(path.c_str(), xfer).bad()) { std::printf("save failed %s\n", path.c_str()); return false; }
    DcmFileFormat read;
    if (read.loadFile(path.c_str()).bad()) { std::printf("load failed %s\n", path.c_str()); return false; }
    return HorosDataSetLacksDeclaredPixels(read.getDataset());
}

int main(int argc, char **argv) {
    std::string dir = argv[1];
    int failed = 0;
    auto expect = [&](const char *name, bool actual, bool expected) {
        std::printf("%s\t%s\n", name, actual == expected ? "ok" : "WRONG");
        if (actual != expected) failed++;
    };

    DcmFileFormat empty; identity(*empty.getDataset(), 512, 512);
    empty.getDataset()->putAndInsertUint16Array(DCM_PixelData, NULL, 0);
    expect("empty native, in memory", HorosDataSetLacksDeclaredPixels(empty.getDataset()), true);
    expect("empty native, read back", roundTrip(empty, EXS_LittleEndianExplicit, dir + "/empty.dcm"), true);

    DcmFileFormat full; identity(*full.getDataset(), 4, 4);
    Uint16 pixels[16] = {0};
    full.getDataset()->putAndInsertUint16Array(DCM_PixelData, pixels, 16);
    expect("native picture, read back", roundTrip(full, EXS_LittleEndianExplicit, dir + "/full.dcm"), false);

    DcmFileFormat none; identity(*none.getDataset(), 1024, 1024);
    DcmItem *icon = NULL;
    none.getDataset()->findOrCreateSequenceItem(DCM_IconImageSequence, icon, -2);
    icon->putAndInsertUint16(DCM_Rows, 32); icon->putAndInsertUint16(DCM_Columns, 32);
    icon->putAndInsertUint8Array(DCM_PixelData, NULL, 0);
    expect("no Pixel Data, empty icon (#101)", roundTrip(none, EXS_LittleEndianExplicit, dir + "/none.dcm"), false);

    DcmFileFormat sizeless; identity(*sizeless.getDataset(), 0, 0);
    sizeless.getDataset()->putAndInsertUint16Array(DCM_PixelData, NULL, 0);
    expect("no declared size", roundTrip(sizeless, EXS_LittleEndianExplicit, dir + "/sizeless.dcm"), false);

    DcmFileFormat encapsulated; identity(*encapsulated.getDataset(), 8, 8);
    DcmPixelData *data = new DcmPixelData(DCM_PixelData);
    DcmPixelSequence *sequence = new DcmPixelSequence(DCM_PixelSequenceTag);
    sequence->insert(new DcmPixelItem(DCM_PixelItemTag));
    DcmPixelItem *fragment = new DcmPixelItem(DCM_PixelItemTag);
    Uint8 bytes[8] = {0xff, 0xd8, 0xff, 0xd9, 0, 0, 0, 0};
    fragment->putUint8Array(bytes, 8);
    sequence->insert(fragment);
    data->putOriginalRepresentation(EXS_JPEGProcess14SV1, NULL, sequence);
    encapsulated.getDataset()->insert(data);
    expect("encapsulated picture, read back", roundTrip(encapsulated, EXS_JPEGProcess14SV1, dir + "/encapsulated.dcm"), false);

    expect("no data set", HorosDataSetLacksDeclaredPixels(NULL), false);
    return failed ? 1 : 0;
}
'''

flags = dcmtk_flags()
with tempfile.TemporaryDirectory(prefix='horos-empty-pixels-') as directory:
    path = Path(directory)
    (path / 'driver.cc').write_text(DRIVER)
    built = subprocess.run(['xcrun', 'clang++', '-std=c++17', str(path / 'driver.cc'), *flags,
                            '-o', str(path / 'driver')], capture_output=True, text=True)
    if built.returncode:
        failures.append('the driver does not compile: ' + built.stderr[-3000:])
    else:
        run = subprocess.run([str(path / 'driver'), directory], capture_output=True, text=True)
        print(run.stdout.strip())
        if run.returncode:
            failures.append('the predicate is wrong for a case above' + (': ' + run.stderr[-800:] if run.stderr else ''))

for failure in failures:
    print('FAIL: %s' % failure)
if failures:
    sys.exit(1)
print('ok: an image with empty Pixel Data is refused before it is written, and nothing else is')
