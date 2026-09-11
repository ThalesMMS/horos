#!/usr/bin/env python3
"""Adapt a reviewed external JPEG plugin checkout locally; never vendors its source.

Input: JPEG to DICOM directory from cloudymedic/horosplugins commit
6b4036242ca4f821679bcd83942a4b842d7ffb2c. Output must be a new directory.
"""
import argparse
import hashlib
import shutil
from pathlib import Path


def adapt(source, output):
    raw = (source/'DCMJpegImportFilter.m').read_bytes()
    expected = 'fd9becb366643999f1d87cd726d0cf88cc299b88eb7467c125738f70922f1671'
    if hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError('Unreviewed plugin revision; refusing to rewrite it')
    if output.exists():
        raise ValueError('Choose a new output directory')
    text = raw.decode('utf-8')
    text = text.replace('"OsiriXAPI/browserController.h"', '<Horos/BrowserController.h>')
    text = text.replace('"OsiriXAPI/DICOMExport.h"', '<Horos/DICOMExport.h>')
    start = text.index('\t\tNSBitmapImageRep *rep =', text.index('- (NSString*) convertImageToDICOM:'))
    end = text.index('            createdFile =', start)
    text = text[:start] + '''        [e setSourceFile:src];
        if( [e setPixelNSImage:image] == 0)
        {
''' + text[end:]
    text = text.replace('NSAutoreleasePool *pool = [[NSAutoreleasePool alloc] init];',
        'NSAutoreleasePool *pool = [[NSAutoreleasePool alloc] init];\n    BOOL conversionFailed = NO;\n    conversionFailures = [[NSMutableArray alloc] init];', 1)
    failure_summary = r'''        conversionFailed = conversionFailures.count > 0;
        if( conversionFailed)
        {
            NSAlert *alert = [[[NSAlert alloc] init] autorelease];
            alert.messageText = @"Image conversion failed";
            NSArray *shown = [conversionFailures subarrayWithRange:NSMakeRange(0, MIN((NSUInteger)10, conversionFailures.count))];
            alert.informativeText = [NSString stringWithFormat:@"Could not convert %lu file(s) to DICOM. Check that the images are readable and the database is writable, then retry.\n\n%@", (unsigned long)conversionFailures.count, [shown componentsJoinedByString:@"\n"]];
            [alert addButtonWithTitle:@"OK"];
            [alert runModal];
        }
        [conversionFailures release];
        conversionFailures = nil;
        [e release];'''
    text = text.replace('        [e release];', failure_summary, 1)
    text = text.replace('\treturn 0;\n}', '\treturn conversionFailed ? -1 : 0;\n}', 1)
    marker = '\t[pool release];\n    \n    return [createdFile autorelease];'
    assert text.count(marker) == 1
    text = text.replace(marker, '    if( !createdFile) [conversionFailures addObject:path.lastPathComponent ?: @"Unknown image"];\n' + marker)
    output.mkdir(parents=True)
    for name in ('DCMJpegImportFilter.h', 'Info.plist', 'Options.xib'):
        shutil.copy2(source/name, output/name)
    (output/'DCMJpegImportFilter.m').write_text(text)
    header = output/'DCMJpegImportFilter.h'
    header.write_text(header.read_text().replace('<HorosAPI/PluginFilter.h>', '<Horos/PluginFilter.h>').replace('DICOMExport *e;', 'DICOMExport *e;\n    NSMutableArray *conversionFailures;'))
    print('Adapted reviewed source: current Horos headers and profile-aware NSImage conversion')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    adapt(args.source, args.output)
