#!/usr/bin/env python3
"""A file that states no character set is read as whatever is chosen, once.

DICOM says which character set a file uses in Specific Character Set (0008,0005).
Equipment that predates that habit writes the bytes of whatever code page the
operating system had - in Russia, Windows-1251 - and says nothing, and a reader
that falls back to Latin-1 turns those bytes into mojibake. Nothing in the file
can tell the two apart, so the choice belongs to the reader and is made once, in
the preferences, rather than guessed per file.

The same Cyrillic name written four ways, imported (macOS 26.6.2 arm64):

    nothing chosen, which is how it ships
      iso-ir-144     Иванов^Иван   Голова
      utf-8          Иванов^Иван   Голова
      cp1251-silent  Èâàíîâ^Èâàí   Ãîëîâà     <- no Specific Character Set
      cp1251-said    Иванов^Иван   Голова     <- says WINDOWS-1251

    DefaultCharacterSetWhenAbsent = WINDOWS-1251
      all four       Иванов^Иван   Голова

With nothing chosen, the conformant files are untouched and the silent one reads
as it always did; the fourth, which names its code page in a vocabulary DICOM
does not define, is now believed. With Windows-1251 chosen, the four collapse
into one patient rather than two.
"""
from pathlib import Path
import re
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
failures = []
character_set = (root / 'DCM Framework/DCMCharacterSet.m').read_bytes().decode('latin1')
category = (root / 'Horos/Sources/DICOMToNSString.m').read_bytes().decode('latin1')
reader = (root / 'Horos/Sources/DicomFileDCMTKCategory.mm').read_bytes().decode('latin1')
defaults = (root / 'Horos/Sources/DefaultsOsiriX.m').read_bytes().decode('latin1')


def body(signature, source):
    at = source.find(signature)
    if at < 0:
        return ''
    opening = source.index('{', at)
    depth, index = 0, opening
    while index < len(source):
        if source[index] == '{':
            depth += 1
        elif source[index] == '}':
            depth -= 1
            if depth == 0:
                return source[opening:index + 1]
        index += 1
    return ''


# --- one table, not two --------------------------------------------------------
duplicate = body('+ (NSStringEncoding)encodingForDICOMCharacterSet:', category)
if not duplicate:
    failures.append('the NSString category no longer answers for a character set')
elif 'DCMCharacterSet encodingForDICOMCharacterSet' not in duplicate:
    failures.append('the category writes out its own table again, so the indexer and the viewer '
                    'can read the same file differently')

# --- the choice, and where it applies ------------------------------------------
chosen = body('+ (NSString*) characterSetWhenAbsent', character_set)
if not chosen:
    failures.append('there is no way to choose what a file that says nothing is read as')
else:
    if 'DefaultCharacterSetWhenAbsent' not in chosen:
        failures.append('the choice does not come from a preference')

table = body('+ (NSStringEncoding)encodingForDICOMCharacterSet:', character_set)
if not table:
    failures.append('the character-set table is gone')
else:
    if 'characterSetWhenAbsent' not in table:
        failures.append('a file that states nothing does not consult the choice')
    if 'characterSet.length == 0' not in table:
        failures.append('the empty and absent cases are no longer the same case')

if 'DefaultCharacterSetWhenAbsent' not in defaults:
    failures.append('the preference is not registered, so it has no documented default')
else:
    at = defaults.find('DefaultCharacterSetWhenAbsent')
    if '@""' not in defaults[max(at - 120, 0):at + 40]:
        failures.append('the preference does not default to empty, so the behaviour would change '
                        'for everyone rather than for whoever asks')

# The indexer has to consult it too, or the database and the viewer disagree.
if 'encodingForDICOMCharacterSet: nil' not in reader:
    failures.append('the indexer still hardcodes Latin-1 for a file that states nothing')
if 'characterSetWhenAbsent' not in reader:
    failures.append('the second reader in the indexer does not consult the choice')

# --- what the table actually answers -------------------------------------------
if table:
    DRIVER = '''
#import <Foundation/Foundation.h>
#include <cstdio>
@interface DCMCharacterSet : NSObject
+ (NSStringEncoding)encodingForDICOMCharacterSet:(NSString *)characterSet;
+ (NSString*) characterSetWhenAbsent;
@end
@implementation DCMCharacterSet
+ (NSString*) characterSetWhenAbsent { return nil; }
TABLE
@end
int main() {
    NSArray *names = @[@"ISO_IR 100", @"ISO_IR 144", @"ISO_IR 192", @"WINDOWS-1251",
                       @"CP1251", @"windows-1251", @"WINDOWS-1252", @"GB18030"];
    for (NSString *name in names)
        printf("%s\\t%u\\n", [name UTF8String],
               (unsigned) [DCMCharacterSet encodingForDICOMCharacterSet: name]);
    printf("absent\\t%u\\n", (unsigned) [DCMCharacterSet encodingForDICOMCharacterSet: nil]);
    printf("latin1\\t%u\\n", (unsigned) NSISOLatin1StringEncoding);
    printf("utf8\\t%u\\n", (unsigned) NSUTF8StringEncoding);
    printf("cyrillic\\t%u\\n",
           (unsigned) CFStringConvertEncodingToNSStringEncoding(kCFStringEncodingISOLatinCyrillic));
    printf("cp1251\\t%u\\n",
           (unsigned) CFStringConvertEncodingToNSStringEncoding(kCFStringEncodingWindowsCyrillic));
    return 0;
}
'''.replace('TABLE', '+ (NSStringEncoding)encodingForDICOMCharacterSet:(NSString *)characterSet\n' + table)
    with tempfile.TemporaryDirectory(prefix='horos-charset-') as directory:
        main = Path(directory) / 'main.mm'
        main.write_text(DRIVER)
        binary = Path(directory) / 'charset'
        build = subprocess.run(['xcrun', 'clang++', '-std=c++11', '-w', '-fobjc-arc',
                                '-framework', 'Foundation', str(main), '-o', str(binary)],
                               capture_output=True, text=True)
        if build.returncode != 0:
            failures.append('the table does not compile on its own:\n%s' % build.stderr[-1200:])
        else:
            run = subprocess.run([str(binary)], capture_output=True, text=True, timeout=120)
            answers = dict(line.split('\t', 1) for line in run.stdout.splitlines() if '\t' in line)
            for name, expected in (('ISO_IR 100', 'latin1'), ('ISO_IR 144', 'cyrillic'),
                                   ('ISO_IR 192', 'utf8'), ('WINDOWS-1251', 'cp1251'),
                                   ('CP1251', 'cp1251'), ('windows-1251', 'cp1251'),
                                   ('WINDOWS-1252', None), ('absent', 'latin1')):
                got = answers.get(name)
                if got is None:
                    failures.append('%s produced no answer' % name)
                elif expected and got != answers.get(expected):
                    failures.append('%s is encoding %s, expected the one for %s (%s)'
                                    % (name, got, expected, answers.get(expected)))
            # A code page that is not Cyrillic must not be read as Cyrillic.
            if answers.get('WINDOWS-1252') == answers.get('cp1251'):
                failures.append('every Windows code page maps to the same encoding')

for failure in failures:
    print('FAIL: %s' % failure)
if failures:
    sys.exit(1)
print('ok: one character-set table, the Windows code pages a file may name are believed, and a '
      'file that names nothing is read as whatever was chosen - Latin-1 when nothing was')
