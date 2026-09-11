#!/usr/bin/env python3
"""Write an element inside a sequence item, and read the file back.

Compiles the production nested-write function against the built GDCM and runs it
on a copy of a synthetic file, then checks the result with an independent
reader. Needs the built GDCM, which this repository does not carry.

Usage: python test-sequence-item-edit.py GDCM_INSTALL_DIR SEQUENCE_FIXTURE
       GDCM_INSTALL_DIR is build/.../GDCM.build/Install, holding include/ and wlib/
"""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

if len(sys.argv) < 3:
    print('skipped: needs the built GDCM and a sequence fixture: '
          'GDCM_INSTALL_DIR SEQUENCE_FIXTURE', file=sys.stderr)
    raise SystemExit(2)

root = Path(__file__).resolve().parents[1]
install = Path(sys.argv[1]).resolve()
fixture = Path(sys.argv[2]).resolve()
original = fixture.read_bytes()

source = (root / 'Horos/Sources/XMLControllerDCMTKCategory.mm').read_bytes().decode('latin1')
start = source.index('typedef struct')
end = source.index('@implementation XMLController (XMLControllerDCMTKCategory)')
production = source[start:end]
# The parser needs Foundation types this program does not want; keep the two
# writers, which is what addresses the element.
production = production[production.index('// gdcm::Anonymizer::Replace refuses'):]

program = r'''
#include <cstdio>
#include <cstring>
#include <sstream>
#include <string>
#include <vector>
#include <gdcmReader.h>
#include <gdcmWriter.h>
#include <gdcmFile.h>
#include <gdcmAnonymizer.h>
#include <gdcmSequenceOfItems.h>
#include <gdcmItem.h>

typedef struct { unsigned short group; unsigned short element; unsigned int item; } HorosTagPathStep;
typedef struct {
    unsigned short group; unsigned short element; bool removes; std::string value;
    std::vector<HorosTagPathStep> path;
} HorosTagEdit;

PRODUCTION

static int failures = 0;
#define check(...) do{ if(!(__VA_ARGS__)){ std::fprintf(stderr, "FAIL: %s\n", #__VA_ARGS__); failures++; } }while(0)

static HorosTagEdit dose(unsigned int item, const char *value)
{
    HorosTagEdit edit;
    edit.group = 0x0018; edit.element = 0x1074; edit.removes = false; edit.value = value;
    HorosTagPathStep step; step.group = 0x0054; step.element = 0x0016; step.item = item;
    edit.path.push_back(step);
    return edit;
}

int main(int argc, char **argv)
{
    const char *path = argv[1];
    std::string reason;

    {
        gdcm::Reader reader; reader.SetFileName(path);
        check(reader.Read());
        gdcm::File &file = reader.GetFile();

        // The reported case: the total dose in the first item.
        check(HorosWriteInDataSet(file.GetDataSet(), dose(0, "123456789"), 0, &reason));

        // An item the sequence does not have is refused, and says so.
        reason.clear();
        check(!HorosWriteInDataSet(file.GetDataSet(), dose(7, "1"), 0, &reason));
        check(reason.find("item") != std::string::npos);

        // A sequence the file does not carry is refused too.
        reason.clear();
        HorosTagEdit absent = dose(0, "1");
        absent.path[0].element = 0x0017;
        check(!HorosWriteInDataSet(file.GetDataSet(), absent, 0, &reason));
        check(reason.find("sequence") != std::string::npos);

        // An element that is not in that item is refused rather than created.
        reason.clear();
        HorosTagEdit missing = dose(0, "1");
        missing.element = 0x9999;
        check(!HorosWriteInDataSet(file.GetDataSet(), missing, 0, &reason));

        gdcm::Writer writer; writer.SetFileName(path); writer.SetFile(file);
        check(writer.Write());
    }

    // Reopen: the change has to be in the file, not only in memory.
    {
        gdcm::Reader reader; reader.SetFileName(path);
        check(reader.Read());
        gdcm::DataSet &ds = reader.GetFile().GetDataSet();
        const gdcm::DataElement &sq = ds.GetDataElement(gdcm::Tag(0x0054, 0x0016));
        gdcm::SmartPointer<gdcm::SequenceOfItems> items = sq.GetValueAsSQ();
        check(items && items->GetNumberOfItems() == 2);
    }

    std::printf("%s\n", failures ? "FAILURES" : "writes applied");
    return failures ? 1 : 0;
}
'''.replace('PRODUCTION', production)

with tempfile.TemporaryDirectory(prefix='horos-sequence-edit-') as tmp:
    p = Path(tmp)
    work = p / 'sequence-edit.dcm'
    shutil.copy(fixture, work)
    (p / 'test.mm').write_text(program)
    subprocess.run(['xcrun', 'clang++', '-std=c++17', '-fno-objc-arc',
                    '-I', str(install / 'include/GDCM'),
                    str(p / 'test.mm'), str(install / 'wlib/libGDCM.a'),
                    '-framework', 'Foundation', '-framework', 'CoreFoundation',
                    '-lz', '-lexpat', '-liconv',
                    '-o', str(p / 'test')], check=True)
    subprocess.run([str(p / 'test'), str(work)], check=True)

    import json
    reader = p / 'read.py'
    reader.write_text(
        'import json, sys, pydicom\n'
        'ds = pydicom.dcmread(sys.argv[1], stop_before_pixels=True)\n'
        'sq = ds.RadiopharmaceuticalInformationSequence\n'
        'print(json.dumps({\n'
        '    "items": len(sq),\n'
        '    "doses": [float(i.RadionuclideTotalDose) for i in sq],\n'
        '    "times": [str(i.RadiopharmaceuticalStartTime) for i in sq],\n'
        '    "routes": [str(i.RadiopharmaceuticalRoute) for i in sq],\n'
        '    "top": "RadionuclideTotalDose" in ds,\n'
        '}))\n')
    for candidate in Path('/private/tmp').glob('*/*/*/scratchpad/*venv*/bin/python'):
        if subprocess.run([str(candidate), '-c', 'import pydicom'],
                          capture_output=True).returncode == 0:
            out = json.loads(subprocess.check_output(
                [str(candidate), str(reader), str(work)], text=True))
            break
    else:
        raise SystemExit('this test needs an interpreter with pydicom')

    assert out['items'] == 2, f'the sequence lost an item: {out}'
    assert out['doses'][0] == 123456789, f'item 0 did not take the new dose: {out}'
    assert out['doses'][1] == 185000000, f'item 1 was changed too: {out}'
    assert out['times'] == ['090000.000', '143000.000'], (
        f'a start time was disturbed: {out}')
    assert out['routes'] == ['Intravenous', 'Intravenous'], (
        f'a sibling element was disturbed: {out}')
    assert out['top'] is False, (
        f'the edit created a top-level element instead: {out}')

assert fixture.read_bytes() == original, 'the fixture itself was modified'
print('PASS: item 0 written, item 1 and both start times untouched, '
      'nothing added at the top level, and absent items, sequences and elements refused')
