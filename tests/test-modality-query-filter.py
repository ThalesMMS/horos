#!/usr/bin/env python3
"""Several modalities go out as several values in one C-FIND key.

The reports say picking CT+MR returns only the first modality. Horos joins the
selected modalities with a backslash and sends them in ModalitiesInStudy, which
is the DICOM way to ask for a list - but only if the join survives the filter and
the join really becomes a multi-valued element rather than one five-character
string.

The QueryFilter and the DICOM encoding here are the ones the application ships:
the test links the object files the Horos target compiled.
"""
from pathlib import Path
from dcmtk_build import dcmtk_flags, CONFIGURATION
import re
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
failures = []

# Use the same explicit configuration for application objects and DCMTK archives.
build = root / 'build/Build'
configuration = CONFIGURATION
if not (build / ('Intermediates.noindex/Horos.build/%s/Horos.build/Objects-normal/arm64' % configuration)).is_dir():
    print('skipped: build the requested Horos target configuration')
    raise SystemExit(2)
objects = build / ('Intermediates.noindex/Horos.build/%s/Horos.build/Objects-normal/arm64' % configuration)
products = build / ('Products/' + configuration)
dcmtk = root / 'DCMTK'

# --- what the query window builds -------------------------------------------
controller = (root / 'Horos/Sources/QueryController.mm').read_bytes().decode('latin1')
# Every place that turns the selected modalities into a query key joins them.
joins = re.findall(r'componentsJoinedByString\s*:\s*@"\\\\"\]\s*(?:forKey|ofSearchType)[^\n]*', controller)
routed = re.findall(r'(ModalitiesinStudy|Modality)"', controller)
if len(joins) < 4:
    failures.append('only %d modality joins found in QueryController; expected the query, the '
                    'auto-query and both getModalityQueryFilter branches' % len(joins))
for site in joins:
    if 'ModalitiesinStudy' not in site and 'Modality' not in site:
        failures.append('a joined modality list goes to an unexpected key: %s' % site.strip())
if 'ModalitiesinStudy' not in routed:
    failures.append('nothing routes the modalities to ModalitiesinStudy')
# The join must not be split up again or quoted anywhere on the way out.
if re.search(r'componentsSeparatedByString\s*:\s*@"\\\\"\]\s*[^\n]*[Mm]odalit', controller):
    failures.append('QueryController splits the joined modality list again before sending it')

# And the C-FIND dataset maps those two keys onto the two real tags.
node = (root / 'Horos/Sources/DCMTKQueryNode.mm').read_bytes().decode('latin1')
for key, tag in (('ModalitiesinStudy', 'DCM_ModalitiesInStudy'), ('Modality', 'DCM_Modality')):
    branch = re.search(r'else if \(\[key isEqualToString:@"%s"\]\)\s*\{(.*?)\}' % key, node, re.S)
    if not branch:
        failures.append('the C-FIND dataset no longer handles %s' % key)
    elif tag not in branch.group(1):
        failures.append('%s no longer goes into %s' % (key, tag))

# ModalitiesInStudy is asked for by default, and the empty key is requested so
# the SCP has somewhere to answer.
defaults = (root / 'Horos/Sources/DefaultsOsiriX.m').read_bytes().decode('latin1')
if not re.search(r'setObject:@"1" forKey:@"SupportQRModalitiesinStudy"', defaults):
    failures.append('SupportQRModalitiesinStudy is no longer on by default')
rootnode = (root / 'Horos/Sources/DCMTKRootQueryNode.mm').read_bytes().decode('latin1')
if 'insertEmptyElement(DCM_ModalitiesInStudy' not in rootnode:
    failures.append('the query no longer asks the SCP to return ModalitiesInStudy')

# --- what those two steps actually produce ----------------------------------
program = r'''
#import <Foundation/Foundation.h>
#import "QueryFilter.h"
#include <dcmtk/config/osconfig.h>
#include <dcmtk/dcmdata/dcdeftag.h>
#include <dcmtk/dcmdata/dcdatset.h>
#include <dcmtk/dcmdata/dcelem.h>
#include <dcmtk/dcmdata/dcistrmb.h>
#include <dcmtk/dcmdata/dcostrmb.h>
#include <cstdio>
#include <cstring>
#include <cstdarg>

static int failed = 0;
static void fail(const char *format, ...) {
    va_list arguments; va_start(arguments, format);
    fputs("FAIL: ", stderr); vfprintf(stderr, format, arguments); fputc('\n', stderr);
    va_end(arguments); failed = 1;
}

// The dataset a C-FIND carries, built the way -queryWithValues:dataset: builds
// it, then encoded and read back the way the association would carry it.
static void check(NSArray *modalities) {
    NSString *joined = [modalities componentsJoinedByString:@"\\"];
    QueryFilter *filter = [QueryFilter queryFilterWithObject:joined
                                                ofSearchType:searchExactMatch
                                                      forKey:@"ModalitiesinStudy"];
    NSString *value = [filter filteredValue];
    if (![value isEqualToString:joined])
        fail("the filter changed %s into %s", joined.UTF8String, value.UTF8String);
    // The query window drops any key that is only wildcards; a modality list has
    // none, so it must survive that rule.
    if ([value rangeOfString:@"*"].location != NSNotFound)
        fail("%s contains a wildcard and would be dropped as too small a query", value.UTF8String);

    DcmDataset dataset;
    dataset.putAndInsertString(DCM_ModalitiesInStudy, [value cStringUsingEncoding:NSISOLatin1StringEncoding]);

    // Encode explicit VR little endian and read it back, so what is checked is
    // what the peer would parse rather than what was put in.
    Uint32 size = 8192; char *buffer = new char[size];
    DcmOutputBufferStream out(buffer, size);
    dataset.transferInit();
    if (dataset.write(out, EXS_LittleEndianExplicit, EET_ExplicitLength, NULL).bad())
        fail("%s could not be encoded", value.UTF8String);
    dataset.transferEnd();
    void *encoded = NULL; offile_off_t written = 0;
    out.flushBuffer(encoded, written);

    DcmDataset parsed;
    DcmInputBufferStream in;
    in.setBuffer(buffer, written); in.setEos();
    parsed.transferInit();
    if (parsed.read(in, EXS_LittleEndianExplicit).bad())
        fail("%s could not be read back", value.UTF8String);
    parsed.transferEnd();

    DcmElement *element = NULL;
    if (parsed.findAndGetElement(DCM_ModalitiesInStudy, element).bad() || element == NULL) {
        fail("%s did not arrive as ModalitiesInStudy", value.UTF8String);
        delete[] buffer; return;
    }
    if (element->getVM() != (unsigned long)modalities.count)
        fail("%s arrived with %lu values, expected %lu", value.UTF8String,
             (unsigned long)element->getVM(), (unsigned long)modalities.count);
    for (unsigned long i = 0; i < element->getVM() && i < modalities.count; i++) {
        OFString one;
        element->getOFString(one, i);
        if (strcmp(one.c_str(), [modalities[i] UTF8String]) != 0)
            fail("%s arrived with [%lu] = %s, expected %s", value.UTF8String, i,
                 one.c_str(), [modalities[i] UTF8String]);
    }
    delete[] buffer;
}

int main() { @autoreleasepool {
    check(@[@"CT"]);
    check(@[@"CT", @"MR"]);
    check(@[@"MR", @"CT"]);
    check(@[@"CR", @"CT"]);
    check(@[@"CT", @"MR", @"US", @"PT"]);
    // A modality list is never trimmed to its first value.
    DcmDataset dataset;
    dataset.putAndInsertString(DCM_ModalitiesInStudy, "CT\\MR");
    OFString whole;
    dataset.findAndGetOFStringArray(DCM_ModalitiesInStudy, whole);
    if (strcmp(whole.c_str(), "CT\\MR") != 0)
        fail("the whole element reads back as %s", whole.c_str());
    if (failed) return 1;
    puts("PASS: five modality selections survive the filter and arrive as one multi-valued "
         "ModalitiesInStudy, in order, after an explicit VR round trip");
    return 0;
}}
'''

with tempfile.TemporaryDirectory(prefix='horos-modality-filter-') as directory:
    path = Path(directory)
    # The linker takes what it needs out of the archive; this is the object code
    # the Horos target compiled, not a rebuild of it.
    archive = path / 'libhoros.a'
    subprocess.run(['ar', 'rcs', str(archive)] + [line for line in (objects / 'Horos.LinkFileList').read_text().splitlines() if line.endswith('.o')],
                   check=True, capture_output=True)
    (path / 'bin').mkdir()
    # DCM.framework is loaded from @executable_path/../Frameworks.
    (path / 'Frameworks').symlink_to(products)
    (path / 'test.mm').write_text(program)
    compiled = subprocess.run(
        ['xcrun', 'clang++', '-std=c++14', '-fobjc-arc', str(path / 'test.mm'), str(archive), *dcmtk_flags('dcmnet'), '-framework', 'Foundation', '-F' + str(products), '-framework', 'DCM', '-o', str(path / 'bin/test')], capture_output=True, text=True)
    if compiled.returncode != 0:
        print(compiled.stderr[-3000:])
        failures.append('the shipped filter and encoding no longer link on their own')
    else:
        run = subprocess.run([str(path / 'bin/test')], capture_output=True, text=True)
        print((run.stdout or run.stderr).strip())
        if run.returncode != 0:
            failures.append('a modality selection does not arrive as several values')

for failure in failures:
    print('FAIL: %s' % failure)
if failures:
    sys.exit(1)
print('ok: the modality selection is joined once, routed to ModalitiesInStudy, and reaches the '
      'peer as one multi-valued element (%s objects)' % configuration)
